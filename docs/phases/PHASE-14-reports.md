# FASE 14 — Contabilidad General + Reportes Profesionales

## Objetivo (ampliado por el usuario al autorizar esta fase)

La especificación original de esta fase (`FASES_OFICIALES_0_24_ACTUALIZADAS.md`)
cubría solo un módulo de reportes. El usuario amplió el alcance
explícitamente al autorizarla — "una de las fases arquitectónicamente
más importantes del ERP" — a dos dominios: **1. Motor de Contabilidad
General** (`apps.accounting`) y **2. Plataforma Integral de Reportes**
(`apps.reports`), con la contabilidad como fuente financiera central:
"Los reportes no deben recalcular cifras financieras de forma
independiente cuando la información deba provenir de contabilidad."
Ver `docs/accounting.md`/`docs/reports.md` para el diseño completo de
cada dominio.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación

### Motor de Contabilidad General (`apps.accounting`) — CONSTRUIDO
- [x] `Account`: plan de cuentas jerárquico (`parent`, `level` calculado una vez al crear), tipo/naturaleza deudora-acreedora derivada automáticamente, `allows_posting` para cuentas de agrupación
- [x] `AccountingPeriod`: `OPEN/CLOSING/CLOSED/REOPENED`, sin `DocumentSequence` (no es un documento emitido), nunca se solapa con otro período no cerrado del mismo tenant
- [x] `JournalEntry`/`JournalEntryLine`: partida doble (débito XOR crédito por línea, `SUM(débitos)==SUM(créditos)` obligatorio para `POSTED`), numerado vía `DocumentSequence` (`AST-`)
- [x] Inmutabilidad: un asiento `POSTED` nunca se edita ni se borra — `reverse_journal_entry` (idempotente) es la única corrección
- [x] Contabilización automática (`record_business_event`, idempotente por `tenant`+`source_type`+`source_event_key`) vía `AccountMapping`: 4 integraciones reales conectadas (venta confirmada, pago de cliente, pago de gasto, pago de nómina) — resiliente por diseño (`try_record_*` nunca relanza, mapeo faltante nunca bloquea la operación)
- [x] Reportes contables: Balance de Comprobación, Libro Mayor, Libro Diario, Balance General (acumulado), Estado de Resultados (acotado al período)
- [x] Multi-Tenant verificado (cuenta padre/mapeo de otro tenant rechazados, 404 cruzando tenant)

### Plataforma de Reportes (`apps.reports`) — CONSTRUIDO
- [x] Ventas, Inventario, Caja, Cuentas por Cobrar (con aging), Cuentas por Pagar (con aging), Compras, Gastos, RRHH, Nómina, Clientes, Proveedores, panel gerencial (resumen ejecutivo) — cada uno `{"summary": ..., "rows": ...}`, agregando sobre servicios/modelos ya existentes, nunca una segunda fuente de verdad
- [x] Drill-down: cada fila enlaza al documento origen ya existente, nunca una copia de esos datos
- [x] Exportación CSV en Ventas/Gastos/Cuentas por Cobrar/Cuentas por Pagar
- [x] Información sensible de RRHH/Nómina (salario, datos bancarios): filtrada en el SERVIDOR (`PayrollReportView`, reutilizando `can_view_sensitive_employee_data` de FASE 13), nunca solo oculta en la plantilla
- [x] Multi-Tenant verificado (reportes aislados por tenant)

## Verificación
- [x] `python manage.py check` en verde en cada commit
- [x] Tests: 45 (`apps.accounting`) + 16 (`apps.reports`) — servicios, HTTP, Multi-Tenant, idempotencia de contabilización automática, resiliencia (mapeo faltante no rompe la venta/pago/gasto/nómina), Balance-Sheet-acumulado-vs-Estado-de-Resultados-por-período
- [x] Bug real encontrado y corregido (test-driven): `get_accounts_receivable_report`/`get_accounts_payable_report` usaban el manager tenant-scoped (`Customer.objects`/`Supplier.objects`, requiere contexto de request HTTP) en vez de `all_objects` — corregido, ver `docs/project-status/KNOWN_ISSUES.md`
- [x] Smoke test HTTP dedicado a Contabilidad + Reportes contra PostgreSQL de desarrollo
- [x] Regresión completa de FASE 3–14 sin cambios de lógica en fases anteriores
- [x] Seguridad revisada: datos sensibles de RRHH/Nómina nunca expuestos solo por ocultarlos en la plantilla
- [x] Documentación: `docs/accounting.md` (nuevo), `docs/accounting-periods.md`/`docs/journal.md`/`docs/general-ledger.md` (punteros a `docs/accounting.md`, consolidación documentada), `docs/reports.md` (reescrito de especificación a construido)
- [x] `docs/project-status/CURRENT_PHASE.md`/`PHASE_HISTORY.md`/`KNOWN_ISSUES.md`/`DECISIONS.md` actualizados
- [x] Git commit: dos commits de dominio (`apps.accounting`, `apps.reports`) + un commit de cierre de documentación

## Ampliación de cierre de FASE 14 (COGS, Compras/AP, Cierre de Caja, Impuestos multi-código)

Cierre inicial de FASE 14 dejó documentadas 4 integraciones sin
conectar por falta de decisiones de política contable. El usuario las
entregó explícitamente en una instrucción posterior ("cierre contable
controlado", sin rehacer FASE 14, sin iniciar FASE 15) — construido en
commits de dominio adicionales:

- [x] Costeo: SERIALIZED costo específico (sin cambios); QUANTITY
  promedio ponderado nuevo (`StockMovement.unit_cost`/
  `average_cost_after`) — nunca FIFO.
- [x] COGS: asiento separado del de ingresos, reverso proporcional en
  devoluciones, `Refund` monetario nunca lo afecta.
- [x] Compras/Cuentas por Pagar: factura de proveedor confirmada, pago
  a proveedor, devolución a proveedor — todos contabilizados,
  distinguiendo inventario de gasto operativo.
- [x] Cierre de caja: Cash Over/Cash Short en `close_cash_session`.
- [x] Impuestos multi-código: `TaxCode`/`SaleItemTax`, aditivo, solo
  Ventas por ahora.
- [x] Reportes: margen bruto en Ventas, valorización de inventario +
  reconciliación contable, Estados de Cuenta de Cliente/Proveedor.
- [x] Exportación PDF/XLSX real (`reportlab`/`openpyxl`, aprobados
  explícitamente por el usuario) en los reportes tabulares principales.
- [x] Tests nuevos, regresión completa, smoke test ampliado.
- [x] Documentación sincronizada (`docs/accounting.md` secciones 11-16,
  `docs/reports.md`, `docs/inventory.md`, `docs/currency.md`,
  `docs/accounts-payable.md`, `CLAUDE.md`/`MASTER-PROMPT.md`/
  `ARCHITECTURE.md`, este archivo, `PHASE_HISTORY.md`/
  `KNOWN_ISSUES.md`/`DECISIONS.md`).

Deliberadamente NO construido en esta ampliación (documentado, no
inventado): GRNI (recibido-no-facturado), impuestos multi-código en
Compras, retenciones/normativa fiscal de país específico, Flujo de
Efectivo/Patrimonio como estados formales, reportes programados,
streaming/paginación real de grandes volúmenes.

## Reportes de Inventario (requisito explícito, sección dedicada)

Los reportes de inventario/stock deben distinguir explícitamente los dos
tipos de seguimiento definidos en FASE 8 (`Product.inventory_tracking_type`,
ver `docs/inventory.md`), nunca sumarlos como si fueran una sola cifra
homogénea, y deben cubrir como mínimo:

- **Existencias**: stock actual, reservado (`apps.sales.services.get_reserved_quantity`,
  FASE 10), disponible para prometer (`get_available_to_promise`) y
  comprometido (cantidad ya incluida en cotizaciones/proformas
  vigentes, si el negocio lo distingue de "reservado") — nunca un
  único número que mezcle las cuatro dimensiones.
- **Productos por cantidad vs. serializados, activos/inactivos**:
  segmentar siempre por `inventory_tracking_type` y por `is_active`.
- **Bajo stock y agotados**: reutilizar `services.get_low_stock_products`
  (ya construido, FASE 8), nunca recalcular el umbral con una consulta
  propia.
- **Movimientos**: entradas, salidas, ajustes y devoluciones —
  agregando `StockMovement` por `movement_type` (productos por
  cantidad).
- **Serializados**: IMEI, serial, estado, fecha, usuario y producto de
  cada `InventoryUnit` — conteo de unidades por estado (`EN_STOCK`,
  `VENDIDO`, `RESERVADO`, `DEVUELTO`, `REPARACION`, `GARANTIA`,
  `DANADO`, `PERDIDO`; cada estado es una dimensión de reporte útil que
  no existe para productos por cantidad). Nunca exponer el IMEI/serie
  completo en un reporte sin necesidad real — mismo principio de
  seguridad que `apps.inventory.services`/la API de Inventario (FASE 15).
- **Trazabilidad completa de movimientos**: un reporte de "historial de
  un producto/unidad" debe poder listar, en orden, cada `StockMovement`/
  transición de `InventoryUnit` con su usuario/fecha/motivo/documento
  de origen (compra, venta, devolución, ajuste).
- **Valorización**: preparada (costo × cantidad por producto/categoría)
  pero sin construir un motor de valorización completo (FIFO/promedio
  ponderado, etc.) salvo necesidad real explícita — mismo criterio de
  "no adelantar contabilidad" ya aplicado en todo el proyecto.
- Reutilizar `services.get_current_stock`/`services.list_products_with_stock`
  (que ya devuelven el valor correcto para ambos tipos vía el mismo
  campo anotado `current_stock`) en vez de recalcular el stock con una
  consulta propia — evita una tercera fuente de verdad.

## Reportes de Caja (FASE 11, `apps.pos`, ya construido)

- Aperturas y cierres por caja/usuario/período, agregando `CashSession`.
- Ventas en efectivo, entradas, salidas, devoluciones en efectivo —
  agregando `CashMovement` por `movement_type`, reutilizando
  `apps.pos.services.get_expected_cash` como referencia de cálculo,
  nunca recalculando el efectivo esperado con una consulta propia.
- Sobrantes/faltantes: `CashSession.difference` por sesión/caja/período.

## Reportes de Cuentas por Pagar (FASE 12, ya construido)

FASE 12 construyó `apps.purchases` (`SupplierPayment`/
`SupplierPaymentAllocation`, ver `docs/accounts-payable.md`) y dejó
preparadas las agregaciones de solo lectura que esta fase debe
consumir, nunca reimplementar: `get_open_purchase_orders_count`,
`get_period_purchases_total`, `get_pending_supplier_invoices_total`
(saldo pendiente total, vía `get_invoice_balance_due_bulk`),
`get_total_supplier_advances`. Equivalentes a los de cuentas por
cobrar (ver más abajo) pero del lado de `Supplier`: órdenes/recepciones
pendientes, pagos a proveedor, anticipos, saldo pendiente por
proveedor — siempre una agregación sobre el ledger real, nunca una
fuente de verdad nueva.

## Nota de FASE 9 — Interfaz de Clientes/Proveedores a consumir

FASE 9 agregó `apps/customers` (`Customer`/`Supplier`, ver
`docs/customers.md`/`docs/suppliers.md`). Los reportes "ventas por
cliente" y "compras por proveedor" pedidos para esta fase deben:

- Agregar `SaleItem`/`PurchaseOrderItem` (FASE 10/12) agrupados por
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

`Payment`/`PaymentAllocation` (FASE 10) y `CreditNote`/
`CreditNoteApplication`/`CashRegister`/`CashSession`/`ApprovalRequest`
(FASE 11) ya están construidos y en producción — esta fase debe
reportar sobre ellos, siempre como agregación de lectura (nunca
recalculando el saldo con una consulta propia):

- **Anticipos**: `Payment` sin `PaymentAllocation` (saldo sin aplicar
  por cliente), ver `docs/accounts-receivable.md`.
- **Notas de crédito**: emitidas, aplicadas parcial/totalmente,
  canceladas — agregando `CreditNote`/`CreditNoteApplication`.
- **Refunds**: dinero devuelto vs. convertido a crédito
  (`Refund`/`CreditNote(source_type=REFUND)`).
- **Saldo pendiente / saldo a favor**: por factura
  (`get_sale_balance_due`) y por cliente (`get_customer_credit_balance`
  — ya generalizado para sumar `Payment`+`CreditNote`, sin
  `CustomerCreditLedger` como tabla separada, ver
  `docs/accounts-receivable.md` sección 3).
- **Estados de cuenta**: la vista "Customer Statement" descrita en
  `docs/accounts-receivable.md` (sección 6) es responsabilidad de esta
  fase.
- **Apertura/cierre de caja**: sobrantes y faltantes por sesión,
  agregando `CashSession.difference` — ver `docs/cash-registers.md`.
- **Descuentos autorizados / créditos aprobados excepcionalmente**:
  agregando `ApprovalRequest` por tipo/estado — ver `docs/approvals.md`.

## Nota de sincronización — Moneda, denominaciones y filtros de caja

Doctrina oficial agregada en `docs/currency.md`: los reportes de Caja
deben poder filtrarse por caja, usuario, fecha y **moneda** una vez que
`CashRegister.currency`/`Currency` existan — ningún reporte debe sumar
montos de monedas distintas como si fueran la misma unidad. Se agrega
un reporte de denominaciones (denominación, cantidad, subtotal, moneda,
cierre) como agregación sobre `CashDenominationCount`/`CashClosing`
(especificación, no construidos). Ver `docs/reports.md`/`docs/currency.md`.

## Nota de sincronización — Gastos, RRHH y Nómina a reportar (FASE 13, ya construidos)

`apps.expenses`/`apps.hr`/`apps.payroll` (FASE 13) ya están construidos
y en producción — esta fase debe reportar sobre ellos, siempre como
agregación de lectura:

- **Gastos**: por gasto/categoría/proveedor/período/método/moneda/
  estado (`Expense`); recurrentes generados vs. pendientes
  (`ExpenseRecurrence`) — ver `docs/expenses.md`.
- **RRHH**: empleados por departamento/cargo/estado; asistencia
  (retrasos, horas trabajadas); ausencias por tipo/estado — ver
  `docs/hr.md`. **Nunca** incluir salario/datos bancarios en un
  reporte visible para quien no pase
  `apps.hr.services.can_view_sensitive_employee_data` — mismo
  principio de esta fase aplicado a reportes (nunca solo ocultar en la
  plantilla).
- **Nómina**: bruto/deducciones/bonos/retenciones/neto/costo total por
  período, agregando `PayrollLine` por `category`/`concept` (`Payroll`
  nunca duplica este desglose en campos propios) — ver
  `docs/payroll.md` sección 1.

## Estado de las notas de sincronización anteriores (todas cumplidas)

Todas las notas de sincronización de esta fase (Inventario/FASE 8,
Clientes-Proveedores/FASE 9, Ventas-Pagos/FASE 10, Cuentas por Cobrar-
Caja-Autorizaciones/FASE 11, Gastos-RRHH-Nómina/FASE 13) quedaron
cumplidas por `apps.reports` — cada reporte agrega exactamente sobre
los servicios/modelos que esas notas señalaban, nunca sobre una
consulta propia. La única excepción documentada es la nota de Moneda/
denominaciones: los reportes de Caja no filtran todavía por moneda
(`CashRegister.currency`/`CashDenominationCount`/`CashClosing` siguen
siendo especificación, no construidos — ver `docs/currency.md`), y el
reporte de denominaciones queda pendiente para cuando esos modelos
existan.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
