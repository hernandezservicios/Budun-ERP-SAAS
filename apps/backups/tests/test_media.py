"""FASE 20, secciones 12-13 — backup/restore reales de archivos de
media (tar.gz real, sin mocks del sistema de archivos)."""

import tarfile
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.backups.services import checksum as checksum_service
from apps.backups.services import media as media_service


class BackupMediaTreeTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.source_dir = self.tmp_path / "media-private"
        self.source_dir.mkdir()
        (self.source_dir / "clientes").mkdir()
        (self.source_dir / "clientes" / "doc1.pdf").write_bytes(b"contenido pdf 1")
        (self.source_dir / "proveedores").mkdir()
        (self.source_dir / "proveedores" / "doc2.pdf").write_bytes(b"contenido pdf 2 mas largo")

    def test_backup_incluye_todos_los_archivos_con_rutas_relativas(self):
        output_path = self.tmp_path / "backup.tar.gz"
        result = media_service.backup_media_tree(self.source_dir, output_path)

        self.assertEqual(result.file_count, 2)
        self.assertGreater(result.total_bytes, 0)
        self.assertTrue(output_path.exists())

        with tarfile.open(output_path, "r:gz") as tar:
            names = sorted(tar.getnames())
        self.assertEqual(names, ["clientes/doc1.pdf", "proveedores/doc2.pdf"])

    def test_arbol_vacio_produce_backup_de_cero_archivos_no_un_error(self):
        empty_dir = self.tmp_path / "vacio"
        output_path = self.tmp_path / "backup_vacio.tar.gz"
        result = media_service.backup_media_tree(empty_dir, output_path)
        self.assertEqual(result.file_count, 0)
        self.assertTrue(output_path.exists())

    def test_directorio_inexistente_se_trata_como_arbol_vacio(self):
        missing_dir = self.tmp_path / "no-existe-todavia"
        output_path = self.tmp_path / "backup_missing.tar.gz"
        result = media_service.backup_media_tree(missing_dir, output_path)
        self.assertEqual(result.file_count, 0)


class RestoreMediaArchiveTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.source_dir = self.tmp_path / "origen"
        self.source_dir.mkdir()
        (self.source_dir / "a.txt").write_bytes(b"contenido A")
        self.archive_path = self.tmp_path / "backup.tar.gz"
        result = media_service.backup_media_tree(self.source_dir, self.archive_path)
        checksum_service.write_checksum_sidecar(
            self.archive_path, self.archive_path.with_name(self.archive_path.name + ".sha256")
        )

    def test_restore_extrae_a_directorio_aislado_nunca_al_original(self):
        target_dir = self.tmp_path / "restaurado"
        result = media_service.restore_media_archive(self.archive_path, target_dir)

        self.assertEqual(result.file_count, 1)
        self.assertTrue((target_dir / "a.txt").exists())
        self.assertEqual((target_dir / "a.txt").read_bytes(), b"contenido A")
        # El original nunca se tocó.
        self.assertEqual((self.source_dir / "a.txt").read_bytes(), b"contenido A")

    def test_restore_verifica_checksum_antes_de_extraer(self):
        # Corromper el archivo DESPUÉS de calcular su checksum válido.
        with open(self.archive_path, "r+b") as fh:
            fh.seek(0)
            fh.write(b"XXXX")

        with self.assertRaises(checksum_service.ChecksumMismatchError):
            media_service.restore_media_archive(self.archive_path, self.tmp_path / "no-deberia-crearse")


class VerifyMediaRestoreTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.original_dir = self.tmp_path / "original"
        self.original_dir.mkdir()
        (self.original_dir / "a.txt").write_bytes(b"contenido A")
        (self.original_dir / "b.txt").write_bytes(b"contenido B")

    def test_restore_identico_reporta_ok(self):
        restored_dir = self.tmp_path / "restaurado_ok"
        restored_dir.mkdir()
        (restored_dir / "a.txt").write_bytes(b"contenido A")
        (restored_dir / "b.txt").write_bytes(b"contenido B")

        report = media_service.verify_media_restore(self.original_dir, restored_dir)
        self.assertTrue(report["ok"])
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["size_mismatches"], [])

    def test_archivo_faltante_se_detecta(self):
        restored_dir = self.tmp_path / "restaurado_incompleto"
        restored_dir.mkdir()
        (restored_dir / "a.txt").write_bytes(b"contenido A")
        # falta b.txt

        report = media_service.verify_media_restore(self.original_dir, restored_dir)
        self.assertFalse(report["ok"])
        self.assertIn("b.txt", report["missing"])

    def test_tamano_distinto_se_detecta(self):
        restored_dir = self.tmp_path / "restaurado_truncado"
        restored_dir.mkdir()
        (restored_dir / "a.txt").write_bytes(b"contenido A")
        (restored_dir / "b.txt").write_bytes(b"truncado")  # tamaño distinto al original

        report = media_service.verify_media_restore(self.original_dir, restored_dir)
        self.assertFalse(report["ok"])
        self.assertIn("b.txt", report["size_mismatches"])
