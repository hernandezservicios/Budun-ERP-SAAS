"""`python manage.py verify_backup --backup <ruta>` — verificación
rápida de checksum sin restaurar nada (FASE 20, sección 7). Útil para
chequeos de integridad periódicos ligeros, distinto del restore drill
completo (`disaster_recovery_drill`)."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.backups.services import checksum as checksum_service


class Command(BaseCommand):
    help = "Verifica el checksum SHA-256 de un archivo de backup contra su sidecar .sha256, sin restaurarlo."

    def add_arguments(self, parser):
        parser.add_argument("--backup", required=True, help="Ruta al archivo de backup (.dump o .tar.gz).")

    def handle(self, *args, **options):
        path = Path(options["backup"])
        if not path.exists():
            raise CommandError(f"No existe el archivo: {path}")
        try:
            checksum = checksum_service.verify_checksum(path)
        except checksum_service.ChecksumMissingError as error:
            raise CommandError(str(error)) from error
        except checksum_service.ChecksumMismatchError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(f"Checksum OK: {path.name} — {checksum}"))
