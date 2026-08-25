# PayPal (especificación)

> **Estado: ESPECIFICACIÓN, no implementación.** Diseño aprobado para
> FASE 16 — ningún campo, modelo ni integración se crea a partir de
> este documento. Detalle completo en
> `docs/phases/PHASE-16-paypal-sandbox.md`.

Sandbox primero, luego Production. La integración debe seguir
documentación oficial vigente de PayPal (nunca inventar endpoints,
argumentos o herramientas MCP). Separar el Payment Service de la UI:
`Django → Payment Service → PayPal`, sin acoplar `Sale`/`Payment`
(`apps.sales`) a PayPal directamente.

## Integración con el motor de pagos ya construido (FASE 10/11)

`Payment.method` ya es extensible (`CASH`/`CARD`/`TRANSFER`/`OTHER`)
precisamente para esto. Un webhook de PayPal verificado debe llamar a
`apps.sales.services.create_payment`/`record_payment_for_sale`/
`apply_payment_to_sales` — nunca escribir `Payment` directamente. La
`idempotency_key` que ya existe en `Payment` (usando el ID de
transacción de PayPal como clave) es exactamente el mecanismo para que
un webhook reintentado nunca duplique el pago.

## Campos de reconciliación (preparación, sin agregarlos todavía)

Cuando esta fase integre un proveedor real, `Payment` necesitará:
`external_id` (ID de transacción del proveedor), `provider`
(extensible, mismo patrón que `PaymentMethod`), `provider_status`
(puede diferir de `Payment.status` mientras se reconcilia). Ninguno
existe hoy — mismo principio de "nunca una columna sin uso real hoy"
aplicado desde FASE 8.

## Refunds

`Refund.status` ya prevé `PENDING`/`FAILED` (no solo `COMPLETED`) para
un reembolso asíncrono de PayPal — usar esos estados, nunca un campo
paralelo. `apps.sales.services.convert_refund_to_credit` (FASE 11)
sigue siendo la vía si el negocio prefiere ofrecer crédito en vez de
devolver dinero por PayPal.

## Webhooks

Verificación de firma obligatoria (documentación oficial vigente).
Reconciliación: un webhook debe poder confirmar/actualizar un
`Payment`/`Refund` existente por `idempotency_key`/`external_id`,
nunca crear un segundo registro paralelo cuando el evento llega
duplicado o fuera de orden.

## MCP

MCP es una herramienta del entorno de agente/desarrollo/operaciones,
no un sustituto del backend de pagos — el flujo real de cobro nunca
depende de que el agente esté disponible.

## Moneda (sincronización posterior a FASE 12, especificación — ver `docs/currency.md`)

Cuando esta fase integre PayPal real, debe usar la moneda del
`Payment`/documento cuando sea compatible con lo que PayPal soporta —
nunca hardcodear una sola moneda en la integración. Mantener, junto con
los campos de reconciliación ya previstos arriba (`external_id`/
`provider`/`provider_status`): `provider_currency` (la moneda que
PayPal reporta para la transacción, que puede diferir de
`Payment.currency` si hubo conversión del lado del proveedor) y
`provider_amount` (el monto exacto que PayPal procesó, en su moneda) —
ninguno existe hoy, mismo principio de "nunca una columna sin uso real"
ya aplicado en este documento. Idempotencia, webhook y `external_id`
siguen exactamente igual (ver arriba).

## Qué NO se construye con este documento

Ninguna integración real, ningún campo en `Payment`/`Refund`, ningún
webhook. Ver `docs/phases/PHASE-16-paypal-sandbox.md` para el
checklist completo de la fase.
