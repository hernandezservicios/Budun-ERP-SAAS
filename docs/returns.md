# Devoluciones y Reembolsos (FASE 10)

`Return`/`ReturnItem` (mercancía) y `Refund` (dinero) — deliberadamente
**separados**, tal como pidió el usuario explícitamente: "debe existir
separación entre devolución de mercancía y devolución de dinero". Ver
`docs/sales.md` para el resumen y `docs/payments.md` para `Refund`.

## Por qué están separados

No toda devolución de mercancía implica un reembolso inmediato (podría
resolverse con una nota de crédito o un cambio por otro producto,
ninguno de los dos construido todavía) — y no todo reembolso parte de
una devolución física (podría ser un ajuste de precio). `Return` afecta
inventario; `Refund` afecta pagos. `Refund.return_document` es opcional
(`null=True`) precisamente para permitir un reembolso sin una
devolución física asociada.

## `Return`: inmutable una vez creado

`Return` **no tiene estados ni una operación de cancelación**. Es en sí
misma una operación correctiva: deshacer una devolución exigiría una
nueva operación compensatoria (¿volver a vender la unidad? ¿sacarla de
inventario otra vez?), no revertir un simple campo de estado — se
decidió no construir esa reversión-de-reversión sin que el usuario la
pidiera explícitamente. `on_delete=PROTECT` en `Return.sale` y
`ReturnItem.sale_item` refuerza que nunca se borra físicamente.

## Devolución parcial y total

`create_return(sale, *, items, user, reason="")` recibe una lista de
líneas a devolver:
- Producto QUANTITY: `{"sale_item": ..., "quantity_returned": Decimal}`
  — puede ser menor a la cantidad vendida (devolución parcial de esa
  línea).
- Producto SERIALIZED: `{"sale_item": ...}` — la unidad completa se
  devuelve de una vez (no tiene sentido "devolver la mitad" de un
  teléfono).

Al terminar, `services._is_full_return(sale)` recorre TODAS las
`ReturnItem` de TODAS las devoluciones de esa venta (no solo la actual)
y compara contra las líneas originales: si cada línea fue devuelta por
completo, `Sale.status` pasa a `RETURNED`; si falta alguna, a
`PARTIALLY_RETURNED`. Una venta `PARTIALLY_RETURNED` admite una nueva
devolución (`create_return` acepta ambos estados) hasta completarse.

## Efecto en inventario

- QUANTITY: `apps.inventory.services.register_stock_in` (una entrada de
  stock real, con nota `"Devolución {número}"`) — nunca se duplica esa
  lógica aquí, se reutiliza literalmente.
- SERIALIZED: `transition_unit_status(..., DEVUELTO, ...)` — transición
  válida en la máquina de estados de FASE 8
  (`VENDIDO → DEVUELTO`).

## Por qué una unidad devuelta NO vuelve sola a `EN_STOCK`

Requisito explícito del usuario: "no reingresar automáticamente una
unidad a stock sin una política de estado válida". Un `DEVUELTO`
necesita revisión humana antes de decidir si vuelve a venderse
(`EN_STOCK`), va a `REPARACION` o se marca `GARANTIA` — las tres son
transiciones ya válidas en la máquina de estados de FASE 8
(`apps.inventory.services.ALLOWED_UNIT_TRANSITIONS[DEVUELTO]`), pero
`create_return` deliberadamente se detiene en `DEVUELTO` y no las
ejecuta automáticamente. Esa decisión de seguimiento pertenece a la
gestión de inventario (FASE 8), no al motor de ventas.

## `Refund`: reembolsos de dinero

`record_refund(payment, *, amount, user, reason="", return_document=None)`:
valida que el monto nunca supere el saldo SIN APLICAR del pago
(`services.get_unallocated_payment_amount`, ampliación "Payment +
PaymentAllocation" — ver `docs/payments.md`), no `payment.amount`
directamente: si el dinero ya está aplicado a una factura, primero hay
que revertir esa aplicación (`reverse_allocation`) antes de poder
reembolsarlo. Sin integración real de pasarela todavía: se registra
como `COMPLETED` de inmediato (`Refund.Status` también prevé
`PENDING`/`FAILED` para cuando FASE 16 conecte un proveedor real con
confirmación asíncrona).

## Multi-Tenancy

Cobertura en `test_isolation.py`: registrar una devolución sobre una
venta de otro tenant da 404 en el formulario de devolución.
