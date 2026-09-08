"""Orquestación completa de un backup/restore (FASE 20).

Esta es la capa que los comandos de gestión (`management/commands/`)
invocan — cada función de aquí es "la operación completa" tal como la
pide la especificación de fase: verificación de espacio → operación
real → checksum → metadata → cifrado opcional → copia off-site
best-effort → retención → registro de `BackupRun`. Separado de
`services.database`/`services.media` (primitivas de bajo nivel) para
que ambas capas se puedan probar independientemente."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from django.utils import timezone

from . import checksum as checksum_service
from . import database as database_service
from . import encryption as encryption_service
from . import media as media_service
from . import offsite as offsite_service
from . import paths as paths_service
from . import retention as retention_service
from . import runs as runs_service
from . import verification as verification_service


def _harden_permissions(paths: list[Path]) -> None:
    """En POSIX (VPS de producción, FASE 21), restringe el backup a
    lectura/escritura del propio dueño (`0600`/`0700`) — sección 20:
    "revisar permisos de archivos". En Windows (desarrollo) los
    permisos POSIX no aplican; se omite en silencio (nunca un error)."""
    if os.name == "nt":
        return
    for path in paths:
        try:
            path.chmod(0o600 if path.is_file() else 0o700)
        except OSError:
            pass


def _default_db_settings() -> dict:
    from django.db import connection

    return dict(connection.settings_dict)


def perform_database_backup(
    *,
    db_settings: dict | None = None,
    apply_retention_policy: bool = True,
    encryption_key: str | None = None,
) -> dict:
    from django.conf import settings

    from ..models import BackupRun

    db_settings = db_settings or _default_db_settings()
    encryption_key = settings.BACKUP_ENCRYPTION_KEY if encryption_key is None else encryption_key

    started_at = timezone.now()
    output_path = paths_service.database_backup_dir() / paths_service.database_backup_filename(
        db_settings["NAME"], started_at
    )

    try:
        dump_result = database_service.run_pg_dump(db_settings, output_path)
    except database_service.BackupFailedError as error:
        runs_service.record_backup_run(
            kind=BackupRun.Kind.DATABASE,
            status=BackupRun.Status.FAILED,
            started_at=started_at,
            finished_at=timezone.now(),
            error_message=str(error),
        )
        return {"ok": False, "stage": "pg_dump", "error": str(error)}

    checksum_path = paths_service.checksum_sidecar(dump_result.dump_path)
    file_checksum = checksum_service.write_checksum_sidecar(dump_result.dump_path, checksum_path)

    postgres_version = database_service.get_postgres_version(db_settings)
    counts_at_backup = verification_service.count_critical_tables(db_settings)

    encrypted = False
    encrypted_path = None
    encryption_note = "BACKUP_ENCRYPTION_KEY no configurado — backup sin cifrar."
    if encryption_key:
        encrypted_path = paths_service.encrypted_sidecar(dump_result.dump_path)
        try:
            encryption_service.encrypt_file(dump_result.dump_path, encrypted_path, encryption_key)
            encrypted = True
            encryption_note = "Cifrado con openssl (AES-256-CBC + PBKDF2)."
        except encryption_service.EncryptionUnavailableError as error:
            encryption_note = f"openssl no disponible — backup sin cifrar ({error})."

    metadata = {
        "created_at": started_at.isoformat(),
        "db_name": db_settings["NAME"],
        "postgres_version": postgres_version,
        "format": "custom",
        "size_bytes": dump_result.size_bytes,
        "duration_seconds": dump_result.duration_seconds,
        "checksum_sha256": file_checksum,
        "status": "success",
        "encrypted": encrypted,
        "encryption_note": encryption_note,
        "counts_at_backup": counts_at_backup,
    }
    metadata_path = paths_service.metadata_sidecar(dump_result.dump_path)
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    hardened = [dump_result.dump_path, checksum_path, metadata_path]
    if encrypted_path:
        hardened.append(encrypted_path)
    _harden_permissions(hardened)

    offsite_source = encrypted_path if encrypted else dump_result.dump_path
    offsite_ok, offsite_detail = offsite_service.copy_to_offsite_if_configured(offsite_source)

    retention_report = None
    if apply_retention_policy:
        entries = retention_service.scan_database_backup_entries()
        retention_report = retention_service.apply_retention(entries)

    run = runs_service.record_backup_run(
        kind=BackupRun.Kind.DATABASE,
        status=BackupRun.Status.SUCCESS,
        started_at=started_at,
        finished_at=timezone.now(),
        relative_path=paths_service.relative_to_backup_root(dump_result.dump_path),
        size_bytes=dump_result.size_bytes,
        duration_seconds=dump_result.duration_seconds,
        checksum_sha256=file_checksum,
        encrypted=encrypted,
        postgres_version=postgres_version,
    )

    return {
        "ok": True,
        "dump_path": dump_result.dump_path,
        "checksum_sha256": file_checksum,
        "size_bytes": dump_result.size_bytes,
        "duration_seconds": dump_result.duration_seconds,
        "postgres_version": postgres_version,
        "counts_at_backup": counts_at_backup,
        "encrypted": encrypted,
        "encryption_note": encryption_note,
        "offsite_ok": offsite_ok,
        "offsite_detail": offsite_detail,
        "retention_report": retention_report,
        "backup_run_id": getattr(run, "pk", None),
    }


def perform_database_restore_drill(
    *, dump_path: Path, db_settings: dict | None = None, keep_database: bool = False
) -> dict:
    from ..models import BackupRun

    db_settings = db_settings or _default_db_settings()
    dump_path = Path(dump_path)
    started_at = timezone.now()

    try:
        checksum_service.verify_checksum(dump_path)
    except (checksum_service.ChecksumMissingError, checksum_service.ChecksumMismatchError) as error:
        return {"ok": False, "stage": "checksum", "error": str(error)}

    expected_counts = None
    metadata_path = paths_service.metadata_sidecar(dump_path)
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            expected_counts = metadata.get("counts_at_backup")
        except (OSError, ValueError):
            expected_counts = None

    target_name = database_service.isolated_database_name(db_settings["NAME"])
    report: dict = {"database_name": target_name, "dump_path": dump_path}

    try:
        database_service.create_isolated_database(db_settings, target_name)
    except Exception as error:
        report.update(ok=False, stage="create_database", error=str(error)[:500])
        return report

    try:
        restore_result = database_service.run_pg_restore(dump_path, db_settings, target_name)
        restore_db_settings = dict(db_settings)
        restore_db_settings["NAME"] = target_name
        verification = verification_service.verify_restored_database(
            restore_db_settings, expected_counts=expected_counts
        )
        report.update(
            ok=verification.ok,
            stage="verify",
            restore_duration_seconds=restore_result.duration_seconds,
            restore_exit_code=restore_result.exit_code,
            restore_stderr=restore_result.stderr_excerpt,
            verification=verification,
        )
    finally:
        if keep_database:
            report["database_dropped"] = False
        else:
            database_service.drop_isolated_database(db_settings, target_name)
            report["database_dropped"] = True

    finished_at = timezone.now()
    report["duration_seconds"] = (finished_at - started_at).total_seconds()
    runs_service.record_backup_run(
        kind=BackupRun.Kind.DATABASE,
        status=BackupRun.Status.SUCCESS if report.get("ok") else BackupRun.Status.FAILED,
        started_at=started_at,
        finished_at=finished_at,
        relative_path=paths_service.relative_to_backup_root(dump_path),
        duration_seconds=report["duration_seconds"],
        error_message="" if report.get("ok") else json.dumps(report.get("verification"), default=str)[:2000],
    )
    return report


def perform_media_backup(
    tree_name: str, source_dir: Path, *, apply_retention_policy: bool = True
) -> dict:
    from ..models import BackupRun

    kind = BackupRun.Kind.MEDIA_PRIVATE if tree_name == "private" else BackupRun.Kind.MEDIA_CATALOG
    started_at = timezone.now()
    output_path = paths_service.media_backup_dir() / paths_service.media_backup_filename(tree_name, started_at)

    try:
        backup_result = media_service.backup_media_tree(source_dir, output_path)
    except media_service.MediaBackupFailedError as error:
        runs_service.record_backup_run(
            kind=kind, status=BackupRun.Status.FAILED,
            started_at=started_at, finished_at=timezone.now(), error_message=str(error),
        )
        return {"ok": False, "stage": "tar", "error": str(error)}

    checksum_path = paths_service.checksum_sidecar(backup_result.archive_path)
    file_checksum = checksum_service.write_checksum_sidecar(backup_result.archive_path, checksum_path)

    metadata = {
        "created_at": started_at.isoformat(),
        "tree_name": tree_name,
        "source_dir": str(source_dir),
        "file_count": backup_result.file_count,
        "total_bytes": backup_result.total_bytes,
        "size_bytes": backup_result.size_bytes,
        "duration_seconds": backup_result.duration_seconds,
        "checksum_sha256": file_checksum,
        "status": "success",
    }
    metadata_path = paths_service.metadata_sidecar(backup_result.archive_path)
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    _harden_permissions([backup_result.archive_path, checksum_path, metadata_path])

    offsite_ok, offsite_detail = offsite_service.copy_to_offsite_if_configured(backup_result.archive_path)

    retention_report = None
    if apply_retention_policy:
        entries = retention_service.scan_media_backup_entries(tree_name)
        retention_report = retention_service.apply_retention(entries)

    run = runs_service.record_backup_run(
        kind=kind, status=BackupRun.Status.SUCCESS,
        started_at=started_at, finished_at=timezone.now(),
        relative_path=paths_service.relative_to_backup_root(backup_result.archive_path),
        size_bytes=backup_result.size_bytes, duration_seconds=backup_result.duration_seconds,
        checksum_sha256=file_checksum,
    )

    return {
        "ok": True,
        "archive_path": backup_result.archive_path,
        "file_count": backup_result.file_count,
        "total_bytes": backup_result.total_bytes,
        "size_bytes": backup_result.size_bytes,
        "duration_seconds": backup_result.duration_seconds,
        "checksum_sha256": file_checksum,
        "offsite_ok": offsite_ok,
        "offsite_detail": offsite_detail,
        "retention_report": retention_report,
        "backup_run_id": getattr(run, "pk", None),
    }


def perform_media_restore_drill(archive_path: Path, source_dir: Path, target_dir: Path) -> dict:
    archive_path = Path(archive_path)
    try:
        restore_result = media_service.restore_media_archive(archive_path, target_dir)
    except Exception as error:
        return {"ok": False, "stage": "extract", "error": str(error)[:500]}

    verification = media_service.verify_media_restore(source_dir, target_dir)
    return {
        "ok": verification["ok"],
        "archive_path": archive_path,
        "target_dir": restore_result.target_dir,
        "file_count": restore_result.file_count,
        "duration_seconds": restore_result.duration_seconds,
        "verification": verification,
    }
