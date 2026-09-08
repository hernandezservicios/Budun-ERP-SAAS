import datetime as dt

from django.test import SimpleTestCase

from apps.backups.services import paths as paths_service


class BackupFilenameTests(SimpleTestCase):
    def test_database_backup_filename_sigue_el_esquema_oficial(self):
        moment = dt.datetime(2026, 9, 8, 15, 30, 45)
        name = paths_service.database_backup_filename("erp_saas_dev", moment)
        self.assertEqual(name, "erp_erp_saas_dev_20260908_153045.dump")

    def test_media_backup_filename_incluye_el_arbol(self):
        moment = dt.datetime(2026, 9, 8, 15, 30, 45)
        name = paths_service.media_backup_filename("private", moment)
        self.assertEqual(name, "erp_media_private_20260908_153045.tar.gz")

    def test_sidecars_derivan_del_nombre_base(self):
        from pathlib import Path

        dump = Path("erp_x_20260101_000000.dump")
        self.assertEqual(paths_service.checksum_sidecar(dump).name, dump.name + ".sha256")
        self.assertEqual(paths_service.metadata_sidecar(dump).name, dump.name + ".meta.json")
        self.assertEqual(paths_service.encrypted_sidecar(dump).name, dump.name + ".enc")

    def test_offsite_root_none_si_no_configurado(self):
        from django.test import override_settings

        with override_settings(BACKUP_OFFSITE_ROOT=""):
            self.assertIsNone(paths_service.offsite_root())
