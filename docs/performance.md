# Performance

> **Estado: FASE 19 — Performance ejecutada.** Este documento reúne
> las prácticas de rendimiento de todo el proyecto (FASE 0–18) más los
> hallazgos reales medidos, reproducidos y corregidos en FASE 19
> (metodología baseline → profiling → reproducir → optimizar → test →
> remedir → comparar → documentar, checklist completo en
> `docs/phases/PHASE-19-performance.md`). Cada sección marca
> **Construido** (verificado con medición real) y, cuando aplica,
> **Pendiente / fuera de alcance de esta pasada** (con la razón
> explícita). El detalle de cada hallazgo con números antes/después
> reales vive en el reporte de cierre entregado al usuario — este
> documento resume el estado final.

## PostgreSQL — índices y constraints
**Construido**: cada dominio con volumen real de datos (Inventario,
Ventas, Compras, Contabilidad, RRHH/Nómina, Auditoría, Permisos, POS)
define sus propios `models.Index`/`UniqueConstraint` compuestos desde
que ese dominio se construyó — no agregados después como optimización
retroactiva, sino parte del diseño original de cada modelo. Ejemplos
reales: `apps.sales.models` (17 índices — numeración de documentos,
búsquedas por cliente/estado/fecha), `apps.purchases.models` (9),
`apps.inventory.models` (8 — incluye los índices parciales de
serial/IMEI únicos por tenant), `apps.accounting`/`apps.expenses`/
`apps.hr.models` (6 cada uno), `apps.audit.models` (4 — `AuditLog`
filtrado por tenant+fecha/dominio/usuario/acción, pensado
explícitamente para que `search_audit_events` no dependa de un table
scan). `UniqueConstraint` con `condition=Q(...)` (índice parcial de
PostgreSQL) ya se usa donde la unicidad es condicional: una versión de
plan vigente por plan+frecuencia (`PlanVersion`), una factura por
período (`SaaSInvoice`), un contrato activo por empleado
(`EmploymentContract`).
**Verificado con `EXPLAIN ANALYZE` real en FASE 19**: la búsqueda
federada de auditoría (`apps.audit.services.search_audit_events`)
sobre 8000 filas de `AuditLog` de un tenant + 2000 de otro (ruido) —
`Index Scan Backward using idx_auditlog_tenant_fecha`, nunca un
sequential scan, `Execution Time: 3.1ms` para la rama de `AuditLog`
sola; la búsqueda federada completa (UNION de las 8 fuentes + count +
página) tomó 70ms para 8000 coincidencias — el índice compuesto
`(tenant, created_at)` se usa exactamente como se diseñó.
**Pendiente / fuera de alcance de esta pasada**: solo se corrió
`EXPLAIN ANALYZE` sobre esta consulta (la más arquitectónicamente
novedosa — un UNION de 9 fuentes); el resto de índices del proyecto
sigue sin verificación formal query-por-query contra un dataset
grande, ni revisión de índices potencialmente sin uso (dead index).

## Django ORM — N+1, select_related/prefetch_related
**Construido**: 46 usos de `select_related`/`prefetch_related` en todo
el proyecto; el principio "nunca un stock/saldo/total desnormalizado,
siempre calculado desde el ledger real" (`StockMovement`,
`PaymentAllocation`, `SupplierPaymentAllocation`, `JournalEntryLine`)
se combina siempre con anotaciones a nivel de base de datos
(`Case`/`When`/`Sum`/`Count` vía `.annotate()`), nunca un bucle Python
que recalcule por fila — el propio `get_current_stock`/
`list_products_with_stock` (FASE 8) es el ejemplo de referencia que
las fases posteriores repiten. Existen archivos de test DEDICADOS a
demostrar ausencia de N+1 comparando el conteo real de queries (vía
`django.test.utils.CaptureQueriesContext`, nunca solo "se ve bien" ni
`assertNumQueries` genérico) entre un escenario con pocos registros y
uno con muchos: `apps/inventory/tests/test_performance.py`,
`apps/sales/tests/test_performance.py`,
`apps/pos/tests/test_performance.py`,
`apps/customers/tests/test_performance.py`, y una verificación
equivalente dentro de `apps/dashboard/tests.py` (KPIs con 1 vs. 10
miembros). Un N+1 real ya fue encontrado y corregido en el pasado
(`get_customer_pending_sales`, FASE 11 — resuelto con
`get_sale_balance_due_bulk`, documentado en `PHASE_HISTORY.md`).
**Hallazgo real corregido en FASE 19 (N+1)**: `apps.accounting.
services.get_general_journal` (Libro Diario) llamaba a
`get_journal_entry_lines` una vez POR ASIENTO dentro de un `for` —
medido con un dataset sintético (`perf_baseline.py`, scratchpad de la
sesión, no commiteado): 10 asientos → 11 queries/42ms; 300 asientos →
**301 queries/783ms** (18.7x más lento, escalando linealmente con el
volumen — N+1 real y demostrado). Corregido con `Prefetch` explícito
sobre `all_objects` (mismo criterio ya establecido para toda relación
inversa sobre un modelo `TenantScopedModel`, `KNOWN_ISSUES.md`
#90/#95/#97/#108): después de la corrección, 300 asientos → **2
queries/189ms** (constante, 4.1x más rápido). Regresión agregada:
`apps/accounting/tests/test_performance.py` (nuevo archivo, mismo
patrón `CaptureQueriesContext` de pocos-vs-muchos registros).
**Verificado sin hallazgo en FASE 19** (medido, no solo revisado por
código): listado HTTP real de Purchases (`GET /compras/ordenes/`, 10
vs. 200 órdenes → 5 queries constante); `get_trial_balance` (una sola
consulta agregada, 300 asientos → 33ms); `get_billing_dashboard_summary`
(10 vs. 200 suscripciones/facturas → 10 queries constante);
`search_audit_events` (10 vs. 300 filas → 2 queries constante, ver
sección PostgreSQL).
**Pendiente / fuera de alcance de esta pasada**: el mismo patrón de
`test_performance.py` dedicado NO existe todavía en `apps.expenses`,
`apps.hr`, `apps.payroll`, `apps.reports`, `apps.permissions`, ni la
Inventory API (`apps.api.views`) — se midió lo suficiente para
confirmar que siguen el mismo principio de diseño (anotar en base de
datos, nunca en Python), pero sin una prueba de regresión explícita
punto por punto en cada uno.

## Multi-Tenant + Performance
**Construido**: toda optimización de consulta hasta ahora se hizo
siempre DENTRO del manager tenant-scoped (`TenantManager`/
`for_current_tenant()`) o con un filtro `tenant=` explícito — nunca se
usó `all_objects` como atajo de rendimiento (su único uso legítimo,
documentado repetidamente en `KNOWN_ISSUES.md` #90/#95/#97/#108, es
resolver el gotcha de contexto fuera de una request real, nunca evitar
un filtro por velocidad).
**Pendiente / fuera de alcance de esta pasada**: confirmar explícitamente, con `EXPLAIN`, que
el índice compuesto `(tenant_id, ...)` de cada tabla de alto volumen
es efectivamente el que PostgreSQL elige primero en los queries reales
del proyecto (nunca asumido).

## Paginación
**Construido**: `paginate_by = 20` consistente en las vistas HTML de
listado (`apps.customers`, `apps.expenses`, `apps.hr`, `apps.inventory`,
`apps.purchases`, `apps.sales`); `apps.api.pagination.ApiV1Pagination`
(DRF) con `page_size=20`, tope duro `max_page_size=100` — un cliente de
la API nunca puede pedir "todo" en una sola página.
**Hallazgo real corregido en FASE 19**: el TOPE de página ya existía y
funcionaba en la Catalog API, pero dos vistas hacían trabajo COSTOSO
(precargar imágenes) sobre el resultado completo ANTES de aplicar ese
tope — ver el hallazgo detallado en la sección "APIs" más abajo. La
paginación en sí (el corte de filas) siempre fue correcta; el error
era el ORDEN de las operaciones alrededor de ella.
**Pendiente / fuera de alcance de esta pasada**: el costo de `Paginator.count`
(un `COUNT(*)` completo en cada página) no se midió contra una tabla
con volumen realmente grande; cursor/keyset pagination explícitamente
NO se considera todavía sin evidencia real de que el `COUNT`/`OFFSET`
sea el cuello de botella (mismo criterio que ya fija la especificación
de la fase).

## Inventory
**Construido**: `get_current_stock`/`list_products_with_stock` es la
única fuente de verdad de stock para QUANTITY y SERIALIZED a la vez,
una sola consulta anotada (nunca 2×N); búsqueda unificada
(`search_catalog`) reutilizada literalmente por POS/Ventas/Compras/
Catalog API en vez de reimplementarse cuatro veces.
**Pendiente / fuera de alcance de esta pasada**: medir `search_catalog`/`low-stock`/
`inventory/movements` de la Inventory API con un catálogo de miles de
productos (el dataset de prueba actual del proyecto es pequeño, nunca
representativo de un tenant real grande).
**Construido** (extensión de FASE 8, ver `docs/products.md`,
"Importación y exportación masiva de productos"): la
importación/exportación de productos vía Excel sigue la misma
disciplina de esta fase — `apps.inventory.product_import.build_preview`
resuelve SKUs/barcodes/categorías con consultas en bloque, nunca una
por fila, verificado con un test de conteo de queries constante entre
5 y 50 filas.

## Sales / POS
**Construido**: confirmación de venta reutiliza literalmente
`apps.inventory.services` (nunca una segunda ruta de movimiento de
stock); `PaymentAllocation`/cuentas por cobrar calculadas siempre desde
el ledger con consultas agregadas (`get_sale_balance_due_bulk`
corrigiendo el N+1 real de FASE 11); cobertura de `test_performance.py`
ya existente en ambos dominios.
**Pendiente / fuera de alcance de esta pasada**: medir el checkout completo (carrito → pagos
múltiples → cambio → cierre de caja) con un volumen de líneas/ítems por
venta más alto que el usado en los tests actuales.

## Purchases / Cuentas por Pagar
**Construido**: `PurchaseOrderItem.received_quantity`/`pending_quantity`
se calculan siempre agregando sobre `PurchaseReceiptItem` (nunca un
campo desnormalizado); ya existe una variante en bloque para evitar
N+1 al calcular la cantidad recibida de varias líneas a la vez
(documentado en el resumen de cierre de FASE 12).
**Verificado en FASE 19**: el listado real (`GET /compras/ordenes/`,
usado también por el template — `select_related("supplier")`, total
ya desnormalizado en `PurchaseOrder.total`) medido con 10 vs. 200
órdenes: 5 queries constante, sin crecer. Los dos usos de
`get_purchase_order_item_pending_quantity` (singular) confirmados
como contextos de UN solo ítem a la vez (recepción línea por línea),
nunca dentro de un loop sobre varios ítems — no son N+1.
**Pendiente / fuera de alcance de esta pasada**: sin `test_performance.py`
dedicado todavía (a diferencia de `apps.accounting`, que sí lo ganó en
esta fase); sin medición real de reportes de Compras/CxP con volumen
alto.

## Accounting
**Construido**: los 5 reportes contables (Balance de Comprobación,
Libro Mayor, Libro Diario, Balance General, Estado de Resultados) leen
directamente de `JournalEntry`/`JournalEntryLine` con agregaciones de
base de datos, nunca recorriendo asientos en Python.
**Hallazgo real corregido en FASE 19**: ver sección "Django ORM" arriba
— el Libro Diario (`get_general_journal`) tenía N+1 real, ahora
corregido y con regresión (`apps/accounting/tests/test_performance.py`).
`get_trial_balance` medido (300 asientos → 1 query/33ms) confirma que
sí es una agregación real de base de datos, nunca un recorrido Python.
**Pendiente / fuera de alcance de esta pasada**: Balance General/Estado
de Resultados/Libro Mayor no se midieron con un volumen de miles de
asientos en esta pasada (solo el Libro Diario, que era el que tenía el
problema real).

## Reports
**Construido**: cada reporte de `apps.reports` agrega siempre sobre
servicios/modelos ya existentes (nunca un modelo propio de datos,
principio ya fijado desde FASE 14); margen/COGS de Ventas y
valorización de Inventario se calculan en una sola consulta agregada
adicional (documentado en la ampliación de cierre de FASE 14), no por
fila.
**Pendiente / fuera de alcance de esta pasada**: preferir SQL para el resto de agregaciones que
todavía combinan una consulta base con post-procesamiento en Python
(revisión pendiente, no auditada campo por campo en esta sincronización);
medir tiempo real de generación de cada reporte con volumen alto.

## Exports (CSV/XLSX/PDF)
**Construido**: los tres exportadores (`apps.reports.exports`,
`reportlab`/`openpyxl`) reciben siempre `rows` ya materializadas por el
servicio del reporte (una sola consulta previa), nunca vuelven a
consultar la base de datos por fila.
**Pendiente / fuera de alcance de esta pasada**: sin streaming/chunks — todo el archivo se
arma en memoria (`BytesIO`) antes de responder; no medido si esto es un
problema real con una exportación de decenas de miles de filas (la
mitigación de FASE 18, `sanitize_cell_value`, no cambia este costo).

## Billing SaaS
**Construido**: mismo principio de agregación en base de datos que
`apps.reports` para `get_billing_dashboard_summary`/`get_revenue_report`/
`get_subscriptions_report`/`get_invoice_aging_report`; `SaaSInvoice.
UniqueConstraint(subscription, period_start)` evita el trabajo
duplicado de una facturación recurrente reintentada, no solo un
problema de correctitud sino también de carga.
**Verificado en FASE 19**: `get_billing_dashboard_summary` medido con
10 vs. 200 suscripciones/facturas — 10 queries constante, sin N+1.
**Pendiente / fuera de alcance de esta pasada**: sin medición real de
la generación masiva de facturas recurrentes
(`generate_due_renewal_invoices`) con muchos tenants/suscripciones a
la vez; `get_revenue_report`/`get_subscriptions_report`/
`get_invoice_aging_report` no medidos en esta pasada (solo el
dashboard).

## APIs (Inventory API / Catalog API)
**Construido**: `ApiV1Pagination` con tope duro; serializers explícitos
(nunca `fields = "__all__"`, confirmado en FASE 18); `ApiKeyRateThrottle`/
`CatalogRateThrottle` limitan el throughput por credencial;
`ProductSerializer.get_category` confirmado seguro — `list_products_with_stock`
ya hace `select_related("category")`, verificado por código.
**Hallazgo real corregido en FASE 19 (Catalog API)**:
`CatalogSearchView`/`CatalogProductListView.list` llamaban a
`_adjuntar_imagenes` (el helper que precarga `ProductImage` en bloque,
sin N+1 — ya bien diseñado en sí mismo) sobre el queryset COMPLETO
**antes** de paginar, no sobre la página ya recortada — con miles de
productos coincidentes, esto consultaba y cargaba en memoria las
imágenes de TODOS ellos aunque `page_size` solo devuelva 20. Medido
(`perf_catalog.py`, scratchpad, con warm-up para descartar el costo de
arranque en frío): `catalog:search` con 20 productos coincidentes →
83ms/136KB de pico; con 2000 → **537ms/5035KB** (6.5x más lento, 37x
más memoria, para devolver la MISMA página de 20 resultados).
Corregido invirtiendo el orden (paginar primero, adjuntar imágenes
solo a la página): con 2000 productos coincidentes →
**40ms/161KB** — plano, ya no escala con el total de coincidencias.
`catalog:products` (sin filtro de búsqueda) pasó de 550ms/4927KB a
157ms/169KB. Regresión agregada (`apps/api/tests/test_catalog_views.py`,
`CatalogPaginationPerformanceTests`): espía sobre `_adjuntar_imagenes`
que confirma que solo recibe los productos de la página (20), nunca
el total de coincidencias (31 en el test).
**Pendiente / fuera de alcance de esta pasada**: tamaño de payload de
cada endpoint restante (`inventory/movements`, `low-stock`, `availability`,
`variants`) no medido contra un catálogo grande en esta pasada.

## PayPal / Webhooks
**Construido**: el webhook nunca abre una transacción de base de datos
larga alrededor de la llamada HTTP externa a PayPal (la verificación de
firma ocurre antes de cualquier escritura); idempotencia vía
`UniqueConstraint` evita reprocesar un evento repetido.
**Pendiente / fuera de alcance de esta pasada**: tiempo real de procesamiento del webhook no
medido; sin revisión explícita de si algún `select_for_update()` del
flujo de confirmación queda retenido más tiempo del necesario alrededor
de la llamada a PayPal.

## Cache
**Construido**: `LocMemCache` (`CACHES["default"]`) se usa HOY
exclusivamente para contadores de rate limiting (`apps.api.throttling`,
`apps.accounts.rate_limit` desde FASE 18, el rate limit del webhook de
PayPal) y para cachear el access token OAuth2 de PayPal
(`apps.billing.providers.paypal`, con expiración real) — nunca para
cachear el resultado de una consulta/reporte. Verificado por búsqueda
exhaustiva de `cache.get`/`cache.set` en todo el proyecto: ningún otro
uso existe.
**Pendiente / fuera de alcance de esta pasada**: evaluar (nunca introducir a ciegas) cache de
resultado para reportes/dashboards costosos, solo si una medición real
demuestra que la consulta es cara Y el dato tolera staleness Y la
invalidación es segura sin riesgo cross-tenant — mismo criterio que ya
fija la especificación de la fase. Redis sigue sin justificación real
de necesidad (`LocMemCache` de un solo proceso sigue siendo suficiente
para todo lo construido hasta ahora).

## Concurrencia
**Construido**: `select_for_update()` en 20 archivos de servicio
distintos (`apps.inventory`, `apps.sales`, `apps.pos`, `apps.purchases`,
`apps.expenses`, `apps.hr`, `apps.payroll`, `apps.accounting`,
`apps.approvals`, `apps.billing` — prácticamente todo dominio con
dinero/inventario compartido); probado con hilos reales
(`TransactionTestCase` + `threading`) desde FASE 8, ampliado en cada
fase posterior (stock, reservas, pagos/allocation, apertura de caja,
recepción de compras, generación de nómina, aprobaciones, rotación de
`ApiKey` desde FASE 18, idempotencia de webhooks, generación de
factura recurrente).
**Pendiente / fuera de alcance de esta pasada**: sin medición de CUÁNTO tiempo retiene cada
lock bajo carga real (duración de la transacción, no solo "gana
exactamente una operación" — que ya está probado); sin prueba de
contención con más de 2 hilos simultáneos en ningún escenario.

## Memoria / CPU
**Construido**: límites duros ya existentes que acotan el peor caso
(`DATA_UPLOAD_MAX_MEMORY_SIZE`/`FILE_UPLOAD_MAX_MEMORY_SIZE` = 10 MB,
`apps.customers.file_validation.MAX_UPLOAD_SIZE_BYTES` = 10 MB).
**Metodología de medición establecida en FASE 19**: `tracemalloc`
(memoria pico) + `time.process_time()` (proxy de CPU) + `time.
perf_counter()` (tiempo real), ambos de la librería estándar — sin
agregar `psutil` ni ninguna dependencia de profiling nueva (no
disponible/instalada, y no se justificó su necesidad). Con esta
metodología se midió el hallazgo de memoria real de esta fase: el
pico de memoria de la Catalog API pasó de ~5MB a ~160KB al corregir el
orden de paginación (ver sección "APIs" arriba) — la única medición de
memoria de esta pasada que reveló un problema real.
**Pendiente / fuera de alcance de esta pasada**: memoria/CPU de
exportaciones grandes (CSV/XLSX/PDF con miles de filas) y de
procesamiento de imágenes de `ProductImage` no medidas en esta pasada.

## Benchmarks
Los benchmarks reales de esta fase (operación/dataset/antes/después)
viven en el reporte de cierre entregado al usuario y, resumidos, en
las secciones "Django ORM" y "APIs" de este documento — 2 hallazgos
reales, cada uno con medición reproducible antes y después (nunca una
métrica inventada). El script de medición (`perf_baseline.py`/
`perf_catalog.py`/`perf_explain_audit.py`) vive en el scratchpad de la
sesión, no commiteado (mismo criterio que los smoke tests de fases
anteriores) — reproducible ejecutándolo contra una base de datos de
desarrollo real.
**Pendiente / fuera de alcance de esta pasada**: benchmarks de los
dominios listados como "fuera de alcance" en cada sección de este
documento (Expenses/HR/Payroll, la mayoría de Reports, exportaciones,
generación masiva de facturas recurrentes).

## Dependencias
Sin ninguna dependencia de profiling/benchmark agregada todavía
(`django-silk`, `django-debug-toolbar` en producción, `locust`, etc.) —
decisión pendiente de FASE 19, solo si se justifica con necesidad real,
nunca por costumbre de la industria sin evidencia de que este proyecto
la necesite.

## Qué NO se construye con este documento
Ningún índice, migración, cache, cambio de código, ni benchmark real —
esta síntesis es exclusivamente documental (inventario de qué ya existe
y qué falta medir/optimizar). Ver
`docs/phases/PHASE-19-performance.md` para el checklist completo de la
fase.
