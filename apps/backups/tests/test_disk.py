"""FASE 20, sección 19 — "insufficient storage" es uno de los
escenarios de fallo obligatorios. No se llena el disco de verdad: se
simula vía `unittest.mock` sobre `shutil.disk_usage`, exactamente como
la propia especificación permite ("cuando sea razonablemente
simulable")."""

import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from apps.backups.services import disk as disk_service


class DiskSpaceTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def test_espacio_suficiente_no_lanza(self):
        free_bytes = disk_service.ensure_sufficient_disk_space(self.tmp_path, minimum_free_bytes=1)
        self.assertGreaterEqual(free_bytes, 1)

    def test_espacio_insuficiente_lanza(self):
        fake_usage = mock.Mock(free=100)
        with mock.patch("shutil.disk_usage", return_value=fake_usage):
            with self.assertRaises(disk_service.InsufficientStorageError):
                disk_service.ensure_sufficient_disk_space(self.tmp_path, minimum_free_bytes=10 * 1024**3)

    def test_ruta_inexistente_sube_al_padre_mas_cercano(self):
        missing_path = self.tmp_path / "no" / "existe" / "todavia.dump"
        # No debe lanzar FileNotFoundError — sube hasta self.tmp_path,
        # que sí existe.
        free_bytes = disk_service.ensure_sufficient_disk_space(missing_path, minimum_free_bytes=1)
        self.assertGreaterEqual(free_bytes, 1)
