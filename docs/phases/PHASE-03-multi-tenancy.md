# FASE 3 — Multi-Tenancy

## Objetivo
Custom User, Tenant, membership, tenant context, managers/querysets y aislamiento de datos.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] A/B isolation tests pasan — 16 tests en `apps/tenants/tests.py`, todos OK.
- [x] backend determina tenant — `TenantMiddleware`; nunca se lee `tenant_id` del frontend (verificado explícitamente en tests).
- [x] queries tenant-aware — `TenantScopedModel`/`TenantManager`/`TenantQuerySet`.

## Verificación
- [x] `python manage.py check` o la validación equivalente está en verde.
- [x] Tests relevantes ejecutados. — 19/19 (`manage.py test`): 16 de aislamiento multi-tenant + 3 de FASE 1.
- [x] Smoke test realizado cuando aplique. — `GET /` → 200 tras los cambios de FASE 3.
- [x] Seguridad revisada para el alcance de la fase. — Ver `docs/multi-tenancy.md`: el middleware nunca lee tenant_id del cliente; una sesión manipulada hacia otro tenant se descarta y se recalcula; `all_objects` es una vía de escape explícita, nunca usada en servicios/vistas; roles mínimos (`OWNER`/`MEMBER`) con `require_role`.
- [x] Documentación actualizada. — `docs/multi-tenancy.md` (arquitectura completa + evidencia), `CURRENT_PHASE.md`, `PHASE_HISTORY.md`, `KNOWN_ISSUES.md`.
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Commit de cierre de FASE 3 (ver historial de Git).

## Evidencia (FASE 3)
- Apps creadas: `apps/accounts` (Custom User Model) y `apps/tenants` (`Tenant`, `Membership`, `TenantScopedModel`, `TenantManager`, `TenantMiddleware`, `permissions.py`, `services.py`, `views.py`, `tests.py`).
- Reset confirmado por el usuario del esquema `public` (vacío, sin datos reales) para fijar `AUTH_USER_MODEL` antes de la primera migración.
- `python manage.py makemigrations accounts tenants` + `migrate`: aplicado sin errores.
- Tablas verificadas en `erp_saas_dev`: `accounts_user(_groups/_user_permissions)`, `tenants_tenant`, `tenants_membership`, `tenants_isolationsample`, más las estándar de Django (ya no `auth_user`).
- `python manage.py test`: **19/19 OK**, incluyendo Tenant A / Tenant B con datos privados (`IsolationSample`) verificados como no accesibles entre sí a nivel de manager (`objects` vs `all_objects`), servicio (`services.py`), y vista HTTP completa (`views.whoami_view` a través de `TenantMiddleware`).
- Verificado explícitamente: un `tenant_id` en la querystring se ignora por completo; una sesión manipulada hacia el tenant de otro usuario se descarta; un usuario sin membresía o no autenticado nunca obtiene un tenant.
- Autorización por rol probada: `require_role` permite al `OWNER` y bloquea a un `MEMBER` para la misma acción.
- Ningún módulo de negocio (POS, ventas, inventario, API, PayPal, Billing) fue creado. `IsolationSample` es un modelo de referencia interno, no una entidad de negocio (ver `docs/multi-tenancy.md`).

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 4 — Authentication.
