"""FASE 20, sección 8 — retention. `classify_retention` es pura (sin
tocar disco, datos sintéticos); `apply_retention`/`scan_backup_entries`
sí tocan archivos reales en un directorio temporal."""

import datetime as dt
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.backups.services import retention as retention_service


def _entry(identifier, days_ago, *, now, status="success", paths=()):
    return retention_service.BackupEntry(
        identifier=identifier,
        created_at=now - dt.timedelta(days=days_ago),
        status=status,
        paths=paths,
    )


class ClassifyRetentionTests(SimpleTestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 8, 12, 0, 0)

    def test_todo_dentro_de_la_ventana_diaria_se_conserva(self):
        entries = [_entry(f"d{i}", i, now=self.now) for i in range(7)]
        keep_ids, protected = retention_service.classify_retention(
            entries, now=self.now, daily_days=7, weekly_weeks=4, monthly_months=12
        )
        self.assertEqual(keep_ids, {e.identifier for e in entries})
        self.assertEqual(protected.identifier, "d0")

    def test_el_ultimo_backup_valido_nunca_se_borra_aunque_sea_muy_viejo(self):
        entries = [_entry("unico-viejo", 400, now=self.now)]
        keep_ids, protected = retention_service.classify_retention(
            entries, now=self.now, daily_days=7, weekly_weeks=4, monthly_months=1
        )
        self.assertEqual(keep_ids, {"unico-viejo"})
        self.assertEqual(protected.identifier, "unico-viejo")

    def test_semanal_conserva_uno_por_semana_fuera_de_la_ventana_diaria(self):
        entries = [
            _entry("s0", 10, now=self.now),   # semana 1 dentro de la ventana semanal
            _entry("s1", 11, now=self.now),   # misma semana ISO que s0 probablemente
            _entry("s2", 17, now=self.now),   # otra semana
        ]
        keep_ids, _ = retention_service.classify_retention(
            entries, now=self.now, daily_days=7, weekly_weeks=4, monthly_months=1
        )
        # Debe sobrevivir como mucho un representante por semana ISO
        # entre los candidatos de la ventana semanal (s0/s1 podrían
        # colapsar a uno solo si comparten semana ISO).
        self.assertLessEqual(len(keep_ids & {"s0", "s1"}), 1)
        self.assertIn("s2", keep_ids)

    def test_mensual_conserva_uno_por_mes_fuera_de_la_ventana_semanal(self):
        entries = [
            _entry("m-viejo-1", 200, now=self.now),
            _entry("m-viejo-2", 205, now=self.now),  # mismo mes aproximado que m-viejo-1
            _entry("m-mas-viejo", 400, now=self.now),  # fuera de TODAS las ventanas
        ]
        keep_ids, protected = retention_service.classify_retention(
            entries, now=self.now, daily_days=7, weekly_weeks=4, monthly_months=6
        )
        # m-mas-viejo es el más antiguo → protegido como último válido
        # SOLO si es el más reciente; aquí no lo es, así que puede expirar
        # salvo que ningún backup más reciente exista realmente — pero
        # "m-mas-viejo" no es el más reciente (los otros dos lo son), así
        # que no está protegido por la regla de "último válido".
        self.assertNotIn("m-mas-viejo", keep_ids)
        self.assertTrue({"m-viejo-1", "m-viejo-2"} & keep_ids)

    def test_backups_fallidos_nunca_participan_de_la_clasificacion(self):
        entries = [
            _entry("ok-reciente", 1, now=self.now, status="success"),
            _entry("fallido-reciente", 1, now=self.now, status="failed"),
        ]
        keep_ids, protected = retention_service.classify_retention(
            entries, now=self.now, daily_days=7, weekly_weeks=4, monthly_months=12
        )
        self.assertNotIn("fallido-reciente", keep_ids)
        self.assertEqual(protected.identifier, "ok-reciente")

    def test_sin_ningun_backup_exitoso_no_hay_protegido(self):
        entries = [_entry("solo-fallido", 1, now=self.now, status="failed")]
        keep_ids, protected = retention_service.classify_retention(
            entries, now=self.now, daily_days=7, weekly_weeks=4, monthly_months=12
        )
        self.assertEqual(keep_ids, set())
        self.assertIsNone(protected)


class ApplyRetentionTests(SimpleTestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 8, 12, 0, 0)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def _entry_with_real_file(self, identifier, days_ago, status="success"):
        path = self.tmp_path / f"{identifier}.dump"
        path.write_bytes(b"contenido")
        return retention_service.BackupEntry(
            identifier=identifier,
            created_at=self.now - dt.timedelta(days=days_ago),
            status=status,
            paths=(path,),
        )

    def test_apply_retention_borra_archivos_expirados_de_verdad(self):
        entries = [
            self._entry_with_real_file("reciente", 1),
            self._entry_with_real_file("expirado", 400),
        ]
        # "reciente" es el más nuevo → protegido; "expirado" no cae en
        # ninguna ventana con retención corta → se elimina.
        report = retention_service.apply_retention(
            entries, now=self.now, daily_days=1, weekly_weeks=0, monthly_months=0
        )
        self.assertEqual({e.identifier for e in report.kept}, {"reciente"})
        self.assertEqual({e.identifier for e in report.deleted}, {"expirado"})
        self.assertFalse((self.tmp_path / "expirado.dump").exists())
        self.assertTrue((self.tmp_path / "reciente.dump").exists())

    def test_apply_retention_dry_run_no_borra_nada(self):
        entries = [
            self._entry_with_real_file("reciente", 1),
            self._entry_with_real_file("expirado", 400),
        ]
        report = retention_service.apply_retention(
            entries, now=self.now, daily_days=1, weekly_weeks=0, monthly_months=0, dry_run=True
        )
        self.assertEqual({e.identifier for e in report.deleted}, {"expirado"})
        self.assertTrue((self.tmp_path / "expirado.dump").exists())

    def test_apply_retention_maneja_fallo_de_eliminacion_sin_reventar(self):
        # Dos backups válidos: "reciente" queda protegido como el más
        # nuevo, "expirado" es el único candidato real a eliminación —
        # con un solo backup en la lista, `apply_retention` lo
        # protegería SIEMPRE como "el último válido" y nunca llegaría a
        # intentar borrarlo (regla explícita de la fase).
        reciente = self._entry_with_real_file("reciente", 1)
        entry = self._entry_with_real_file("expirado", 400)
        from unittest import mock

        with mock.patch("pathlib.Path.unlink", side_effect=OSError("disco bloqueado")):
            report = retention_service.apply_retention(
                [reciente, entry], now=self.now, daily_days=1, weekly_weeks=0, monthly_months=0
            )
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.errors[0][0].identifier, "expirado")
        # Un fallo de eliminación se reporta pero el backup no
        # desaparece de "kept" — nunca se declara eliminado sin serlo.
        self.assertIn(entry, report.kept)


class ScanBackupEntriesTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def test_scan_lee_metadata_real_de_disco(self):
        import json

        dump_path = self.tmp_path / "erp_test_20260101_000000.dump"
        dump_path.write_bytes(b"x")
        meta_path = self.tmp_path / (dump_path.name + ".meta.json")
        meta_path.write_text(
            json.dumps({"created_at": "2026-01-01T00:00:00", "status": "success"}), encoding="utf-8"
        )

        entries = retention_service.scan_backup_entries(self.tmp_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].identifier, dump_path.name)
        self.assertIn(dump_path, entries[0].paths)

    def test_scan_ignora_metadata_ilegible_sin_reventar(self):
        meta_path = self.tmp_path / "roto.dump.meta.json"
        meta_path.write_text("{no es json valido", encoding="utf-8")

        entries = retention_service.scan_backup_entries(self.tmp_path)
        self.assertEqual(entries, [])
