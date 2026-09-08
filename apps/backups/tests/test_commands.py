"""FASE 20 — comandos de gestión, pensados para invocarse desde un
scheduler del sistema operativo (`python manage.py backup_all`, etc.)
— ver `docs/backup-recovery.md` sección 9. Se prueban con
`call_command` real (no mocks del propio comando) contra PostgreSQL
real."""

import io
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings

from apps.tenants.models import Tenant


class BackupDatabaseCommandTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._override = override_settings(BACKUP_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        Tenant.objects.create(name="Command Test Tenant", slug="command-test-tenant")

    def test_backup_database_command_ok(self):
        out = io.StringIO()
        call_command("backup_database", stdout=out)
        self.assertIn("Backup OK", out.getvalue())
        self.assertTrue(list((Path(self._tmp.name) / "database").glob("*.dump")))

    def test_verify_backup_command_sobre_backup_recien_creado(self):
        call_command("backup_database", stdout=io.StringIO())
        dump_path = next((Path(self._tmp.name) / "database").glob("*.dump"))

        out = io.StringIO()
        call_command("verify_backup", backup=str(dump_path), stdout=out)
        self.assertIn("Checksum OK", out.getvalue())

    def test_verify_backup_command_sobre_archivo_inexistente_lanza_commanderror(self):
        with self.assertRaises(CommandError):
            call_command("verify_backup", backup=str(Path(self._tmp.name) / "no-existe.dump"))

    def test_restore_database_command_ok(self):
        call_command("backup_database", stdout=io.StringIO())
        dump_path = next((Path(self._tmp.name) / "database").glob("*.dump"))

        out = io.StringIO()
        call_command("restore_database", backup=str(dump_path), stdout=out)
        self.assertIn("Restore verification OK", out.getvalue())

    def test_cleanup_backups_command_dry_run(self):
        call_command("backup_database", stdout=io.StringIO())
        out = io.StringIO()
        call_command("cleanup_backups", dry_run=True, stdout=out)
        self.assertIn("conservado", out.getvalue())

    def test_backup_health_command_ok_cuando_hay_backup_reciente(self):
        call_command("backup_database", stdout=io.StringIO())
        call_command("backup_media", target="both", stdout=io.StringIO())
        out = io.StringIO()
        call_command("backup_health", stdout=out)
        self.assertIn("OK", out.getvalue())

    def test_backup_health_command_falla_cuando_no_hay_ningun_backup(self):
        with self.assertRaises(CommandError):
            call_command("backup_health")

    def test_backup_all_command_ejecuta_db_y_media(self):
        out = io.StringIO()
        call_command("backup_all", stdout=out)
        self.assertIn("completado sin errores", out.getvalue())
        self.assertTrue(list((Path(self._tmp.name) / "database").glob("*.dump")))
        self.assertTrue(list((Path(self._tmp.name) / "media").glob("*.tar.gz")))

    def test_disaster_recovery_drill_command_ok(self):
        out = io.StringIO()
        call_command("disaster_recovery_drill", stdout=out)
        self.assertIn("TODO OK", out.getvalue())
