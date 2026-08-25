# FASE 12 — Purchases + Purchase Orders + Receiving + Costs + AP preparation

## Objetivo
Órdenes de compra, recepciones parciales/completas (productos por
cantidad y serializados, con IMEI/serie en la recepción), costos
históricos, landed cost preparado (sin construirlo todavía si no hay
necesidad real), devoluciones a proveedor, documentos adjuntos,
reutilización de `apps.approvals` para cualquier autorización que
corresponda, y preparación de cuentas por pagar (incluyendo anticipos
a proveedores) — mismo criterio que FASE 9/10 con cuentas por cobrar:
preparar el dominio sin construir un motor contable completo salvo que
el usuario lo pida explícitamente. Ver la sección "Nota de
sincronización" más abajo y `docs/purchases.md` para el diseño
detallado.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] `PurchaseOrder`/`PurchaseOrderItem` — flujo de orden de compra (borrador → enviada → parcialmente recibida/recibida/cerrada/cancelada), numeración propia vía `DocumentSequence` (`OC-`).
- [x] Recepción parcial y completa — `PurchaseReceipt`/`PurchaseReceiptItem`, pudiendo recibir una orden en varias entregas (`REC-`).
- [x] Recepción de productos por CANTIDAD — impacta inventario vía `apps.inventory.services.register_stock_in`, nunca duplicando esa lógica.
- [x] Recepción de productos SERIALIZADOS — alta de `InventoryUnit` por IMEI/serie vía `apps.inventory.services.register_serialized_unit`, una unidad por cada IMEI/serie recibido.
- [x] Costos históricos por línea (snapshot al recibir, mismo principio que `SaleItem`/`QuotationItem` en FASE 10 — nunca recalculado desde el costo actual del producto); landed cost preparado a nivel de cabecera (flete/seguro/otros costos), sin prorrateo por línea.
- [x] Devoluciones a proveedor (mercancía) — inmutables, mismo principio que `Return` de FASE 10; nuevo estado `InventoryUnit.Status.DEVUELTO_PROVEEDOR` para serializados.
- [x] Documentos adjuntos — reutilizando la validación de archivos de FASE 9 (`apps.customers.file_validation`), nunca un segundo sistema de archivos.
- [x] Pago en efectivo desde caja requiere `CashSession` abierta (`apps.pos`, FASE 11) — otros medios no afectan el efectivo físico.
- [x] Cuentas por pagar y anticipos a proveedores — `SupplierPayment`/`SupplierPaymentAllocation`, espejo exacto de `Payment`/`PaymentAllocation`, sin motor contable completo.
- [x] Autorizaciones (`apps.approvals`, FASE 11) — compra sobre el límite (`PURCHASE_OVER_THRESHOLD`) y sobre-recepción (`OVER_RECEIVING`), dos dimensiones nuevas en `ApprovalPolicy`.
- [x] tests (unitarios, integración, Multi-Tenant, concurrencia) — 44 tests nuevos en `apps/purchases/tests/`.

## Verificación
- [x] `python manage.py check` en verde.
- [x] Tests relevantes ejecutados (44/44 en `apps.purchases`; suite completa del proyecto sin regresiones).
- [x] Smoke test HTTP realizado contra la base de datos real de desarrollo.
- [x] Seguridad revisada para el alcance de la fase (Multi-Tenant, autorización, documentos).
- [x] Documentación actualizada.
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado.

## Nota de FASE 8 — Interfaz de Inventario Serializado a consumir

FASE 8 agregó `apps/inventory/services.register_serialized_unit(...)`
(ver `docs/inventory.md`) como la única vía sancionada para dar de alta
una `InventoryUnit` nueva. Al recibir una compra de un producto
SERIALIZADO, esta fase debe:

- Por cada unidad física recibida, llamar a `register_serialized_unit`
  con `product`, `user`, y al menos uno de `serial`/`imei_1`/`imei_2`,
  más `unit_cost` (del costo real de esa compra) y `entry_date`. La
  unidad queda automáticamente en estado `EN_STOCK`.
- Pasar `purchase_origin` con una referencia legible a la compra/orden
  de FASE 12 (por ahora ese campo es texto libre en `InventoryUnit`,
  documentado como provisional en `docs/inventory.md`; cuando exista el
  modelo `Purchase` real, lo natural es que `Purchase`/`PurchaseItem`
  referencien a `InventoryUnit` con su propia FK, no al revés).
- Para productos por CANTIDAD, la recepción de compra sigue impactando
  el inventario vía `services.register_stock_in` (StockMovement),
  exactamente igual que hoy.
- Nunca crear una `InventoryUnit` a mano (fuera de `services.py`): así se
  preservan las constraints de unicidad por tenant y las validaciones
  (IMEI 1 ≠ IMEI 2, al menos un identificador) en un único punto.

## Nota de FASE 9 — Interfaz de Proveedores a consumir

FASE 9 agregó `apps/customers` (`Supplier`, ver `docs/suppliers.md`).
Esta fase debe integrarse con esa interfaz ya existente, sin
reinventarla:

- `Purchase`/`PurchaseItem` deben referenciar a `Supplier` mediante su
  propia FK (`Purchase.supplier`, `on_delete=PROTECT` recomendado), no
  al revés.
- Reutilizar `apps.customers.services.get_active_suppliers(tenant)`
  para poblar cualquier selector de proveedor.
- Los campos comerciales de `Supplier` (`payment_terms`, `credit_days`,
  `credit_enabled`, `currency`) ya están preparados desde FASE 9 sin
  ningún motor financiero detrás — esta fase (o una fase de cuentas por
  pagar) es responsable de calcular cualquier saldo/deuda real y de
  decidir cómo aplicar esas condiciones a una compra concreta.
- Registrar aquí cualquier evento de compra en el historial del
  proveedor: la pestaña "Historial" del detalle de proveedor (FASE 9)
  hoy muestra un estado vacío explícito esperando esta fase.

## Nota de FASE 10 — Interfaz del motor comercial a consumir (trazabilidad, no ventas)

FASE 10 construyó `apps/sales` (ver `docs/sales.md`). Compras no
necesita la mayoría de ese motor (Cotizaciones/Proformas/Pagos son
conceptos de venta, no de compra), pero sí debe respetar:

- **No duplicar numeración**: si Compras necesita su propio número
  comercial, reutilizar el patrón de `DocumentSequence`/
  `generate_document_number` (agregando un `DocumentType.PURCHASE`), no
  inventar un esquema de numeración distinto.
- **`InventoryUnit.purchase_origin`** (texto libre provisional desde
  FASE 8) debería reemplazarse por una FK real de `Purchase`/
  `PurchaseItem` hacia `InventoryUnit` — ya anticipado en la nota de
  FASE 8 arriba, sigue vigente sin cambios.
- El `salesperson`/comprador responsable de una compra puede seguir el
  mismo patrón que `Sale.salesperson` (FK a usuario, `SET_NULL`) para
  consistencia, aunque es una decisión de esta fase.

## Nota de sincronización — Caja y Autorizaciones ya construidas (FASE 11)

FASE 11 construyó `apps.pos` (`CashRegister`/`CashSession`/
`CashMovement`, ver `docs/cash-registers.md`) y `apps.approvals`
(`ApprovalPolicy`/`ApprovalRequest`, ver `docs/approvals.md`) como
servicios reales y reutilizables — esta fase debe consumirlos tal
cual, nunca reimplementar su lógica:

- **Pago en efectivo de una compra**: si esta fase permite pagar una
  compra en efectivo desde una caja física, requiere una `CashSession`
  `OPEN` exactamente igual que una venta de mostrador
  (`apps.pos.services.ensure_open_session_for_checkout`/
  `record_cash_movement`, con un `CashMovement.MovementType` nuevo si
  hace falta uno específico para "pago a proveedor" — nunca duplicar
  el cálculo de efectivo esperado). Otros medios de pago no afectan el
  efectivo físico.
- **Autorizaciones**: cualquier descuento/excepción de esta fase que
  necesite aprobación (p. ej. un ajuste de costo fuera de rango, una
  recepción con discrepancia) debe usar `apps.approvals.services`
  (`request_approval`/`resolve_approval`/`check_*_authorization`),
  nunca una implementación paralela — ver `docs/approvals.md` sección
  7 ("Operaciones autorizables futuras"), que ya anticipa ajustes de
  inventario como caso de uso de esta fase.
- **Cuentas por pagar**: preparar el dominio siguiendo exactamente el
  mismo criterio que cuentas por cobrar (FASE 9/10/11) — un anticipo a
  proveedor es un pago sin aplicar, un saldo a favor del proveedor se
  deriva de ledgers reales, nunca un campo `balance` editable. Ver
  `docs/purchases.md` para el diseño detallado (especificación, sin
  implementación todavía).

## Evidencia (FASE 12)

- Arquitectura: `apps/purchases`, orquestación pura sobre `apps.customers` (Suppliers), `apps.inventory` (register_stock_in/register_stock_out/register_serialized_unit/transition_unit_status), `apps.approvals` (autorizaciones) y `apps.pos` (caja) — nunca un segundo motor de inventario/aprobaciones/caja/archivos. Reutiliza literalmente la `DocumentSequence` de `apps.sales` (tres tipos de documento nuevos: `OC-`/`REC-`/`DEVP-`).
- `PurchaseOrder`/`PurchaseOrderItem`: borrador → enviada → parcialmente recibida/recibida/cerrada/cancelada; `PurchaseOrderItem` nunca guarda recibido/pendiente como campo (siempre agregado sobre `PurchaseReceiptItem`, con variante en bloque sin N+1).
- `PurchaseReceipt`/`PurchaseReceiptItem`: inmutable, recepción parcial/completa verificada con el ejemplo exacto de la especificación (10 → 6+4). QUANTITY vía `register_stock_in`; SERIALIZED vía `register_serialized_unit`, una llamada por IMEI/serie (verificado: 2 unidades recibidas = 2 `InventoryUnit` reales).
- Sobre-recepción rechazada por defecto (`OverReceivingRequiresApproval`), autorizable vía `apps.approvals` (`ApprovalPolicy.max_over_receiving_percent`, `ActionType.OVER_RECEIVING`) — mismo flujo bloquear→solicitar→aprobar→reintentar que descuentos/crédito excedido en FASE 11. Compra sobre el límite (`PurchaseOverThresholdRequiresApproval`, `max_purchase_order_amount`) con el mismo patrón.
- `SupplierInvoice`/`SupplierInvoiceItem`: borrador → confirmada/cancelada; número del PROVEEDOR (no generado por nosotros), único por `(tenant, supplier)`.
- Cuentas por pagar: `SupplierPayment`/`SupplierPaymentAllocation`, espejo estructural exacto de `Payment`/`PaymentAllocation` (FASE 10/11) pero un ledger completamente independiente — nunca mezclado con Cuentas por Cobrar. Anticipo a proveedor = `SupplierPayment` sin aplicar. Pago en efectivo exige `CashSession` abierta y genera `CashMovement` propio (`SUPPLIER_PAYMENT_CASH`/`SUPPLIER_ADVANCE_CASH`).
- `SupplierReturn`/`SupplierReturnItem`: inmutable. Nuevo estado terminal `InventoryUnit.Status.DEVUELTO_PROVEEDOR` (migración aditiva sobre `apps.inventory`) para unidades serializadas devueltas al proveedor — nunca se reutilizó `DEVUELTO`, que significa lo opuesto.
- 1 bug real encontrado por el smoke test HTTP (no por los tests unitarios): `receive_purchase_order` usaba `dict.get(clave, default)` para el costo unitario opcional, que no cae al `default` cuando la clave está presente con valor `None` (el caso real desde la vista) — corregido con una comprobación explícita, 2 tests de regresión agregados. Ver `KNOWN_ISSUES.md` #81.
- Concurrencia: 5 escenarios con hilos reales (`TransactionTestCase`) — recepción simultánea de la misma orden (una gana, la otra requiere autorización), sobre-recepción simultánea que comparte una misma aprobación (se consume una sola vez), registro simultáneo del mismo IMEI en órdenes distintas (la constraint de FASE 8 rechaza una), devolución simultánea de la misma unidad (una gana), y dos recepciones simultáneas que juntas completan exactamente una orden sin doble conteo.
- Multi-Tenant: cobertura dedicada en `apps/purchases/tests/test_isolation.py` (proveedor/producto de otro tenant rechazados a nivel de servicio, orden de otro tenant invisible, pago de un tenant no aplicable a factura de otro, detalle de orden de otro tenant → 404 vía HTTP).
- 50 tests nuevos en `apps.purchases` (todos verdes); suite completa del proyecto ejecutada sin regresiones.
- Smoke test HTTP real contra PostgreSQL de desarrollo: crear orden → agregar líneas (cantidad + serializado) → enviar → recibir parcial → recibir completo (incluyendo 2 IMEI reales) → registrar factura → confirmar → pagar → registrar anticipo → devolución a proveedor → aislamiento Multi-Tenant (404 cross-tenant) — 34/34 verificaciones OK.
- Documentado en `docs/purchases.md` (actualizado de especificación a "construido"); nuevos `docs/purchase-orders.md`, `docs/receiving.md`, `docs/supplier-invoices.md`, `docs/accounts-payable.md`, `docs/supplier-returns.md`. `CLAUDE.md`/`docs/MASTER-PROMPT.md`/`ARCHITECTURE.md` actualizados con la doctrina permanente de Compras y Cuentas por Pagar.
- Ningún módulo de negocio adicional (Gastos, Reportes, Roles/Audit/API, PayPal, Billing) fue construido; prorrateo de landed cost y varios de los 6 escenarios de autorización mencionados quedan como primitivas genéricas reutilizables sin UI dedicada — ver `KNOWN_ISSUES.md` #77/#78.

## Nota de sincronización — Moneda, denominaciones y cierre de caja

Doctrina oficial agregada en `docs/currency.md` (sin implementación,
sin cambios de código en `apps.purchases`): `PurchaseOrder.currency`/
`SupplierInvoice.currency`/`SupplierPayment.currency`, ya existentes,
siguen siendo válidos exactamente como están — el catálogo real
(`Currency`/`CurrencyDenomination`) no los migra ni reemplaza. Tipo de
cambio y costos históricos preservados en la moneda del documento
quedan preparados conceptualmente, sin motor de FX completo. Ver
`docs/currency.md`/`docs/purchases.md` sección "Moneda".

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Suite completa del proyecto: 554/554 tests OK (502 de fases anteriores sin cambios de lógica + 52 nuevos de `apps.purchases`, incluyendo los 2 tests de regresión del bug de `unit_cost` agregados después de la primera corrida de verificación — corregido en la sincronización de Moneda posterior, ver nota más abajo). Esperando autorización explícita para iniciar FASE 13 — Expenses.

**Corrección de conteo (sincronización de Moneda posterior a esta fase)**: el reporte de cierre original de esta fase citó "552/552 tests OK", contado por una corrida de verificación que arrancó como proceso justo antes de agregarse los 2 tests de regresión de `unit_cost` a `test_receiving.py` — ambos tests ya estaban en el commit de esta fase (`fa077f9`), simplemente no alcanzaron a contarse en esa corrida puntual. Una corrida completa posterior confirmó el conteo real: 554/554, sin ningún cambio de código adicional.
