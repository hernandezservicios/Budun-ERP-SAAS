"""Rutas y nombres de archivo de backup (FASE 20).

Todo lo que vive bajo `settings.BACKUP_ROOT` está FUERA de cualquier
ruta que Django sirva (nunca `STATIC_ROOT`/`MEDIA_ROOT`/
`CATALOG_MEDIA_ROOT`, nunca registrado en `config/urls.py`) — ver
`docs/backup-recovery.md` sección "Seguridad"."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from django.conf import settings
from django.utils import timezone

DATABASE_SUBDIR = "database"
MEDIA_SUBDIR = "media"
OFFSITE_SUBDIR = "offsite"

# Formato de nombre oficial (docs/phases/PHASE-20-backups.md sección 24):
# erp_YYYYMMDD_HHMMSS.<extension> — nunca incluye secretos.
_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def backup_root() -> Path:
    return Path(settings.BACKUP_ROOT)


def database_backup_dir() -> Path:
    path = backup_root() / DATABASE_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def media_backup_dir() -> Path:
    path = backup_root() / MEDIA_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def offsite_root() -> Path | None:
    """`None` si no hay copia off-site configurada (`BACKUP_OFFSITE_ROOT`
    vacío) — ver `services.offsite`."""
    configured = getattr(settings, "BACKUP_OFFSITE_ROOT", "") or ""
    if not configured.strip():
        return None
    path = Path(configured)
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp_slug(moment: dt.datetime | None = None) -> str:
    moment = moment or timezone.now()
    return moment.strftime(_TIMESTAMP_FORMAT)


def database_backup_filename(db_name: str, moment: dt.datetime | None = None) -> str:
    return f"erp_{db_name}_{timestamp_slug(moment)}.dump"


def media_backup_filename(tree_name: str, moment: dt.datetime | None = None) -> str:
    return f"erp_media_{tree_name}_{timestamp_slug(moment)}.tar.gz"


def checksum_sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def metadata_sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".meta.json")


def encrypted_sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".enc")


def relative_to_backup_root(path: Path) -> str:
    """Ruta relativa a `BACKUP_ROOT` para guardar en `BackupRun.relative_path`
    — nunca la ruta absoluta real del servidor (ver `models.py`)."""
    try:
        return str(Path(path).resolve().relative_to(backup_root().resolve()))
    except ValueError:
        return str(path)
