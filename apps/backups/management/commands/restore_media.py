"""`python manage.py restore_media --backup <ruta> --target-dir <dir>`
— restore real de un archivo de media a un directorio AISLADO (nunca
sobrescribe `media-private/`/`catalog-media/` en uso, FASE 20 sección
12-13)."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.backups.services import media as media_service


class Command(BaseCommand):
    help = "Extrae un backup de media a un directorio AISLADO y compara contra el árbol original."

    def add_arguments(self, parser):
        parser.add_argument("--backup", required=True, help="Ruta al archivo .tar.gz a restaurar.")
        parser.add_argument("--target-dir", required=True, help="Directorio AISLADO donde extraer (nunca el árbol real en uso).")
        parser.add_argument("--compare-to", help="Directorio original contra el que comparar (opcional).")

    def handle(self, *args, **options):
        archive_path = Path(options["backup"])
        target_dir = Path(options["target_dir"])
        if not archive_path.exists():
            raise CommandError(f"No existe el archivo: {archive_path}")
        if target_dir.exists() and any(target_dir.iterdir()):
            raise CommandError(f"{target_dir} ya existe y no está vacío — se exige un destino aislado y vacío.")

        result = media_service.restore_media_archive(archive_path, target_dir)
        self.stdout.write(self.style.SUCCESS(
            f"Restaurado: {result.file_count} archivo(s) en {result.target_dir} ({result.duration_seconds:.2f}s)"
        ))

        compare_to = options.get("compare_to")
        if compare_to:
            verification = media_service.verify_media_restore(Path(compare_to), target_dir)
            self.stdout.write(f"Comparación: {verification}")
            if not verification["ok"]:
                raise CommandError("La comparación contra el árbol original encontró diferencias.")
