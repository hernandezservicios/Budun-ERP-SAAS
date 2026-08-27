# FASE 19 — Performance Profesional

## Objetivo
Medir, perfilar y optimizar el rendimiento real del ERP SaaS construido en FASES 0–18 mediante evidencia reproducible. No optimizar por intuición.

## Regla incremental
Modificar únicamente lo necesario para resolver problemas de rendimiento demostrados. No iniciar FASE 20 ni implementar funcionalidad de negocio nueva.

## Cobertura
Auditar PostgreSQL, Django ORM, N+1, índices, query plans, paginación, agregaciones, servicios, APIs, Inventory API, Catalog API, POS/caja, ventas, compras/CxP, inventario, RRHH/nómina, contabilidad, reportes, exportaciones, Billing SaaS, PayPal/webhooks cuando aplique, cache, concurrencia y memoria/CPU cuando sea medible.

## Auditoría previa
Leer CLAUDE.md, MASTER-PROMPT, ARCHITECTURE, FASES 0–18, docs de performance/API/reportes/Billing/inventario/ventas/compras y estado del proyecto. Inspeccionar código real.

## Baseline
Antes de optimizar crear mediciones reproducibles: queries, tiempo, latencia por operación, payload, memoria/CPU cuando sea medible, throughput, locks/contención y tiempo de exportación. Usar datos de prueba representativos y reportar volúmenes reales.

## PostgreSQL
Revisar índices simples/compuestos, constraints, FKs, filtros, ordenamientos, joins, agregaciones y query plans. Usar EXPLAIN/EXPLAIN ANALYZE cuando sea seguro. No añadir índices duplicados ni eliminar existentes sin evidencia.

## Django ORM
Buscar N+1, relaciones inversas, select_related, prefetch_related/Prefetch, annotate/aggregate, Exists/Subquery, consultas en loops, consultas repetidas, objetos cargados innecesariamente y uso incorrecto de managers tenant-scoped. La optimización no puede romper Multi-Tenant.

## N+1
Para cada problema relevante demostrar antes/después. Sustituir N consultas por consultas constantes/razonables con evidencia.

## Multi-Tenant + Performance
Toda optimización debe conservar aislamiento y permisos. Especial cuidado con all_objects vs managers tenant-scoped, reportes, dashboards, APIs, Billing y Catalog.

## Paginación
Revisar defaults, máximos, count costoso, API y grandes listados. Evaluar cursor/keyset solo si existe evidencia y sin romper orden/consistencia.

## Inventory
Medir stock, movimientos, productos, serialized units, availability, search, low-stock y Catalog API. No crear segunda fuente de stock.

## Sales/POS
Medir catálogo, carrito, checkout, confirmación, pagos, CxC, allocations, caja, cambio/denominaciones y cierres.

## Purchases/CxP
Medir órdenes, recepciones, facturas, pagos, allocations, devoluciones y reportes.

## Accounting
Medir journal entries, general ledger, balances, COGS, periodos y agregaciones. No sustituir contabilidad por datos desnormalizados sin justificación.

## Reports
Auditar reportes de ventas, inventario, CxC/CxP, compras, gastos, RRHH/nómina, contabilidad, clientes/proveedores, dashboard y Billing. Preferir SQL para agregaciones.

## Exports
Medir CSV, XLSX y PDF; revisar queries previas, memoria, streaming/chunks cuando sea necesario. Nunca eliminar validaciones de seguridad.

## Billing SaaS
Medir dashboard, invoices, payments, allocations, subscriptions, recurring generation, transfers, verification y reports.

## APIs
Inventory API y Catalog API: paginación, serializers, select/prefetch, payload size, throttling, búsqueda y disponibilidad. No optimizar incluyendo campos sensibles.

## PayPal/Webhooks
Revisar tiempo de procesamiento, queries, locks e idempotencia. Evitar transacciones largas alrededor de llamadas externas.

## Cache
Primero medir. Cache solo cuando la consulta sea costosa, el dato soporte cierto stale, la invalidación sea segura y no exista riesgo cross-tenant. Las claves deben contener el contexto necesario. No introducir Redis por obligación estética.

## Concurrency
Revisar locks, transacciones, duración de locks, contención y deadlocks. No retirar locks críticos para ganar latencia.

## Memory/CPU
Cuando sea medible, revisar QuerySets grandes, exports, serialización, imágenes, PDF/XLSX. Evitar cargar datasets completos en RAM sin necesidad.

## Benchmarks
Para cada mejora significativa registrar:
- operación;
- dataset;
- queries antes;
- tiempo antes;
- cambio;
- queries después;
- tiempo después;
- resultado.

Nunca inventar métricas.

## Performance regression
Crear tests de query count/bulk/report/API pagination/no-N+1/large export cuando aporten valor. No crear benchmarks frágiles sin utilidad.

## Seguridad durante optimización
No aceptar optimizaciones que eliminen filtros tenant, autorización, validaciones, idempotencia o locks críticos ni que expongan datos.

## Dependencias
No cambiar paquetes por rendimiento sin evidencia. No actualizar todo el stack masivamente.

## Metodología
Cada optimización: reproducir → medir baseline → cambiar → test → medir después → comparar → documentar.

## Criterios de aceptación
- [ ] no N+1 crítico conocido;
- [ ] consultas críticas medidas y optimizadas cuando corresponda;
- [ ] índices justificados;
- [ ] paginación revisada;
- [ ] Inventory/Catalog revisados;
- [ ] Sales/POS revisados;
- [ ] Purchases/CxP revisados;
- [ ] Accounting revisado;
- [ ] Reports/Exports revisados;
- [ ] Billing revisado;
- [ ] cache solo donde se justifique;
- [ ] Multi-Tenant intacto;
- [ ] seguridad intacta;
- [ ] concurrencia intacta;
- [ ] benchmarks reales;
- [ ] regression tests pertinentes;
- [ ] documentación;
- [ ] suite completa verde;
- [ ] smoke tests cuando aplique;
- [ ] working tree limpio;
- [ ] Git commit.

## Reporte final
Incluir baseline, problemas, impacto, queries/tiempos antes/después, índices, cache, cambios relevantes, tests, smoke, regresión, documentación, commits y pendientes. No inventar métricas.

## Regla de parada
Al cerrar FASE 19: DETENERSE. No iniciar FASE 20.
