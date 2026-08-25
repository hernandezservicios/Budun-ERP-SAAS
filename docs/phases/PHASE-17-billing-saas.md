# FASE 17 — Billing SaaS

## Objetivo
Planes, suscripciones, estados, límites y sincronización con PayPal.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] tenant→plan→subscription
- [ ] limits
- [ ] status sync
- [ ] cancel flow

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 10 — Revisado, sin cambios de diseño necesarios

FASE 10 agregó el motor comercial de los TENANTS (`apps/sales`, ventas
de cada empresa cliente del SaaS) — conceptualmente distinto del
Billing del propio SaaS (lo que Budun ERP le cobra a cada tenant por
usar la plataforma). Revisado explícitamente: no hay ninguna relación
directa; esta fase no necesita consumir `apps.sales`. Si en el futuro
se quisiera facturar a un tenant basándose en su volumen de ventas
(p. ej. un plan por transacción), sería una agregación de solo lectura
sobre `Sale`/`Payment`, nunca una dependencia estructural.

## Nota de sincronización — Cuentas por Cobrar del ERP vs. Billing del SaaS (separación obligatoria)

Sincronización de doctrina previa a FASE 11, reafirmando explícitamente
la nota anterior ahora que el ERP tiene un dominio de cuentas por
cobrar más rico (`Payment`/`PaymentAllocation`/`CustomerCreditLedger`/
`CreditNote`, ver `docs/accounts-receivable.md`): **estos dos dominios
nunca deben mezclarse**, ni conceptual ni técnicamente:

| | ERP Accounts Receivable | SaaS Billing |
|---|---|---|
| Qué es | Lo que un CLIENTE le debe a un TENANT (una empresa usando el ERP) | Lo que un TENANT le debe a Budun ERP (el SaaS) por usar la plataforma |
| Modelos | `Customer`, `Sale`, `Payment`, `PaymentAllocation`, `CustomerCreditLedger`, `CreditNote` | `Tenant`, `Plan`, `Subscription` (esta fase) |
| Saldo | Saldo a favor / pendiente de un `Customer` | Estado de la suscripción de un `Tenant` |

**Nunca** debe existir un campo, modelo o consulta que combine el
"saldo de un cliente" de un tenant con la "suscripción del tenant" —
son ejes ortogonales. Si en el futuro se quisiera un plan de Billing
basado en el volumen de cuentas por cobrar de un tenant (métrica de
uso, no un acoplamiento estructural), sería una agregación de solo
lectura sobre `apps.sales`/`apps.accounts_receivable` (cuando exista),
nunca una relación directa entre `Subscription` y `Customer`.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
