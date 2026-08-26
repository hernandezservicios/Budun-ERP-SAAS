# MASTER PROMPT — SaaS ERP Multi-Tenant

Actúa como un equipo senior de arquitectura, Django, PostgreSQL, REST API, seguridad, UX/UI, QA, DevOps y pagos. Construye desde cero un SaaS ERP Multi-Tenant profesional.

## Stack oficial

- Windows para desarrollo.
- Python + virtualenv.
- Django.
- PostgreSQL.
- pgAdmin 4 para administración gráfica local.
- Git/GitHub.
- Hostinger VPS en producción.
- Gunicorn + Nginx o servidor web apropiado en producción.
- Redis solo si se justifica posteriormente.
- PayPal + PayPal MCP.

## Prohibiciones

- NO Docker.
- NO Docker Desktop.
- NO Docker Compose.
- NO MySQL.
- NO MariaDB.
- NO WAMP como dependencia.
- NO SQLite como base oficial del proyecto.
- NO Django Admin como UI principal.

## Fases

Hay exactamente 25 fases: 0 a 24. No saltar ninguna.

0. Auditoría del entorno
1. Project Foundation
2. PostgreSQL Foundation
3. Multi-Tenancy
4. Authentication
5. Design System
6. Landing + Pricing
7. Dashboard
8. Products + Inventory
9. Customers + Suppliers
10. Sales Engine
11. POS
12. Purchases
13. Expenses
14. Reports
15. Roles + Audit + Inventory API
16. PayPal Sandbox
17. Billing SaaS
18. Security Hardening
19. Performance
20. Backups
21. Hostinger Deployment
22. Data Migration
23. Production Verification
24. Final Audit

## Ciclo por fase

Analizar → planificar → implementar → ejecutar → probar → verificar → corregir → volver a probar → documentar → commit → cerrar.

Nunca avanzar con fallos críticos.

## UX/UI

Diseña una interfaz moderna, profesional, sobria y legible. Tú decides la dirección visual concreta, pero debe priorizar experiencia de usuario, claridad, jerarquía, consistencia, accesibilidad y productividad. La identidad puede usar azul y verde como colores principales/secundarios, con neutros y colores semánticos. Evita colores extraños, neón, exceso de gradientes y saturación visual.

## Multi-Tenancy

Single PostgreSQL database con aislamiento estricto por tenant. Ningún tenant puede acceder a datos de otro. Probar expresamente este requisito.

## API de Inventario

En `Configuración → API de Inventario` crear una integración para agentes CRM IA:

- Base URL `/api/v1/`.
- API Key por tenant.
- Generar, regenerar y revocar.
- Mostrar la clave completa solo en el momento controlado de creación/rotación; después enmascararla.
- Botón Probar Conexión.
- Estado: Conectado, No conectado, Error, Deshabilitado.
- Última prueba, última conexión, último error.
- API read-only inicialmente.
- Scopes mínimos para `inventory:read`, `products:read`, `categories:read`.
- Rate limiting.
- Audit log.
- Pagination/filtering.
- Tenant isolation.
- Documentación para el agente CRM IA.

Endpoints mínimos:

- `GET /api/v1/health/`
- `GET /api/v1/products/`
- `GET /api/v1/products/{id}/`
- `GET /api/v1/categories/`
- `GET /api/v1/inventory/`
- `GET /api/v1/inventory/low-stock/`
- `GET /api/v1/inventory/movements/`

El agente IA nunca accede directamente a PostgreSQL.

## Inventario: por cantidad y serializado

Incorporado oficialmente a partir de FASE 8. Todo producto declara un tipo de seguimiento de inventario:

- **QUANTITY** (por cantidad, por defecto): la fuente de verdad es `StockMovement`, un libro mayor append-only. El stock actual es el `stock_after` del movimiento más reciente — nunca un campo desnormalizado.
- **SERIALIZED** (IMEI / número de serie): la fuente de verdad es `InventoryUnit`, una fila por unidad física real. La disponibilidad es el conteo de unidades en estado EN_STOCK.

Un producto usa exactamente una de las dos fuentes a la vez; nunca deben coexistir dos fuentes de verdad contradictorias para el mismo producto, y un producto no puede cambiar de tipo si ya tiene historial registrado.

Unicidad de `serial`, `imei_1` e `imei_2` (modelo `InventoryUnit`): por tenant, no global, y solo entre valores no vacíos; `imei_1` nunca puede ser igual a `imei_2`; toda unidad requiere al menos un identificador no vacío.

Los endpoints de la API de Inventario (FASE 15) deben poder exponer también el inventario serializado, respetando el mismo principio read-only, de scopes y de aislamiento por tenant que el resto de la API. Ver `docs/inventory.md` para el diseño completo.

## Pagos y cuentas por cobrar

Incorporado oficialmente a partir de FASE 10 (ampliado tras el cierre inicial): `Payment` (dinero recibido de un cliente) puede aplicarse a una o varias facturas del mismo cliente mediante `PaymentAllocation`, un ledger append-only. El monto aplicado nunca excede el saldo disponible del pago ni el saldo pendiente de la factura; `Payment`/`Sale` deben ser del mismo tenant y, al aplicar, del mismo cliente; `Payment.customer` nulo (venta de mostrador) nunca genera saldo a favor. Todo se calcula desde el ledger, nunca un campo desnormalizado; toda operación es idempotente y auditada. Ver `docs/payments.md`.

Construido a partir de FASE 11 (`apps/pos`, `apps/approvals`) — ver `docs/accounts-receivable.md`, `docs/cash-registers.md` y `docs/approvals.md`:

- **Anticipo/saldo a favor**: un único saldo por cliente (nunca dos balances paralelos). No hay una tabla `CustomerCreditLedger` separada: se generalizaron `get_customer_credit_balance`/`get_sale_paid_amount` para sumar `Payment`+`PaymentAllocation` y `CreditNote`+`CreditNoteApplication` — los dos ledgers reales.
- **Notas de crédito** (`CreditNote`/`CreditNoteApplication`, en `apps.sales`): misma disciplina de validación que `PaymentAllocation`, nunca altera la factura histórica.
- **Cajas** (`CashRegister`/`CashSession`/`CashMovement`, en `apps.pos`): cualquier cantidad de cajas por tenant (sin límite fijo); una sesión de caja abierta es obligatoria antes de confirmar una venta operativa de mostrador; solo el efectivo afecta el efectivo físico.
- **Autorizaciones** (`ApprovalPolicy`/`ApprovalRequest`, en `apps.approvals`): servicio centralizado y reutilizable para descuentos por encima del límite (porcentaje Y monto) y crédito excedido, con jerarquía usuario → rol → tenant → negar. El propietario del tenant siempre está autorizado.

## Compras y cuentas por pagar

Incorporado oficialmente a partir de FASE 12 (`apps/purchases`) — ver `docs/purchases.md`, `docs/purchase-orders.md`, `docs/receiving.md`, `docs/supplier-invoices.md`, `docs/accounts-payable.md` y `docs/supplier-returns.md`. Orquesta sobre `apps.customers`/`apps.inventory`/`apps.approvals`/`apps.pos` ya construidos, nunca un segundo sistema de inventario, aprobaciones, caja ni archivos:

- **`PurchaseOrder`/`PurchaseReceipt`**: documentos independientes (`OC-`/`REC-`, misma `DocumentSequence` de FASE 10); la orden es el compromiso, la recepción es el evento físico. Recepción parcial/completa; `PurchaseOrderItem` nunca guarda cantidad recibida/pendiente como campo — se calcula siempre desde `PurchaseReceiptItem`.
- **Recepción**: QUANTITY vía `register_stock_in`; SERIALIZED vía `register_serialized_unit`, una llamada por unidad física.
- **Cuentas por pagar** (`SupplierPayment`/`SupplierPaymentAllocation`): espejo exacto de `Payment`/`PaymentAllocation`, nunca mezclado con Cuentas por Cobrar. Anticipo a proveedor = `SupplierPayment` sin aplicar.
- **Devolución a proveedor** (`SupplierReturn`): inmutable; serializados transicionan a `InventoryUnit.Status.DEVUELTO_PROVEEDOR` (nuevo, distinto de `DEVUELTO`).
- **Caja**: pago a proveedor en efectivo exige `CashSession` abierta y genera `CashMovement` propio; otros medios no afectan el efectivo físico.
- **Autorizaciones**: compra sobre el límite y sobre-recepción vía `apps.approvals`, mismas primitivas que descuentos/crédito excedido.

## Gastos, Recursos Humanos y Nómina

Incorporado oficialmente a partir de FASE 13 (`apps/expenses`, `apps/hr`, `apps/payroll`) — ver `docs/expenses.md`, `docs/hr.md`, `docs/payroll.md`. Tres dominios relacionados pero separados, reutilizando literalmente `apps.customers`/`apps.approvals`/`apps.pos`/`apps.sales` ya construidos:

- **Gastos**: `ExpenseCategory` tenant-configurable; `Expense` con máquina de estados (`DRAFT→PENDING_APPROVAL→APPROVED→PARTIALLY_PAID/PAID`, `REJECTED`, `CANCELED`); autorización por MONTO (`ApprovalPolicy.max_expense_amount`) o excepcional (`Expense.is_exceptional`), sin importar el monto; `ExpensePayment` ledger append-only; `ExpenseRecurrence` con generación idempotente por diseño (nunca duplica un gasto del mismo período, ni bajo concurrencia).
- **Recursos Humanos**: `Department`/`Position`/`Employee` (máquina de estados `ACTIVE/INACTIVE/ON_LEAVE/SUSPENDED/TERMINATED`); `EmploymentContract` (nunca dos `ACTIVE` a la vez por empleado); `Attendance` (entrada/salida, retraso/horas contra `WorkSchedule`); `LeaveType`/`Leave` con autorización por AUTORIDAD pura (`can_user_approve`, sin dimensión de monto — distinto del criterio de Gastos); `Incident`. Información sensible (salario, datos bancarios): nunca solo oculta en la UI — verificada también en el servidor, auditada en cada lectura por el propietario.
- **Nómina**: `PayrollPeriod` (`DRAFT→PROCESSING→APPROVED→PAID→CLOSED`, o `CANCELED` antes de aprobar; inmutable una vez `CLOSED`); `Payroll` snapshotea al empleado (nombre/departamento/cargo/salario) al calcularse, nunca recalculado después; `PayrollLine` es una única tabla con `category`/`concept` (nunca tablas separadas por tipo, mismo principio que evitó `CustomerCreditLedger`); `PayrollPayment` ledger append-only. Aprobación de período también por AUTORIDAD pura, no por monto.
- Pago de gasto/nómina en efectivo exige `CashSession` abierta y genera `CashMovement` propio (`EXPENSE_PAYMENT_CASH`/`PAYROLL_PAYMENT_CASH`); ninguno se mezcla con Billing del SaaS (dominios ortogonales).

## Moneda, denominaciones y cierre de caja (especificación — ver `docs/currency.md`)

El ERP es internacional: `Currency`/`CurrencyDenomination` es el catálogo real (nunca DOP ni sus denominaciones hardcodeadas en código; cada moneda define su propia lista de billetes/monedas con orden de presentación). `CurrencyConfiguration` por tenant define moneda funcional, monedas habilitadas y prepara tipos de cambio (sin motor de FX completo). `CashRegister` tendrá una moneda operativa principal (campo nuevo, no existe hoy); su `CashSession` cuenta físicamente en esa única moneda, nunca mezclando denominaciones de monedas distintas. El cierre por denominaciones (`CashDenominationCount`, siempre referenciando `CurrencyDenomination`, nunca un segundo catálogo) es el modo profesional recomendado; `CashClosing` es inmutable una vez cerrado, con "sobrante"/"faltante" como lecturas de `difference` (nunca campos redundantes). El vocabulario oficial de cambio (`amount_due`/`amount_received`/`change_amount`, cambio calculado solo sobre la parte en efectivo de un pago mixto) y el efecto neto de `CashMovement` en una venta con cambio **ya están correctamente implementados desde FASE 11** — esta doctrina los formaliza sin cambiar código. Sugerencia de cambio por denominaciones: preparada, nunca obligatoria para el cajero.

## Contabilidad General y Reportes Profesionales

Incorporado oficialmente a partir de FASE 14 (`apps/accounting`, `apps/reports`) — ver `docs/accounting.md` y `docs/reports.md`. La contabilidad se convierte en la fuente financiera central del ERP; los reportes nunca recalculan una cifra financiera de forma independiente cuando esa información debe provenir de contabilidad:

- **Motor de contabilidad**: `Account` (plan de cuentas jerárquico, tipo/naturaleza deudora-acreedora, `allows_posting`), `AccountingPeriod` (OPEN/CLOSING/CLOSED/REOPENED, nunca se solapa con otro período abierto del mismo tenant, sin numeración de `DocumentSequence` por no ser un documento emitido), `JournalEntry`/`JournalEntryLine` (partida doble: débito XOR crédito por línea, `SUM(débitos)==SUM(créditos)` obligatorio para pasar a `POSTED`). Inmutable una vez contabilizado: toda corrección es un reverso (`reverse_journal_entry`, idempotente), nunca una edición ni un borrado físico.
- **Contabilización automática**: arquitectura Evento de negocio → Servicio de Contabilidad → `JournalEntry`, nunca lógica contable en una vista de otro módulo. Idempotente por `(tenant, source_type, source_event_key)`. Cada integración resuelve sus cuentas de control vía `AccountMapping`; si falta un mapeo, la contabilización se omite en silencio y se audita — nunca bloquea la operación de negocio subyacente. Toda función que envuelve una integración automática debe atrapar cualquier excepción y auditar, nunca relanzarla.
- **Reportes contables**: Balance de Comprobación, Libro Mayor, Libro Diario, Balance General (acumulado desde el origen) y Estado de Resultados (acotado al período) — leídos siempre directamente de `JournalEntry`/`JournalEntryLine`.
- **Plataforma de reportes** (`apps/reports`, sin modelos propios): un reporte por dominio de negocio (Ventas, Inventario, Caja, Cuentas por Cobrar/Pagar con aging, Compras, Gastos, RRHH, Nómina, Clientes, Proveedores, panel gerencial), cada uno agregando sobre los servicios/modelos YA existentes — nunca una segunda fuente de verdad ni una copia de los datos de detalle. Información sensible (salario/datos bancarios) se filtra siempre en el servidor, nunca solo oculta en la UI.

## PayPal

Implementar primero Sandbox. Consultar documentación oficial vigente para API y MCP. No inventar herramientas MCP ni endpoints. El frontend se comunica con Django; Django usa una capa de servicios de pago; MCP es herramienta del agente/desarrollo/operación.

## Integraciones: regla para usuario no técnico

Claude debe intentar automatizar la configuración. Cuando una acción dependa de una contraseña, credencial, cuenta externa, interfaz gráfica o permiso que no tenga, debe explicar exactamente qué hacer, dónde hacerlo, qué valor usar y cómo verificarlo. No debe asumir que pgAdmin se configura mágicamente. Debe leer y seguir `docs/setup/windows-postgresql-pgadmin-step-by-step.md` antes de configurar la base local.

## Verificación visual

Toda fase que cambie UI debe verificarse con navegador cuando sea posible, incluyendo estados normal, vacío, error y responsive.

## Estado

Mantener `docs/project-status/CURRENT_PHASE.md`, `PHASE_HISTORY.md`, `KNOWN_ISSUES.md` y `DECISIONS.md` actualizados.

## Primera ejecución

Ejecuta solamente FASE 0 y FASE 1. Luego detente. No continúes automáticamente.


## CONSTRUCCIÓN INCREMENTAL OBLIGATORIA

No generes todo el proyecto al inicio. En cada fase crea solo lo necesario para alcanzar los criterios de aceptación de esa fase y mantener las fases anteriores funcionando. No construyas placeholders de módulos futuros salvo que una dependencia inmediata lo requiera.

## PGADMIN 4 — ASISTENCIA PASO A PASO

No supongas que pgAdmin se conecta automáticamente. Antes de la FASE 2, lee `docs/setup/windows-postgresql-pgadmin-step-by-step.md`. Detecta PostgreSQL instalado, versión, servicio y puerto. Automatiza por terminal cuando sea seguro. Cuando se requiera contraseña, confirmación o interacción GUI, explica al usuario exactamente qué hacer en pgAdmin 4 y cómo verificarlo.

## PARADA POR CREDENCIALES

Si falta una credencial externa, no improvises. Explica: qué credencial es, dónde obtenerla, dónde introducirla, cómo protegerla y cómo verificar que funciona.
