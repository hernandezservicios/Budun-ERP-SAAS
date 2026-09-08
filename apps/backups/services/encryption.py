"""Cifrado OPCIONAL de backups (FASE 20, sección 11).

Usa `openssl enc` (AES-256-CBC + PBKDF2) — herramienta estándar ya
presente en el stack del proyecto (Git para Windows en desarrollo;
`openssl` es un paquete del sistema en cualquier VPS Linux real, ya
necesario para SSL/Nginx per `CLAUDE.md`) en vez de una dependencia
Python nueva o criptografía propia (la especificación de fase lo
prohíbe explícitamente: "No desarrollar criptografía propia").

La clave (`settings.BACKUP_ENCRYPTION_KEY`) se pasa a `openssl` por
STDIN (`-pass stdin`), NUNCA como argumento de línea de comandos
(visible en la lista de procesos del sistema operativo) y NUNCA se
escribe en ningún archivo dentro de `BACKUP_ROOT` — vive únicamente en
la variable de entorno `BACKUP_ENCRYPTION_KEY` (`.env`, fuera de Git,
mismo criterio que `DJANGO_SECRET_KEY`/`DB_PASSWORD`) o en un gestor de
secretos de plataforma en producción."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class EncryptionUnavailableError(Exception):
    """`openssl` no está disponible en este entorno — el backup se deja
    SIN cifrar y se documenta así explícitamente (nunca se finge un
    cifrado que no ocurrió)."""


class EncryptionFailedError(Exception):
    pass


def openssl_available() -> bool:
    return shutil.which("openssl") is not None


def encrypt_file(source_path: Path, output_path: Path, passphrase: str) -> Path:
    if not openssl_available():
        raise EncryptionUnavailableError("openssl no está disponible en PATH.")
    if not passphrase:
        raise EncryptionFailedError("BACKUP_ENCRYPTION_KEY vacío — no se puede cifrar.")
    result = subprocess.run(
        [
            "openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
            "-pass", "stdin",
            "-in", str(source_path),
            "-out", str(output_path),
        ],
        input=passphrase.encode("utf-8"),
        capture_output=True,
    )
    if result.returncode != 0:
        # stderr de openssl no incluye la contraseña (se pasó por stdin,
        # nunca como argumento), pero igual se recorta por prudencia.
        stderr_text = result.stderr.decode("utf-8", errors="replace")[:500]
        raise EncryptionFailedError(f"openssl enc falló (exit={result.returncode}): {stderr_text}")
    return output_path


def decrypt_file(source_path: Path, output_path: Path, passphrase: str) -> Path:
    if not openssl_available():
        raise EncryptionUnavailableError("openssl no está disponible en PATH.")
    result = subprocess.run(
        [
            "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
            "-pass", "stdin",
            "-in", str(source_path),
            "-out", str(output_path),
        ],
        input=passphrase.encode("utf-8"),
        capture_output=True,
    )
    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")[:500]
        raise EncryptionFailedError(f"openssl enc -d falló (exit={result.returncode}): {stderr_text}")
    return output_path
