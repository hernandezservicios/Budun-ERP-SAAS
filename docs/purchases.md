# Compras: Órdenes, Recepción, Costos y Cuentas por Pagar (FASE 12)

> **Estado: CONSTRUIDO.** `apps/purchases` es el dominio central de
> Compras del ERP, orquestando sobre `apps.customers` (Suppliers, FASE 9),
> `apps.inventory` (FASE 8), `apps.approvals` (FASE 11) y `apps.pos`
> (FASE 11) — nunca un segundo sistema de inventario, aprobaciones, caja
> ni archivos. Ver `docs/purchase-orders.md`, `docs/receiving.md`,
> `docs/supplier-invoices.md`, `docs/accounts-payable.md` y
> `docs/supplier-returns.md` para el detalle de cada dominio.

## 1. Documentos independientes, no una sola entidad con estados

Mismo principio que FASE 10 (Cotización/Proforma/Venta): `PurchaseOrder`
(orden de compra), `PurchaseReceipt` (recepción física), `SupplierInvoice`
(factura del proveedor) y `SupplierReturn` (devolución a proveedor) son
modelos independientes, no una sola entidad con un campo `type` — cada
uno es conceptualmente distinto y tiene su propia tabla de líneas
(`PurchaseOrderItem`/`PurchaseReceiptItem`/`SupplierInvoiceItem`/
`SupplierReturnItem`). Ver `docs/purchase-orders.md`/`docs/receiving.md`.

## 2. Recepción e inventario: reutiliza literalmente FASE 8

- **Productos por CANTIDAD**: cada recepción llama a
  `apps.inventory.services.register_stock_in` — nunca se duplica esa
  lógica.
- **Productos SERIALIZADOS**: cada unidad físicamente recibida llama a
  `apps.inventory.services.register_serialized_unit` — una llamada por
  IMEI/serie, nunca un alta masiva que no pase por esa función. La
  unidad queda automáticamente en `EN_STOCK`, con `purchase_origin`
  poblado con la referencia legible orden/recepción y
  `PurchaseReceiptItem.inventory_unit` como la FK real hacia ella
  (resolviendo la relación "texto libre provisional" documentada desde
  FASE 8).
- Nunca se crea una `InventoryUnit`/`StockMovement` a mano fuera de
  `apps.inventory.services` — ver `docs/receiving.md`.

## 3. Costos históricos (snapshot) y landed cost

Cada línea de orden (`PurchaseOrderItem.unit_cost`) y cada línea de
recepción (`PurchaseReceiptItem.unit_cost`, el costo REAL registrado al
recibir, que puede diferir del estimado en la orden) congelan su costo
en el momento correspondiente — mismo principio de snapshot histórico
que `SaleItem`/`QuotationItem` (FASE 10): un costo ya registrado nunca
cambia si el costo del producto cambia después.

**Landed cost**: `PurchaseOrder` tiene `freight_cost`/`insurance_cost`/
`other_costs` a nivel de CABECERA — se suman al total de la orden
(`services.recalculate_purchase_order_totals`), preparando el concepto
de costo total de la operación. El **prorrateo** de esos costos entre
líneas/unidades individuales se deja **conceptualmente preparado, sin
construir** — mismo criterio que ya se aplicó a `CustomerCreditLedger`/
facturación fiscal en fases anteriores: no agregar un cálculo de
distribución sin un caso de uso real que lo exija. Si se construye en
el futuro, debe ser un ajuste explícito documentado sobre `unit_cost`
de cada línea, nunca un cálculo oculto.

## 4. Devoluciones a proveedor

`SupplierReturn`/`SupplierReturnItem` — mismo principio de inmutabilidad
que `Return` (FASE 10): sin estados, sin cancelación, una operación
correctiva en sí misma. Efecto en inventario: productos por CANTIDAD vía
`register_stock_out`; productos SERIALIZADOS transicionando la unidad a
un nuevo estado terminal `DEVUELTO_PROVEEDOR` agregado a
`InventoryUnit.Status` (FASE 8) — ver `docs/supplier-returns.md` para el
razonamiento completo de por qué no se reutilizó `DEVUELTO`.

## 5. Documentos adjuntos

`PurchaseDocumentAttachment` reutiliza literalmente
`apps.customers.file_validation` (`validar_archivo_adjunto`/
`nombre_original_seguro`) y el patrón de `SalesDocumentAttachment`
(FASE 10) — nunca un segundo sistema de archivos. Referencia genérica
(`document_type`/`document_id`) hacia orden de compra, recepción,
factura de proveedor o devolución a proveedor.

## 6. Pagos y cuentas por pagar: el espejo de cuentas por cobrar

`SupplierPayment`/`SupplierPaymentAllocation` son estructuralmente
idénticos a `Payment`/`PaymentAllocation` (FASE 10/11) — mismos
principios, ledger append-only, nunca un campo `balance` editado a
mano. Ver `docs/accounts-payable.md` para el diseño completo (anticipos,
saldo pendiente, pago en efectivo vía `apps.pos`, reversas).

**Explícitamente nunca mezclado con Cuentas por Cobrar**: `SupplierPayment`
nunca referencia un `Customer`; `Payment` (FASE 10) nunca referencia un
`Supplier` — dos ledgers paralelos, cada uno con su propia disciplina de
validación, sin ninguna tabla ni función compartida entre ambos salvo el
vocabulario común `PaymentMethod` (importado, no duplicado).

## 7. Autorizaciones (reutiliza `apps.approvals`, FASE 11)

`ApprovalPolicy` se amplió con dos dimensiones nuevas
(`max_purchase_order_amount`, `max_over_receiving_percent`), y
`ApprovalRequest.ActionType` con `PURCHASE_OVER_THRESHOLD`/
`OVER_RECEIVING` — reutilizando las mismas primitivas
(`check_*_authorization`/`request_approval`/`resolve_approval`/
`mark_consumed`/`get_usable_approved_request`) que ya usa `apps.pos`
para descuentos y crédito excedido, nunca una implementación paralela.
Ver `docs/purchase-orders.md` sección 5 y `docs/receiving.md` sección 4.

## 8. Trazabilidad obligatoria

Proveedor → Orden de compra → Recepción(es) → Producto →
`StockMovement`/`InventoryUnit` (con IMEI/serie para serializados) →
(opcional) Devolución a proveedor → (opcional) Factura de proveedor →
Pago(s), todo consultable end-to-end con usuario y fecha en cada paso —
mismo estándar que `Quotation → ProformaInvoice → Sale → Payment` en
FASE 10.

## 9. Moneda (sincronización posterior a FASE 12, especificación — ver `docs/currency.md`)

`PurchaseOrder.currency`/`SupplierInvoice.currency`/`SupplierPayment.currency`
ya existen como `CharField(max_length=3)`, snapshot de texto simple —
la doctrina oficial de moneda (`docs/currency.md`) no los migra ni
reemplaza con este documento. Preparado, no construido: moneda del
proveedor (ya vive en `Supplier.currency`, FASE 9, sin cambios), tipo
de cambio entre la moneda de la orden y la funcional del tenant
(`ExchangeRate`, conceptual) para reportes consolidados — sin motor de
conversión (FX) completo. Los costos históricos (`unit_cost` congelado
por línea, ver sección 3) se preservan exactamente igual, en la moneda
del documento en el momento de crearse, nunca reconvertidos
retroactivamente si cambia una tasa de cambio futura.

## 10. Qué NO se construyó en esta fase (deliberado)

- **Contabilidad general**: ningún libro mayor contable, ningún asiento
  de partida doble — el ledger de Cuentas por Pagar es una agregación de
  solo lectura sobre `SupplierPayment`/`SupplierPaymentAllocation`,
  igual que Cuentas por Cobrar.
- **Prorrateo de landed cost**: preparado a nivel de cabecera
  (`freight_cost`/`insurance_cost`/`other_costs`), no distribuido entre
  líneas/unidades (ver sección 3).
- **UI de dashboard/reportes real**: `apps.purchases.services` expone
  funciones de agregación de solo lectura (`get_open_purchase_orders_count`,
  `get_period_purchases_total`, `get_pending_supplier_invoices_total`,
  `get_total_supplier_advances`) para que FASE 7 (Dashboard)/FASE 14
  (Reportes) las consuman — ningún dashboard ni reporte nuevo se
  construye aquí.
- **Facturación fiscal electrónica** de la factura del proveedor:
  `SupplierInvoice` registra el número que el proveedor ya emitió, no
  genera ni valida un documento fiscal.
