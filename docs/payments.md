# Pagos (FASE 10)

`Payment` — uno o más pagos por venta. Ver `docs/sales.md` para la
arquitectura compartida (concurrencia, idempotencia).

## Múltiples pagos por venta

Una venta puede tener varios `Payment` (efectivo + tarjeta, por
ejemplo: "Venta $10,000 → Efectivo $5,000, Tarjeta $5,000", el ejemplo
que dio el usuario). `Payment.sale` es un `ForeignKey` normal (no
`OneToOneField`): varias filas de `Payment` por una misma `Sale` son el
caso esperado. Solo se puede registrar un pago sobre una venta
`CONFIRMED` (`services.record_payment` lo exige).

## Sin `PaymentAllocation`

El usuario permitió explícitamente omitirlo "cuando no sea necesario".
Aquí no lo es: un pago siempre pertenece a exactamente una venta. Un
mismo pago cubriendo varias facturas a la vez (el caso que sí exigiría
`PaymentAllocation`) no está en el alcance pedido para esta fase — si
se necesitara en el futuro, es una tabla nueva sin tocar `Payment.sale`.

## Estado de pago de la venta (`Sale.payment_status`)

Calculado, no inventado: `services.recompute_payment_status(sale)`
suma los `Payment` `CONFIRMED` de la venta, resta los `Refund`
`COMPLETED` asociados, y compara el neto contra `sale.total`:

| Condición | Estado |
|---|---|
| Reembolsado > 0 y neto ≤ 0 | `REFUNDED` |
| Reembolsado > 0 y neto > 0 | `PARTIALLY_REFUNDED` |
| Neto ≤ 0 (sin pagos) | `UNPAID` |
| 0 < neto < total | `PARTIALLY_PAID` |
| neto ≥ total | `PAID` |

Se recalcula (nunca se asume) cada vez que se registra/anula un pago o
se registra un reembolso — el campo `payment_status` en `Sale` es una
caché de consulta rápida para listados/filtros, siempre recalculada
dentro de la misma transacción que la origina; la fuente de verdad real
sigue siendo la suma de `Payment`/`Refund`.

## Idempotencia

`record_payment(sale, *, method, amount, user, idempotency_key="", ...)`:
si se pasa una `idempotency_key` y ya existe un `Payment` con esa
clave para el tenant, se devuelve el pago existente **sin crear uno
nuevo** — un doble clic o un reintento de red tras un timeout nunca
duplica el cobro. `void_payment` también es idempotente (anular un pago
ya anulado es un no-op).

## Anular un pago (`void_payment`)

No elimina la fila (preserva el historial/auditoría): cambia
`Payment.status` a `VOIDED` y recalcula `payment_status` de la venta.
Un pago anulado no cuenta en `_sum_confirmed_payments`.

## Reembolsos: separados de las devoluciones de mercancía

`Refund` es la devolución de DINERO, ligada a un `Payment` concreto
(nunca directamente a la venta) — ver "Devoluciones y reembolsos" en
`docs/returns.md` para la justificación completa de por qué están
separados de `Return`. `record_refund` valida que la suma de
reembolsos `COMPLETED` de un pago nunca supere el monto de ese pago.

## Preparación para PayPal (FASE 16) sin acoplar `Sale`

`Payment.method` incluye `OTHER` como valor extensible (mismo patrón de
`choices` extensible que `IdentificationType` en FASE 9). Toda la
lógica de negocio pasa por `services.record_payment` — cuando FASE 16
integre un proveedor real, el cambio se localiza ahí (o en un nuevo
módulo de "Payment Service"/`PaymentProvider" que esta función invoque),
nunca en las vistas ni en `models.py`. No se construyó ninguna
integración real todavía.

## Multi-Tenancy

Cobertura en `test_isolation.py`: registrar/anular un pago de otro
tenant siempre da 404, nunca confirma ni niega su existencia de otra
forma.
