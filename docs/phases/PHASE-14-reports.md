# FASE 14 — Reports

## Objetivo
Reportes de ventas, inventario, productos, clientes, compras, gastos y utilidad; filtros y exportaciones según alcance.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] filtros
- [ ] tenant scoped
- [ ] queries optimizadas

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 8 — Interfaz de Inventario Serializado a consumir

Los reportes de inventario/stock deben distinguir explícitamente los dos
tipos de seguimiento definidos en FASE 8 (`Product.inventory_tracking_type`,
ver `docs/inventory.md`), nunca sumarlos como si fueran una sola cifra
homogénea:

- Productos por CANTIDAD: cantidad disponible desde `StockMovement`
  (vía `services.get_current_stock`/`services.list_products_with_stock`).
- Productos SERIALIZADOS: conteo de unidades por estado desde
  `InventoryUnit` (p. ej. cuántas `EN_STOCK`, cuántas `VENDIDO`,
  `REPARACION`, `GARANTIA`, etc. — cada estado es una dimensión de
  reporte útil que no existe para productos por cantidad).
- Reutilizar `services.get_current_stock`/`services.list_products_with_stock`
  (que ya devuelven el valor correcto para ambos tipos vía el mismo
  campo anotado `current_stock`) en vez de recalcular el stock con una
  consulta propia — evita una tercera fuente de verdad.

## Nota de FASE 9 — Interfaz de Clientes/Proveedores a consumir

FASE 9 agregó `apps/customers` (`Customer`/`Supplier`, ver
`docs/customers.md`/`docs/suppliers.md`). Los reportes "ventas por
cliente" y "compras por proveedor" pedidos para esta fase deben:

- Agregar `SaleItem`/`PurchaseItem` (FASE 10/12) agrupados por
  `customer`/`supplier`, reutilizando
  `services.list_customers`/`list_suppliers`/`get_active_customers`/
  `get_active_suppliers` como fuente de la lista de clientes/proveedores
  — nunca reimplementar esa consulta ni duplicar datos de contacto en
  el módulo de reportes.
- "Clientes activos"/"proveedores activos" (pedido explícitamente) se
  obtienen directamente de `get_active_customers`/`get_active_suppliers`
  (ya filtran por `is_active=True` y por tenant) — no hace falta ningún
  cálculo adicional.

## Nota de FASE 10 — Interfaz del motor comercial a consumir

FASE 10 agregó el motor comercial completo (`apps/sales`, ver
`docs/sales.md`). Los reportes pedidos para esta fase deben reutilizar,
no recalcular:

- **Ventas por cliente/producto/serial/vendedor**: agregar `SaleItem`
  (`sale__customer`, `product`, `inventory_unit`, `sale__salesperson`
  respectivamente) filtrado por `sale__status = CONFIRMED` (o
  `RETURNED`/`PARTIALLY_RETURNED` si el reporte quiere neto de
  devoluciones) — cada línea ya tiene su snapshot histórico
  (`unit_price`, `tax_rate`, `total`), así que el reporte nunca necesita
  volver a leer `Product` para calcular importes históricos.
- **Cotizaciones/conversiones/proformas/facturas**: contar/agrupar por
  `status` de `Quotation`/`ProformaInvoice`/`Sale` respectivamente;
  "tasa de conversión" = cotizaciones en `CONVERTED` sobre el total no
  `CANCELED`/`EXPIRED`.
- **Pagos**: agregar `Payment` (`status=CONFIRMED`) por `method`/fecha;
  usar `Sale.payment_status` (ya calculado, ver `docs/payments.md`) para
  "ventas pendientes de cobro" sin recalcular la suma de pagos. Para el
  monto exacto pendiente por factura o por cliente, reutilizar
  `services.get_sale_balance_due`/`get_customer_pending_sales`/
  `get_customer_credit_balance` (ampliación de FASE 10:
  `Payment`/`PaymentAllocation`) en vez de recalcular el ledger — un
  reporte de "cuentas por cobrar" es una agregación sobre estas mismas
  funciones, no una fuente de verdad nueva.
- **Devoluciones**: agregar `ReturnItem`/`Return` — nunca inventar un
  cálculo de "devuelto" distinto al que ya usa
  `services._is_full_return`.
- **Descuentos e impuestos**: ya están en el snapshot de cada línea
  (`discount_amount`, `tax_amount`) — un reporte de "descuentos
  otorgados" o "impuesto recaudado" es una agregación directa sobre
  `SaleItem`, sin recalcular nada.

## Nota de sincronización — Cuentas por Cobrar y Caja a reportar

Sincronización de doctrina previa a FASE 11, sin implementación nueva.
Cuando los modelos correspondientes existan (`CustomerCreditLedger`,
`CreditNote`, `CashRegister`/`CashSession`, `ApprovalRequest`), esta
fase debe poder reportar, siempre como agregación de lectura sobre
esos modelos (nunca recalculando el saldo con una consulta propia):

- **Anticipos**: `Payment` sin `PaymentAllocation` (saldo sin aplicar
  por cliente), ver `docs/accounts-receivable.md`.
- **Notas de crédito**: emitidas, aplicadas parcial/totalmente,
  canceladas — agregando `CreditNote`/`CreditNoteApplication`.
- **Refunds**: dinero devuelto vs. convertido a crédito.
- **Saldo pendiente / saldo a favor**: por factura
  (`get_sale_balance_due`) y por cliente
  (`get_customer_credit_balance`/`CustomerCreditLedger` cuando exista).
- **Estados de cuenta**: la vista "Customer Statement" descrita en
  `docs/accounts-receivable.md` (sección 6) es responsabilidad de esta
  fase.
- **Apertura/cierre de caja**: sobrantes y faltantes por sesión,
  agregando `CashSession.difference` — ver `docs/cash-registers.md`.
- **Descuentos autorizados / créditos aprobados excepcionalmente**:
  agregando `ApprovalRequest` por tipo/estado — ver `docs/approvals.md`.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
