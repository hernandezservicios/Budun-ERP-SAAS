# FASE 0 — Auditoría del entorno

## Objetivo
Detectar Windows, Python, pip, Git, Node/npm, PostgreSQL, pgAdmin 4, puertos, servicios, permisos y carpeta del proyecto. No Docker.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] Entorno documentado
- [x] PostgreSQL accesible (servicio `postgresql-x64-18` en ejecución, puerto 5432 en escucha, `psql 18.6` funcional)
- [x] pgAdmin 4 abre — binario instalado y localizado; **apertura visual pendiente de confirmación del usuario** (app gráfica)
- [x] Git disponible (2.55.0, repo ya inicializado en `main`, sin commits)
- [x] Python disponible (3.14.4, único intérprete instalado)
- [x] No se requiere Docker (no hay Dockerfile/docker-compose; Docker Desktop existe en el sistema pero no se usa en el proyecto)

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde. — N/A: aún no existe proyecto Django (corresponde a FASE 1).
- [ ] Tests relevantes ejecutados. — N/A: no hay código de aplicación todavía.
- [x] Smoke test realizado cuando aplique. — Se verificó conexión TCP al puerto 5432 y ejecución real de `psql --version`; se confirmó por `pip download` (sin instalar) que las dependencias de `requirements.txt` tienen ruedas compatibles con Python 3.14 en Windows.
- [x] Seguridad revisada para el alcance de la fase. — `pg_hba.conf` usa `scram-sha-256` (no `trust`); no se expusieron ni solicitaron credenciales; no se commiteó ningún secreto.
- [x] Documentación actualizada. — Este archivo, `CURRENT_PHASE.md`, `PHASE_HISTORY.md` y `KNOWN_ISSUES.md`.
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Commit de cierre de FASE 0 (ver historial de Git).

## Evidencia (FASE 0)
- SO: Windows 10 Pro (10.0.19045).
- Python: 3.14.4 (`C:\Python314\python.exe`), pip 26.0.1.
- Git: 2.55.0.windows.3; repo local ya inicializado (`main`, 0 commits); `user.name`/`user.email` globales configurados.
- Node: v25.9.0; npm: 11.12.1.
- PostgreSQL: versión 18.6, instalado en `C:\Program Files\PostgreSQL\18`; servicio `postgresql-x64-18` = Running/Automatic; puerto 5432 en escucha (IPv4/IPv6); autenticación `scram-sha-256` en `pg_hba.conf`.
- pgAdmin 4: instalado junto con PostgreSQL 18; ejecutable en `...\pgAdmin 4\runtime\pgAdmin4.exe`; perfiles previos detectados en `%APPDATA%`.
- Entorno virtual: no existe todavía (`.venv`/`venv` no encontrados) — se creará en FASE 1.
- Estructura del proyecto: solo archivos de kit/documentación (`CLAUDE.md`, `AGENTS.md`, `ARCHITECTURE.md`, `KIT-MANIFEST.md`, `README.md`, `docs/`, `scripts/`, `.claude/`, `.github/`, `.mcp.json`, `.env.example`, `.gitignore`, `requirements.txt`); sin `manage.py` ni apps Django.
- Corrección aplicada: se agregó `C:\Program Files\PostgreSQL\18\bin` al PATH de usuario (registro, sin `setx`) para que `psql` esté disponible en nuevas terminales.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 1 — Project Foundation.
