# Recepción (FASE 12)

`PurchaseReceipt`/`PurchaseReceiptItem` — el evento físico que
efectivamente mueve inventario. Una orden puede recibirse en varias
entregas (recepción parcial); `services.receive_purchase_order` es la
única función que las registra. Ver `docs/purchase-orders.md` y
`docs/purchases.md`.

## `PurchaseReceipt`: inmutable una vez creada

Mismo principio que `apps.sales.Return` (FASE 10): sin estados, sin
edición ni cancelación — es en sí misma una operación correctiva de
inventario. Numerada vía la misma `DocumentSequence`
(`DocumentType.PURCHASE_RECEIPT`, prefijo `REC-`).

## Recepción parcial y completa (el ejemplo de la especificación)

Orden con 10 unidades pedidas de una línea: una primera recepción de 6
dejа la línea con 4 pendientes (`PurchaseOrder.status =
PARTIALLY_RECEIVED`); una segunda recepción de esas 4 la completa
(`status = RECEIVED`). El pendiente se deriva SIEMPRE de
`get_purchase_order_item_pending_quantity` — nunca un campo editado a
mano (ver `docs/purchase-orders.md`).

## Productos QUANTITY: reutiliza literalmente FASE 8

Cada línea de recepción llama a
`apps.inventory.services.register_stock_in(product=..., quantity=...,
user=..., notes=f"Recepción {numero} (OC {numero_orden})")` — nunca se
duplica esa lógica. `PurchaseReceiptItem.quantity_received` guarda la
cantidad recibida EN ESA recepción (no el pendiente ni el total).

## Productos SERIALIZED: una llamada por unidad física

Recibir 5 unidades serializadas significa **5 llamadas** a
`apps.inventory.services.register_serialized_unit` (una por IMEI/serie),
nunca un alta masiva "recibí 5" sin 5 `InventoryUnit` reales — mismo
requisito explícito ya aplicado en FASE 10 (Ventas) y FASE 11 (POS).
Cada unidad queda en `EN_STOCK`, con `purchase_origin` poblado con una
referencia legible ("OC-000001 / REC-000001") y
`PurchaseReceiptItem.inventory_unit` como la FK real hacia ella — la
relación de trazabilidad que `docs/inventory.md` dejó anticipada desde
FASE 8 como "texto libre provisional hasta que exista Compras".

Costo real registrado por unidad (`unit_cost`, puede diferir del
estimado en la orden — base de landed cost) se congela en
`PurchaseReceiptItem.unit_cost` en el momento de recibirse, nunca
recalculado después.

## Sobre-recepción: rechazada por defecto, autorizable

Por defecto, `receive_purchase_order` **rechaza** recibir más de lo
pendiente de una línea. Si se intenta, calcula el porcentaje de exceso
sobre lo pendiente y lo valida contra
`apps.approvals.services.check_over_receiving_authorization` (nueva
dimensión `ApprovalPolicy.max_over_receiving_percent`, mismo patrón que
`max_discount_percent`) — jerarquía usuario → rol → tenant → negar,
propietario siempre autorizado. Si no está cubierto, lanza
`OverReceivingRequiresApproval`; la vista crea automáticamente la
`ApprovalRequest` (`ActionType.OVER_RECEIVING`) y pide reintentar una
vez aprobada — mismo flujo que descuentos/crédito excedido/compra sobre
el límite, nunca un bypass silencioso.

## Serial/IMEI: reutiliza las constraints de FASE 8

Ninguna validación de duplicados/IMEI1≠IMEI2/al menos un identificador
se reimplementa aquí — `register_serialized_unit` ya las aplica. Un
`IntegrityError` de la constraint de unicidad de PostgreSQL (sin una
única fila que bloquear con `select_for_update()`, ya que la unicidad
es por tenant, no por una fila concreta — mismo caso ya resuelto en
FASE 11 para la exclusividad de `CashSession` por usuario) se traduce a
un `InvalidPurchaseOperation` claro, nunca se deja escapar sin traducir.

## Trazabilidad

Proveedor → Orden de compra → Recepción → Producto →
`StockMovement`/`InventoryUnit` (IMEI/serie para serializados), con
usuario y fecha en cada paso — consultable end-to-end desde el detalle
de la orden (pestaña "Recepciones").

## Concurrencia

Toda la operación corre dentro de `receive_purchase_order`
(`transaction.atomic` + `select_for_update()` sobre la `PurchaseOrder`),
que serializa dos recepciones concurrentes de la MISMA orden: la
segunda ve siempre el "pendiente" ya actualizado por la primera antes
de decidir si hay sobre-recepción. Probado con hilos reales
(`TransactionTestCase`, ver `apps/purchases/tests/test_concurrency.py`):
dos recepciones simultáneas de la misma orden, dos intentos simultáneos
de sobre-recepción que comparten la misma aprobación (se consume una
sola vez), y dos recepciones simultáneas que juntas completan
exactamente la orden sin doble conteo.
