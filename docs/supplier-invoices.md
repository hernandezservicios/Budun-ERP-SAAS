# Facturas de Proveedor (FASE 12)

`SupplierInvoice`/`SupplierInvoiceItem` — el documento fiscal que el
PROVEEDOR emite, conceptualmente separado de `PurchaseOrder`
(nuestro compromiso) y `PurchaseReceipt` (el evento físico). Ver
`docs/purchase-orders.md`, `docs/receiving.md` y
`docs/accounts-payable.md` (a qué habilita una factura confirmada).

## Por qué es un documento aparte

Una factura puede llegar después de una recepción parcial, cubrir solo
parte de lo recibido, o incluso no estar ligada a ninguna orden de
compra formal (`purchase_order` es `null=True` — compra directa). Varias
facturas pueden corresponder a una misma orden (recepciones parciales
facturadas por separado). `supplier_invoice_number` es el número que
EL PROVEEDOR ya asignó a su propio documento — texto libre, único por
`(tenant, supplier)`, nunca generado por nuestra `DocumentSequence`
(que solo numera documentos NUESTROS: órdenes, recepciones,
devoluciones).

## Máquina de estados

`DRAFT → CONFIRMED`, más `CANCELED`.

- **`DRAFT`**: editable — agregar líneas (`add_supplier_invoice_item`,
  snapshot de `description`/`unit_cost`/impuesto, misma matemática que
  `PurchaseOrderItem`: descuento % con prioridad sobre monto fijo,
  impuesto sobre la base ya descontada).
- **`CONFIRMED`**: reconoce la factura como una cuenta por pagar real —
  a partir de aquí participa en `get_invoice_balance_due`/
  `get_supplier_pending_invoices` y puede recibir pagos. Exige al menos
  una línea.
- **`CANCELED`**: rechazada si la factura ya tiene pagos aplicados
  (`get_invoice_paid_amount(factura) > 0`) — hay que reversar los pagos
  primero, mismo principio de nunca "deshacer en cascada silenciosamente"
  ya aplicado en `apps.sales`.

## Multi-Tenancy

`create_supplier_invoice` rechaza una `PurchaseOrder` que no pertenezca
al `Supplier` indicado — segunda barrera a nivel de servicio.

## Auditoría

`PurchasesActivityLog`: `INVOICE_REGISTERED`/`INVOICE_CONFIRMED`/
`INVOICE_CANCELED`, además de los eventos de pago (ver
`docs/accounts-payable.md`).
