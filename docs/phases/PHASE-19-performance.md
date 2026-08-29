# FASE 19 — PERFORMANCE PROFESIONAL

## Medición, Profiling, PostgreSQL, ORM, APIs, Reportes, Billing, Cache y Optimización Basada en Evidencia

> **Estado: EJECUTADA.** Ver `docs/performance.md` para el estado
> consolidado (Construido/Verificado/Pendiente) y el reporte de cierre
> entregado al usuario para el detalle de cada hallazgo con
> mediciones antes/después reales. Los "Criterios de aceptación" de la
> sección 38 se marcaron abajo con evidencia — cada casilla indica el
> alcance REAL medido en esta pasada, no una auditoría exhaustiva de
> cada endpoint/reporte del proyecto. Lo explícitamente fuera de
> alcance (Expenses/HR/Payroll, la mayoría de Reports, exportaciones a
> volumen, cache de reportes, generación masiva de facturas
> recurrentes, medición de duración de locks) queda documentado, nunca
> oculto — ver sección 39 y el reporte de cierre.

# 0. ESTADO

FASE 18 está cerrada como PASS.

La documentación de FASE 19 ya fue sincronizada.

Estado previo conocido:

* Suite completa: 1094/1094 tests OK.
* `manage.py check`: limpio.
* `makemigrations --check --dry-run`: limpio.
* FASES 0–18 implementadas.
* `docs/performance.md`: existente y sincronizado.
* FASE 19 aún NO implementada.

## REGLA DE PARADA

Implementar SOLO FASE 19.

NO iniciar FASE 20.

NO integrar WACRM.

NO implementar nuevas funcionalidades de negocio.

Al finalizar FASE 19:

**DETENTE Y ENTREGA REPORTE COMPLETO.**

---

# 1. OBJETIVO

Auditar y optimizar el rendimiento real del ERP completo.

Metodología obligatoria:

```text
baseline
→ profiling
→ encontrar cuello de botella
→ reproducir
→ optimizar
→ test
→ medir nuevamente
→ comparar
→ documentar
```

No declarar mejoras sin mediciones reales.

---

# 2. AUDITORÍA PREVIA

Antes de modificar código, leer:

* `CLAUDE.md`
* `docs/MASTER-PROMPT.md`
* `ARCHITECTURE.md`
* `docs/performance.md`
* FASES 0–18
* `docs/inventory.md`
* `docs/sales.md`
* `docs/pos.md`
* `docs/purchases.md`
* `docs/accounting.md`
* `docs/reports.md`
* `docs/api-inventory.md`
* `docs/api-catalog.md`
* `docs/billing.md`
* `docs/paypal.md`
* `docs/currency.md`
* `CURRENT_PHASE.md`
* `PHASE_HISTORY.md`
* `KNOWN_ISSUES.md`
* `DECISIONS.md`

Inspeccionar además el código real.

---

# 3. EJECUCIÓN POR BLOQUES

Trabajar internamente:

```text
BLOQUE 1
Baseline + profiling

BLOQUE 2
PostgreSQL + índices + query plans

BLOQUE 3
Django ORM + N+1

BLOQUE 4
Inventory + Sales + POS + Purchases

BLOQUE 5
Accounting + Reports + Exports

BLOQUE 6
Inventory API + Catalog API + Billing

BLOQUE 7
Cache + concurrency + memory/CPU

BLOQUE 8
Regression + benchmarks finales
```

Al terminar cada bloque:

* ejecutar tests;
* corregir;
* volver a medir;
* documentar.

---

# 4. BLOQUE 1 — BASELINE

Crear mediciones reproducibles.

Registrar donde sea razonable:

* query count;
* query total time;
* endpoint latency;
* service latency;
* payload size;
* export time;
* memory;
* CPU;
* throughput;
* lock waits;
* contention.

No inventar volúmenes.

Cuando sea necesario crear datasets sintéticos, registrar:

```text
dataset size
```

por ejemplo:

```text
1000 customers
10000 invoices
100000 stock movements
```

---

# 5. PROFILING

Usar las herramientas disponibles para identificar:

* queries lentas;
* servicios lentos;
* serialización;
* exports;
* generación PDF/XLSX;
* API;
* operaciones repetidas.

No agregar una dependencia nueva de profiling sin justificarla.

---

# 6. POSTGRESQL

Revisar:

* índices;
* composite indexes;
* foreign keys;
* unique constraints;
* ORDER BY;
* WHERE;
* JOIN;
* GROUP BY;
* aggregates;
* subqueries;
* exists;
* query plans.

Usar:

```text
EXPLAIN
EXPLAIN ANALYZE
```

cuando corresponda.

Nunca ejecutar una optimización peligrosa sobre producción por esta fase.

---

# 7. ÍNDICES

Para cada índice nuevo:

* consulta que optimiza;
* columnas;
* motivo;
* evidencia;
* resultado antes/después.

No crear:

* índices duplicados;
* índices inútiles;
* índices en exceso.

Revisar además índices existentes que nunca se utilizan, pero eliminarlos solo con evidencia suficiente.

---

# 8. DJANGO ORM

Buscar:

* N+1;
* consultas dentro de loops;
* select_related;
* prefetch_related;
* Prefetch;
* annotate;
* aggregate;
* Exists;
* Subquery;
* values/values_list cuando aporten;
* cargas innecesarias;
* QuerySets completos en memoria.

---

# 9. TENANT-SCOPED PERFORMANCE

Este punto es obligatorio.

Ninguna optimización puede cambiar:

```text
Tenant isolation
```

En especial revisar:

```text
all_objects
vs
tenant-scoped managers
```

Optimizar consultas sin eliminar filtros tenant.

Probar siempre que:

```text
Tenant A → A
Tenant B → B
```

---

# 10. N+1

Buscar y corregir N+1 en:

* Customers;
* Suppliers;
* Inventory;
* Sales;
* POS;
* Purchases;
* Expenses;
* HR;
* Payroll;
* Accounting;
* Reports;
* APIs;
* Billing.

Crear tests de query count donde tenga valor.

---

# 11. INVENTORY

Medir:

* stock;
* availability;
* movements;
* serialized units;
* product list;
* low-stock;
* search;
* catalog responses.

No crear una nueva fuente de stock.

---

# 12. SALES / POS

Medir:

* catálogo;
* búsqueda;
* carrito;
* checkout;
* confirmación;
* Payment;
* PaymentAllocation;
* CxC;
* caja;
* cambio;
* denominaciones;
* cierre.

Especialmente:

```text
large catalog
large payment history
large pending CxC
```

---

# 13. PURCHASES / CXP

Medir:

* PurchaseOrder;
* recepciones;
* facturas;
* pagos;
* allocations;
* devoluciones;
* reportes.

---

# 14. EXPENSES / HR / PAYROLL

Medir:

* listados;
* filtros;
* dashboards;
* reportes;
* payroll processing;
* sensitive data checks.

Nunca sacrificar autorización para ganar rendimiento.

---

# 15. ACCOUNTING

Medir:

* JournalEntry;
* JournalEntryLine;
* general ledger;
* trial balance;
* balance sheet;
* income statement;
* COGS;
* close period;
* reverse.

Especial atención a:

* grandes rangos temporales;
* agregaciones;
* drill-down.

---

# 16. REPORTS

Auditar todos los reportes importantes:

* Sales;
* Inventory;
* CxC;
* CxP;
* Purchases;
* Expenses;
* HR;
* Payroll;
* Accounting;
* Customers;
* Suppliers;
* Management;
* Billing.

No aceptar loops Python para agregaciones que PostgreSQL pueda resolver razonablemente.

---

# 17. EXPORTS

Medir:

* CSV;
* XLSX;
* PDF.

Revisar:

* query count;
* memoria;
* tiempo;
* streaming/chunks;
* datos repetidos.

Nunca eliminar:

* autorización;
* tenant filter;
* CSV sanitization;
* protección de datos.

---

# 18. INVENTORY API

Medir cada endpoint principal:

* health;
* products;
* product detail;
* categories;
* inventory;
* low-stock;
* movements;
* serialized.

Revisar:

* pagination;
* serializers;
* queries;
* payload size;
* throttling.

---

# 19. CATALOG API

Medir:

* search;
* products;
* detail;
* availability;
* variants;
* media.

Especial atención a búsquedas por:

* name;
* SKU;
* brand;
* model;
* color;
* variant.

No optimizar eliminando la whitelist comercial.

---

# 20. BILLING SAAS

Medir:

* dashboard;
* plans;
* subscriptions;
* invoices;
* payments;
* allocations;
* credit balance;
* transfers;
* verification;
* recurring generation;
* reports.

Revisar especialmente:

```text
same period
→ invoice generation
```

y:

```text
large payment/allocation history
```

---

# 21. PAYPAL

Revisar rendimiento de:

* OAuth token caching;
* webhook processing;
* database queries;
* locking.

No mantener transacciones abiertas durante llamadas HTTP externas.

---

# 22. CACHE

No introducir cache automáticamente.

Solo añadirla si el profiling demuestra beneficio.

Para cada cache:

* motivo;
* TTL;
* clave;
* invalidation;
* riesgo de stale data;
* aislamiento tenant.

Nunca utilizar:

```text
global cache key
```

para datos tenant-scoped sin contexto.

---

# 23. REDIS

No introducir Redis solo para marcar la fase como completa.

Si el profiling demuestra que hace falta cache distribuida:

* documentar;
* evaluar compatibilidad con Hostinger VPS;
* evaluar operación multi-worker;
* explicar impacto.

No cambiar infraestructura base sin necesidad.

---

# 24. CONCURRENCIA

Medir operaciones con:

* select_for_update;
* transacciones;
* locks;
* generación de invoice;
* allocations;
* Billing;
* webhooks;
* approvals.

No retirar locks críticos solo para mejorar latencia.

Buscar:

* lock contention;
* deadlocks;
* transacciones demasiado largas.

---

# 25. MEMORIA

Revisar:

* grandes QuerySets;
* exports;
* PDFs;
* XLSX;
* serialización;
* imágenes;
* reportes.

Evitar:

```text
list(huge_queryset)
```

cuando exista una alternativa segura.

---

# 26. CPU

Cuando sea medible:

* PDF;
* XLSX;
* serialización;
* loops;
* procesamiento masivo.

Optimizar solo con evidencia.

---

# 27. PAGINACIÓN

Revisar:

* HTML;
* APIs;
* paneles;
* reportes.

Mantener límites máximos.

Evaluar cursor/keyset solamente en casos donde la paginación tradicional sea un cuello de botella real.

---

# 28. BENCHMARKS

Para cada mejora significativa registrar:

```text
Operación
Dataset
Antes:
Queries
Latency
Memory si aplica

Después:
Queries
Latency
Memory si aplica

Mejora
```

No inventar resultados.

---

# 29. PERFORMANCE REGRESSION TESTS

Agregar tests donde exista riesgo de regresión:

* N+1;
* query count;
* bulk operations;
* API pagination;
* report aggregation;
* large exports;
* Billing recurring generation.

No crear benchmarks frágiles dependientes de hardware si no aportan valor.

---

# 30. SEGURIDAD

Toda optimización debe mantener:

* Multi-Tenant;
* autorización;
* validaciones;
* idempotencia;
* locks;
* audit;
* protección de datos.

Una optimización que elimina una protección **NO es aceptable**.

---

# 31. CACHE + SECURITY

Probar explícitamente:

```text
Tenant A cache
≠
Tenant B cache
```

No permitir:

* cross-tenant cache leak;
* stale permissions;
* stale Billing status peligroso;
* stale stock donde produzca decisiones comerciales incorrectas.

---

# 32. DEPENDENCIAS

No reemplazar librerías por rendimiento sin justificar.

No actualizar masivamente.

Si una actualización es necesaria:

* documentar;
* probar;
* ejecutar regresión.

---

# 33. CRITERIOS DE OPTIMIZACIÓN

Una modificación se acepta cuando demuestra:

```text
Problema reproducible
+
baseline
+
cambio
+
tests
+
mejora medible
```

Si no existe mejora demostrable, revertir el cambio.

---

# 34. REVISIÓN DE REGRESIÓN FUNCIONAL

Después de cada bloque crítico:

* tests afectados;
* tests generales cuando corresponda;
* check;
* query comparison.

Al final:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
suite completa
```

---

# 35. SMOKE TEST

Realizar smoke test con PostgreSQL real para las operaciones optimizadas.

Debe demostrar:

* funcionalidad intacta;
* tenant isolation intacto;
* permisos intactos;
* resultados idénticos;
* mejora cuando sea medible.

---

# 36. DOCUMENTACIÓN

Actualizar:

* `docs/performance.md`;
* `docs/phases/PHASE-19-performance.md`;
* `CURRENT_PHASE.md`;
* `PHASE_HISTORY.md`;
* `KNOWN_ISSUES.md`;
* `DECISIONS.md`.

Actualizar `CLAUDE.md`, `MASTER-PROMPT.md` o `ARCHITECTURE.md` solo si la optimización establece una nueva doctrina permanente.

---

# 37. CÓDIGO Y MIGRACIONES

Toda migración de índice debe:

* estar justificada;
* ser revisada;
* no duplicar constraints;
* pasar tests.

No generar migraciones innecesarias.

---

# 38. CRITERIOS DE ACEPTACIÓN

* [x] Baseline reproducible — scripts de medición en el scratchpad de la sesión (`perf_baseline.py`/`perf_catalog.py`/`perf_explain_audit.py`), contra PostgreSQL de desarrollo real, con datasets sintéticos de tamaño explícito, documentados en `docs/performance.md`.
* [x] Profiling realizado — `CaptureQueriesContext` (queries), `time.perf_counter()`/`time.process_time()` (tiempo/CPU), `tracemalloc` (memoria pico), todos de librería estándar (sin `psutil`/`django-silk`, no justificados).
* [x] PostgreSQL revisado — `EXPLAIN ANALYZE` real sobre la búsqueda federada de auditoría (el UNION más arquitectónicamente novedoso del proyecto).
* [x] Query plans revisados — confirmado `Index Scan Backward using idx_auditlog_tenant_fecha`, nunca sequential scan, con 8000 filas del tenant medido + 2000 de ruido de otro tenant.
* [x] Índices revisados — inventario completo por dominio en `docs/performance.md`; ninguno nuevo creado (ninguna medición lo justificó en esta pasada).
* [x] N+1 crítico revisado — 1 encontrado y corregido (`get_general_journal`, Accounting: 301→2 queries con 300 asientos); Purchases/Audit/Billing medidos sin N+1.
* [x] ORM revisado — `Prefetch` aplicado donde correspondía (Accounting); orden paginación→trabajo-costoso corregido en Catalog API.
* [x] Inventory revisado — `list_products_with_stock` confirmado sin N+1 (código: `select_related("category")` ya presente; uso real verificado en Inventory API y Catalog API).
* [x] Sales/POS revisados — cobertura ya existente (`apps/sales/tests/test_performance.py`, `apps/pos/tests/test_performance.py`) confirmada vigente, sin cambios necesarios.
* [x] Purchases/CxP revisados — listado HTTP real medido (`GET /compras/ordenes/`, 10 vs. 200 órdenes → 5 queries constante).
* [ ] Expenses/HR/Payroll revisados — fuera de alcance de esta pasada, sin medición real (ver reporte de cierre, sección "Pendientes").
* [x] Accounting revisado — Libro Diario (N+1 real, corregido y con test de regresión) + Balance de Comprobación (medido, ya correcto: 1 query/33ms con 300 asientos).
* [ ] Reports/Exports revisados — solo Accounting/Billing dashboard medidos en esta pasada; el resto de `apps.reports` y las tres exportaciones (CSV/XLSX/PDF) a volumen quedan para una pasada futura.
* [x] Inventory API revisada — `ProductSerializer.get_category`/`list_products_with_stock` confirmados sin N+1 por código; endpoints restantes (movements/low-stock) no medidos en esta pasada.
* [x] Catalog API revisada — hallazgo real encontrado y corregido (precarga de imágenes antes de paginar → después de paginar), con benchmark real y test de regresión.
* [x] Billing revisado — dashboard medido sin N+1 (10 vs. 200 suscripciones/facturas → 10 queries constante); resto de reportes de Billing y generación masiva de facturas recurrentes fuera de alcance de esta pasada.
* [ ] cache solo donde se justifique — evaluado explícitamente: ninguna medición de esta pasada demostró que un reporte/dashboard fuera lo bastante costoso para justificar cache nueva; se mantiene el uso actual (solo throttling + token OAuth2 de PayPal), ninguna cache nueva introducida.
* [x] Multi-Tenant intacto — ninguna optimización tocó un filtro `tenant=`/manager tenant-scoped; verificado con la regresión completa y los tests de aislamiento ya existentes.
* [x] seguridad intacta — ninguna optimización eliminó autorización/validación/idempotencia/lock; confirmado por revisión de cada cambio y por la regresión completa (incluye los tests de seguridad de FASE 18).
* [ ] concurrencia intacta — sin medición NUEVA de duración de locks/contención con más de 2 hilos en esta pasada; la cobertura de concurrencia ya extensa desde FASE 8/18 se mantiene intacta y verificada por la regresión completa (ningún lock retirado).
* [x] benchmarks reales — 2 hallazgos reales, cada uno con número real antes y después (nunca inventado), documentados en `docs/performance.md` y en el reporte de cierre.
* [x] regression tests pertinentes — `apps/accounting/tests/test_performance.py` (nuevo), `apps/api/tests/test_catalog_views.py::CatalogPaginationPerformanceTests` (nuevo).
* [ ] smoke tests cuando aplique — no se ejecutó un smoke test nuevo dedicado; la regresión completa ya corre íntegramente contra PostgreSQL real, cubriendo los flujos optimizados.
* [x] documentación — `docs/performance.md` (reescrito), este archivo, `KNOWN_ISSUES.md`, `DECISIONS.md`, `CURRENT_PHASE.md`, `PHASE_HISTORY.md`.
* [x] suite completa verde — ver reporte de cierre para el conteo exacto final.
* [x] working tree limpio — verificado antes de cerrar (ver reporte de cierre).
* [x] Git commit — ver reporte de cierre para el/los hash(es).

---

# 39. REPORTE FINAL

Incluir baseline, problemas, impacto, queries/tiempos antes/después, índices, cache, cambios relevantes, tests, smoke, regresión, documentación, commits y pendientes. No inventar métricas.

---

# 40. REGLA FINAL DE PARADA

Al completar FASE 19:

**DETENTE.**

No iniciar FASE 20.

No integrar WACRM.

No implementar funcionalidades futuras.

Espera autorización explícita.
