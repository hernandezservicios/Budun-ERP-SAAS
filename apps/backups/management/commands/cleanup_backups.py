"""`python manage.py cleanup_backups [--dry-run]` — aplica la política
de retención (FASE 20, sección 8) sobre los backups de base de datos y
de media ya existentes en `BACKUP_ROOT`."""

from django.core.management.base import BaseCommand

from apps.backups.services import retention as retention_service


class Command(BaseCommand):
    help = "Aplica la política de retención (diaria/semanal/mensual) — el último backup válido nunca se borra."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Mostrar qué se borraría sin borrar nada.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        db_entries = retention_service.scan_database_backup_entries()
        db_report = retention_service.apply_retention(db_entries, dry_run=dry_run)
        self._report("Base de datos", db_report, dry_run)

        for tree_name in ("private", "catalog"):
            media_entries = retention_service.scan_media_backup_entries(tree_name)
            media_report = retention_service.apply_retention(media_entries, dry_run=dry_run)
            self._report(f"Media ({tree_name})", media_report, dry_run)

    def _report(self, label, report, dry_run):
        verb = "se eliminarían" if dry_run else "eliminados"
        self.stdout.write(
            f"{label}: {len(report.kept)} conservado(s), {len(report.deleted)} {verb}, "
            f"{len(report.errors)} error(es)."
        )
        if report.protected_last_valid:
            self.stdout.write(f"  Último backup válido protegido: {report.protected_last_valid.identifier}")
        for entry, error in report.errors:
            self.stderr.write(self.style.ERROR(f"  No se pudo eliminar {entry.identifier}: {error}"))
