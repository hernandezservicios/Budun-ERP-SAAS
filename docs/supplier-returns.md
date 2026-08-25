# Devoluciones a Proveedor (FASE 12)

`SupplierReturn`/`SupplierReturnItem` — mercancía que devolvemos a
quien nos la vendió. Mismo principio de inmutabilidad que
`apps.sales.Return` (FASE 10, ver `docs/returns.md`): sin estados, sin
cancelación, una operación correctiva en sí misma.

## `SupplierReturn`: inmutable, referencia la orden y la recepción

`purchase_order` (la orden de origen) + cada `SupplierReturnItem`
referencia la `PurchaseReceiptItem` exacta que se está devolviendo —
trazabilidad completa Orden → Recepción → Devolución. Numerada vía la
misma `DocumentSequence` (`DocumentType.SUPPLIER_RETURN`, prefijo
`DEVP-`).

## Devolución parcial y total

- Producto QUANTITY: `{"receipt_item": ..., "quantity_returned": Decimal}`
  — no puede exceder `receipt_item.quantity_received`.
- Producto SERIALIZED: `{"receipt_item": ...}` — la unidad completa se
  devuelve de una vez.

## Efecto en inventario

- **QUANTITY**: `apps.inventory.services.register_stock_out` (una
  salida de stock real) — nunca se duplica esa lógica.
- **SERIALIZED**: la unidad transiciona a un nuevo estado terminal,
  `DEVUELTO_PROVEEDOR` ("Devuelta al proveedor").

### Por qué un estado nuevo, y no reutilizar `DEVUELTO`

`InventoryUnit.Status` (FASE 8) ya tenía 8 valores, incluyendo
`DEVUELTO` — pero ese estado significa lo **opuesto**: un CLIENTE nos
devolvió la unidad a NOSOTROS (`apps.sales.services.create_return`,
transición `VENDIDO → DEVUELTO`). Una devolución a proveedor es una
unidad que SALE de nuestro inventario porque nosotros se la
regresamos a quien nos la vendió — reutilizar `DEVUELTO` habría sido
semánticamente ambiguo (¿la fila representa mercancía que tenemos de
vuelta, o que ya no tenemos?) y además `EN_STOCK → DEVUELTO` nunca fue
una transición válida en la máquina de estados original (`DEVUELTO`
solo es alcanzable desde `VENDIDO`).

Se agregó `DEVUELTO_PROVEEDOR` como una línea nueva al enum existente
— el mismo patrón extensible ya usado por
`CashMovement.MovementType`/`ApprovalRequest.ActionType` — y una única
transición nueva, `EN_STOCK → DEVUELTO_PROVEEDOR`, en
`apps.inventory.services.ALLOWED_UNIT_TRANSITIONS`. Es un estado
terminal (sin salida), igual que `PERDIDO`. Requirió una migración
aditiva sobre `apps.inventory` (`alter_inventoryunit_status`) — ningún
dato existente se modifica, solo se amplía el conjunto de valores
válidos.

## Multi-Tenancy

`create_supplier_return` rechaza una `PurchaseReceiptItem` que no
pertenezca a la orden de compra indicada — segunda barrera a nivel de
servicio.

## Concurrencia

Dos devoluciones simultáneas de la MISMA unidad serializada: la segunda
ve la unidad ya transicionada (no `EN_STOCK`) y `transition_unit_status`
rechaza la transición inválida — probado con hilos reales
(`apps/purchases/tests/test_concurrency.py`).

## Auditoría

`PurchasesActivityLog.Action.SUPPLIER_RETURN_CREATED`.
