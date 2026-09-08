"""Política de retención (FASE 20, sección 8).

Reglas permanentes de esta política:
- Solo se consideran para retención los backups que terminaron con
  éxito (`status="success"`) — un backup fallido nunca deja un
  archivo `.dump` "ambiguo" en disco: el comando que lo genera lo
  limpia inmediatamente (ver `management/commands/backup_database.py`),
  así que la retención nunca tiene que decidir sobre un backup roto.
- El backup válido MÁS RECIENTE nunca se borra, sin importar la
  configuración de retención — regla explícita e incondicional de la
  especificación de fase ("Nunca borrar automáticamente el último
  backup válido").
- Tres ventanas, evaluadas de más reciente a más antigua: diaria
  (todos los backups de los últimos N días), semanal (uno por semana
  ISO, el más reciente de cada semana, durante M semanas después de la
  ventana diaria) y mensual (uno por mes calendario, durante P meses
  después de la ventana semanal). Cualquier backup fuera de las tres
  ventanas y no protegido como "último válido" expira."""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

from django.utils import timezone


@dataclasses.dataclass(frozen=True)
class BackupEntry:
    identifier: str
    created_at: dt.datetime
    status: str
    paths: tuple[Path, ...] = ()


@dataclasses.dataclass
class RetentionReport:
    kept: list[BackupEntry]
    deleted: list[BackupEntry]
    protected_last_valid: BackupEntry | None
    errors: list[tuple[BackupEntry, str]]


def classify_retention(
    entries: list[BackupEntry],
    *,
    now: dt.datetime,
    daily_days: int,
    weekly_weeks: int,
    monthly_months: int,
) -> tuple[set[str], BackupEntry | None]:
    valid_entries = sorted(
        (entry for entry in entries if entry.status == "success"),
        key=lambda entry: entry.created_at,
    )
    if not valid_entries:
        return set(), None

    protected = valid_entries[-1]
    keep_ids = {protected.identifier}

    daily_cutoff = now - dt.timedelta(days=daily_days)
    weekly_start = daily_cutoff - dt.timedelta(weeks=weekly_weeks)
    monthly_start = weekly_start - dt.timedelta(days=30 * monthly_months)

    for entry in valid_entries:
        if entry.created_at >= daily_cutoff:
            keep_ids.add(entry.identifier)

    by_week: dict[tuple[int, int], BackupEntry] = {}
    for entry in valid_entries:
        if weekly_start <= entry.created_at < daily_cutoff:
            key = entry.created_at.isocalendar()[:2]
            if key not in by_week or entry.created_at > by_week[key].created_at:
                by_week[key] = entry
    keep_ids.update(entry.identifier for entry in by_week.values())

    by_month: dict[tuple[int, int], BackupEntry] = {}
    for entry in valid_entries:
        if monthly_start <= entry.created_at < weekly_start:
            key = (entry.created_at.year, entry.created_at.month)
            if key not in by_month or entry.created_at > by_month[key].created_at:
                by_month[key] = entry
    keep_ids.update(entry.identifier for entry in by_month.values())

    return keep_ids, protected


def apply_retention(
    entries: list[BackupEntry],
    *,
    now: dt.datetime | None = None,
    daily_days: int | None = None,
    weekly_weeks: int | None = None,
    monthly_months: int | None = None,
    dry_run: bool = False,
) -> RetentionReport:
    from django.conf import settings

    now = now or timezone.now()
    daily_days = daily_days if daily_days is not None else settings.BACKUP_RETENTION_DAILY_DAYS
    weekly_weeks = weekly_weeks if weekly_weeks is not None else settings.BACKUP_RETENTION_WEEKLY_WEEKS
    monthly_months = monthly_months if monthly_months is not None else settings.BACKUP_RETENTION_MONTHLY_MONTHS

    keep_ids, protected = classify_retention(
        entries, now=now, daily_days=daily_days, weekly_weeks=weekly_weeks, monthly_months=monthly_months
    )

    kept: list[BackupEntry] = []
    deleted: list[BackupEntry] = []
    errors: list[tuple[BackupEntry, str]] = []

    # Los backups FAILED nunca participan de la clasificación (ver
    # docstring del módulo) — se conservan tal cual, la limpieza de un
    # backup fallido es responsabilidad inmediata del comando que lo
    # generó, nunca de esta política periódica.
    for entry in entries:
        if entry.status != "success":
            kept.append(entry)
            continue
        if entry.identifier in keep_ids:
            kept.append(entry)
            continue
        if dry_run:
            deleted.append(entry)
            continue
        try:
            for path in entry.paths:
                if path.exists():
                    path.unlink()
            deleted.append(entry)
        except OSError as error:
            errors.append((entry, str(error)))
            kept.append(entry)

    return RetentionReport(kept=kept, deleted=deleted, protected_last_valid=protected, errors=errors)


def scan_backup_entries(directory: Path, *, name_prefix: str = "") -> list[BackupEntry]:
    """Construye la lista de `BackupEntry` reales a partir de los
    `.meta.json` presentes en `directory` — separado de
    `classify_retention`/`apply_retention` (que son puras y se prueban
    con datos sintéticos, sin tocar el disco). `name_prefix` filtra por
    árbol de media cuando `directory` mezcla varios (p. ej. privada y
    de catálogo comparten `services.paths.media_backup_dir()`)."""
    import json

    from . import paths as paths_service

    entries: list[BackupEntry] = []
    for meta_path in sorted(Path(directory).glob(f"{name_prefix}*.meta.json")):
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        dump_path = meta_path.with_name(meta_path.name[: -len(".meta.json")])
        related = [meta_path]
        if dump_path.exists():
            related.append(dump_path)
        checksum_path = paths_service.checksum_sidecar(dump_path)
        if checksum_path.exists():
            related.append(checksum_path)
        encrypted_path = paths_service.encrypted_sidecar(dump_path)
        if encrypted_path.exists():
            related.append(encrypted_path)
        try:
            created_at = dt.datetime.fromisoformat(metadata["created_at"])
        except (KeyError, ValueError):
            continue
        entries.append(
            BackupEntry(
                identifier=dump_path.name,
                created_at=created_at,
                status=metadata.get("status", "success"),
                paths=tuple(related),
            )
        )
    return entries


def scan_database_backup_entries() -> list[BackupEntry]:
    from . import paths as paths_service

    return scan_backup_entries(paths_service.database_backup_dir())


def scan_media_backup_entries(tree_name: str) -> list[BackupEntry]:
    from . import paths as paths_service

    return scan_backup_entries(paths_service.media_backup_dir(), name_prefix=f"erp_media_{tree_name}_")
