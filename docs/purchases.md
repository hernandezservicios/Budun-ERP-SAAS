# Compras: Órdenes, Recepción, Costos y Cuentas por Pagar (especificación)

> **Estado: ESPECIFICACIÓN, no implementación.** Diseño aprobado para
> FASE 12 — ningún modelo, vista ni migración se crea a partir de este
> documento. FASE 12 debe releerlo antes de implementar, junto con
> `docs/phases/PHASE-12-purchases.md`.

## 1. Documentos independientes, no una sola entidad con estados

Mismo principio que FASE 10 (Cotización/Proforma/Venta): `PurchaseOrder`
(orden de compra) y `PurchaseReceipt` (recepción) son modelos
independientes, no una sola entidad con un campo `type` — la orden es
un compromiso de compra; la recepción es el evento físico que
efectivamente mueve inventario, y una orden puede recibirse en varias
entregas (recepción parcial).

**`PurchaseOrder`/`PurchaseOrderItem`**: cabecera (`tenant`, `supplier`,
`user` comprador, `currency`, `notes`, `status`, `number` — numeración
propia vía `DocumentSequence`/`generate_document_number`, nuevo
`DocumentType.PURCHASE`, prefijo p. ej. `OC-`) + líneas con snapshot
(`product`, `quantity`, `unit_cost` esperado, `total`). Estados:
`DRAFT → SENT → CONFIRMED/CANCELED`.

**`PurchaseReceipt`/`PurchaseReceiptItem`**: una recepción física contra
una orden (o, si el negocio lo permite, sin orden previa — decisión de
la fase). Cada línea de recepción referencia la línea de la orden que
cubre, con la `quantity_received` (puede ser menor a la pedida —
recepción parcial) y, para productos SERIALIZADOS, el/los IMEI/serie
concretos recibidos. Una orden puede tener múltiples recepciones hasta
completarse; `PurchaseOrder.status` refleja si está totalmente
recibida (mismo patrón que `Sale.status`/`_is_full_return` en FASE 10
para devoluciones — "totalmente recibida" se deriva de comparar todas
las recepciones contra las líneas originales, nunca un booleano
editado a mano).

## 2. Recepción e inventario: reutiliza literalmente FASE 8

- **Productos por CANTIDAD**: cada recepción llama a
  `apps.inventory.services.register_stock_in(product=..., quantity=...,
  user=..., notes=f"Recepción {numero_recepcion}")` — nunca se duplica
  esa lógica.
- **Productos SERIALIZADOS**: cada unidad físicamente recibida llama a
  `apps.inventory.services.register_serialized_unit(product=..., user=...,
  serial=...|imei_1=...|imei_2=..., unit_cost=..., entry_date=...,
  purchase_origin=<referencia legible a la recepción>)` — una llamada
  por IMEI/serie, nunca un alta masiva que no pase por esa función. La
  unidad queda automáticamente en `EN_STOCK`.
- **`InventoryUnit.purchase_origin`** (texto libre provisional desde
  FASE 8) se reemplaza aquí por una relación real:
  `PurchaseReceiptItem` debería tener su propia FK hacia
  `InventoryUnit` (o viceversa, según convenga al diseño final de esta
  fase) — nunca las dos direcciones a la vez.
- Nunca crear una `InventoryUnit`/`StockMovement` a mano fuera de
  `apps.inventory.services`: preserva las constraints de unicidad y
  las validaciones (IMEI 1 ≠ IMEI 2, al menos un identificador) en un
  único punto, exactamente como ya hace FASE 10 (Ventas).

## 3. Costos históricos (snapshot) y landed cost

Cada línea de recepción congela el costo real de esa entrega
(`unit_cost`) en el momento de recibirse — mismo principio de snapshot
histórico que `SaleItem`/`QuotationItem` (FASE 10): el costo de una
recepción ya registrada nunca cambia si el costo del producto cambia
después.

**Landed cost** (costo de flete/aduana/seguro prorrateado entre las
líneas de una recepción) se **prepara conceptualmente** aquí pero
**no se construye salvo necesidad real explícita** — mismo criterio ya
aplicado a `CustomerCreditLedger`/facturación fiscal en fases
anteriores: no agregar campos/lógica sin un caso de uso real que los
llene. Si se construye, debe ser un ajuste explícito sobre
`unit_cost` de cada línea, nunca un cálculo oculto o un campo
paralelo.

## 4. Devoluciones a proveedor

`SupplierReturn`/`SupplierReturnItem` (o el nombre que decida la
fase): mismo principio de inmutabilidad que `Return` (FASE 10) —
sin estados, sin cancelación, una operación correctiva en sí misma.
Efecto en inventario: productos por CANTIDAD vía
`register_stock_out`; productos SERIALIZADOS transicionando la unidad
según la máquina de estados de FASE 8 (nunca escribir el estado a
mano). Documenta el motivo y referencia la recepción/orden de origen
para trazabilidad completa (Orden → Recepción → Devolución a
proveedor).

## 5. Documentos adjuntos

Reutiliza literalmente `apps.customers.file_validation`
(`validar_archivo_adjunto`/`nombre_original_seguro`) y el patrón de
`SalesDocumentAttachment` (FASE 10) — nunca un segundo sistema de
archivos. Adjuntar facturas de proveedor, guías de remisión, etc. a la
orden o a la recepción mediante una referencia genérica
(`document_type`/`document_id`), igual que `apps.sales`.

## 6. Pagos y cuentas por pagar: mismo patrón que cuentas por cobrar

Cuentas por pagar es el espejo de cuentas por cobrar (FASE 9/10/11) —
**mismos principios, nunca un motor contable completo sin necesidad
real**:

- **Anticipo a proveedor**: dinero entregado antes de una recepción
  definitiva — análogo a un `Payment` sin aplicar en cuentas por
  cobrar, aquí representable como un pago a proveedor sin aplicar a
  ninguna orden/recepción todavía. Nunca es una compra en sí misma.
- **Saldo pendiente por pagar**: se deriva siempre de un ledger real
  (pagos a proveedor aplicados a órdenes/recepciones), nunca un campo
  `balance` editado a mano — mismo principio que
  `get_sale_balance_due`/`get_customer_credit_balance` en `apps.sales`.
- **Pago en efectivo desde caja**: si esta fase permite pagar una
  recepción en efectivo desde una `CashRegister` física, requiere una
  `CashSession` `OPEN` (`apps.pos.services.ensure_open_session_for_checkout`)
  exactamente igual que una venta de mostrador — otros medios de pago
  (transferencia, cheque) no afectan el efectivo físico de la caja.
- Los campos comerciales de `Supplier` (`payment_terms`, `credit_days`,
  `credit_enabled`, `currency`, ya preparados desde FASE 9) son la
  configuración real que esta fase debe leer al decidir condiciones de
  pago — nunca reinventar esos campos en `apps.purchases`.
- Registrar todo evento de compra en el historial del proveedor (la
  pestaña "Historial" del detalle de proveedor, FASE 9, hoy muestra un
  estado vacío explícito esperando esta fase).

## 7. Autorizaciones (reutiliza `apps.approvals`, FASE 11)

Cualquier excepción que esta fase necesite autorizar (una recepción
con discrepancia de cantidad/costo fuera de tolerancia, un ajuste de
costo post-recepción, un pago a proveedor que excede una política)
debe pasar por `apps.approvals.services`
(`request_approval`/`resolve_approval`/jerarquía usuario→rol→tenant→
negar) — nunca una implementación paralela. Ver `docs/approvals.md`
sección 7, que ya anticipa "ajustes de inventario" como una de las
operaciones autorizables futuras que esta fase conectaría.

## 8. Trazabilidad obligatoria

Orden de compra → Recepción(es) → (opcional) Devolución a proveedor →
(opcional) Pago a proveedor, todo consultable end-to-end — mismo
estándar que `Quotation → ProformaInvoice → Sale → Payment` en FASE 10.

## 9. Qué NO se construye con este documento

Ningún modelo (`PurchaseOrder`, `PurchaseReceipt`, `SupplierReturn`,
ledger de cuentas por pagar), ningún campo nuevo en `Supplier`/
`InventoryUnit`, ninguna migración, ninguna vista. Diseño aprobado
para que FASE 12 lo implemente sin re-derivarlo desde cero ni inventar
una arquitectura incompatible con `apps.inventory`/`apps.customers`/
`apps.pos`/`apps.approvals`.
