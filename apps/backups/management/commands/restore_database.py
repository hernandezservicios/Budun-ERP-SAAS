"""`python manage.py restore_database --backup <ruta>` — restore REAL
a una base de datos AISLADA (nunca la base principal), con
verificación real de conteos (FASE 20, secciones 5-6). Por defecto
suelta la base aislada al terminar; `--keep` la conserva para
inspección manual."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.backups.services import jobs as jobs_service


class Command(BaseCommand):
    help = "Restaura un backup de base de datos a una base AISLADA y verifica el resultado (nunca toca la base principal)."

    def add_arguments(self, parser):
        parser.add_argument("--backup", required=True, help="Ruta al archivo .dump a restaurar.")
        parser.add_argument(
            "--keep", action="store_true",
            help="No soltar la base de datos aislada al terminar (para inspección manual con pgAdmin 4).",
        )

    def handle(self, *args, **options):
        dump_path = Path(options["backup"])
        if not dump_path.exists():
            raise CommandError(f"No existe el archivo: {dump_path}")

        report = jobs_service.perform_database_restore_drill(dump_path=dump_path, keep_database=options["keep"])

        if report.get("stage") == "checksum":
            raise CommandError(f"Verificación de checksum falló: {report.get('error')}")

        verification = report.get("verification")
        self.stdout.write(f"Base aislada: {report['database_name']} (eliminada={report['database_dropped']})")
        self.stdout.write(f"Duración del restore: {report.get('restore_duration_seconds', 0):.2f}s")
        if verification:
            self.stdout.write(f"Migraciones aplicadas en la base restaurada: {verification.migrations_applied}")
            for label, value in verification.counts.items():
                self.stdout.write(f"  {label}: {value}")
            if verification.mismatches:
                self.stdout.write(self.style.WARNING(f"Discrepancias: {verification.mismatches}"))

        if not report.get("ok"):
            raise CommandError("Restore verification FALLÓ — ver detalle arriba.")
        self.stdout.write(self.style.SUCCESS("Restore verification OK."))
