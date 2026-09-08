"""Backup y restore reales de PostgreSQL (FASE 20, secciones 3, 5, 27).

Primitivas de bajo nivel — la orquestación completa (checksum,
metadata, cifrado, copia off-site, retención, registro de
`BackupRun`) vive en `services.jobs`, que es lo que los comandos de
gestión (`management/commands/`) invocan.

Seguridad: la contraseña de la base de datos SOLO viaja por la
variable de entorno `PGPASSWORD` del subproceso — nunca como
argumento de línea de comandos (visible en la lista de procesos del
sistema operativo) y nunca en un log. `_sanitize_output` es una
segunda capa de defensa sobre la salida capturada de `pg_dump`/
`pg_restore`, aunque ninguno de los dos imprime la contraseña en
circunstancias normales."""

from __future__ import annotations

import dataclasses
import datetime as dt
import locale
import os
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql

from . import disk as disk_service

# Marcador obligatorio en cualquier nombre de base sobre el que este
# módulo tiene permitido ejecutar CREATE DATABASE / DROP DATABASE —
# guarda de seguridad explícita para que un error de programación
# nunca pueda soltar la base principal de desarrollo/producción (ver
# `docs/phases/PHASE-20-backups.md` sección 5: "Nunca destruir la base
# principal de desarrollo para probar restore").
RESTORE_DB_MARKER = "_restorecheck_"


class BackupFailedError(Exception):
    pass


class RestoreFailedError(Exception):
    pass


class UnsafeDatabaseNameError(Exception):
    pass


@dataclasses.dataclass
class DumpResult:
    dump_path: Path
    size_bytes: int
    duration_seconds: float


@dataclasses.dataclass
class RestoreResult:
    database_name: str
    duration_seconds: float
    exit_code: int = 0
    stderr_excerpt: str = ""


def _decode_subprocess_output(raw: bytes) -> str:
    """`pg_dump`/`pg_restore` emiten UTF-8 en Linux (producción) pero la
    consola de Windows (desarrollo) suele entregar bytes en la
    codificación ANSI del sistema (`cp1252`/similar) cuando el
    subproceso escribe a un pipe redirigido — se intenta UTF-8 primero
    (correcto en producción) y se cae a la codificación preferida del
    sistema antes de recurrir a reemplazar caracteres, para que un
    mensaje de error con acentos siga siendo legible en el reporte."""
    for encoding in ("utf-8", locale.getpreferredencoding(False)):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _sanitize_output(raw: bytes, *, secrets: tuple[str, ...] = ()) -> str:
    sanitized = _decode_subprocess_output(raw)
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "***")
    return sanitized[:2000]


def isolated_database_name(source_db_name: str, moment: dt.datetime | None = None) -> str:
    moment = moment or dt.datetime.now()
    return f"{source_db_name}{RESTORE_DB_MARKER}{moment.strftime('%Y%m%d%H%M%S')}"


def _require_safe_isolated_name(name: str) -> None:
    if RESTORE_DB_MARKER not in name:
        raise UnsafeDatabaseNameError(
            f"Rechazado por seguridad: '{name}' no contiene el marcador de base "
            f"aislada de restore ('{RESTORE_DB_MARKER}') — este módulo nunca opera "
            "(crear/soltar) sobre una base que no fue generada explícitamente por "
            "él para una verificación de restore."
        )


def _admin_conninfo(db_settings: dict, dbname: str) -> str:
    return psycopg.conninfo.make_conninfo(
        dbname=dbname,
        user=db_settings["USER"],
        password=db_settings.get("PASSWORD") or "",
        host=db_settings.get("HOST") or "127.0.0.1",
        port=str(db_settings.get("PORT") or "5432"),
    )


def get_postgres_version(db_settings: dict) -> str:
    with psycopg.connect(_admin_conninfo(db_settings, db_settings["NAME"]), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW server_version")
            (version,) = cur.fetchone()
    return version


def create_isolated_database(db_settings: dict, new_name: str) -> None:
    _require_safe_isolated_name(new_name)
    with psycopg.connect(_admin_conninfo(db_settings, db_settings["NAME"]), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(new_name)))


def drop_isolated_database(db_settings: dict, name: str) -> None:
    _require_safe_isolated_name(name)
    with psycopg.connect(_admin_conninfo(db_settings, db_settings["NAME"]), autocommit=True) as conn:
        with conn.cursor() as cur:
            # Cierra cualquier conexión abierta contra la base aislada
            # (p.ej. una verificación que dejó una conexión de Django
            # colgando) antes de soltarla — DROP DATABASE falla si
            # existen conexiones activas.
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (name,),
            )
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def run_pg_dump(db_settings: dict, output_path: Path) -> DumpResult:
    """`pg_dump` en formato `custom` (`-F c`) — soporta restore
    selectivo y compresión nativa, el formato recomendado por la propia
    documentación oficial de PostgreSQL para backups que se van a
    restaurar con `pg_restore` (a diferencia del formato plano `.sql`,
    pensado para inspección humana, no para operaciones)."""
    import time

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    disk_service.ensure_sufficient_disk_space(output_path.parent)

    env = dict(os.environ)
    env["PGPASSWORD"] = db_settings.get("PASSWORD") or ""

    command = [
        "pg_dump",
        "-h", str(db_settings.get("HOST") or "127.0.0.1"),
        "-p", str(db_settings.get("PORT") or "5432"),
        "-U", db_settings["USER"],
        "-d", db_settings["NAME"],
        "-F", "c",
        "-f", str(output_path),
    ]

    started = time.perf_counter()
    result = subprocess.run(command, env=env, capture_output=True)
    duration = time.perf_counter() - started

    if result.returncode != 0 or not output_path.exists():
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass
        stderr_text = _sanitize_output(
            result.stderr, secrets=(env["PGPASSWORD"],)
        )
        raise BackupFailedError(f"pg_dump falló (exit={result.returncode}): {stderr_text}")

    return DumpResult(dump_path=output_path, size_bytes=output_path.stat().st_size, duration_seconds=duration)


def run_pg_restore(dump_path: Path, db_settings: dict, target_db_name: str) -> RestoreResult:
    """Restaura `dump_path` (formato `custom`) en `target_db_name`, que
    DEBE existir ya (ver `create_isolated_database`) y estar vacía."""
    import time

    _require_safe_isolated_name(target_db_name)

    env = dict(os.environ)
    env["PGPASSWORD"] = db_settings.get("PASSWORD") or ""

    command = [
        "pg_restore",
        "-h", str(db_settings.get("HOST") or "127.0.0.1"),
        "-p", str(db_settings.get("PORT") or "5432"),
        "-U", db_settings["USER"],
        "-d", target_db_name,
        "--no-owner", "--no-privileges",
        str(dump_path),
    ]

    started = time.perf_counter()
    result = subprocess.run(command, env=env, capture_output=True)
    duration = time.perf_counter() - started

    # pg_restore puede devolver un código distinto de cero por
    # advertencias no fatales (p. ej. objetos que ya no aplican con
    # --no-owner); se valida el resultado REAL contando tablas en
    # `services.verification`, nunca solo el exit code — pero un
    # backup corrupto/truncado sí produce errores fatales que se
    # reportan aquí.
    stderr_text = _sanitize_output(
        result.stderr, secrets=(env["PGPASSWORD"],)
    )
    # Solo se considera fallo DURO si ninguna tabla llegó a crearse — se
    # verifica en la capa de orquestación (`services.jobs`), que decide
    # si el restore fue exitoso a partir de `services.verification`,
    # nunca solo de este exit code (sección 6 de la especificación).
    return RestoreResult(
        database_name=target_db_name,
        duration_seconds=duration,
        exit_code=result.returncode,
        stderr_excerpt=stderr_text if result.returncode != 0 else "",
    )
