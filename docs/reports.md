# Reportes (especificación)

> **Estado: ESPECIFICACIÓN, no implementación.** Diseño aprobado para
> FASE 14 — ningún modelo, vista ni migración se crea a partir de este
> documento. El detalle completo, dominio por dominio, vive en
> `docs/phases/PHASE-14-reports.md` (secciones "Reportes de
> Inventario"/"Reportes de Caja"/"Nota de sincronización — Cuentas por
> Cobrar y Caja a reportar" y las notas de FASE 9/10) — este documento
> es el resumen arquitectónico, no una fuente de verdad paralela.

## Principio central: reportes son agregaciones de lectura, nunca una fuente de verdad nueva

Todo reporte de este módulo se construye agregando/filtrando los
modelos y funciones de servicio que YA existen en cada dominio — nunca
recalculando una regla de negocio con una consulta propia, y nunca
introduciendo un campo o tabla que pudiera desincronizarse de la
fuente real (mismo principio ya aplicado desde FASE 8 a `StockMovement`/
`InventoryUnit`, y desde FASE 10 a `PaymentAllocation`).

| Dominio | Reportes | Fuente (nunca recalculada) |
|---|---|---|
| Inventario | existencias, movimientos, bajo stock, serializados, trazabilidad, valorización preparada | `apps.inventory.services` (`get_current_stock`, `list_products_with_stock`, `get_low_stock_products`, `StockMovement`, `InventoryUnit`) |
| Ventas | por cliente/producto/serial/vendedor, cotizaciones/conversiones, descuentos/impuestos | `apps.sales.services`/`SaleItem` (snapshot histórico ya congelado por línea) |
| Pagos / cuentas por cobrar | pendientes, allocations, anticipos, saldo a favor, notas de crédito, refunds, estado de cuenta | `apps.sales.services` (`get_sale_balance_due`, `get_customer_pending_sales`, `get_customer_credit_balance`) |
| Caja | aperturas/cierres, ventas en efectivo, entradas/salidas, refunds, sobrantes/faltantes | `apps.pos.services` (`get_expected_cash`, `CashSession`, `CashMovement`) |
| Compras / cuentas por pagar | equivalentes a ventas/cuentas por cobrar, del lado proveedor | `apps.purchases` (FASE 12, cuando exista — ver `docs/purchases.md`) |
| Gastos | por categoría/proveedor/método/fecha | `apps.expenses` (FASE 13, cuando exista) |

## Multi-Tenancy y performance

Todo reporte se filtra explícitamente por `tenant` (nunca `objects`
sin filtro, mismo principio que el resto del proyecto desde FASE 3) y
se diseña desde el inicio evitando N+1 — el precedente ya establecido
en FASE 11 (`get_sale_balance_due_bulk`, corrigiendo un N+1 real al
listar facturas pendientes de un cliente) es el estándar a seguir: si
un reporte necesita el mismo dato derivado para muchas filas, se
calcula en una agregación SQL, nunca en un bucle Python que repita la
consulta por fila.

## Qué NO se construye con este documento

Ningún modelo, vista, exportación ni motor de reportes. La fase que
implemente FASE 14 debe releer `docs/phases/PHASE-14-reports.md` para
el detalle completo antes de diseñar.
