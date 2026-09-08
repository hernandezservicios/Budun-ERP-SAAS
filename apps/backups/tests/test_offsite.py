"""FASE 20, sección 10 — copia off-site (interfaz + `LocalOffsiteAdapter`
real) y sección 19 — "off-site unavailable" nunca debe romper el
backup local ya generado con éxito."""

import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.backups.services import offsite as offsite_service


class LocalOffsiteAdapterTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def test_copia_real_a_un_segundo_directorio(self):
        source = self.tmp_path / "origen" / "backup.dump"
        source.parent.mkdir()
        source.write_bytes(b"contenido de backup")

        destination_root = self.tmp_path / "offsite"
        adapter = offsite_service.LocalOffsiteAdapter(destination_root)
        destination = adapter.copy(source)

        self.assertTrue(destination.exists())
        self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_falla_de_copia_se_reporta_como_offsiteunavailable(self):
        adapter = offsite_service.LocalOffsiteAdapter(self.tmp_path / "offsite")
        with mock.patch("shutil.copy2", side_effect=OSError("disco lleno")):
            with self.assertRaises(offsite_service.OffsiteUnavailableError):
                adapter.copy(self.tmp_path / "no-existe.dump")


class CloudOffsiteAdapterTests(SimpleTestCase):
    def test_placeholder_documentado_nunca_finge_subir(self):
        adapter = offsite_service.CloudOffsiteAdapter()
        with self.assertRaises(NotImplementedError):
            adapter.copy(Path("cualquier-cosa.dump"))


class CopyToOffsiteIfConfiguredTests(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.source = self.tmp_path / "backup.dump"
        self.source.write_bytes(b"contenido")

    @override_settings(BACKUP_OFFSITE_ROOT="")
    def test_sin_configurar_devuelve_ok_false_sin_lanzar(self):
        ok, detail = offsite_service.copy_to_offsite_if_configured(self.source)
        self.assertFalse(ok)
        self.assertIn("no configurado", detail.lower())

    def test_configurado_pero_no_disponible_nunca_lanza(self):
        with override_settings(BACKUP_OFFSITE_ROOT=str(self.tmp_path / "offsite")):
            with mock.patch("shutil.copy2", side_effect=OSError("no disponible")):
                # No debe lanzar — best-effort per diseño.
                ok, detail = offsite_service.copy_to_offsite_if_configured(self.source)
        self.assertFalse(ok)
        self.assertIn("no disponible", detail.lower())
