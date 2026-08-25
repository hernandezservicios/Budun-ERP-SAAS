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
- [ ] `PurchaseOrder`/`PurchaseOrderItem` — flujo de orden de compra (borrador → enviada → confirmada/cancelada), numeración propia vía `DocumentSequence`.
- [ ] Recepción parcial y completa — `PurchaseReceipt`/`PurchaseReceiptItem` (o equivalente), pudiendo recibir una orden en varias entregas.
- [ ] Recepción de productos por CANTIDAD — impacta inventario vía `apps.inventory.services.register_stock_in`, nunca duplicando esa lógica.
- [ ] Recepción de productos SERIALIZADOS — alta de `InventoryUnit` por IMEI/serie vía `apps.inventory.services.register_serialized_unit`, una unidad por cada IMEI/serie recibido.
- [ ] Costos históricos por línea (snapshot al recibir, mismo principio que `SaleItem`/`QuotationItem` en FASE 10 — nunca recalculado desde el costo actual del producto).
- [ ] Devoluciones a proveedor (mercancía) — inmutables, mismo principio que `Return` de FASE 10.
- [ ] Documentos adjuntos — reutilizando la validación de archivos de FASE 9 (`apps.customers.file_validation`), nunca un segundo sistema de archivos.
- [ ] Pago en efectivo desde caja requiere `CashSession` abierta (`apps.pos`, FASE 11) — otros medios no afectan el efectivo físico.
- [ ] Preparación de cuentas por pagar y anticipos a proveedores — sin motor contable completo, mismo criterio que cuentas por cobrar en FASE 9/10.
- [ ] tests (unitarios, integración, Multi-Tenant, concurrencia donde aplique)

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

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

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
