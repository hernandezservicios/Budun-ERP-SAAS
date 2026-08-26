# Pagos y cuentas por cobrar (FASE 10 + ampliación obligatoria)

`Payment` + `PaymentAllocation` — dinero recibido de un cliente,
aplicado (parcial o totalmente, a una o varias facturas) mediante un
ledger append-only. Ver `docs/sales.md` para la arquitectura compartida
del motor comercial (concurrencia, idempotencia, auditoría).

> **Historial del diseño**: FASE 10 se cerró originalmente con
> `Payment.sale` como `ForeignKey` directo (un pago siempre pertenecía a
> exactamente una venta) y sin `PaymentAllocation`, con el usuario
> permitiendo explícitamente omitirlo "cuando no sea necesario". Una
> ampliación obligatoria posterior, pedida explícitamente por el
> usuario, exigió soportar "un Payment puede aplicarse a una o varias
> facturas del mismo Customer" — este documento describe la
> arquitectura **actual** (post-ampliación); `Payment.sale` ya no
> existe.

## El ledger: `Payment` + `PaymentAllocation`

- **`Payment`**: dinero recibido de un cliente (`Payment.customer`,
  nulo solo para el cobro inmediato de una venta de mostrador sin
  cliente registrado). Ya NO tiene una venta asociada directamente.
- **`PaymentAllocation`**: cuánto de un `Payment` se aplicó a qué
  `Sale`. Un pago puede tener varias asignaciones (a varias facturas
  distintas); una factura puede recibir asignaciones de varios pagos
  distintos. Inmutable en el sentido de `Return` (FASE 10 original):
  nunca se borra ni se edita in-place — una asignación equivocada se
  corrige con `reverse_allocation` (`status=REVERSED` + auditoría), no
  con un `UPDATE` silencioso.

Un pago sin ninguna asignación representa dinero recibido pero sin
aplicar todavía a ninguna factura — el "saldo a favor" de ese pago
(ver "Saldo a favor del cliente" más abajo).

### Ejemplo (el que dio el usuario)

```
Factura A = 10,000
Factura B = 7,500
Factura C = 12,000

Pago = 20,000

PaymentAllocation:
  A = 10,000
  B = 7,500
  C = 2,500        (factura C queda con 9,500 pendiente)
```

```python
pago = services.create_payment(tenant, customer=cliente, method="transfer", amount=Decimal("20000"), user=user)
services.apply_payment_to_sales(pago, [
    {"sale": factura_a, "amount": Decimal("10000")},
    {"sale": factura_b, "amount": Decimal("7500")},
    {"sale": factura_c, "amount": Decimal("2500")},
], user)
```

## Reglas de validación (todas en `allocate_payment`/`apply_payment_to_sales`)

1. Un pago puede relacionarse con múltiples facturas — sin límite, cada
   una es una fila de `PaymentAllocation`.
2. Una factura puede recibir múltiples pagos — mismo mecanismo, en
   sentido inverso.
3. El monto aplicado nunca puede exceder **ninguno** de los dos límites,
   validados dentro de la misma transacción bloqueada
   (`select_for_update()` sobre `Payment` y `Sale`):
   - el saldo **disponible** del pago (`get_unallocated_payment_amount`);
   - el saldo **pendiente** de la factura (`get_sale_balance_due`).
4. `apply_payment_to_sales` valida la suma total solicitada contra lo
   disponible del pago **antes** de aplicar ninguna asignación
   individual — todo o nada, nunca aplica parcialmente una lista.
5. El pago y la factura deben pertenecer al mismo `tenant`
   (`allocate_payment` lo revalida explícitamente, aunque nunca podría
   ocurrir vía HTTP).
6. La factura debe pertenecer al mismo `customer` que el pago
   (`payment.customer_id == sale.customer_id`, incluyendo
   `None == None` para el caso de venta de mostrador sin cliente).
7. Cross-tenant y cross-customer se rechazan con `InvalidSalesOperation`
   — nunca una excepción genérica ni un `IntegrityError` de PostgreSQL.
8. Pagos parciales: `amount` puede ser menor al saldo pendiente de la
   factura sin problema; la factura queda `PARTIALLY_PAID`.
9. El pago y la factura deben compartir la misma `currency`
   (`payment.currency == sale.currency`) — sin un motor de tipos de
   cambio (ver `docs/currency.md` sección 7), mezclar monedas
   distintas en una misma asignación se rechaza con
   `InvalidSalesOperation` en vez de sumar montos de monedas
   diferentes como si fueran la misma unidad. Ninguna conversión
   automática; cuando exista FX real en una fase futura, la conversión
   deberá ser explícita, auditada y con tasa. Mismo principio aplicado
   a `apply_credit_note` (`CreditNote.currency` debe coincidir con
   `Sale.currency`) y a `get_customer_credit_balance` (solo suma
   `Payment`/`CreditNote` en la moneda del cliente).

## Saldo pendiente de una factura (`get_sale_balance_due`)

```python
def get_sale_paid_amount(sale):
    # Suma de PaymentAllocation ACTIVE de Payment CONFIRMED aplicadas a esta venta.
    ...

def get_sale_balance_due(sale):
    return sale.total - get_sale_paid_amount(sale)
```

Nunca un campo desnormalizado: se calcula siempre desde el ledger, mismo
principio que `get_current_stock` en `apps.inventory.services`.

## Estado de pago de la venta (`Sale.payment_status`)

`recompute_payment_status(sale)` deriva **únicamente** de
`get_sale_paid_amount(sale)` contra `sale.total`:

| Condición | Estado |
|---|---|
| Pagado ≤ 0 | `UNPAID` |
| 0 < pagado < total | `PARTIALLY_PAID` |
| pagado ≥ total | `PAID` |

`REFUNDED`/`PARTIALLY_REFUNDED` siguen existiendo como valores del
enum (compatibilidad), pero **ya no se derivan automáticamente aquí** —
ver "Reembolsos" más abajo para el porqué. Se recalcula (nunca se
asume) dentro de la misma transacción que aplica/revierte una
asignación; `Sale.payment_status` es una caché de consulta rápida para
listados/filtros, la fuente de verdad real es siempre el ledger.

## Reversar una asignación (`reverse_allocation`)

Deshace la aplicación de un pago a UNA factura concreta: libera el
saldo pendiente de esa factura y devuelve el monto al saldo disponible
del pago (el dinero sigue dentro del sistema, solo deja de estar
aplicado). Idempotente. Distinta de anular un pago completo
(`void_payment`, que reversa **todas** sus asignaciones activas en
cascada) y distinta de un reembolso (`record_refund`, que saca el
dinero **fuera** del sistema).

## Reembolsos: solo desde el saldo sin aplicar

`Refund` sigue separado de `Return` (dinero vs. mercancía — ver
`docs/returns.md`). La regla cambió con la ampliación: un reembolso
**solo puede salir del saldo sin aplicar de un pago**
(`get_unallocated_payment_amount(payment)`), nunca de dinero ya
aplicado a una factura. Si el dinero ya está aplicado, hay que
**revertir la asignación primero** (`reverse_allocation`) — eso ya dej
a la factura en `UNPAID`/`PARTIALLY_PAID` de forma natural — y **luego**
reembolsar desde el saldo ahora libre.

> **Cambio de comportamiento respecto al cierre original de FASE 10**:
> antes, reembolsar el pago completo de una venta totalmente pagada
> dejaba `Sale.payment_status = REFUNDED` directamente. Bajo la regla
> nueva (más correcta: nunca "des-aplicar" una factura en silencio
> dentro de un reembolso) ese mismo resultado requiere dos pasos
> explícitos — `reverse_allocation` seguido de `record_refund` — y dos
> tests de FASE 10 (`test_reembolso_total_deja_estado_refunded`,
> `test_reembolso_parcial_deja_estado_partially_refunded`) se
> actualizaron para reflejar el flujo correcto (ver
> `apps/sales/tests/test_payments.py`).

## Saldo a favor del cliente (preparación, sin ledger completo)

`get_customer_credit_balance(customer)`: suma `get_unallocated_payment_amount`
de todos los pagos `CONFIRMED` **en la moneda del cliente**
(`currency=customer.currency`) y el saldo sin aplicar de sus
`CreditNote` en esa misma moneda. Es una agregación de solo lectura
sobre `Payment`/`PaymentAllocation`/`CreditNote`/`CreditNoteApplication`
ya existentes — **no** una tabla ni un campo de saldo nuevo, ni un
ledger contable completo (eso queda para una fase posterior si se
decide construir cuentas por cobrar reales). Un pago o nota en otra
moneda simplemente no participa en este saldo (ver "Moneda" abajo).

Un `Payment` con `customer=None` (venta de mostrador) **nunca**
participa en el cálculo de saldo a favor de ningún cliente — no hay
ningún cliente al que atribuírselo (regla confirmada como doctrina
permanente, ver `docs/accounts-receivable.md` sección 2). Esta misma
función ya está generalizada (FASE 11) para sumar también el saldo sin
aplicar de las `CreditNote` del cliente (`apps.sales`, ver
`docs/accounts-receivable.md`) — deliberadamente **sin** una tabla
`CustomerCreditLedger` separada, para no coexistir como un segundo
saldo independiente que pudiera divergir.

## Facturas pendientes del cliente (preparación de estado de cuenta)

`get_customer_pending_sales(customer)`: ventas `CONFIRMED` o
`PARTIALLY_RETURNED` del cliente con `get_sale_balance_due(venta) > 0`.
Consulta reutilizable (no un reporte — eso es FASE 14), pensada
explícitamente para que FASE 11 (POS) pueda listar "facturas
pendientes de este cliente" y cobrarlas.

## Idempotencia

- `create_payment(tenant, *, ..., idempotency_key="")`: una clave
  repetida devuelve el `Payment` ya existente sin crear uno duplicado.
- `record_payment_for_sale(sale, *, ..., idempotency_key="")`: atajo
  atómico que crea el pago y lo aplica por completo a una sola venta en
  un solo paso — si la clave ya existía Y el pago ya fue aplicado, el
  reintento no vuelve a aplicar (nunca duplica ni la creación ni la
  aplicación).
- `void_payment`/`reverse_allocation`: ambos idempotentes (repetir la
  operación sobre algo ya anulado/revertido es un no-op).

## Auditoría

Cuatro eventos distintos en `SalesActivityLog`, cada uno con su propio
`entity_type`/`entity_id` (`"payment"` para el pago en sí, `"sale"`
para el efecto sobre una factura concreta):

| Acción | `entity_type` | Cuándo |
|---|---|---|
| `PAYMENT_RECORDED` | `payment` | Al crear el `Payment` (`create_payment`) |
| `PAYMENT_ALLOCATED` | `sale` | Al aplicar dinero a una factura (`allocate_payment`) |
| `PAYMENT_ALLOCATION_REVERSED` | `sale` | Al revertir una asignación (`reverse_allocation`) |
| `PAYMENT_VOIDED` | `payment` | Al anular el pago completo (`void_payment`) |
| `REFUNDED` | `payment` | Al reembolsar dinero (`record_refund`) |

## Vista de una sola venta (`SalePaymentAddView`/`sale_detail.html`)

La UI de FASE 10 (pestaña "Pagos" del detalle de venta) usa
`record_payment_for_sale`: registra un pago y lo aplica de inmediato al
100% a esa venta, preservando la experiencia simple de "cobrar esta
venta" sin que el usuario necesite saber que el ledger de asignaciones
existe debajo. La tabla de esa pestaña lista `PaymentAllocation`
(no `Payment` directamente) — el monto mostrado es lo aplicado a
**esta** venta, correcto incluso si el pago subyacente también se
aplicó a otra factura.

El botón "Revertir" de esa tabla llama a `reverse_allocation` (no
`void_payment`): deshace solo la aplicación a esta venta, sin afectar
otras facturas que el mismo pago pudiera cubrir.

## Multi-factura: preparación explícita para FASE 11 (POS)

`apply_payment_to_sales(payment, allocations, user)` es el mecanismo de
"aplicar un solo pago a varias facturas" pedido explícitamente para que
FASE 11 (POS) pueda: cobrar la venta actual, recibir pago parcial,
recibir pago múltiple, cobrar facturas pendientes de un cliente, y
aplicar un solo pago a varias facturas a la vez. La capa de servicio ya
soporta esto completo y está cubierta por tests (incluyendo
concurrencia); FASE 10 no construyó una UI dedicada a esto — igual que
en el cierre original ("no construir todavía el POS completo"), esa
interfaz operacional le corresponde a quien la consuma (FASE 11, o una
futura pantalla de "cuenta corriente de cliente").

## Preparación para PayPal (FASE 16) sin acoplar `Sale`

`Payment.method` incluye `OTHER` como valor extensible (mismo patrón de
`choices` extensible que `IdentificationType` en FASE 9). Toda la
lógica de negocio pasa por `services.py` — cuando FASE 16 integre un
proveedor real, el cambio se localiza ahí (o en un nuevo módulo de
"Payment Service"/`PaymentProvider` que estas funciones invoquen),
nunca en las vistas ni en `models.py`. No se construyó ninguna
integración real todavía.

## Concurrencia

Cubierto con hilos reales (`TransactionTestCase`, ver
`test_concurrency.py`, clase `PaymentAllocationConcurrencyTests`): dos
asignaciones simultáneas del mismo pago que juntas exceden lo
disponible, y dos asignaciones simultáneas a la misma factura desde
pagos distintos que juntas exceden el saldo pendiente — en ambos casos
exactamente una gana, nunca una sobre-aplicación.

## Multi-Tenancy

Cobertura en `test_isolation.py`: registrar/revertir un pago de otro
tenant siempre da 404 vía HTTP; `allocate_payment` además rechaza
explícitamente a nivel de servicio cualquier intento de aplicar un pago
de un tenant a una venta de otro (segunda barrera, nunca confiada solo
al filtrado de las vistas).

## Moneda (sincronización posterior a FASE 12, especificación — ver `docs/currency.md`)

`Payment.currency` (y `Sale.currency`/`Quotation.currency`/
`ProformaInvoice.currency`) ya existen como `CharField(max_length=3)` —
un snapshot de texto simple, sin ningún catálogo real detrás. La
doctrina oficial de moneda (`docs/currency.md`) define `Currency`/
`CurrencyDenomination` como el catálogo real, sin migrar ni reemplazar
estos campos con este documento — siguen siendo válidos exactamente
como están. Preparado, no construido: `Payment.amount_received`/
`change_amount` (nulos, solo relevantes para `method=CASH`, ver
`docs/currency.md` sección 9) para registrar el detalle de cuánto
entregó el cliente y cuánto cambio recibió, sin que eso cambie el
principio ya vigente de que el `CashMovement`/monto aplicado a la venta
sigue siendo siempre el neto. Pagos multi-moneda (un `Payment` en una
moneda distinta a la del documento que paga) quedan preparados
conceptualmente vía `CurrencyConfiguration`/tipos de cambio futuros —
ningún motor de conversión (FX) se construye todavía; **hoy se
rechazan explícitamente** (ver regla 9 arriba y `KNOWN_ISSUES.md`
#83), nunca se mezclan ni se convierten automáticamente.
