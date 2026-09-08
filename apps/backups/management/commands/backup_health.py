"""`python manage.py backup_health` — chequeo de salud de backups
(FASE 20, sección 20 — Monitoring). Termina con exit code distinto de
cero si algún tipo de backup está vencido/nunca-exitoso, para que un
scheduler externo (cron/Task Scheduler) pueda detectar el fallo por el
exit code sin necesitar ninguna infraestructura de alertas nueva."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.backups.services import monitoring as monitoring_service


class Command(BaseCommand):
    help = "Reporta si cada tipo de backup (base de datos, media privada, media de catálogo) está al día."

    def add_arguments(self, parser):
        parser.add_argument("--max-age-hours", type=int, default=30)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        summary = monitoring_service.get_backup_health_summary(max_age_hours=options["max_age_hours"])

        if options["as_json"]:
            self.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            for kind, info in summary["kinds"].items():
                style = self.style.SUCCESS if info["healthy"] else self.style.ERROR
                self.stdout.write(style(f"{info['label']}: {'OK' if info['healthy'] else 'ATENCIÓN'} — {info['reason']}"))

        if not summary["healthy"]:
            raise CommandError("Al menos un tipo de backup no está al día — ver detalle arriba.")
