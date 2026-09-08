"""Backup y restore de archivos/media (FASE 20, secciones 12-13).

`media-private/` (documentos de Clientes/Proveedores, `PaymentProof`)
y `catalog-media/` (`ProductImage`) se respaldan SIEMPRE por
separado — nunca en el mismo archivo — porque son dos superficies de
seguridad distintas (una es privada, la otra explícitamente pública/
publicable, ver `docs/security.md` sección "Uploads y media"). El
restore SIEMPRE extrae a un directorio AISLADO, nunca sobrescribe el
árbol real en uso (mismo principio que `services.database`: nunca
destruir el original para probar la recuperación)."""

from __future__ import annotations

import dataclasses
import tarfile
import time
from pathlib import Path

from . import checksum as checksum_service
from . import disk as disk_service
from . import paths as paths_service


class MediaBackupFailedError(Exception):
    pass


@dataclasses.dataclass
class MediaBackupResult:
    archive_path: Path
    file_count: int
    total_bytes: int
    size_bytes: int
    duration_seconds: float


@dataclasses.dataclass
class MediaRestoreResult:
    target_dir: Path
    file_count: int
    duration_seconds: float


def backup_media_tree(source_dir: Path, output_path: Path) -> MediaBackupResult:
    source_dir = Path(source_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    disk_service.ensure_sufficient_disk_space(output_path.parent)

    if not source_dir.exists():
        # Un tenant que nunca subió ningún archivo es un caso válido —
        # se produce un archivo vacío (0 archivos), nunca un error.
        source_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    file_count = 0
    total_bytes = 0
    try:
        with tarfile.open(output_path, mode="w:gz") as tar:
            for path in sorted(source_dir.rglob("*")):
                if path.is_file():
                    file_count += 1
                    total_bytes += path.stat().st_size
                    tar.add(path, arcname=str(path.relative_to(source_dir)))
    except (OSError, tarfile.TarError) as error:
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass
        raise MediaBackupFailedError(str(error)) from error
    duration = time.perf_counter() - started

    return MediaBackupResult(
        archive_path=output_path,
        file_count=file_count,
        total_bytes=total_bytes,
        size_bytes=output_path.stat().st_size,
        duration_seconds=duration,
    )


def restore_media_archive(archive_path: Path, target_dir: Path) -> MediaRestoreResult:
    """Extrae SIEMPRE a `target_dir` (que debe estar vacío o no
    existir) — nunca al `MEDIA_ROOT`/`CATALOG_MEDIA_ROOT` real en uso.
    Verifica el checksum del archivo antes de extraer."""
    archive_path = Path(archive_path)
    target_dir = Path(target_dir)
    checksum_service.verify_checksum(archive_path, paths_service.checksum_sidecar(archive_path))

    target_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    file_count = 0
    with tarfile.open(archive_path, mode="r:gz") as tar:
        # `filter="data"` (Python 3.12+, disponible aquí) rechaza rutas
        # absolutas y "../" — nunca se confía en el contenido del
        # archivo para decidir dónde escribir (path traversal), mismo
        # criterio ya aplicado a la importación de productos (FASE 8,
        # `apps.inventory.product_import`).
        tar.extractall(path=target_dir, filter="data")
        file_count = sum(1 for member in tar.getmembers() if member.isfile())
    duration = time.perf_counter() - started

    return MediaRestoreResult(target_dir=target_dir, file_count=file_count, duration_seconds=duration)


def verify_media_restore(original_dir: Path, restored_dir: Path) -> dict:
    """Compara cantidad de archivos y tamaño total entre el árbol
    original y el restaurado — sección 13 ("comprobar cantidad,
    existencia, tamaños")."""
    original_dir = Path(original_dir)
    restored_dir = Path(restored_dir)

    def _inventory(base: Path) -> dict:
        if not base.exists():
            return {}
        return {
            str(path.relative_to(base)): path.stat().st_size
            for path in sorted(base.rglob("*"))
            if path.is_file()
        }

    original_files = _inventory(original_dir)
    restored_files = _inventory(restored_dir)

    missing = sorted(set(original_files) - set(restored_files))
    extra = sorted(set(restored_files) - set(original_files))
    size_mismatches = sorted(
        name
        for name in (set(original_files) & set(restored_files))
        if original_files[name] != restored_files[name]
    )

    return {
        "original_file_count": len(original_files),
        "restored_file_count": len(restored_files),
        "missing": missing,
        "extra": extra,
        "size_mismatches": size_mismatches,
        "ok": not missing and not size_mismatches,
    }
