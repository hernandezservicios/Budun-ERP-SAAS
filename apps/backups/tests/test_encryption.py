"""FASE 20, sección 11 — cifrado real vía `openssl` (sin criptografía
propia). Se omite (`skipUnless`) si `openssl` no está en el `PATH` del
entorno que corre la suite — el propio `docs/backup-recovery.md`
documenta que este entorno de desarrollo SÍ lo tiene (Git para
Windows)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from apps.backups.services import encryption as encryption_service

_OPENSSL_DISPONIBLE = shutil.which("openssl") is not None


@unittest.skipUnless(_OPENSSL_DISPONIBLE, "openssl no está disponible en PATH en este entorno")
class EncryptionRoundTripTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def test_encrypt_decrypt_round_trip(self):
        source = self.tmp_path / "origen.txt"
        source.write_bytes(b"contenido secreto de prueba \xc3\xa1\xc3\xa9\xc3\xad")
        encrypted = self.tmp_path / "origen.txt.enc"
        decrypted = self.tmp_path / "origen_dec.txt"

        encryption_service.encrypt_file(source, encrypted, "clave-de-prueba-123")
        self.assertTrue(encrypted.exists())
        self.assertNotEqual(encrypted.read_bytes(), source.read_bytes())

        encryption_service.decrypt_file(encrypted, decrypted, "clave-de-prueba-123")
        self.assertEqual(decrypted.read_bytes(), source.read_bytes())

    def test_clave_incorrecta_falla_al_desencriptar(self):
        source = self.tmp_path / "origen.txt"
        source.write_bytes(b"contenido")
        encrypted = self.tmp_path / "origen.txt.enc"
        encryption_service.encrypt_file(source, encrypted, "clave-correcta")

        with self.assertRaises(encryption_service.EncryptionFailedError):
            encryption_service.decrypt_file(encrypted, self.tmp_path / "salida.txt", "clave-incorrecta")

    def test_sin_passphrase_lanza_sin_invocar_openssl(self):
        source = self.tmp_path / "origen.txt"
        source.write_bytes(b"contenido")
        with self.assertRaises(encryption_service.EncryptionFailedError):
            encryption_service.encrypt_file(source, self.tmp_path / "salida.enc", "")


class EncryptionUnavailableTests(SimpleTestCase):
    def test_openssl_no_disponible_se_reporta_explicitamente(self):
        from unittest import mock

        with mock.patch("apps.backups.services.encryption.shutil.which", return_value=None):
            with self.assertRaises(encryption_service.EncryptionUnavailableError):
                encryption_service.encrypt_file(Path("no-importa"), Path("no-importa.enc"), "clave")
