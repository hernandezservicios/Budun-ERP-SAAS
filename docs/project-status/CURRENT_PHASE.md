# Estado actual del proyecto

```text
Fase actual: 3
Estado: PASS (cerrada, pendiente de autorización para FASE 4)
Última fase cerrada: FASE 3 — Multi-Tenancy
Próxima acción: esperar autorización explícita del usuario para iniciar FASE 4 — Authentication
```

## Regla
Claude debe actualizar este archivo al inicio y al cierre de cada fase.

## Resumen de FASE 3
Se introdujo el Custom User Model (`accounts.User`, `AUTH_USER_MODEL`), la app `tenants` (modelos `Tenant` y `Membership`), el mecanismo de "Tenant Context" (`contextvars`), `TenantMiddleware` (determina el tenant activo del usuario autenticado, nunca del frontend), `TenantManager`/`TenantQuerySet`/`TenantScopedModel` (aislamiento automático para futuros modelos de negocio desde FASE 8), controles de autorización por rol (`require_tenant`/`require_role`), una capa de servicios de ejemplo y un modelo de referencia (`IsolationSample`, no es una entidad de negocio) usado exclusivamente por las pruebas. Requirió resetear el esquema `public` de `erp_saas_dev` (vacío, sin datos reales, confirmado por el usuario) para poder fijar `AUTH_USER_MODEL` antes de la primera migración. 19/19 tests OK (16 nuevos de aislamiento + 3 de FASE 1), incluyendo Tenant A/Tenant B con datos privados verificados como no accesibles entre sí, a nivel de manager, servicio y vista HTTP completa. `manage.py check` en verde. Smoke test HTTP real OK. Arquitectura documentada en `docs/multi-tenancy.md`. Ningún módulo de negocio (POS, ventas, inventario, API, PayPal, Billing) fue construido.
