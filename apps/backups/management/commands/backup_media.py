"""`python manage.py backup_media [--target private|catalog|both]` —
backup real de `media-private/`/`catalog-media/` (FASE 20, sección
12), SIEMPRE en archivos separados (nunca mezclados)."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.backups.services import jobs as jobs_service


class Command(BaseCommand):
    help = "Genera un backup real de media-private/ y/o catalog-media/ (tar.gz + checksum, siempre separados)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--target", choices=["private", "catalog", "both"], default="both",
            help="Qué árbol de media respaldar (por defecto: both).",
        )
        parser.add_argument("--skip-retention", action="store_true")

    def handle(self, *args, **options):
        targets = []
        if options["target"] in ("private", "both"):
            targets.append(("private", settings.MEDIA_ROOT))
        if options["target"] in ("catalog", "both"):
            targets.append(("catalog", settings.CATALOG_MEDIA_ROOT))

        any_failed = False
        for tree_name, source_dir in targets:
            result = jobs_service.perform_media_backup(
                tree_name, source_dir, apply_retention_policy=not options["skip_retention"]
            )
            if not result["ok"]:
                any_failed = True
                self.stderr.write(self.style.ERROR(f"[{tree_name}] falló: {result.get('error')}"))
                continue
            self.stdout.write(self.style.SUCCESS(
                f"[{tree_name}] OK: {result['archive_path']} — {result['file_count']} archivo(s), "
                f"{result['size_bytes']} bytes, {result['duration_seconds']:.2f}s"
            ))

        if any_failed:
            raise CommandError("Al menos un backup de media falló — ver detalle arriba.")
