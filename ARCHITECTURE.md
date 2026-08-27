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

## Contabilidad General y Reportes: la contabilidad como fuente financiera central
Incorporado oficialmente a partir de FASE 14 (`apps/accounting`, `apps/reports`, ver `docs/accounting.md`/`docs/reports.md`). La contabilidad se convierte en la fuente financiera central del ERP — los reportes nunca recalculan una cifra financiera de forma independiente cuando esa información debe provenir de contabilidad.

| Concepto | Fuente de verdad | Estado |
|---|---|---|
| Plan de cuentas | `Account` (jerárquico, `level` calculado una sola vez al crear, `allows_posting`) | Construido (FASE 14) |
| Período contable | `AccountingPeriod` (OPEN/CLOSING/CLOSED/REOPENED, sin `DocumentSequence` — no es un documento emitido) | Construido (FASE 14) |
| Asiento contable | `JournalEntry`/`JournalEntryLine` (partida doble: débito XOR crédito por línea, `SUM(débitos)==SUM(créditos)` obligatorio) | Construido (FASE 14) — numeración `AST-` vía `DocumentSequence` de FASE 10 |
| Contabilización automática | `record_business_event` (idempotente por `tenant`+`source_type`+`source_event_key`) vía `AccountMapping` | Construido (FASE 14, ampliado en el cierre controlado posterior) — 9 eventos conectados: Venta confirmada + COGS, Pago de cliente, Devolución (reverso de COGS), Pago de gasto, Pago de nómina, Factura de proveedor confirmada, Pago a proveedor, Devolución a proveedor, Cierre de sesión de caja (Cash Over/Short) |
| Costeo de inventario | SERIALIZED: costo específico (`InventoryUnit.unit_cost`); QUANTITY: promedio ponderado (`StockMovement.unit_cost`/`average_cost_after`, mismo patrón que `stock_before`/`stock_after`) | Construido (ampliación de cierre de FASE 14) — nunca FIFO, ver `docs/accounting.md` sección 11 |
| Impuestos multi-código | `TaxCode`/`SaleItemTax` — aditivo, cuenta de control propia por código | Construido (ampliación, solo Ventas) — `docs/accounting.md` sección 15 |
| Reportes contables | Balance de Comprobación, Libro Mayor, Libro Diario, Balance General (acumulado), Estado de Resultados (acotado al período) | Construido (FASE 14) — leen siempre `JournalEntry`/`JournalEntryLine` directamente |
| Plataforma de reportes | `apps/reports` (sin modelos propios), un reporte por dominio de negocio con `{"summary", "rows"}` y drill-down a los documentos ya existentes; Estados de Cuenta de Cliente/Proveedor; exportación CSV/PDF/XLSX | Construido (FASE 14, ampliado) — `docs/reports.md` |

Reglas permanentes: un `JournalEntry` `POSTED` nunca se edita ni se borra físicamente — toda corrección es un reverso (`reverse_journal_entry`, idempotente). Toda integración automática que envuelve `record_business_event` (patrón `try_record_*`) debe atrapar cualquier excepción y auditar, nunca relanzarla — la contabilización es siempre aditiva/opcional, nunca puede bloquear la venta/pago/gasto/nómina/compra/cierre-de-caja subyacente. Balance General = acumulado desde el origen; Estado de Resultados = acotado al período — nunca la misma lógica de fechas para ambos. `apps/reports` nunca introduce una segunda fuente de verdad ni copia datos de detalle; información sensible (salario/datos bancarios) se filtra siempre en el servidor.

## Roles, Permisos, Auditoría transversal y API de Inventario
Incorporado oficialmente a partir de FASE 15 (`apps/permissions`, `apps/audit`, `apps/api`, ver `docs/roles-permissions.md`/`docs/audit.md`/`docs/api-inventory.md`). Generaliza — nunca reemplaza — la autorización binaria OWNER/MEMBER y los 7 registros de actividad por dominio ya existentes.

| Concepto | Fuente de verdad | Estado |
|---|---|---|
| Roles | `Membership.Role` (OWNER/ADMIN/MANAGER/CASHIER/EMPLOYEE/MEMBER); `SUPER_ADMIN` → `User.is_superuser` | Construido (FASE 15) |
| Permisos granulares | `apps.permissions.services.has_permission` (catálogo código-definido, jerarquía usuario→rol→tenant→negar) + `RolePermission`/`UserPermissionOverride` (personalización por tenant/usuario) | Construido (FASE 15) — `require_tenant`/`require_role` nunca retirados, retrofit por superficies de mayor riesgo |
| Auditoría transversal | `apps.audit.AuditLog` (tenant nulable) + `search_audit_events` (`UNION` SQL sobre los 7 `*ActivityLog` + `AuditLog` + `StockMovement`) | Construido (FASE 15) — inmutable, nunca bloquea la operación que audita |
| API de Inventario v1 | `apps.api` (Django REST Framework), `/api/v1/health,products,categories,inventory,inventory/low-stock,inventory/movements,inventory/serialized` | Construido (FASE 15) — read-only, sin escritura en ningún endpoint |
| `ApiKey` | Hash SHA-256, secreto en texto plano nunca guardado, una sola clave activa por tenant (rotar reescribe la misma fila) | Construido (FASE 15) |
| Scopes de API | `inventory:read`/`products:read`/`categories:read`/`inventory_movements:read`/`serialized_inventory:read`/`health:read` | Construido (FASE 15) — nunca acceso financiero por defecto |

Reglas permanentes: el tenant de una request a `/api/v1/` SIEMPRE se resuelve desde la `ApiKey` (nunca de un parámetro enviado por el cliente) — mismo principio de aislamiento ya aplicado en todo el proyecto desde FASE 3. Un permiso de acción (`apps.permissions`) y un umbral de aprobación (`ApprovalPolicy`, FASE 11) son sistemas deliberadamente distintos que coexisten, nunca fusionados. Identificadores sensibles (IMEI/serie, prefijo de `ApiKey`) se enmascaran vía el helper compartido `apps.core.utils.mask_secret`.

### Ampliación final de FASE 15: Catalog API + Integraciones externas Multi-Tenant
Segunda capa de API (`/api/v1/catalog/`), comercial, deliberadamente separada de la Inventory API administrativa — ver `docs/api-catalog.md`/`docs/integrations.md`.

| Concepto | Fuente de verdad | Estado |
|---|---|---|
| Integración externa | `Integration` (`apps.api`) — varias por tenant, espejo estructural de `ApiKey` sin compartir tabla ni scopes | Construido (ampliación) |
| Credencial de integración | `secret_hash` (SHA-256, mostrado una vez); `app_key` público, nunca usado para autenticar | Construido (ampliación) — mecanismo compartido con `ApiKey` vía `apps.api.crypto` |
| Scopes de Catalog API | `catalog:read`/`catalog:availability:read`/`catalog:media:read` — catálogo separado de los de Inventory API | Construido (ampliación) — nunca acceso financiero |
| Catalog API | `apps.api` (Catalog API), `/api/v1/catalog/search,products,products/{id},availability,variants,media` | Construido (ampliación) — read-only, whitelist server-side estricta |
| Campos comerciales de producto | `Product.brand`/`model_name`/`variant_attributes` (JSON flexible) | Construido (ampliación) — migración aditiva |
| Imágenes de catálogo | `ProductImage` (`settings.CATALOG_MEDIA_ROOT`, servidas por UUID `public_id`) | Construido (ampliación) — carpeta física distinta de `media-private/` |

Reglas permanentes: una credencial de una capa (`ApiKey`/`Integration`) nunca autentica a la otra. `provider` (quién construyó el consumidor externo) nunca se confunde con una "tool" de agente IA (que vive en el consumidor, nunca en este proyecto — nunca se implementa `search_budun()` ni funciones acopladas a un consumidor concreto). Disponibilidad comercial siempre de la misma fuente de verdad que la Inventory API, nunca un contador paralelo.

## PayPal (Payment Provider Interface): construido en FASE 16
`apps.billing` — ver `docs/paypal.md`. Proveedor de pagos exclusivo del Billing SaaS (FASE 17), nunca del ERP operativo de cada tenant.

| Concepto | Fuente de verdad | Estado |
|---|---|---|
| Abstracción de proveedor | `PaymentProvider` (`apps.billing.providers.base`) → `PayPalProvider` (`.paypal`), único hoy | Construido |
| Transacción de pago | `PayPalTransaction` — no hereda `TenantScopedModel` (actor de plataforma); `amount`/`currency` internos separados de `provider_amount`/`provider_currency` | Construido |
| Idempotencia de webhook | `PayPalWebhookEvent.event_id` (`UniqueConstraint`) | Construido |
| Estado del gateway | `PayPalGatewayStatus` (fila única) — credenciales SIEMPRE en variables de entorno, nunca en esta tabla | Construido |
| Webhook | `/webhooks/paypal/`, público, verificado por firma oficial (`/v1/notifications/verify-webhook-signature`), nunca ORM directo desde la vista | Construido |
| Administración | `/plataforma/billing/paypal/`, exclusiva `is_superuser` (`apps.tenants.permissions.require_superuser`) | Construido |
| `Plan`/`Subscription`/`SaaS Invoice`/`SaaS Payment` | — | FASE 17, no construido |

Reglas permanentes: Orders API v2, nunca Subscriptions API (evita anticipar el `Plan` de FASE 17 del lado de PayPal). El access token OAuth2 nunca se persiste (solo cache en memoria del proceso); el client secret nunca se audita ni se expone. Señales de Django (`apps.billing.signals`) son el contrato estable que FASE 17 conectará — `SUBSCRIPTION_ACTIVATED`/`CANCELLED` no se modelan todavía porque no existe ningún `Subscription` al que asociarlos.

## UI
Dashboard custom; no Django Admin como UI principal. Dirección visual: SaaS moderno, empresarial, sobrio, legible, azul/verde con neutrales y sin colores estridentes.
