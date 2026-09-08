"""FASE 20, sección 7 — checksum e integridad."""

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.backups.services import checksum as checksum_service


class ChecksumTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def _make_file(self, name, content=b"contenido de prueba"):
        path = self.tmp_path / name
        path.write_bytes(content)
        return path

    def test_sha256_es_determinista(self):
        path = self._make_file("a.dump")
        self.assertEqual(checksum_service.sha256_of_file(path), checksum_service.sha256_of_file(path))

    def test_sha256_cambia_con_el_contenido(self):
        path_a = self._make_file("a.dump", b"contenido A")
        path_b = self._make_file("b.dump", b"contenido B")
        self.assertNotEqual(checksum_service.sha256_of_file(path_a), checksum_service.sha256_of_file(path_b))

    def test_sidecar_formato_compatible_sha256sum(self):
        path = self._make_file("a.dump")
        sidecar = path.with_name(path.name + ".sha256")
        checksum = checksum_service.write_checksum_sidecar(path, sidecar)
        content = sidecar.read_text(encoding="utf-8")
        self.assertTrue(content.startswith(checksum))
        self.assertIn(path.name, content)

    def test_verify_checksum_ok(self):
        path = self._make_file("a.dump")
        sidecar = path.with_name(path.name + ".sha256")
        checksum_service.write_checksum_sidecar(path, sidecar)
        result = checksum_service.verify_checksum(path, sidecar)
        self.assertEqual(len(result), 64)

    def test_verify_checksum_sin_sidecar_lanza_missing(self):
        path = self._make_file("a.dump")
        with self.assertRaises(checksum_service.ChecksumMissingError):
            checksum_service.verify_checksum(path)

    def test_verify_checksum_detecta_corrupcion(self):
        path = self._make_file("a.dump")
        sidecar = path.with_name(path.name + ".sha256")
        checksum_service.write_checksum_sidecar(path, sidecar)

        # Corromper el archivo DESPUÉS de calcular su checksum válido.
        with open(path, "r+b") as fh:
            fh.seek(0)
            fh.write(b"X")

        with self.assertRaises(checksum_service.ChecksumMismatchError):
            checksum_service.verify_checksum(path, sidecar)

    def test_verify_checksum_nunca_modifica_el_archivo_original(self):
        path = self._make_file("a.dump")
        sidecar = path.with_name(path.name + ".sha256")
        checksum_service.write_checksum_sidecar(path, sidecar)
        original_bytes = path.read_bytes()

        checksum_service.verify_checksum(path, sidecar)

        self.assertEqual(path.read_bytes(), original_bytes)
