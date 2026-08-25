# Estado actual del proyecto

```text
Fase actual: 4
Estado: PASS (cerrada, pendiente de autorización para FASE 5)
Última fase cerrada: FASE 4 — Authentication
Próxima acción: esperar autorización explícita del usuario para iniciar FASE 5 — Design System
```

## Regla
Claude debe actualizar este archivo al inicio y al cierre de cada fase.

## Resumen de FASE 4
Se implementó el ciclo completo de autenticación sobre el Custom User Model de FASE 3: login por correo electrónico (se eliminó `username`, verificado 0 usuarios reales antes del cambio), registro, logout, recuperación y cambio de contraseña (reutilizando las vistas integradas de Django), perfil editable, y onboarding con creación **transaccional** de `Tenant` + `Membership` (rol `OWNER`). Se preservaron intactas todas las protecciones Multi-Tenant de FASE 3 (Tenant Context, managers/querysets tenant-aware, fail-closed, prohibición de `tenant_id` desde el cliente, `all_objects` fuera de vistas de negocio, `IsolationSample` solo como soporte de pruebas) — documentado explícitamente en `docs/authentication.md`. 45/45 tests OK (incluyendo los 16 de FASE 3 sin cambios de lógica, y 2 nuevos de regresión Multi-Tenant que ejercitan el aislamiento vía el flujo HTTP real de registro/login/onboarding). `manage.py check` en verde. Smoke tests HTTP reales de todas las páginas nuevas. Ningún módulo de negocio (POS, ventas, inventario, API, PayPal, Billing) fue construido; el Design System completo queda para FASE 5.
