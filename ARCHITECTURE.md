# Arquitectura

## Capas
1. Presentación: templates/componentes y JavaScript ligero.
2. Aplicación: views, serializers, permissions y services.
3. Dominio: reglas de negocio.
4. Datos: Django ORM + PostgreSQL.
5. Integraciones: PayPal, API de Inventario y futuras integraciones.

## Desarrollo
Windows → Python virtualenv → Django → PostgreSQL local → pgAdmin 4.

## Producción
Hostinger VPS → Linux → Nginx → Gunicorn → Django → PostgreSQL.

## Multi-tenant
Single database, tenant isolation a nivel de aplicación y base de datos mediante relaciones, constraints, managers/querysets y permissions. La arquitectura debe permitir evolucionar a particionado o separación de bases si fuese necesario, sin diseñar eso ahora.

## API
`/api/v1/` es el contrato versionado inicial. La API de Inventario es tenant-scoped, read-only por defecto, autenticada mediante API Key, limitada por rate limit y auditada.

## Inventario: dos fuentes de verdad, una por producto
Incorporado oficialmente a partir de FASE 8. Cada producto tiene un tipo de seguimiento de inventario, y ese tipo determina cuál es su única fuente de verdad de stock — nunca dos a la vez:

| Tipo | Fuente de verdad | Disponibilidad |
|---|---|---|
| QUANTITY | `StockMovement` (libro mayor append-only) | `stock_after` del movimiento más reciente |
| SERIALIZED | `InventoryUnit` (una fila por unidad física) | conteo de unidades en estado EN_STOCK |

Prohibido cualquier campo de stock desnormalizado o cualquier segunda fuente que pueda desincronizarse de la anterior. `serial`/`imei_1`/`imei_2` de `InventoryUnit` son únicos por tenant (no global) entre valores no vacíos; `imei_1` ≠ `imei_2`; toda unidad requiere al menos un identificador. Ver `docs/inventory.md` para el diseño completo (estados, máquina de estados, búsqueda unificada, reglas de venta).

## Cuentas por cobrar, caja y autorizaciones: ledgers append-only, nunca un campo editable
Incorporado oficialmente a partir de FASE 10 (ampliado tras el cierre inicial) y completado en FASE 11 (`apps/pos`, `apps/approvals`). Mismo principio que el inventario: el saldo se deriva siempre de un ledger append-only, nunca de un campo desnormalizado que alguien pueda editar directamente.

| Concepto | Fuente de verdad | Estado |
|---|---|---|
| Pago aplicado a factura(s) | `Payment` + `PaymentAllocation` | Construido (FASE 10) |
| Anticipo / saldo a favor | `Payment` sin aplicar + `CreditNote` sin aplicar, sumados por `get_customer_credit_balance` | Construido (FASE 11) — sin tabla `CustomerCreditLedger` separada, ver `docs/accounts-receivable.md` sección 3 |
| Nota de crédito | `CreditNote`/`CreditNoteApplication` (misma disciplina que `PaymentAllocation`) | Construido (FASE 11) — `docs/accounts-receivable.md` |
| Caja | `CashRegister`/`CashSession`/`CashMovement` | Construido (FASE 11) — `docs/cash-registers.md` |
| Autorización | `ApprovalPolicy`/`ApprovalRequest`, jerarquía usuario → rol → tenant → negar | Construido (FASE 11) — `docs/approvals.md` |

Reglas permanentes: un `PaymentAllocation`/`CreditNoteApplication` nunca excede el saldo disponible del origen ni el saldo pendiente de la factura destino; origen y destino deben ser del mismo tenant y del mismo cliente; un `Payment` sin cliente nunca genera saldo a favor; nunca dos balances paralelos ("anticipo" y "saldo a favor" son el mismo saldo, distintos orígenes); nunca una tercera tabla que resuma los dos ledgers reales. Cuentas por Cobrar del ERP (lo que un cliente le debe a un tenant) y Billing del SaaS (lo que un tenant le debe a Budun ERP) son ejes ortogonales — nunca se mezclan.

## Compras y cuentas por pagar: el espejo de cuentas por cobrar
Incorporado oficialmente a partir de FASE 12 (`apps/purchases`, ver `docs/purchases.md` y sus documentos de dominio). Orquesta sobre `apps.customers`/`apps.inventory`/`apps.approvals`/`apps.pos` ya construidos — nunca un segundo sistema de inventario, aprobaciones, caja ni archivos.

| Concepto | Fuente de verdad | Estado |
|---|---|---|
| Orden de compra / recepción | `PurchaseOrder`/`PurchaseOrderItem` + `PurchaseReceipt`/`PurchaseReceiptItem` (recibido/pendiente calculado, nunca campo) | Construido (FASE 12) — `docs/purchase-orders.md`/`docs/receiving.md` |
| Pago aplicado a factura(s) de proveedor | `SupplierPayment` + `SupplierPaymentAllocation` | Construido (FASE 12) — `docs/accounts-payable.md` |
| Anticipo a proveedor | `SupplierPayment` sin aplicar, sumado por `get_supplier_advance_balance` | Construido (FASE 12) — sin tabla separada, mismo criterio que cuentas por cobrar |
| Devolución a proveedor | `SupplierReturn`/`SupplierReturnItem`, `InventoryUnit.Status.DEVUELTO_PROVEEDOR` | Construido (FASE 12) — `docs/supplier-returns.md` |

`SupplierPayment`/`SupplierPaymentAllocation` son estructuralmente idénticos a `Payment`/`PaymentAllocation` (mismas reglas de sobre-aplicación, mismo ledger append-only) pero **nunca mezclados**: `SupplierPayment` no referencia `Customer`, `Payment` no referencia `Supplier` — dos ledgers paralelos e independientes.

## Gastos, Recursos Humanos y Nómina: tres dominios separados, ledgers append-only
Incorporado oficialmente a partir de FASE 13 (`apps/expenses`, `apps/hr`, `apps/payroll`, ver `docs/expenses.md`/`docs/hr.md`/`docs/payroll.md`). Tres dominios relacionados pero separados — nunca fusionados. Reutilizan literalmente `apps.customers`/`apps.approvals`/`apps.pos`/`apps.sales` ya construidos.

| Concepto | Fuente de verdad | Estado |
|---|---|---|
| Gasto | `Expense` (máquina de estados) + `ExpenseCategory` tenant-configurable | Construido (FASE 13) — `docs/expenses.md` |
| Pago de gasto | `ExpensePayment` (ledger append-only, nunca campo `paid_amount`) | Construido (FASE 13) |
| Gasto recurrente | `ExpenseRecurrence`, idempotente por diseño (`select_for_update` sobre la propia fila) | Construido (FASE 13) |
| Empleado / contrato | `Employee` (máquina de estados) / `EmploymentContract` (único `ACTIVE` por empleado) | Construido (FASE 13) — `docs/hr.md` |
| Ausencia | `LeaveType` tenant-configurable + `Leave`, autorización por AUTORIDAD (`can_user_approve`) | Construido (FASE 13) |
| Nómina | `PayrollPeriod`/`Payroll` (snapshot histórico del empleado, nunca recalculado) | Construido (FASE 13) — `docs/payroll.md` |
| Línea de nómina | `PayrollLine` única con `category`/`concept` (nunca 4 tablas separadas) | Construido (FASE 13) |
| Pago de nómina | `PayrollPayment` (ledger append-only) | Construido (FASE 13) |

Reglas permanentes: autorización por MONTO (gasto sobre el límite, `ApprovalPolicy.max_expense_amount`) vs. por AUTORIDAD pura (ausencias, período de nómina) son dos criterios deliberadamente distintos, documentados caso por caso. Pago en efectivo (gasto o nómina) exige `CashSession` abierta y genera `CashMovement` propio (`EXPENSE_PAYMENT_CASH`/`PAYROLL_PAYMENT_CASH`). Información sensible de RRHH (salario, datos bancarios) nunca se restringe solo en la UI — verificada también en el servidor, auditada en cada lectura. Ninguno de los tres dominios se mezcla con Billing del SaaS (eje ortogonal, mismo criterio que Cuentas por Cobrar vs. Billing).

## Moneda, denominaciones y cierre de caja (especificación, ver `docs/currency.md`)
Doctrina oficial: el ERP es internacional, nunca hardcodea una moneda ni sus denominaciones. `Currency`/`CurrencyDenomination` es el catálogo real (una moneda puede tener cualquier cantidad de denominaciones — billete o moneda, con orden de presentación); `CurrencyConfiguration` por tenant define moneda funcional/monedas habilitadas y prepara tipos de cambio (sin motor de FX). `CashRegister` tendrá una moneda operativa principal (campo nuevo); su `CashSession` cuenta físicamente en esa única moneda, sin mezclar denominaciones de monedas distintas. `CashDenominationCount` (siempre referenciando `CurrencyDenomination`, nunca un segundo catálogo) es el modo profesional de cierre; `CashClosing` es inmutable, con "sobrante"/"faltante" como lecturas de `difference`, nunca campos redundantes. El vocabulario `amount_due`/`amount_received`/`change_amount` y el efecto neto de `CashMovement` en una venta con cambio ya están correctamente implementados desde FASE 11 — esta doctrina los formaliza sin cambiar código.

## UI
Dashboard custom; no Django Admin como UI principal. Dirección visual: SaaS moderno, empresarial, sobrio, legible, azul/verde con neutrales y sin colores estridentes.
