# CLAUDE.md — ERP SaaS Multi-Tenant

## Mandato
Construir desde cero un SaaS ERP Multi-Tenant profesional con Django + PostgreSQL + pgAdmin 4, sin Docker, sin MySQL y sin WAMP como dependencia del proyecto.

## Arquitectura oficial
- Desarrollo: Windows + Python + virtualenv + Django + PostgreSQL + pgAdmin 4 + Git.
- Producción: Hostinger VPS + Linux + PostgreSQL + Django + Gunicorn + Nginx (o servidor web equivalente si la infraestructura real lo recomienda) + SSL.
- Redis solo si una fase posterior demuestra necesidad real.
- PayPal y PayPal MCP según documentación oficial vigente.

## Prohibiciones
- No crear Dockerfile.
- No crear docker-compose.*.
- No utilizar Docker Desktop/Engine.
- No utilizar MySQL/MariaDB.
- No usar Django Admin como UI principal.
- No exponer secretos.

## Idioma y UX
Toda la UI visible debe estar en español. Diseño moderno, profesional, limpio, sobrio y muy legible. La dirección visual la decide el agente técnico, priorizando UX y claridad. Azul y verde forman la identidad, sin colores raros, neón, arcoíris ni efectos excesivos.

## Multi-tenancy
Toda entidad empresarial es tenant-scoped. Una API Key pertenece a un único tenant. Tenant A nunca puede leer o modificar datos de Tenant B. El backend determina el tenant; no se confía en IDs enviados por el frontend.

## API de Inventario
Existe una sección Configuración → API de Inventario. Debe incluir Base URL /api/v1/, generación/rotación/revocación de API Key, visibilidad segura de la clave, prueba real de conexión, estado, última prueba, último error y auditoría. La API es READ-ONLY por defecto y está preparada para agentes CRM IA.

Endpoints iniciales previstos: GET /api/v1/health/, /products/, /products/{id}/, /categories/, /inventory/, /inventory/low-stock/, /inventory/movements/.

## Inventario: por cantidad y serializado
Todo producto tiene un tipo de seguimiento de inventario: QUANTITY (por cantidad) o SERIALIZED (IMEI/número de serie), incorporado oficialmente a partir de FASE 8. Cada tipo tiene una única fuente de verdad, nunca dos a la vez para el mismo producto:
- QUANTITY → `StockMovement` (libro mayor append-only). Stock actual = `stock_after` del movimiento más reciente.
- SERIALIZED → `InventoryUnit` (una fila por unidad física real). Disponibilidad = conteo de unidades en estado EN_STOCK.

Prohibido introducir un campo de stock desnormalizado o una segunda fuente de verdad para cualquiera de los dos tipos. Un producto no puede cambiar de tipo de seguimiento una vez que ya tiene movimientos o unidades registradas.

Unicidad de identificadores de `InventoryUnit` (serial, IMEI 1, IMEI 2): únicos **por tenant**, nunca global, y solo entre valores no vacíos (varias unidades pueden no tener alguno de los tres). IMEI 1 nunca puede ser igual a IMEI 2. Toda unidad debe tener al menos un identificador no vacío. Ver `docs/inventory.md` para el detalle completo (estados, máquina de estados, búsqueda unificada, reglas de venta).

## Pagos y cuentas por cobrar
Incorporado oficialmente a partir de FASE 10 (ampliado tras el cierre inicial). Un `Payment` (dinero recibido de un cliente) puede aplicarse a una o varias facturas del mismo cliente mediante `PaymentAllocation` (ledger append-only, nunca editado in-place — las correcciones son reversos, no ediciones). Reglas permanentes:
- El monto aplicado nunca puede exceder el saldo disponible del pago ni el saldo pendiente de la factura.
- `Payment` y la `Sale`/factura destino deben pertenecer al mismo tenant; al aplicar, `Payment.customer` debe coincidir con `Sale.customer`.
- `Payment.customer` puede ser nulo solo para ventas de mostrador/consumidor final sin cliente registrado — un pago sin cliente **nunca** genera saldo a favor de nadie.
- El saldo pendiente de una factura y el saldo sin aplicar de un pago se calculan siempre desde el ledger, nunca un campo desnormalizado.
- Idempotencia obligatoria (`idempotency_key`); toda operación audita payment recorded/allocated/reversed/voided/refunded.

**Cuentas por cobrar, caja y autorizaciones — construido a partir de FASE 11** (`apps/pos`, `apps/approvals`; diseño completo en `docs/accounts-receivable.md`, `docs/cash-registers.md`, `docs/approvals.md`):
- Anticipo = dinero recibido antes de una factura (un `Payment` sin aplicar); saldo a favor = un único saldo por cliente (nunca dos balances paralelos para "anticipo" y "saldo a favor"). No existe una tabla `CustomerCreditLedger` separada — decisión final: `get_customer_credit_balance`/`get_sale_paid_amount` se generalizaron para sumar `Payment`+`PaymentAllocation` y `CreditNote`+`CreditNoteApplication`, los dos ledgers reales, en vez de crear una tercera fuente de verdad.
- `CreditNote`/`CreditNoteApplication` (en `apps.sales`): nota de crédito compensatoria, misma disciplina de validación que `PaymentAllocation` (nunca sobre-aplicación, nunca cruza tenant/cliente, nunca altera la factura histórica).
- `CashRegister`/`CashSession`/`CashMovement` (`apps.pos`): un tenant puede tener cualquier cantidad de cajas (sin límite fijo). Una `CashSession` abierta es obligatoria antes de confirmar una venta operativa de mostrador. Solo el efectivo afecta el efectivo físico de la caja.
- `ApprovalPolicy`/`ApprovalRequest` (`apps.approvals`): servicio centralizado y reutilizable (nunca lógica de autorización duplicada por módulo) para descuentos por encima del límite (por porcentaje Y por monto, cada uno con su propio tope) y crédito excedido. Jerarquía de resolución: usuario → rol → tenant → negar. El propietario del tenant siempre está autorizado (regla de negocio explícita).

## Compras y cuentas por pagar
Incorporado oficialmente a partir de FASE 12 (`apps/purchases`; diseño completo en `docs/purchases.md`, `docs/purchase-orders.md`, `docs/receiving.md`, `docs/supplier-invoices.md`, `docs/accounts-payable.md`, `docs/supplier-returns.md`). Orquesta sobre `apps.customers` (Suppliers), `apps.inventory`, `apps.approvals` y `apps.pos` — nunca un segundo sistema de inventario, aprobaciones, caja ni archivos. Reglas permanentes:
- `PurchaseOrder`/`PurchaseOrderItem` (numeración `OC-` vía la misma `DocumentSequence` de FASE 10) y `PurchaseReceipt`/`PurchaseReceiptItem` (`REC-`, inmutable, recepción parcial o completa) son documentos independientes — la orden es el compromiso, la recepción es el evento físico que mueve inventario.
- `PurchaseOrderItem` nunca guarda `received_quantity`/`pending_quantity` como campo: se calculan siempre agregando sobre `PurchaseReceiptItem`, nunca una segunda fuente de verdad.
- Recepción de productos QUANTITY vía `register_stock_in`; SERIALIZED vía `register_serialized_unit`, una llamada por unidad física (nunca un alta masiva sin unidades individuales reales).
- `SupplierPayment`/`SupplierPaymentAllocation` (Cuentas por Pagar) son el espejo exacto de `Payment`/`PaymentAllocation` — mismas reglas de sobre-aplicación, mismo tenant/proveedor, mismo ledger append-only — pero **nunca mezclado** con Cuentas por Cobrar (`SupplierPayment` nunca referencia un `Customer`; `Payment` nunca referencia un `Supplier`). Un anticipo a proveedor es un `SupplierPayment` sin aplicar, nunca un modelo aparte.
- `SupplierReturn`/`SupplierReturnItem`: inmutable, mismo principio que `Return`. Una unidad serializada devuelta al proveedor transiciona a `InventoryUnit.Status.DEVUELTO_PROVEEDOR` (agregado en FASE 12) — nunca se reutiliza `DEVUELTO`, que significa lo opuesto (un cliente nos devolvió a nosotros).
- Pago a proveedor en efectivo exige una `CashSession` abierta (`apps.pos`) y genera `CashMovement` (`SUPPLIER_PAYMENT_CASH`/`SUPPLIER_ADVANCE_CASH`) — otros medios no afectan el efectivo físico; no toda compra requiere caja, solo el pago en efectivo.
- Compra sobre el límite y sobre-recepción se autorizan vía `apps.approvals` (`ApprovalPolicy.max_purchase_order_amount`/`max_over_receiving_percent`, `ApprovalRequest.ActionType.PURCHASE_OVER_THRESHOLD`/`OVER_RECEIVING`) — mismas primitivas reutilizables que descuentos/crédito excedido, jerarquía usuario → rol → tenant → negar, propietario siempre autorizado.

## Gastos, Recursos Humanos y Nómina
Incorporado oficialmente a partir de FASE 13 (`apps/expenses`, `apps/hr`, `apps/payroll`; diseño completo en `docs/expenses.md`, `docs/hr.md`, `docs/payroll.md`). Tres dominios relacionados pero separados — nunca fusionados en una sola app ni en un solo modelo. Reutilizan literalmente `apps.customers` (Supplier, `IdentificationType`, documentos seguros de FASE 9), `apps.approvals`, `apps.pos` y `apps.sales` (`DocumentSequence`/`PaymentMethod`) — nunca un segundo sistema de aprobaciones, caja, archivos o numeración. Reglas permanentes:
- `ExpenseCategory`/`LeaveType` son tenant-configurables (nunca una lista cerrada en código); las categorías/tipos sugeridos se crean bajo demanda, nunca automáticamente ni duplicando uno ya personalizado por el tenant.
- `Expense`/`ExpensePayment`/`ExpenseRecurrence`, `Employee`/`EmploymentContract`/`Attendance`/`Leave`/`Incident`, `PayrollPeriod`/`Payroll`/`PayrollLine`/`PayrollPayment`: cada ledger de pago (`ExpensePayment`, `PayrollPayment`) nunca guarda `paid_amount`/`balance_due` como campo — se calculan siempre agregando sobre el ledger, mismo principio que `Payment`/`SupplierPayment` desde FASE 10/12.
- Un pago de gasto o de nómina en efectivo exige una `CashSession` abierta y genera su propio `CashMovement` (`EXPENSE_PAYMENT_CASH`/`PAYROLL_PAYMENT_CASH`) — otros medios no afectan el efectivo físico.
- Autorización por MONTO (gasto sobre el límite, `ApprovalPolicy.max_expense_amount`) vs. autorización por AUTORIDAD pura (ausencias, período de nómina — `can_user_approve`, sin dimensión de umbral): dos criterios deliberadamente distintos según si la operación tiene un "monto dentro de mi límite" natural o no — documentado el porqué en cada caso.
- `PayrollLine` es una única tabla con `category`/`concept` — nunca tablas separadas por tipo de línea (ingreso/deducción/bono/ajuste), mismo principio de no-duplicación que evitó `CustomerCreditLedger` como tercera fuente de verdad en Cuentas por Cobrar.
- `Payroll` congela un snapshot histórico del empleado (nombre, departamento, cargo, salario) al calcularse — modificar `Employee` después nunca altera una nómina ya calculada, mismo principio que `SaleItem` desde FASE 10.
- Información sensible de RRHH (salario, datos bancarios): nunca se restringe ocultando elementos de la UI únicamente — `apps.hr.services.can_view_sensitive_employee_data` es la única fuente de verdad (hoy, con solo dos roles OWNER/MEMBER, solo el propietario), verificada también en el servidor al guardar, y cada lectura por el propietario se audita explícitamente.
- Ningún gasto/nómina se mezcla con Billing del SaaS (`Plan`/`Subscription`, FASE 17) — dominios ortogonales, mismo principio que Cuentas por Cobrar del ERP vs. Billing.

## Moneda, denominaciones y cierre de caja (doctrina, especificación — ver `docs/currency.md`)
El ERP es internacional: nunca hardcodear DOP (ni ninguna otra moneda) ni sus denominaciones como arquitectura fija. `Currency`/`CurrencyDenomination` es el catálogo real (una moneda puede tener cualquier cantidad de denominaciones, cada una billete o moneda, con orden de presentación); `CurrencyConfiguration` define por tenant la moneda funcional, las monedas habilitadas y prepara tipos de cambio futuros (sin motor de FX completo). Reglas permanentes para cuando se implemente:
- `CashRegister` tendrá una moneda operativa principal; su `CashSession` cuenta físicamente en esa única moneda — nunca mezclar denominaciones de monedas distintas en un mismo conteo.
- El cierre por denominaciones (`CashDenominationCount`, referenciando siempre `CurrencyDenomination` — nunca un segundo catálogo) es el modo profesional recomendado; el modo por total manual queda como opción administrativa, nunca el diseño por defecto.
- `CashClosing` es inmutable una vez cerrado (mismo principio que `Return`/`PaymentAllocation` revertida): correcciones posteriores son un nuevo `CashMovement` `ADJUSTMENT` autorizado en una sesión nueva, nunca una edición del cierre histórico. "Sobrante"/"faltante" son lecturas de `difference`, nunca campos nuevos que puedan desincronizarse.
- Vocabulario oficial de cambio en el POS: `amount_due`/`amount_received`/`change_amount`, con el cambio calculado únicamente sobre la parte en efectivo de un pago mixto — **ya implementado correctamente desde FASE 11** (`CheckoutView`), esta doctrina solo lo formaliza. `CashMovement` de una venta con cambio registra siempre el efecto neto (ej. venta 1275, cliente entrega 2000, cambio 725 → movimiento de `+1275`, nunca `+2000`/`-725` por separado) — también ya correcto hoy.
- Sugerencia de cambio por denominaciones: preparada conceptualmente (cálculo codicioso sobre `CurrencyDenomination`), nunca obligatoria para el cajero.

## Contabilidad General y Reportes Profesionales
Incorporado oficialmente a partir de FASE 14 (`apps/accounting`, `apps/reports`; diseño completo en `docs/accounting.md`, `docs/reports.md`). La contabilidad es la fuente financiera central del ERP: los reportes nunca recalculan una cifra financiera de forma independiente cuando esa información debe provenir de contabilidad, y ningún módulo de negocio duplica `Payment`/`PaymentAllocation`/`SupplierPayment`/`CashRegister`/`ApprovalService`/`DocumentSequence` — la contabilidad se contabiliza SOBRE esos módulos, nunca los reemplaza. Reglas permanentes:
- `Account`/`AccountingPeriod`/`JournalEntry`/`JournalEntryLine` son las únicas fuentes de verdad contables. `JournalEntryLine` exige débito XOR crédito (nunca ambos, nunca ninguno); un asiento solo puede pasar a `POSTED` si `SUM(débitos) == SUM(créditos)` — nunca un asiento desbalanceado. `AccountingPeriod` no usa `DocumentSequence` (no es un documento que se emite, es un contenedor de tiempo) y nunca se solapa con otro período no cerrado del mismo tenant.
- Inmutabilidad: un asiento `POSTED` nunca se edita ni se borra físicamente. Toda corrección es un reverso (`reverse_journal_entry`, débito/crédito invertidos, enlazado vía `reversal_of`, idempotente) — mismo principio que `Return`/`PaymentAllocation` revertida.
- Contabilización automática: arquitectura Evento de negocio → Servicio de Contabilidad → `JournalEntry`, nunca lógica contable dentro de una vista de otro módulo. `record_business_event` es idempotente por `(tenant, source_type, source_event_key)` — un reintento nunca duplica un asiento. Cada integración resuelve sus cuentas de control vía `AccountMapping`; si falta un mapeo, la contabilización se omite en silencio y se audita — **nunca bloquea la operación de negocio subyacente**. Toda función `try_record_*` que envuelve una integración debe atrapar cualquier excepción y auditar, nunca relanzarla — regla permanente para toda futura integración automática.
- Balance General = acumulado desde el origen (activo/pasivo/patrimonio son saldos, no flujos); Estado de Resultados = acotado al período (ingreso/costo/gasto reinician cada período) — nunca la misma lógica de fechas para ambos.
- `apps/reports` nunca introduce un modelo propio de datos de negocio: cada reporte agrega/filtra sobre los servicios/modelos que YA existen en cada dominio (mismo principio que evitó una segunda fuente de verdad en Inventario/Cuentas por Cobrar), y expone siempre `{"summary": ..., "rows": ...}` con drill-down como enlace directo al documento origen, nunca una copia de esos datos. Información sensible (salario/datos bancarios en reportes de RRHH/Nómina) se filtra siempre en el servidor, nunca solo oculta en la UI — mismo criterio que FASE 13.

### Ampliación de cierre de FASE 14: costeo, COGS, Compras/AP, cierre de caja, impuestos multi-código
Cierre controlado posterior al cierre inicial de FASE 14, autorizado explícitamente por el usuario con las decisiones de política contable que faltaban (nunca inventadas). Reglas permanentes agregadas:
- Costeo: SERIALIZED usa costo específico por unidad (`InventoryUnit.unit_cost`, sin cambios desde FASE 8/12); QUANTITY usa promedio ponderado (`StockMovement.unit_cost`/`average_cost_after`, mismo patrón que `stock_before`/`stock_after` — calculados y guardados una vez por movimiento, nunca editados después). Nunca FIFO en esta ampliación (descartado explícitamente). `SaleItem.cost_amount` snapshotea el costo de cada línea al momento de `confirm_sale` (cuando el inventario REALMENTE se mueve, nunca al agregar la línea a un borrador).
- COGS: asiento SEPARADO del de ingresos (Dr Costo de Ventas / Cr Inventario), nunca fusionado con `record_sale_confirmed`. Reverso de COGS en devoluciones de mercancía (proporcional, solo si el COGS original existe) — un `Refund` monetario nunca lo dispara, por construcción (son código-caminos independientes).
- Compras/Cuentas por Pagar: factura de proveedor confirmada distingue línea de inventario (Dr Inventario) de línea de gasto (Dr Gasto Operativo, sin orden de compra asociada) — nunca la misma cuenta para ambas. `SupplierPayment`/`SupplierReturn` contabilizan como espejo exacto de Cuentas por Cobrar, nunca mezclado con ella.
- Cierre de caja: la diferencia (sobrante/faltante) descubierta al contar se reconoce en cuentas dedicadas (`cash_over`/`cash_short`, convención "Cash Over and Short") — nunca duplica el efectivo esperado ya contabilizado por los eventos de venta/pago/gasto/nómina. No se crea un modelo `CashClosing` nuevo: el evento de cierre sigue siendo `CashSession.status=CLOSED` (FASE 11).
- Impuestos multi-código: `TaxCode` (tenant-configurable, su propia cuenta de control) + `SaleItemTax` (cero/una/varias filas por línea) son ADITIVOS — los campos planos `SaleItem.tax_rate`/`tax_amount` siguen funcionando igual para cualquier tenant que nunca asigne un `TaxCode`. Nunca normativa fiscal de un país específico hardcodeada.
- Exportación PDF/XLSX real (`reportlab`/`openpyxl`, puro-Python, sin dependencias nativas) en los reportes tabulares principales — aprobado explícitamente por el usuario, a diferencia de librerías con dependencias de sistema operativo (rechazadas en fases anteriores).

## Roles, Permisos, Auditoría transversal y API de Inventario
Incorporado oficialmente a partir de FASE 15 (`apps/permissions`, `apps/audit`, `apps/api`; diseño completo en `docs/roles-permissions.md`, `docs/audit.md`, `docs/api-inventory.md`). Tres subsistemas que generalizan — nunca reemplazan — lo ya construido: la autorización binaria OWNER/MEMBER (`apps.tenants.permissions.require_role`), los 7 registros de actividad por dominio (`*ActivityLog`) y la especificación de API previa. Reglas permanentes:
- `Membership.Role` se amplía con `ADMIN`/`MANAGER`/`CASHIER`/`EMPLOYEE` como opciones adicionales (`MEMBER` se conserva sin cambios); `SUPER_ADMIN` de la especificación se adapta a `User.is_superuser` (concepto de plataforma, no de tenant). `apps.permissions.services.has_permission` resuelve un catálogo código-definido de ~85 permisos (`PERMISSION_CATALOG`, nunca una tabla tenant-configurable — los permisos son funcionalidad del código) con la MISMA jerarquía usuario→rol→tenant→negar que `apps.approvals.get_effective_policy` ya usaba para umbrales de aprobación; `RolePermission`/`UserPermissionOverride` son la personalización por tenant/usuario. `require_tenant`/`require_role` NUNCA se retiran de ninguna vista existente — el retrofit de permisos granulares es un rollout deliberado por fases (RRHH/Nómina sensible, operaciones contables, caja, Auditoría, Configuración, más un dominio CRUD representativo), documentado explícitamente, nunca una brecha de seguridad.
- `apps.audit.AuditLog` (tenant NULABLE — a diferencia de `TenantScopedModel`, un login fallido de un email inexistente no tiene tenant que asignarle) complementa, nunca reemplaza, los 7 `*ActivityLog` ya existentes: `apps.audit.services.search_audit_events` los federa a todos (más `StockMovement`) en una sola búsqueda vía `UNION` SQL, con todos los filtros aplicados por rama ANTES de unir. Inmutable (sin `update`/`delete`, admin de solo lectura). Toda integración automática (señales de login/logout/login fallido, cambios de permiso, lecturas sensibles, exportaciones) sigue el mismo patrón resiliente que `try_record_*` de `apps.accounting`: la auditoría nunca debe poder romper la operación que audita. Un login fallido nunca guarda la contraseña.
- `apps.api` (`/api/v1/`, Django REST Framework) es la API de Inventario v1: **read-only por defecto**, autenticada por `ApiKey` (hash SHA-256, el secreto en texto plano nunca se guarda, se muestra una única vez al generar/rotar), un tenant tiene como máximo una clave activa a la vez (rotar reescribe la misma fila, nunca crea una segunda). El tenant SIEMPRE se resuelve desde la clave, nunca de un parámetro enviado por el cliente. Scopes cerrados y código-definidos (`inventory:read`/`products:read`/`categories:read`/`inventory_movements:read`/`serialized_inventory:read`/`health:read`) — **nunca acceso financiero por defecto**, ninguna escritura en ningún endpoint. Sobre de respuesta consistente (`success`/`data`/`meta`/`errors`, nunca un traceback interno), paginación con tope de `page_size`, rate limiting configurable a nivel de proyecto (`LocMemCache`, Redis deferido). Identificadores sensibles (IMEI/serie, y ahora también la propia API Key) se enmascaran vía el helper compartido `apps.core.utils.mask_secret`.

### Ampliación final de FASE 15: Catalog API + Integraciones externas Multi-Tenant
Segunda capa de API, deliberadamente separada de la Inventory API administrativa — diseño completo en `docs/api-catalog.md`, `docs/integrations.md`. Reglas permanentes:
- **Dos capas, nunca mezcladas**: `/api/v1/` (Inventory API, administrativa, autenticada por `ApiKey`) y `/api/v1/catalog/` (Catalog API, comercial, autenticada por `Integration`) tienen credenciales, scopes (`catalog:read`/`catalog:availability:read`/`catalog:media:read`, catálogo separado de los de Inventory API) y límites de tasa completamente independientes — una credencial de una capa nunca autentica a la otra.
- `Integration` (`apps.api`) es el concepto GENÉRICO de aplicación externa conectada — un tenant puede tener varias (a diferencia de `ApiKey`, una por tenant). Espejo estructural deliberado de `ApiKey` (mismo criterio ya usado para `SupplierPayment`/`Payment`: dos conceptos separados que nunca comparten tabla aunque su forma sea casi idéntica) — comparten únicamente el mecanismo de generación/hash del secreto (`apps.api.crypto`), nunca la tabla. `provider` (hoy solo `BUDUN` con soporte real) identifica QUIÉN construyó el consumidor — nunca confundido con una "tool" de agente IA, que vive exclusivamente en el consumidor externo (el ERP nunca implementa `search_budun()` ni ninguna función acoplada a un consumidor concreto).
- `Product` gana campos comerciales opcionales (`brand`, `model_name`, `variant_attributes` — JSON flexible, nunca columnas fijas de color/capacidad/talla) y `ProductImage` (imágenes públicas/publicables, almacenadas en `settings.CATALOG_MEDIA_ROOT`, físicamente separado de `media-private/`, servidas por UUID no adivinable, nunca por ID secuencial). La disponibilidad comercial (`available`/`available_quantity`) viene SIEMPRE de la misma fuente de verdad que la Inventory API (`current_stock` anotado) — nunca un contador paralelo.
- Whitelist server-side estricta en los serializers de Catalog API: nunca expone IMEI/serie (ni siquiera enmascarado), costo/margen/proveedor, ni datos de otro dominio (clientes, pagos, caja, contabilidad, nómina, RRHH) — verificado con tests que comprueban la AUSENCIA de esos campos, no solo la presencia de los permitidos.

## PayPal (Payment Provider Interface)
Incorporado oficialmente a partir de FASE 16 (`apps/billing`; diseño completo en `docs/paypal.md`). PayPal es un proveedor de pagos EXCLUSIVO del Billing SaaS (lo que un `Tenant` paga a Budun ERP por usar la plataforma, FASE 17) — **nunca** se conecta a `apps.sales.Payment`/`PaymentAllocation`/`Refund` (el motor de cuentas por cobrar de cada tenant, FASE 10/11), ejes ortogonales que no se mezclan. Reglas permanentes:
- Arquitectura obligatoria `Billing SaaS → Payment Provider Interface (apps.billing.providers.base.PaymentProvider) → PayPal Provider` — ninguna lógica específica de PayPal en modelos ni en vistas; `get_default_provider()` es el único punto de construcción, dejando espacio para Transferencia Bancaria u otro proveedor (FASE 17) sin rehacer el núcleo.
- `PayPalTransaction`/`PayPalWebhookEvent`/`PayPalGatewayStatus` (`apps.billing.models`) NO heredan `TenantScopedModel` — el actor es el Super Admin de PLATAFORMA, no un tenant (mismo principio que `AuditLog`/`Membership`). Las credenciales (Client ID/Secret/ambiente/Webhook ID) son variables de entorno de plataforma, nunca de base de datos ni de un tenant; el access token OAuth2 nunca se persiste, solo se cachea en memoria del proceso.
- Orders API v2 (crear orden, capturar, reembolsar) es el flujo elegido — nunca Subscriptions API (crear `Plan`/`Product` del lado de PayPal habría anticipado el `Plan` real de FASE 17 antes de que exista, el "segundo sistema de Billing" que la fase prohíbe). Idempotencia en dos niveles: `PayPal-Request-Id` hacia PayPal (derivado de `client_reference`, estable por transacción) y `UniqueConstraint` en `PayPalWebhookEvent.event_id` hacia nosotros mismos — un evento externo repetido o fuera de orden nunca duplica dinero ni retrocede un estado ya alcanzado.
- Webhook (`/webhooks/paypal/`) público sin autenticación por sesión — la seguridad es la verificación oficial de firma (`/v1/notifications/verify-webhook-signature`), nunca confiar en el remitente; la vista nunca toca el ORM directamente, siempre delega al servicio central.
- Acceso a la administración de PayPal (estado, Test Connection, iniciar cobro, reembolsar) exige `request.user.is_superuser` (`apps.tenants.permissions.require_superuser`/`SuperuserRequiredMixin`) — nunca el catálogo de `apps.permissions` (tenant-scoped por diseño, no aplica a un recurso de plataforma). Toda operación se audita (`apps.audit`, dominio `"billing_paypal"`, `tenant` puede ser `None`); el client secret/access token/firma cruda nunca se auditan.

## Fases
Exactamente 25 fases: 0–24. No saltar, fusionar ni crear nuevas fases sin justificación documentada.

## Ciclo de fase
Analizar → planificar → implementar → ejecutar → probar → corregir → volver a probar → documentar → commit → cerrar.

## Criterio de PASS
Una fase solo pasa si está implementada, ejecutada y verificada con evidencia.

## Seguridad
CSRF, XSS, SQL injection protection, auth/authz, secure cookies, rate limiting, tenant isolation, webhook verification, secrets fuera de Git, logs sin secretos, auditoría.

## Datos y dinero
PostgreSQL con constraints, índices y transacciones apropiadas. Usar Decimal para dinero. Operaciones de venta/pago/inventario deben ser atómicas.

## Git
Commit por fase. No hacer commits gigantes. No commitear .env, API keys, passwords, tokens, dumps ni claves privadas.

## Regla de parada
Al terminar una fase, generar un reporte y detenerse hasta recibir autorización para la siguiente fase, salvo que el usuario haya indicado expresamente que se pueden ejecutar las siguientes fases en la misma instrucción.

## Fuente de verdad
Este archivo, docs/MASTER-PROMPT.md, docs/phases/PHASES.md y docs/phases/FASES_OFICIALES_0_24_ACTUALIZADAS.md (fuente maestra de alcance por fase, entregada por el usuario tras el cierre de FASE 11) son la fuente de verdad del proyecto. Si hay conflicto, prevalecen en ese orden.


## Construcción incremental
Claude NO debe crear toda la estructura del ERP en la FASE 1. Debe crear únicamente los archivos, apps, modelos, servicios, templates, pruebas y documentación necesarios para la fase activa y sus dependencias inmediatas. Puede preparar interfaces de extensión, pero no debe implementar funcionalidades futuras anticipadamente. Cada fase amplía el proyecto de manera incremental.

## PostgreSQL + pgAdmin 4
Antes de configurar la base local, leer `docs/setup/windows-postgresql-pgadmin-step-by-step.md`. Claude debe detectar instalación, servicio, puerto y versión de PostgreSQL. Si puede crear DB/usuario por CLI de forma segura, puede hacerlo; pgAdmin 4 se usa para administrar y verificar. Si se necesita una contraseña o confirmación que solo el usuario puede suministrar, detenerse y dar instrucciones paso a paso.

## Integraciones
Para PayPal, PayPal MCP, GitHub y Hostinger, Claude debe consultar documentación oficial vigente cuando la implementación llegue a esa fase. Nunca inventar endpoints, herramientas MCP, argumentos o configuraciones.
