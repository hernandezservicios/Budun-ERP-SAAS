# FASE 4 — Authentication

## Objetivo
Registro, login, logout, recuperación, perfil, sesiones y onboarding.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] Flujos auth pasan — registro, login, logout, recuperación y cambio de contraseña, todos con tests HTTP reales en verde.
- [x] permisos base pasan — `LoginRequiredMixin` en onboarding/perfil/cambio de contraseña; protecciones Multi-Tenant de FASE 3 (`require_tenant`/`require_role`, fail-closed) sin modificar.
- [x] onboarding crea tenant correctamente — creación transaccional (`transaction.atomic`) de `Tenant` + `Membership` con rol `OWNER`, slug único desambiguado automáticamente.

## Verificación
- [x] `python manage.py check` o la validación equivalente está en verde.
- [x] Tests relevantes ejecutados. — 45/45 (`manage.py test`): 3 FASE 1 + 16 FASE 3 (sin cambios de lógica) + 26 nuevos de FASE 4.
- [x] Smoke test realizado cuando aplique. — `GET` real de `/`, `/cuentas/registro/`, `/cuentas/login/`, `/cuentas/perfil/` (redirige), `/cuentas/password/reset/`, `/cuentas/password/cambiar/` (redirige).
- [x] Seguridad revisada para el alcance de la fase. — Ver `docs/authentication.md`: email único normalizado, `AUTH_PASSWORD_VALIDATORS` aplicados en registro/cambio/recuperación, mensaje de login genérico (no revela si el email existe), mismo mensaje de "correo enviado" exista o no la cuenta, tokens de un solo uso con expiración (vistas integradas de Django), sesión se mantiene tras cambio de contraseña, ningún endpoint acepta `tenant_id` del cliente.
- [x] Documentación actualizada. — `docs/authentication.md` (nuevo, arquitectura completa), `CURRENT_PHASE.md`, `PHASE_HISTORY.md`, `KNOWN_ISSUES.md`.
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Dos commits de funcionalidad (`dd6d374`, `8671135`) más el de cierre de fase (ver historial de Git).

## Evidencia (FASE 4)
- `accounts.User`: login por email (`username` eliminado, 0 usuarios reales antes del cambio, sin pérdida de datos).
- Registro → autentica inmediatamente → onboarding; login existente redirige a perfil (si ya tiene tenant) u onboarding (si no); logout invalida la sesión.
- Bug real encontrado y corregido: `request.tenant` no sirve para decidir el redirect post-login (se calcula antes de que la vista autentique); corregido con consulta fresca a `Membership`.
- Recuperación/cambio de contraseña con las vistas integradas de Django; verificado con tests que el flujo completo permite iniciar sesión con la nueva contraseña y que un token inválido es rechazado.
- Protecciones Multi-Tenant de FASE 3 preservadas sin cambios de lógica (Tenant Context, managers/querysets tenant-aware, fail-closed, sin `tenant_id` del cliente, sin `all_objects` en vistas, `IsolationSample` solo como soporte de pruebas) — confirmado explícitamente en `docs/authentication.md`.
- 2 tests nuevos de regresión Multi-Tenant vía HTTP real (registro/login/onboarding de dos usuarios distintos, cada uno aislado del otro; intento de manipular la sesión hacia el tenant ajeno, descartado).
- Ningún módulo de negocio (POS, ventas, inventario, API, PayPal, Billing) fue creado. El Design System completo (layout, sidebar, componentes reutilizables) queda para FASE 5; las plantillas de esta fase son mínimas y sobrias.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 5 — Design System.
