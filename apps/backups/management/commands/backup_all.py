"""`python manage.py backup_all` — el ÚNICO comando que un scheduler
del sistema operativo (Task Scheduler en Windows, cron/systemd timer
en Linux, ver `docs/backup-recovery.md` sección 9) necesita invocar:
base de datos + ambos árboles de media + retención. Nunca depende de
`runserver` ni de ningún proceso Django persistente."""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Ejecuta el backup completo (base de datos + media privada + media de catálogo) en un solo comando."

    def handle(self, *args, **options):
        failures = []
        for label, command_name, command_args in (
            ("base de datos", "backup_database", {}),
            ("media", "backup_media", {"target": "both"}),
        ):
            self.stdout.write(f"--- {label} ---")
            try:
                call_command(command_name, stdout=self.stdout, stderr=self.stderr, **command_args)
            except CommandError as error:
                failures.append(label)
                self.stderr.write(self.style.ERROR(f"{label} falló: {error}"))

        if failures:
            raise CommandError(f"Falló: {', '.join(failures)}. Ver detalle arriba.")
        self.stdout.write(self.style.SUCCESS("backup_all completado sin errores."))
