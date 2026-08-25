# Cuentas por Pagar (FASE 12)

`SupplierPayment`/`SupplierPaymentAllocation` — el espejo exacto de
Cuentas por Cobrar (`Payment`/`PaymentAllocation`, FASE 10/11, ver
`docs/payments.md`/`docs/accounts-receivable.md`). Mismos principios,
mismo ledger append-only, **nunca mezclado** con las tablas de
clientes.

## El ledger

- **`SupplierPayment`**: dinero entregado a un proveedor
  (`supplier`, siempre requerido — a diferencia de `Payment.customer`,
  no existe un "proveedor anónimo de mostrador"). Sin ninguna
  asignación todavía, representa un **anticipo** (ver más abajo).
- **`SupplierPaymentAllocation`**: cuánto de un `SupplierPayment` se
  aplicó a qué `SupplierInvoice`. Un pago puede aplicarse a varias
  facturas; una factura puede recibir varios pagos. Inmutable:
  `status=REVERSED` (con auditoría) corrige una asignación equivocada,
  nunca una edición in-place.

```python
factura = services.create_supplier_invoice(tenant, supplier=proveedor, supplier_invoice_number="F-0001", user=user)
services.add_supplier_invoice_item(factura, description="Mercancía", quantity=1, unit_cost=Decimal("1000"), user=user)
services.confirm_supplier_invoice(factura, user)

pago = services.create_supplier_payment(tenant, supplier=proveedor, method="transfer", amount=Decimal("1000"), user=user)
services.allocate_supplier_payment(pago, factura, Decimal("1000"), user)
```

## Reglas de validación (`allocate_supplier_payment`)

Idénticas a `apps.sales.services.allocate_payment`: el monto aplicado
nunca excede el saldo disponible del pago
(`get_unallocated_supplier_payment_amount`) ni el saldo pendiente de la
factura (`get_invoice_balance_due`); pago y factura deben ser del mismo
tenant Y del mismo proveedor; la factura debe estar `CONFIRMED`; el
pago debe estar `CONFIRMED`. `apply_supplier_payment_to_invoices`
valida la suma total contra lo disponible **antes** de aplicar ninguna
asignación (todo o nada).

## Saldo pendiente de una factura

```python
def get_invoice_paid_amount(invoice): ...  # suma de asignaciones ACTIVE de pagos CONFIRMED
def get_invoice_balance_due(invoice):
    return invoice.total - get_invoice_paid_amount(invoice)
```

Siempre calculado desde el ledger — nunca un campo `balance`
desnormalizado (`get_invoice_balance_due_bulk` evita N+1 en listados,
mismo patrón que `get_sale_balance_due_bulk`).

## Anticipos a proveedor: un `SupplierPayment` sin aplicar, nunca un modelo aparte

Mismo principio que un anticipo de cliente en Cuentas por Cobrar:
`register_supplier_advance` simplemente crea un `SupplierPayment` sin
ninguna asignación. `get_supplier_advance_balance(supplier)` suma el
saldo sin aplicar de todos sus pagos confirmados — una agregación de
solo lectura, nunca una tercera tabla de saldo que pudiera divergir del
ledger real (mismo razonamiento que llevó a NUNCA construir un
`CustomerCreditLedger` separado, ver `docs/accounts-receivable.md`
sección 3). `apply_supplier_advance_to_invoice` aplica los anticipos
disponibles (más antiguos primero) a una factura pendiente hasta cubrir
el monto pedido, sin todo-o-nada.

## Pago en efectivo: exige `CashSession` (reutiliza `apps.pos`, FASE 11)

Si `method == PaymentMethod.CASH`, `create_supplier_payment` exige una
sesión de caja abierta
(`apps.pos.services.ensure_open_session_for_checkout`) y registra el
`CashMovement` de salida correspondiente
(`apps.pos.services.record_cash_movement`) — dos tipos nuevos y
distintos, igual que en Cuentas por Cobrar (`SALE_CASH` vs.
`CUSTOMER_ADVANCE_CASH`):

| Tipo | Cuándo |
|---|---|
| `SUPPLIER_PAYMENT_CASH` | Pago en efectivo aplicado a una factura |
| `SUPPLIER_ADVANCE_CASH` | Anticipo en efectivo sin factura todavía |

Ambos son salidas de efectivo (restan del efectivo esperado de la
sesión) — **explícitamente NO se exige `CashSession` para todos los
pagos a proveedor**, solo cuando el método es efectivo; transferencia y
otros métodos nunca afectan la caja física.

## Reversar / anular

`reverse_supplier_allocation` deshace UNA asignación (libera saldo de
la factura y del pago); `void_supplier_payment` anula el pago completo,
reversando en cascada todas sus asignaciones activas — mismos nombres y
comportamiento que `apps.sales.services.reverse_allocation`/
`void_payment`. Ambos idempotentes.

## Idempotencia

`create_supplier_payment(..., idempotency_key="")`: un reintento con la
misma clave devuelve el pago ya existente sin duplicar ni la creación
ni (al usar `record_supplier_payment_for_invoice`) su aplicación.

## Nunca mezclado con Cuentas por Cobrar

`SupplierPayment` nunca referencia un `Customer`; `Payment` (FASE 10)
nunca referencia un `Supplier`. Comparten únicamente el vocabulario
`PaymentMethod` (importado de `apps.sales.models`, no duplicado) — dos
ledgers completamente independientes, cada uno con su propia
disciplina de validación.

## Auditoría

`PurchasesActivityLog`: `PAYMENT_RECORDED`/`PAYMENT_ALLOCATED`/
`PAYMENT_ALLOCATION_REVERSED`/`PAYMENT_VOIDED` — mismo patrón que
`SalesActivityLog` en Cuentas por Cobrar.

## Concurrencia

`allocate_supplier_payment` bloquea (`select_for_update()`) tanto el
`SupplierPayment` como la `SupplierInvoice` antes de validar — dos
asignaciones concurrentes del mismo pago, o dos asignaciones
concurrentes a la misma factura, nunca sobre-aplican (mismo patrón
verificado con hilos reales para `PaymentAllocation` en FASE 10/11).
