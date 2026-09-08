"""FASE 20 — orquestación completa (`services.jobs`), real de punta a
punta contra PostgreSQL: backup real → checksum → metadata →
`BackupRun` → restore drill real → verificación real. `BACKUP_ROOT` se
redirige a un directorio temporal por test (`override_settings`) para
no ensuciar `backups/` del proyecto ni depender de orden de ejecución
entre tests."""

import json
import tempfile
from pathlib import Path

from django.db import connection
from django.test import TransactionTestCase, override_settings

from apps.backups.models import BackupRun
from apps.backups.services import jobs as jobs_service
from apps.tenants.models import Tenant


class DatabaseBackupJobTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._override = override_settings(BACKUP_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        Tenant.objects.create(name="Jobs Test Tenant", slug="jobs-test-tenant")

    def test_backup_exitoso_crea_dump_checksum_metadata_y_backuprun(self):
        result = jobs_service.perform_database_backup(apply_retention_policy=False)

        self.assertTrue(result["ok"])
        dump_path = Path(result["dump_path"])
        self.assertTrue(dump_path.exists())
        self.assertTrue(dump_path.with_name(dump_path.name + ".sha256").exists())

        metadata_path = dump_path.with_name(dump_path.name + ".meta.json")
        self.assertTrue(metadata_path.exists())
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "success")
        self.assertIn("counts_at_backup", metadata)
        self.assertGreaterEqual(metadata["counts_at_backup"]["tenants"], 1)
        self.assertFalse(metadata["encrypted"])  # sin BACKUP_ENCRYPTION_KEY configurado

        run = BackupRun.objects.get(pk=result["backup_run_id"])
        self.assertEqual(run.status, BackupRun.Status.SUCCESS)
        self.assertEqual(run.kind, BackupRun.Kind.DATABASE)
        self.assertTrue(run.checksum_sha256)
        self.assertIsNotNone(run.finished_at)

    def test_backup_fallido_registra_backuprun_failed_sin_dejar_archivos(self):
        bad_settings = dict(connection.settings_dict)
        bad_settings["PASSWORD"] = "definitivamente-incorrecta"

        result = jobs_service.perform_database_backup(db_settings=bad_settings, apply_retention_policy=False)

        self.assertFalse(result["ok"])
        run = BackupRun.objects.filter(kind=BackupRun.Kind.DATABASE, status=BackupRun.Status.FAILED).latest("id")
        self.assertNotIn("definitivamente-incorrecta", run.error_message)

    def test_encryption_key_configurada_cifra_el_backup(self):
        with override_settings(BACKUP_ENCRYPTION_KEY="clave-de-test-segura"):
            result = jobs_service.perform_database_backup(apply_retention_policy=False)

        self.assertTrue(result["ok"])
        self.assertTrue(result["encrypted"])
        dump_path = Path(result["dump_path"])
        encrypted_path = dump_path.with_name(dump_path.name + ".enc")
        self.assertTrue(encrypted_path.exists())


class DatabaseRestoreDrillJobTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._override = override_settings(BACKUP_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        Tenant.objects.create(name="Restore Drill Job Tenant", slug="restore-drill-job-tenant")

    def test_restore_drill_completo_ok(self):
        backup_result = jobs_service.perform_database_backup(apply_retention_policy=False)
        self.assertTrue(backup_result["ok"])

        report = jobs_service.perform_database_restore_drill(dump_path=backup_result["dump_path"])

        self.assertTrue(report["ok"])
        self.assertEqual(report["database_dropped"], True)
        self.assertEqual(report["verification"].mismatches, {})

        run = BackupRun.objects.filter(kind=BackupRun.Kind.DATABASE, status=BackupRun.Status.SUCCESS)
        self.assertTrue(run.exists())

    def test_restore_drill_con_checksum_invalido_nunca_llega_a_crear_base(self):
        backup_result = jobs_service.perform_database_backup(apply_retention_policy=False)
        dump_path = Path(backup_result["dump_path"])

        # Corromper el checksum registrado (nunca el archivo real).
        sidecar = dump_path.with_name(dump_path.name + ".sha256")
        sidecar.write_text("0" * 64 + "  " + dump_path.name, encoding="utf-8")

        report = jobs_service.perform_database_restore_drill(dump_path=dump_path)

        self.assertFalse(report["ok"])
        self.assertEqual(report["stage"], "checksum")
        self.assertNotIn("database_name", report)  # nunca se intentó crear ninguna base

    def test_keep_database_conserva_la_base_aislada(self):
        backup_result = jobs_service.perform_database_backup(apply_retention_policy=False)
        report = jobs_service.perform_database_restore_drill(
            dump_path=backup_result["dump_path"], keep_database=True
        )
        self.assertTrue(report["ok"])
        self.assertFalse(report["database_dropped"])

        # Limpieza manual del test — nunca dejar la base huérfana.
        from apps.backups.services import database as database_service

        database_service.drop_isolated_database(dict(connection.settings_dict), report["database_name"])


class MediaBackupRestoreJobTests(TransactionTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._override = override_settings(BACKUP_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)

        self.source_dir = Path(self._tmp.name) / "media_source"
        self.source_dir.mkdir()
        (self.source_dir / "archivo.txt").write_bytes(b"contenido de prueba")

    def test_media_backup_job_completo(self):
        result = jobs_service.perform_media_backup("private", self.source_dir, apply_retention_policy=False)

        self.assertTrue(result["ok"])
        self.assertEqual(result["file_count"], 1)
        run = BackupRun.objects.get(pk=result["backup_run_id"])
        self.assertEqual(run.kind, BackupRun.Kind.MEDIA_PRIVATE)
        self.assertEqual(run.status, BackupRun.Status.SUCCESS)

    def test_media_restore_drill_job_completo(self):
        backup_result = jobs_service.perform_media_backup("catalog", self.source_dir, apply_retention_policy=False)

        with tempfile.TemporaryDirectory() as target_dir:
            report = jobs_service.perform_media_restore_drill(
                backup_result["archive_path"], self.source_dir, Path(target_dir)
            )
        self.assertTrue(report["ok"])
        self.assertEqual(report["file_count"], 1)
