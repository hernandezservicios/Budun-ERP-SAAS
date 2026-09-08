"""`python manage.py backup_database` — backup real de PostgreSQL vía
`pg_dump` (FASE 20). Pensado para invocarse desde el scheduler del
sistema operativo (Task Scheduler en Windows, cron/systemd timer en
Linux — ver `docs/backup-recovery.md` sección 9), nunca desde un
scheduler propio de Django."""

from django.core.management.base import BaseCommand, CommandError

from apps.backups.services import jobs as jobs_service


class Command(BaseCommand):
    help = "Genera un backup real de la base de datos PostgreSQL configurada (pg_dump, formato custom)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-retention", action="store_true",
            help="No aplicar la política de retención después de este backup.",
        )

    def handle(self, *args, **options):
        result = jobs_service.perform_database_backup(apply_retention_policy=not options["skip_retention"])
        if not result["ok"]:
            raise CommandError(f"Backup de base de datos falló: {result.get('error')}")

        self.stdout.write(self.style.SUCCESS(
            f"Backup OK: {result['dump_path']} "
            f"({result['size_bytes']} bytes, {result['duration_seconds']:.2f}s, "
            f"checksum {result['checksum_sha256'][:12]}…, cifrado={result['encrypted']})"
        ))
        if not result["encrypted"]:
            self.stdout.write(self.style.WARNING(result["encryption_note"]))
        if result["offsite_detail"]:
            self.stdout.write(f"Off-site: {result['offsite_ok']} — {result['offsite_detail']}")
        retention = result.get("retention_report")
        if retention:
            self.stdout.write(
                f"Retención: {len(retention.kept)} conservado(s), {len(retention.deleted)} eliminado(s), "
                f"{len(retention.errors)} error(es)."
            )
