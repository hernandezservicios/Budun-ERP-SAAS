# FASE 1 — Project Foundation

## Objetivo
Crear virtualenv, Django base, settings, requirements, CLAUDE.md integration, Git structure, env example, base templates and test runner. Solo foundation, sin construir módulos futuros.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] Django check pasa
- [x] virtualenv funciona (`.venv`, Python 3.14.4, dependencias de `requirements.txt` instaladas)
- [x] Git inicializado (ya lo estaba desde FASE 0)
- [x] env example existe (`.env.example`; además se creó `.env` local no commiteado)
- [x] proyecto arranca (ver nota sobre PostgreSQL vs. smoke test temporal más abajo)

## Verificación
- [x] `python manage.py check` o la validación equivalente está en verde. — "System check identified no issues (0 silenced)."
- [x] Tests relevantes ejecutados. — `python manage.py test`: 3/3 OK (`apps/core/tests.py`, `SimpleTestCase`).
- [x] Smoke test realizado cuando aplique. — `runserver` con la configuración oficial (PostgreSQL) falla porque `erp_saas_app`/`erp_saas_dev` aún no existen (FASE 2). Se hizo un smoke test end-to-end **temporal y explícito con SQLite** (permitido por CLAUDE.md solo como herramienta de prueba puntual, nunca como base oficial): HTTP 200 en `/`, HTML en español correcto. El archivo SQLite temporal se eliminó al terminar la prueba.
- [x] Seguridad revisada para el alcance de la fase. — `SECRET_KEY` real generado y fuera de Git (`.env` en `.gitignore`); `DEBUG`/`ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` leídos desde entorno; cookies seguras condicionadas a `DEBUG=False`; `X_FRAME_OPTIONS=DENY`; `SECURE_CONTENT_TYPE_NOSNIFF=True`; sin uso de Django Admin como UI principal (se deja disponible solo como herramienta interna).
- [x] Documentación actualizada. — Este archivo, `CURRENT_PHASE.md`, `PHASE_HISTORY.md`, `KNOWN_ISSUES.md`.
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Commit de cierre de FASE 1 (ver historial de Git).

## Evidencia (FASE 1)
- Estructura creada: `manage.py`, `config/` (settings, urls, wsgi, asgi), `apps/core/` (apps.py, views.py, urls.py, tests.py, template `home.html`), `templates/base.html`, `static/css/base.css`.
- `.venv` creado con `python -m venv .venv`; `pip install -r requirements.txt` exitoso (Django 5.2.17, psycopg 3.3.4 + psycopg-binary, djangorestframework 3.18.0, python-dotenv 1.2.3, gunicorn 23.0.0).
- `.env` local generado con `SECRET_KEY` real (vía `get_random_secret_key()`), `DB_PASSWORD=change-me` como placeholder intencional hasta FASE 2. No commiteado (ver `.gitignore`).
- `python manage.py check` → sin errores.
- `python manage.py test` → 3/3 tests OK.
- Smoke test HTTP real (SQLite temporal, puerto 8010): `GET /` → `200`, contenido `"Fundación del proyecto lista"` en español, confirmado y luego eliminado.
- Solo se creó la app `core` (fundación); ninguna app de negocio (productos, ventas, POS, etc.) fue creada, respetando la construcción incremental.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 2 — PostgreSQL Foundation.
