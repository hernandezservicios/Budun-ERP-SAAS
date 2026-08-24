# FASE 2 — PostgreSQL Foundation

## Objetivo
Configurar PostgreSQL local y Django; crear DB/usuario; verificar desde pgAdmin; migrations; conexión y persistencia.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] Django conecta a PostgreSQL — usuario creó `erp_saas_dev`/`erp_saas_app` en pgAdmin 4; `.env` configurado; conexión verificada con `manage.py migrate`.
- [x] migrations pasan — 18 migraciones estándar (`admin`, `auth`, `contenttypes`, `sessions`) aplicadas sin errores.
- [x] pgAdmin muestra tablas — verificado por Claude vía `information_schema.tables` (10 tablas esperadas); confirmación visual directa en pgAdmin queda como paso opcional del usuario (ver `KNOWN_ISSUES.md`).
- [ ] backup/restore de prueba documentado — **diferido a FASE 20 (Backups)**, que es la fase dedicada a esto; no corresponde al alcance de "PostgreSQL Foundation" (ver `docs/phases/PHASE-20-backups.md`).

## Verificación
- [x] `python manage.py check` o la validación equivalente está en verde.
- [x] Tests relevantes ejecutados. — `manage.py test`: 3/3 OK, usando `TestCase` real (crea/destruye BD de pruebas en PostgreSQL).
- [x] Smoke test realizado cuando aplique. — `runserver` con la configuración oficial (PostgreSQL, sin SQLite): `GET /` → 200.
- [x] Seguridad revisada para el alcance de la fase. — `pg_hba.conf` en `scram-sha-256`; rol de aplicación sin `SUPERUSER`; contraseña real solo en `.env` (no commiteada, nunca solicitada ni mostrada en el chat); rol de mantenimiento (`postgres`) usado únicamente por el usuario desde pgAdmin, nunca por Django.
- [x] Documentación actualizada. — `docs/postgresql.md` (configuración real de conexión, sin contraseña), `CURRENT_PHASE.md`, `PHASE_HISTORY.md`, `KNOWN_ISSUES.md`.
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Commit de cierre de FASE 2 (ver historial de Git).

## Evidencia (FASE 2)
- `erp_saas_dev` y `erp_saas_app` creados por el usuario en pgAdmin 4 (Query Tool), incluida la contraseña real de `erp_saas_app`, nunca compartida por chat.
- `.env` actualizado localmente por el usuario con `DB_PASSWORD` real (archivo no commiteado).
- `python manage.py migrate` → 18 migraciones aplicadas (`contenttypes`, `auth`, `admin`, `sessions`).
- `python manage.py check` → sin errores.
- `python manage.py test` → 3/3 OK contra una base de datos de pruebas PostgreSQL real (`test_erp_saas_dev`), creada y destruida automáticamente (requirió otorgar `CREATEDB` al rol de aplicación, corregido durante la fase).
- Smoke test HTTP real: `GET http://127.0.0.1:8020/` → `200`, contenido en español, usando la configuración oficial (PostgreSQL), sin SQLite.
- Tablas confirmadas en `erp_saas_dev` (esquema `public`): `auth_group`, `auth_group_permissions`, `auth_permission`, `auth_user`, `auth_user_groups`, `auth_user_user_permissions`, `django_admin_log`, `django_content_type`, `django_migrations`, `django_session`.
- Configuración de conexión completa documentada en `docs/postgresql.md` (host, puerto, base, rol de aplicación, tipo de autenticación) — sin exponer la contraseña en ningún archivo del repositorio.
- Ninguna app ni tabla de negocio creada; solo las tablas estándar de Django.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 3 — Multi-Tenancy.
