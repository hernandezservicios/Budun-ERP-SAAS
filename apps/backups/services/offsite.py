"""Copia off-site OPCIONAL (FASE 20, sección 10).

Interfaz deliberadamente pequeña para que un proveedor cloud real
(objeto de una decisión de negocio futura, nunca inventada aquí) se
pueda enchufar sin rediseñar el resto del módulo — mismo principio que
`apps.billing.providers.base.PaymentProvider` en FASE 16. Hoy solo
existe `LocalOffsiteAdapter` (copia a un segundo directorio local,
típicamente en otro disco/punto de montaje vía
`settings.BACKUP_OFFSITE_ROOT`) — una interpretación real y honesta de
"local + off-site" cuando ningún proveedor cloud está todavía
aprobado (ver `docs/backup-recovery.md` sección 10 y `DECISIONS.md`).

La copia off-site es SIEMPRE best-effort: un fallo aquí nunca debe
marcar como fallido el backup local ya generado con éxito (sección 19:
"off-site unavailable" debe manejarse sin romper la operación
principal)."""

from __future__ import annotations

import shutil
from pathlib import Path


class OffsiteUnavailableError(Exception):
    pass


class OffsiteAdapter:
    """Interfaz — ver `LocalOffsiteAdapter` y `CloudOffsiteAdapter`."""

    def copy(self, source_path: Path) -> Path:
        raise NotImplementedError


class LocalOffsiteAdapter(OffsiteAdapter):
    """Copia el archivo a un segundo directorio local ya configurado vía
    `settings.BACKUP_OFFSITE_ROOT`. Construido y probado — no es un
    placeholder."""

    def __init__(self, destination_root: Path):
        self.destination_root = Path(destination_root)

    def copy(self, source_path: Path) -> Path:
        try:
            self.destination_root.mkdir(parents=True, exist_ok=True)
            destination = self.destination_root / source_path.name
            shutil.copy2(source_path, destination)
            return destination
        except OSError as error:
            raise OffsiteUnavailableError(str(error)) from error


class CloudOffsiteAdapter(OffsiteAdapter):
    """Placeholder documentado a propósito — ningún proveedor cloud
    (S3/GCS/Azure/Backblaze) está aprobado todavía (ver CLAUDE.md: no
    inventar infraestructura). Implementar esta clase es el único
    cambio que una decisión de negocio futura necesitaría hacer; el
    resto del módulo ya está preparado para consumir cualquier
    `OffsiteAdapter`."""

    def copy(self, source_path: Path) -> Path:
        raise NotImplementedError(
            "Ningún proveedor de almacenamiento externo está aprobado todavía "
            "— ver docs/backup-recovery.md sección 10."
        )


def get_offsite_adapter() -> OffsiteAdapter | None:
    from django.conf import settings

    configured = getattr(settings, "BACKUP_OFFSITE_ROOT", "") or ""
    if not configured.strip():
        return None
    return LocalOffsiteAdapter(Path(configured))


def copy_to_offsite_if_configured(source_path: Path) -> tuple[bool, str]:
    """Nunca lanza — best-effort per diseño. Devuelve `(ok, detalle)`."""
    adapter = get_offsite_adapter()
    if adapter is None:
        return False, "Off-site no configurado (BACKUP_OFFSITE_ROOT vacío)."
    try:
        destination = adapter.copy(source_path)
        return True, str(destination)
    except OffsiteUnavailableError as error:
        return False, f"Off-site no disponible: {error}"
