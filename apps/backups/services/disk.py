"""Verificación de espacio en disco antes de iniciar un backup
(FASE 20, sección 19: "insufficient storage" es uno de los escenarios
de fallo obligatorios a probar)."""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings


class InsufficientStorageError(Exception):
    pass


def ensure_sufficient_disk_space(path: Path, minimum_free_bytes: int | None = None) -> int:
    """Lanza `InsufficientStorageError` si el disco que contiene `path`
    tiene menos de `minimum_free_bytes` libres. Devuelve el espacio
    libre real (bytes) cuando la verificación pasa. `path` no necesita
    existir todavía — se resuelve al padre más cercano que sí exista
    (para poder verificar el disco de destino antes de crear el
    archivo)."""
    minimum_free_bytes = (
        minimum_free_bytes
        if minimum_free_bytes is not None
        else getattr(settings, "BACKUP_MIN_FREE_BYTES", 500 * 1024 * 1024)
    )
    probe = Path(path)
    while not probe.exists():
        if probe.parent == probe:
            break
        probe = probe.parent
    free_bytes = shutil.disk_usage(probe).free
    if free_bytes < minimum_free_bytes:
        raise InsufficientStorageError(
            f"Espacio libre insuficiente en {probe} ({free_bytes} bytes disponibles, "
            f"se requieren al menos {minimum_free_bytes})."
        )
    return free_bytes
