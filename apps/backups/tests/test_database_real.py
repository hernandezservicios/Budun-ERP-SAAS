"""FASE 20, secciones 3-7, 19, 27 — backup/restore REALES contra
PostgreSQL de verdad (nunca simulados). `TransactionTestCase` (no
`TestCase`) es obligatorio aquí: `pg_dump`/`pg_restore` corren en un
subproceso EXTERNO que abre su propia conexión — solo ve filas que ya
fueron COMMITTED, y `TestCase` envuelve cada test en una transacción
sin confirmar (invisible para un proceso externo). Se opera siempre
sobre `connection.settings_dict` (la base de pruebas efímera real que
`manage.py test` ya crea/destruye, `test_erp_saas_dev`) — NUNCA sobre
`erp_saas_dev` (la base de desarrollo real)."""

import tempfile
from pathlib import Path
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase

from apps.backups.services import database as database_service
from apps.backups.services import disk as disk_service
from apps.backups.services import verification as verification_service
from apps.tenants.models import Tenant


class RealPgDumpTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.db_settings = dict(connection.settings_dict)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def test_pg_dump_produce_un_archivo_custom_format_real(self):
        output_path = self.tmp_path / "real.dump"
        result = database_service.run_pg_dump(self.db_settings, output_path)

        self.assertTrue(output_path.exists())
        self.assertEqual(result.size_bytes, output_path.stat().st_size)
        self.assertGreater(result.size_bytes, 0)
        self.assertGreater(result.duration_seconds, 0)
        # Firma binaria real del formato "custom" de pg_dump — confirma
        # que se generó un archivo real, no un placeholder.
        self.assertEqual(output_path.read_bytes()[:5], b"PGDMP")

    def test_pg_dump_con_credenciales_invalidas_falla_sin_dejar_archivo_parcial(self):
        bad_settings = dict(self.db_settings)
        bad_settings["PASSWORD"] = "contrasena-definitivamente-incorrecta"
        output_path = self.tmp_path / "fallido.dump"

        with self.assertRaises(database_service.BackupFailedError) as ctx:
            database_service.run_pg_dump(bad_settings, output_path)

        self.assertNotIn("contrasena-definitivamente-incorrecta", str(ctx.exception))
        self.assertFalse(output_path.exists(), "un backup fallido nunca debe dejar un .dump parcial")

    def test_pg_dump_con_host_inalcanzable_falla_limpiamente(self):
        bad_settings = dict(self.db_settings)
        bad_settings["HOST"] = "127.0.0.1"
        bad_settings["PORT"] = "1"  # puerto privilegiado, nada escuchando ahí
        output_path = self.tmp_path / "fallido2.dump"

        with self.assertRaises(database_service.BackupFailedError):
            database_service.run_pg_dump(bad_settings, output_path)
        self.assertFalse(output_path.exists())

    def test_pg_dump_respeta_el_chequeo_de_espacio_en_disco(self):
        output_path = self.tmp_path / "sin_espacio.dump"
        fake_usage = mock.Mock(free=1)
        with mock.patch("shutil.disk_usage", return_value=fake_usage):
            with self.assertRaises(disk_service.InsufficientStorageError):
                database_service.run_pg_dump(self.db_settings, output_path)
        self.assertFalse(output_path.exists())

    def test_get_postgres_version_devuelve_version_real(self):
        version = database_service.get_postgres_version(self.db_settings)
        self.assertRegex(version, r"^\d+")


class RealIsolatedDatabaseSafetyTests(TransactionTestCase):
    def setUp(self):
        self.db_settings = dict(connection.settings_dict)

    def test_create_isolated_database_rechaza_nombre_sin_marcador(self):
        with self.assertRaises(database_service.UnsafeDatabaseNameError):
            database_service.create_isolated_database(self.db_settings, self.db_settings["NAME"])

    def test_drop_isolated_database_rechaza_nombre_sin_marcador(self):
        with self.assertRaises(database_service.UnsafeDatabaseNameError):
            database_service.drop_isolated_database(self.db_settings, self.db_settings["NAME"])

    def test_isolated_database_name_siempre_contiene_el_marcador(self):
        name = database_service.isolated_database_name(self.db_settings["NAME"])
        self.assertIn(database_service.RESTORE_DB_MARKER, name)


class RealBackupRestoreRoundTripTests(TransactionTestCase):
    """El test más importante de todo el módulo: backup real → base
    AISLADA real → restore real → verificación real de conteos —
    nunca la base de desarrollo/pruebas principal."""

    reset_sequences = True

    def setUp(self):
        self.db_settings = dict(connection.settings_dict)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        # Datos reales y committed (TransactionTestCase, no TestCase) —
        # visibles para el subproceso externo de pg_dump.
        Tenant.objects.create(name="Restore Drill Tenant A", slug="restore-drill-a")
        Tenant.objects.create(name="Restore Drill Tenant B", slug="restore-drill-b")

    def test_backup_restore_round_trip_conteos_identicos(self):
        output_path = self.tmp_path / "roundtrip.dump"
        database_service.run_pg_dump(self.db_settings, output_path)

        expected_counts = verification_service.count_critical_tables(self.db_settings)
        self.assertGreaterEqual(expected_counts["tenants"], 2)

        target_name = database_service.isolated_database_name(self.db_settings["NAME"])
        database_service.create_isolated_database(self.db_settings, target_name)
        try:
            restore_result = database_service.run_pg_restore(output_path, self.db_settings, target_name)
            self.assertGreater(restore_result.duration_seconds, 0)

            restore_settings = dict(self.db_settings)
            restore_settings["NAME"] = target_name
            report = verification_service.verify_restored_database(
                restore_settings, expected_counts=expected_counts
            )
            self.assertEqual(report.mismatches, {})
            self.assertTrue(report.ok)
            self.assertEqual(report.counts["tenants"], expected_counts["tenants"])
            self.assertGreater(report.migrations_applied, 0)
        finally:
            database_service.drop_isolated_database(self.db_settings, target_name)

        # La base aislada realmente desapareció — nunca queda basura.
        with self.assertRaises(Exception):
            verification_service.count_critical_tables(restore_settings)

    def test_restore_de_dump_truncado_no_deja_la_base_a_medias_sin_reportarlo(self):
        output_path = self.tmp_path / "para_truncar.dump"
        database_service.run_pg_dump(self.db_settings, output_path)

        # Corrupción real: se trunca el archivo a la mitad.
        original_bytes = output_path.read_bytes()
        output_path.write_bytes(original_bytes[: len(original_bytes) // 2])

        target_name = database_service.isolated_database_name(self.db_settings["NAME"])
        database_service.create_isolated_database(self.db_settings, target_name)
        try:
            database_service.run_pg_restore(output_path, self.db_settings, target_name)
            restore_settings = dict(self.db_settings)
            restore_settings["NAME"] = target_name
            report = verification_service.verify_restored_database(restore_settings)
            # Un dump truncado nunca debe "verificarse" como saludable.
            self.assertFalse(report.ok)
        finally:
            database_service.drop_isolated_database(self.db_settings, target_name)
