# Órdenes de Compra (FASE 12)

`PurchaseOrder`/`PurchaseOrderItem` — el compromiso de compra a un
proveedor. Ver `docs/purchases.md` para la arquitectura general y
`docs/receiving.md` para cómo una orden se recibe.

## Modelo

Hereda `TenantScopedModel`. Cabecera: `supplier` (FK a
`apps.customers.Supplier`, `PROTECT`), `number` (numeración propia vía
`apps.sales.services.generate_document_number` con
`DocumentSequence.DocumentType.PURCHASE_ORDER`, prefijo `OC-`),
`status`, `issue_date`, `expected_date`, `currency`, `payment_terms`
(mismo enum `PaymentTerms` de `apps.customers`, sin duplicarlo),
`global_discount_percent`/`global_discount_amount`, `freight_cost`/
`insurance_cost`/`other_costs` (preparación de landed cost, ver
`docs/purchases.md` sección 3), `subtotal`/`discount_total`/
`tax_total`/`total`.

Líneas (`PurchaseOrderItem`): snapshot de `description`/`sku_snapshot`/
`unit_cost` tomado al agregarse — nunca se vuelve a leer `Product` para
recalcular una línea ya guardada, mismo principio que `SaleItem` (FASE 10).

**Deliberadamente sin `received_quantity`/`pending_quantity` como
campos guardados**: serían una segunda fuente de verdad frente a
`PurchaseReceiptItem` — se calculan siempre agregando sobre el ledger de
recepción (`services.get_purchase_order_item_received_quantity`/
`get_purchase_order_item_pending_quantity`, y su variante en bloque
`get_purchase_order_items_received_bulk` para evitar N+1 en listados,
mismo patrón que `get_sale_balance_due_bulk` de FASE 11).

## Máquina de estados

`DRAFT → SENT → PARTIALLY_RECEIVED/RECEIVED`, más `CANCELED`/`CLOSED`.

- **`DRAFT`**: editable — agregar/quitar líneas, editar cabecera
  (`services.add_purchase_order_item`/`remove_purchase_order_item`/
  `update_purchase_order_header`).
- **`SENT`**: la orden ya no admite líneas nuevas; puede recibirse.
- **`PARTIALLY_RECEIVED`**/**`RECEIVED`**: derivados automáticamente por
  `services._recompute_purchase_order_status` al recibir — nunca
  editados a mano (mismo principio que `Sale.status` tras una
  devolución parcial/total en FASE 10).
- **`CANCELED`**: solo desde `DRAFT`/`SENT` **sin ninguna recepción
  registrada todavía** — una orden con recepciones ya tiene efectos
  reales en inventario y no puede simplemente "desaparecer"; usa
  `close_purchase_order` en su lugar.
- **`CLOSED`**: cierre manual de una orden que no recibirá más
  mercancía (p. ej. quedó parcialmente recibida y el resto ya no
  llegará) — distinto de `RECEIVED`, que solo se alcanza recibiendo por
  completo.

## Compra sobre el límite (reutiliza `apps.approvals`, FASE 11)

`send_purchase_order` valida el total de la orden contra
`apps.approvals.services.check_purchase_authorization` (nueva dimensión
`ApprovalPolicy.max_purchase_order_amount`, mismo patrón que
`max_credit_overage`) — jerarquía usuario → rol → tenant → negar,
propietario siempre autorizado. Si excede el límite, lanza
`PurchaseOverThresholdRequiresApproval`; la vista captura la excepción,
crea automáticamente la `ApprovalRequest`
(`ActionType.PURCHASE_OVER_THRESHOLD`) y pide reintentar una vez
aprobada — mismo flujo ya usado para descuentos/crédito excedido en el
POS, nunca una implementación paralela.

## Multi-Tenancy

`create_purchase_order` rechaza un `Supplier` de otro tenant;
`add_purchase_order_item` rechaza un `Product` de otro tenant — segunda
barrera a nivel de servicio, nunca confiada solo al filtrado de las
vistas (mismo principio que `apps.sales.services.allocate_payment`).

## Auditoría

`PurchasesActivityLog` (creación, edición, envío, cancelación, cierre,
recepción parcial/completa) — bitácora mínima acotada a este módulo,
mismo patrón que `SalesActivityLog`/`ActivityLog` de FASES 9/10.
