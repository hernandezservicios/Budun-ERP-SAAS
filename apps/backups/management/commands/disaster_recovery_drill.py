"""`python manage.py disaster_recovery_drill` — el "Restore Drill" +
"Smoke End-to-End" obligatorios de la especificación de fase
(secciones 17, 25, 26), todo en un único comando reproducible:

    backup real (DB + media)
    → checksum
    → restore a base/directorios AISLADOS
    → conexión
    → verificación de conteos
    → verificación de media
    → limpieza (nunca deja rastro en la base/carpetas principales)

Nunca toca la base de datos principal más allá de leerla (pg_dump es
de solo lectura); nunca sobrescribe `media-private/`/`catalog-media/`
reales. Pensado para ejecutarse periódicamente como evidencia viva de
que el backup realmente es recuperable — no solo que el archivo
existe."""

import json
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.backups.services import jobs as jobs_service


class Command(BaseCommand):
    help = "Ejecuta un restore drill completo real (base de datos + media) y reporta evidencia detallada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-database", action="store_true",
            help="No soltar la base de datos aislada de verificación al terminar (para inspección manual).",
        )

    def handle(self, *args, **options):
        report: dict = {}
        ok = True

        self.stdout.write("=== 1/4 Backup de base de datos ===")
        db_backup = jobs_service.perform_database_backup(apply_retention_policy=False)
        report["db_backup"] = db_backup
        if not db_backup["ok"]:
            raise CommandError(f"Backup de base de datos falló: {db_backup.get('error')}")
        self.stdout.write(self.style.SUCCESS(
            f"OK — {db_backup['size_bytes']} bytes, {db_backup['duration_seconds']:.2f}s, "
            f"checksum {db_backup['checksum_sha256'][:12]}…"
        ))

        self.stdout.write("=== 2/4 Restore drill de base de datos (base aislada) ===")
        db_restore = jobs_service.perform_database_restore_drill(
            dump_path=db_backup["dump_path"], keep_database=options["keep_database"]
        )
        report["db_restore"] = db_restore
        if not db_restore.get("ok"):
            ok = False
            self.stderr.write(self.style.ERROR(f"Restore verification FALLÓ: {db_restore}"))
        else:
            verification = db_restore["verification"]
            self.stdout.write(self.style.SUCCESS(
                f"OK — restore {db_restore['restore_duration_seconds']:.2f}s, "
                f"{verification.migrations_applied} migraciones aplicadas, "
                f"{len(verification.counts)} tablas verificadas, 0 discrepancias."
            ))

        media_reports = {}
        for tree_name, source_dir in (("private", settings.MEDIA_ROOT), ("catalog", settings.CATALOG_MEDIA_ROOT)):
            self.stdout.write(f"=== 3/4 Backup + restore drill de media ({tree_name}) ===")
            media_backup = jobs_service.perform_media_backup(tree_name, source_dir, apply_retention_policy=False)
            if not media_backup["ok"]:
                ok = False
                self.stderr.write(self.style.ERROR(f"Backup de media ({tree_name}) falló: {media_backup.get('error')}"))
                media_reports[tree_name] = {"backup": media_backup}
                continue

            with tempfile.TemporaryDirectory(prefix=f"erp_media_restore_{tree_name}_") as tmp_dir:
                media_restore = jobs_service.perform_media_restore_drill(
                    media_backup["archive_path"], source_dir, Path(tmp_dir)
                )
            media_reports[tree_name] = {"backup": media_backup, "restore": media_restore}
            if not media_restore["ok"]:
                ok = False
                self.stderr.write(self.style.ERROR(f"Restore de media ({tree_name}) encontró diferencias: {media_restore['verification']}"))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"OK — {media_backup['file_count']} archivo(s), {media_backup['size_bytes']} bytes, "
                    f"restore {media_restore['duration_seconds']:.2f}s, verificación sin diferencias."
                ))
        report["media"] = media_reports

        self.stdout.write("=== 4/4 Resumen ===")
        self.stdout.write(json.dumps(_json_safe(report), indent=2, ensure_ascii=False, default=str))

        if not ok:
            raise CommandError("El restore drill encontró al menos un problema — ver detalle arriba.")
        self.stdout.write(self.style.SUCCESS("Restore drill completo: TODO OK."))


def _json_safe(value):
    """Convierte dataclasses/Path/otros objetos no serializables del
    reporte a algo que `json.dumps` pueda imprimir, solo para el
    resumen impreso en pantalla — nunca se usa para lógica real."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {field: _json_safe(getattr(value, field)) for field in value.__dataclass_fields__}
    return value
