# Reportes (FASE 14 — construido)

`apps/reports` es la plataforma integral de reportes — construida
sobre el motor de Contabilidad General (`apps.accounting`, ver
`docs/accounting.md`) y reutilizando literalmente los servicios de
cada dominio de negocio ya existente.

## Principio central: reportes son agregaciones de lectura, nunca una fuente de verdad nueva

Todo reporte agrega/filtra sobre los modelos y funciones de servicio
que YA existen en cada dominio — nunca recalcula una regla de negocio
con una consulta propia (mismo principio ya aplicado desde FASE 8 a
`StockMovement`/`InventoryUnit`, y desde FASE 10 a `PaymentAllocation`).
Cada función de `apps.reports.services` devuelve
`{"summary": {...}, "rows": [...]}` — "resumen" y "análisis" de la
especificación de esta fase se combinan en `summary` (agregaciones/
agrupaciones vía `Sum`/`Count`/`values().annotate()`, nunca en un bucle
Python que repita una consulta por fila); "detalle" es `rows`, y el
drill-down real es un enlace directo al documento origen ya existente
(`Sale`/`PurchaseOrder`/`Expense`/`Employee`/etc.) — nunca una copia de
esos datos en una tabla de reporte.

| Dominio | Reporte | Fuente (nunca recalculada) |
|---|---|---|
| Ventas | por período/cliente/estado, subtotal/descuentos/impuestos/total, por estado de pago | `apps.sales.models.Sale` (agregación) |
| Inventario | stock actual, bajo stock, agotados | `apps.inventory.services.list_products_with_stock`/`get_low_stock_products` |
| Caja | sesiones (esperado/contado/diferencia), movimientos por tipo | `apps.pos.models.CashSession`/`CashMovement` |
| Cuentas por Cobrar | pendiente total, aging (0-30/31-60/61-90/90+), saldo a favor total | `apps.sales.services.get_customer_pending_sales`/`get_sale_balance_due_bulk`/`get_customer_credit_balance` |
| Cuentas por Pagar | pendiente total, aging, anticipos totales | `apps.purchases.services.get_supplier_pending_invoices`/`get_invoice_balance_due_bulk`/`get_supplier_advance_balance` |
| Compras | por período/proveedor/estado | `apps.purchases.models.PurchaseOrder` |
| Gastos | por período/categoría/estado | `apps.expenses.models.Expense` |
| RRHH | headcount por estado/departamento, ausencias pendientes — **nunca salario/datos bancarios** | `apps.hr.models.Employee`/`Leave` |
| Nómina | bruto/deducciones/neto agregados; desglose por empleado **solo para quien puede ver datos sensibles** | `apps.payroll.models.Payroll` + `apps.hr.services.can_view_sensitive_employee_data` |
| Clientes | top clientes por facturado, pendiente | `apps.sales.models.Sale` + `apps.sales.services` |
| Proveedores | top proveedores por comprado | `apps.purchases.models.PurchaseOrder` |
| Contables | Balance de Comprobación, Libro Mayor, Libro Diario, Balance General, Estado de Resultados | `apps.accounting` (construido, ver `docs/accounting.md` sección 8) — viven en `apps.accounting`, el panel de Reportes solo enlaza a ellos, nunca los duplica |
| Panel gerencial | resumen ejecutivo (ventas, gastos, CXC/CXP pendientes, stock bajo, margen estimado) | `get_executive_summary` — reúne los totales YA calculados arriba, nunca una cifra nueva |

## Aging (Cuentas por Cobrar/Pagar) — aproximación documentada

Ni `Sale` ni el sistema de Cuentas por Cobrar tienen un campo
`due_date` propio (a diferencia de `SupplierInvoice`, que sí lo
tiene) — el aging de CXC usa `sale.issue_date + timedelta(days=
customer.credit_days)` como fecha de vencimiento estimada. Es una
aproximación explícita, documentada aquí: `Customer.credit_days` ya
existe como término de crédito real (FASE 9), reutilizarlo evita
inventar un campo nuevo solo para el reporte.

## RRHH y Nómina — información sensible, nunca solo oculta en la UI

`PayrollReportView` decide en el SERVIDOR si el usuario puede ver el
desglose por empleado (`apps.hr.services.can_view_sensitive_employee_data`
— mismo criterio ya establecido en FASE 13): si no puede, `rows` se
vacía ANTES de llegar a la plantilla — nunca se envía el dato sensible
al navegador para luego ocultarlo con CSS. El reporte de RRHH nunca
incluye salario/datos bancarios en ninguna fila, ni siquiera para el
propietario (esa información vive en el detalle del empleado,
`apps.hr`, no en un reporte agregado).

## Exportación

CSV está disponible en los reportes tabulares principales (Ventas,
Gastos, Cuentas por Cobrar, Cuentas por Pagar) — genera el archivo al
vuelo desde las mismas `rows` que ve la pantalla, sin dependencias
nuevas. PDF/XLSX/JSON de exportación y reportes programados **no se
construyeron** en esta fase (ver "Qué NO se construyó" abajo).

## Multi-Tenancy y performance

Todo reporte se filtra explícitamente por `tenant`. Las agregaciones
(`Sum`/`Count`/`values().annotate()`) se resuelven en SQL, nunca en un
bucle Python que repita la consulta por fila — mismo estándar que
`get_sale_balance_due_bulk` estableció en FASE 11.

## Moneda (ver `docs/currency.md`)

Ningún reporte suma montos de monedas distintas como si fueran la
misma unidad — los reportes que agregan (Ventas, Gastos, Compras)
muestran el total en la moneda de cada fila individualmente en el
detalle; el `Sum` agregado en `summary` asume la moneda por defecto
del tenant (sin `CurrencyConfiguration`/motor de FX completo todavía,
ver `docs/currency.md`) — mezclar monedas reales en los totales
agregados queda documentado como una limitación conocida hasta que
exista ese motor.

## Qué NO se construyó en esta fase (deliberado)

- **Exportación PDF/XLSX**: ninguna librería nueva instalada sin
  decisión explícita del usuario (mismo criterio que
  `docs/invoice-documents.md` desde FASE 10 — impresión HTML
  `@media print` en vez de PDF binario).
- **Reportes programados** (envío por email diario/semanal/mensual):
  arquitectura no preparada en esta fase — no hay infraestructura de
  tareas en segundo plano todavía (mismo criterio que
  `apps.expenses.ExpenseRecurrence`, FASE 13).
- **Drill-down multi-nivel dentro del propio reporte** (resumen →
  análisis → detalle como una única pantalla con expansión): cada
  reporte muestra resumen+detalle en una sola vista, con enlaces
  directos al documento origen (Sale/Expense/Employee/etc.) como
  "siguiente nivel" — nunca una reimplementación de esas pantallas de
  detalle dentro de `apps.reports`.
- **Streaming/paginación de reportes de gran volumen**: los reportes
  tabulares limitan a 500 filas (`rows[:500]`) como salvaguarda simple
  contra un reporte accidentalmente enorme — paginación real/streaming
  queda para cuando el volumen real de un tenant lo exija.
- **Reporte de flujo de efectivo y cambios en el patrimonio**: viven
  en `apps.accounting` como pendientes (ver `docs/accounting.md`
  sección 10), no en `apps.reports`.
