# FASE 16 — PayPal Sandbox

## Objetivo
Integración PayPal Sandbox mediante service layer; Orders/Payments/Subscriptions/Webhooks según alcance. Configurar MCP con documentación oficial vigente. Ver `docs/paypal.md` para el resumen arquitectónico.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] Sandbox funciona
- [ ] webhooks verifican
- [ ] idempotencia
- [ ] secrets fuera de Git

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 10 — Interfaz de Pagos a consumir sin acoplar `Sale` a PayPal

FASE 10 preparó explícitamente `apps.sales.services` (`create_payment`/
`record_payment_for_sale`/`allocate_payment`) como el único punto de
entrada para registrar y aplicar un pago (ver `docs/payments.md`), con
`Payment.method` extensible (`CASH`/`CARD`/`TRANSFER`/`OTHER`)
precisamente para no acoplar `Sale`/`Payment` a ningún proveedor
concreto. Esta fase debe:

- Agregar el flujo `Django → Payment Service → PayPal` (o equivalente)
  como una capa que, al confirmar un pago de PayPal (vía webhook
  verificado), llame a `services.record_payment_for_sale(sale, method=...,
  amount=..., idempotency_key=<id de la transacción de PayPal>, ...)`
  (o `services.create_payment`/`apply_payment_to_sales` si el webhook
  debe cubrir varias facturas a la vez) — la `idempotency_key` ya
  existente es exactamente el mecanismo pensado para que un webhook
  reintentado nunca duplique el pago. Ver `docs/payments.md` para el
  ledger `Payment`/`PaymentAllocation` sobre el que se construye esto.
- `Refund.status` ya prevé `PENDING`/`FAILED` (no solo `COMPLETED`) para
  cuando un reembolso de PayPal sea asíncrono — usarlos en vez de
  agregar un campo de estado paralelo.
- Nunca registrar un pago directamente en `Payment` desde el código de
  integración con PayPal: siempre a través de
  `apps.sales.services.create_payment`/`record_payment_for_sale`/
  `apply_payment_to_sales`/`record_refund`.

## Nota de sincronización — Preparación de campos, sin agregarlos todavía

Sincronización de doctrina previa a FASE 11, sin implementación nueva:
cuando esta fase integre un proveedor real, `Payment` necesitará
campos de reconciliación que **hoy no existen y no se agregan con este
documento** (mismo principio de "nunca una columna sin uso real hoy"
aplicado desde FASE 8):

- `external_id` (ID de la transacción en el proveedor).
- `provider` (extensible, mismo patrón que `PaymentMethod`).
- `provider_status` (estado reportado por el proveedor, puede diferir
  de `Payment.status` mientras se reconcilia).
- Idempotencia ante webhooks: `Payment.idempotency_key` ya existe y es
  exactamente el mecanismo a usar (el ID de transacción del proveedor
  como clave), sin necesidad de un campo nuevo.
- Reembolsos vía proveedor: `Refund.status` ya prevé `PENDING`/`FAILED`
  para una confirmación asíncrona (ver arriba).
- Reconciliación de webhooks: un webhook debe poder confirmar/actualizar
  un `Payment`/`Refund` existente por `idempotency_key`/`external_id`,
  nunca crear un segundo registro paralelo cuando el evento llega
  duplicado o fuera de orden.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
