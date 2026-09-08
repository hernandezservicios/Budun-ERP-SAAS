"""FASE 20, secciones 14-15, 20-22 — seguridad y aislamiento de
plataforma. Ningún tenant puede descargar/listar/restaurar un backup:
esta app deliberadamente NO expone ningún `urls.py`/vista HTTP — la
única superficie es el admin de solo lectura (superusuario) y los
comandos de gestión (acceso de shell/infraestructura, nunca web)."""

import importlib
import tempfile
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase, override_settings

from apps.backups.admin import BackupRunAdmin
from apps.backups.models import BackupRun
from apps.backups.services import jobs as jobs_service
from apps.tenants.models import Tenant


class NoHttpSurfaceTests(TransactionTestCase):
    def test_apps_backups_no_declara_ningun_modulo_de_urls(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("apps.backups.urls")

    def test_apps_backups_no_declara_ninguna_vista(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("apps.backups.views")


class BackupRunAdminReadOnlyTests(TransactionTestCase):
    def test_admin_es_de_solo_lectura(self):
        admin_instance = BackupRunAdmin(BackupRun, None)
        self.assertFalse(admin_instance.has_add_permission(request=None))
        self.assertFalse(admin_instance.has_change_permission(request=None))


class BackupRootLocationTests(TransactionTestCase):
    def test_backup_root_nunca_coincide_con_las_raices_servidas(self):
        backup_root = Path(settings.BACKUP_ROOT).resolve()
        self.assertNotEqual(backup_root, Path(settings.MEDIA_ROOT).resolve())
        self.assertNotEqual(backup_root, Path(settings.CATALOG_MEDIA_ROOT).resolve())
        for pattern in getattr(settings, "STATICFILES_DIRS", []):
            self.assertNotEqual(backup_root, Path(pattern).resolve())

    def test_media_roots_nunca_son_la_raiz_del_proyecto(self):
        # Invariante permanente: si algún día MEDIA_ROOT/CATALOG_MEDIA_ROOT
        # coincidieran con BASE_DIR, un backup de media empezaría a
        # incluir accidentalmente `.env` — este test lo bloquea.
        base_dir = Path(settings.BASE_DIR).resolve()
        self.assertNotEqual(Path(settings.MEDIA_ROOT).resolve(), base_dir)
        self.assertNotEqual(Path(settings.CATALOG_MEDIA_ROOT).resolve(), base_dir)
        env_file = base_dir / ".env"
        self.assertFalse(str(env_file).startswith(str(Path(settings.MEDIA_ROOT).resolve())))
        self.assertFalse(str(env_file).startswith(str(Path(settings.CATALOG_MEDIA_ROOT).resolve())))


class SecretsNeverLeakTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._override = override_settings(
            BACKUP_ROOT=self._tmp.name, BACKUP_ENCRYPTION_KEY="clave-secreta-de-test-9x7"
        )
        self._override.enable()
        self.addCleanup(self._override.disable)
        Tenant.objects.create(name="Secrets Test Tenant", slug="secrets-test-tenant")

    def test_encryption_key_nunca_aparece_en_metadata_json(self):
        result = jobs_service.perform_database_backup(apply_retention_policy=False)
        self.assertTrue(result["ok"])

        dump_path = Path(result["dump_path"])
        metadata_path = dump_path.with_name(dump_path.name + ".meta.json")
        raw_metadata_text = metadata_path.read_text(encoding="utf-8")

        self.assertNotIn("clave-secreta-de-test-9x7", raw_metadata_text)

    def test_db_password_nunca_aparece_en_error_message_de_backuprun(self):
        bad_settings = dict(connection.settings_dict)
        bad_settings["PASSWORD"] = "password-que-nunca-debe-aparecer-XYZ"

        jobs_service.perform_database_backup(db_settings=bad_settings, apply_retention_policy=False)

        failed_runs = BackupRun.objects.filter(status=BackupRun.Status.FAILED)
        for run in failed_runs:
            self.assertNotIn("password-que-nunca-debe-aparecer-XYZ", run.error_message)

    def test_relative_path_guardado_en_backuprun_nunca_es_absoluto(self):
        result = jobs_service.perform_database_backup(apply_retention_policy=False)
        run = BackupRun.objects.get(pk=result["backup_run_id"])
        self.assertFalse(Path(run.relative_path).is_absolute())
