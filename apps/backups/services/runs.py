"""Registro de `BackupRun` (FASE 20, sección 20 — Monitoring).

Aislado en su propio módulo por el mismo motivo que
`apps.audit.services.log_event`: registrar un backup NUNCA debe poder
romper la operación de backup/restore real que está registrando —
cualquier excepción al escribir el modelo se atrapa aquí, nunca se
relanza (mismo patrón `try_record_*` que `apps.accounting`/
`apps.audit` ya usan)."""

from __future__ import annotations

import datetime as dt


def record_backup_run(
    *,
    kind: str,
    status: str,
    started_at: dt.datetime,
    finished_at: dt.datetime | None = None,
    relative_path: str = "",
    size_bytes: int | None = None,
    duration_seconds: float | None = None,
    checksum_sha256: str = "",
    encrypted: bool = False,
    postgres_version: str = "",
    error_message: str = "",
):
    try:
        from ..models import BackupRun  # noqa: local import evita ciclos con apps aún no listas

        return BackupRun.objects.create(
            kind=kind,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            relative_path=relative_path,
            size_bytes=size_bytes,
            duration_seconds=duration_seconds,
            checksum_sha256=checksum_sha256,
            encrypted=encrypted,
            postgres_version=postgres_version,
            error_message=error_message[:4000],
        )
    except Exception:
        return None
