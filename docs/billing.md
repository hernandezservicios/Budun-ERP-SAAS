# SaaS Billing (especificación)

> **Estado: ESPECIFICACIÓN, no implementación.** Diseño aprobado para
> FASE 17 — ningún modelo, campo ni migración se crea a partir de este
> documento. Detalle completo en
> `docs/phases/PHASE-17-billing-saas.md`.

Billing de la **suscripción del tenant al SaaS** — lo que un `Tenant`
le debe a Budun ERP por usar la plataforma. Planes, período de prueba,
suscripciones, estados, sincronización con PayPal (FASE 16), flujo de
cancelación y límites por plan.

## Separación obligatoria de Cuentas por Cobrar del ERP

**Nunca se mezcla** con lo que un `Customer` le debe a un `Tenant`
(`apps.sales`: `Payment`/`PaymentAllocation`/`CreditNote`, FASE 10/11)
— son ejes ortogonales:

| | ERP Accounts Receivable | SaaS Billing |
|---|---|---|
| Qué es | Lo que un CLIENTE le debe a un TENANT | Lo que un TENANT le debe a Budun ERP |
| Modelos | `Customer`, `Sale`, `Payment`, `PaymentAllocation`, `CreditNote` (construidos) | `Tenant`, `Plan`, `Subscription` (esta fase) |

Ver `docs/phases/PHASE-17-billing-saas.md` para el razonamiento
completo. Si en el futuro se quisiera un plan de Billing basado en el
volumen de ventas/cuentas por cobrar de un tenant (métrica de uso),
sería una agregación de solo lectura sobre `apps.sales`, nunca una
relación estructural directa entre `Subscription` y `Customer`.

## Alcance previsto

- `Plan`: nombre, precio, límites (usuarios, cajas, productos, etc.
  — a definir con datos reales, mismo criterio que
  `apps.core.pricing` en FASE 6: nunca un precio inventado sin
  decisión de negocio real).
- `Subscription`: `tenant` → `plan`, estado (trial/activa/vencida/
  cancelada), fechas, sincronización con PayPal Subscriptions.
- Flujo de cancelación y qué ocurre con los datos del tenant al
  cancelar (fuera de alcance decidir aquí — requiere una política de
  retención explícita del usuario cuando llegue la fase).

## Qué NO se construye con este documento

Ningún modelo (`Plan`, `Subscription`), ninguna integración con
PayPal, ningún límite de plan aplicado. Ver
`docs/phases/PHASE-17-billing-saas.md` para el checklist completo de
la fase.
