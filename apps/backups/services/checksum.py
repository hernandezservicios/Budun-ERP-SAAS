"""Checksum de integridad de backups (FASE 20, sección 7).

SHA-256 — mismo algoritmo estándar ya usado en el proyecto para
`ApiKey`/`Integration` (`apps.api.crypto`), sin introducir un segundo
mecanismo de hash. El formato del sidecar `.sha256` es el mismo que
produce/consume `sha256sum` de línea de comandos
(`"<hex>  <nombre-del-archivo>\\n"`), para que un operador humano
también pueda verificar un backup fuera de este proyecto si hace
falta."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024  # 1 MB — evita cargar backups grandes enteros en memoria.


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def write_checksum_sidecar(path: Path, sidecar_path: Path) -> str:
    checksum = sha256_of_file(path)
    sidecar_path.write_text(f"{checksum}  {path.name}\n", encoding="utf-8")
    return checksum


def read_checksum_sidecar(sidecar_path: Path) -> str | None:
    if not sidecar_path.exists():
        return None
    first_line = sidecar_path.read_text(encoding="utf-8").splitlines()[0]
    return first_line.split()[0].strip().lower()


class ChecksumMismatchError(Exception):
    """El backup no coincide con su checksum registrado — nunca debe
    usarse para un restore (sección 7: "comprobar que alteraciones sean
    detectadas antes de restaurar")."""


class ChecksumMissingError(Exception):
    """No existe un sidecar `.sha256` para este backup — un backup sin
    checksum verificable nunca se considera válido para restore."""


def verify_checksum(path: Path, sidecar_path: Path | None = None) -> str:
    """Devuelve el checksum verificado si coincide; lanza
    `ChecksumMissingError`/`ChecksumMismatchError` en caso contrario.
    Nunca modifica `path` ni el sidecar (sección 7: "no modificar el
    backup original")."""
    sidecar_path = sidecar_path or path.with_name(path.name + ".sha256")
    expected = read_checksum_sidecar(sidecar_path)
    if not expected:
        raise ChecksumMissingError(f"No existe checksum registrado para {path.name}")
    actual = sha256_of_file(path)
    if actual.lower() != expected.lower():
        raise ChecksumMismatchError(
            f"Checksum de {path.name} no coincide (esperado {expected}, real {actual}) — "
            "el archivo pudo haberse corrompido o alterado."
        )
    return actual
