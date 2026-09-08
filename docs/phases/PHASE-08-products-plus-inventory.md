# FASE 8 — Products + Inventory

## Objetivo
Productos, categorías, SKU, barcode, precios, impuestos, stock, movimientos y alertas. Incluye inventario serializado (IMEI/número de serie), ampliación de alcance auditada y ordenada explícitamente por el usuario antes del cierre de la fase (ver nota de transparencia en `docs/inventory.md`).

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] CRUD completo — Categorías y Productos, con búsqueda, filtros, paginación y estados vacíos.
- [x] stock consistente — calculado siempre desde el libro mayor `StockMovement` (nunca un campo desnormalizado); operaciones inválidas rechazadas antes de crear ningún movimiento.
- [x] tests pasan — 175/175 (suite completa del proyecto, incluyendo inventario serializado).
- [x] inventario serializado — `Product.inventory_tracking_type`, `InventoryUnit` (constraints, máquina de estados, búsqueda unificada, reglas de venta), ampliación de alcance auditada por el usuario. Ver `docs/inventory.md`.

## Verificación
- [x] `python manage.py check` o la validación equivalente está en verde.
- [x] Tests relevantes ejecutados. — 175/175 (`manage.py test`, suite completa del proyecto: 53 de `apps.inventory` FASE 8 base + 46 nuevos de inventario serializado + regresión de FASE 3-7 sin cambios de lógica de negocio).
- [x] Smoke test realizado cuando aplique. — HTTP real con login, creación de producto QUANTITY y SERIALIZED, movimiento de stock, alta de unidad por IMEI, búsqueda unificada, cambio de estado de unidad.
- [x] Seguridad revisada para el alcance de la fase. — `TenantRequiredMixin` + `LoginRequiredMixin` en todas las vistas; ningún `tenant_id` aceptado del cliente; `all_objects` solo en `services.py`/`admin.py` (nunca en vistas de negocio); IMEI/serie nunca expuestos completos en errores/logs (verificado con tests).
- [x] Documentación actualizada. — `docs/products.md`, `docs/inventory.md`; especificaciones de FASE 10-15 actualizadas con la interfaz de inventario serializado que deben consumir.
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Ver historial de Git.

## Evidencia (FASE 8)
- Arquitectura separada: `models.py` (datos/constraints), `services.py` (reglas de negocio), `forms.py` (validación), `views.py` (delgadas), `templates/` (presentación) — ninguna lógica de inventario vive en las vistas.
- PostgreSQL: `UniqueConstraint` (SKU y código de barras por tenant, barcode parcial; serial/IMEI 1/IMEI 2 de `InventoryUnit` por tenant, también parciales), `CheckConstraint` (precios/stock/cantidad nunca negativos, IMEI 1 ≠ IMEI 2, al menos un identificador por unidad — verificado incluso saltándose el formulario, directo a BD), índices compuestos (`tenant+is_active+order/name`, `tenant+sku`, `tenant+product+created_at`, `tenant+product+status`, `tenant+status`).
- Definido explícitamente qué ocurre en cada caso pedido: stock aumenta/disminuye/llega a 0/por debajo del mínimo/ajuste/operación inválida — ver tabla en `docs/inventory.md`.
- Auditoría completa en cada `StockMovement`: tenant, producto, tipo, cantidad, stock anterior, stock posterior, usuario, fecha, notas.
- **Inventario serializado**: `InventoryUnit` como libro mayor equivalente para productos IMEI/serie (disponibilidad = conteo de unidades `EN_STOCK`, nunca un contador aparte); máquina de estados (`ALLOWED_UNIT_TRANSITIONS`) que impide vender una unidad ya vendida/reservada/en reparación/inexistente; búsqueda unificada (`services.search_catalog`) por nombre/SKU/código de barras/serie/IMEI, reutilizable por FASE 10/11/15; un producto no puede cambiar de tipo de seguimiento con historial existente (evita dos fuentes de verdad).
- Multi-Tenant: tests explícitos de lectura, modificación, eliminación, búsquedas, filtros, URLs e IDs manipulados (Tenant A nunca accede a datos de Tenant B), incluyendo regresión de manipulación de sesión (FASE 3); cobertura dedicada para unidades/IMEI/serie (`test_serialized_inventory.py::SerializedInventoryIsolationTests`).
- Performance: `select_related`/subquery correlacionada para stock anotado (sin N+1), verificado comparando el número de queries con pocos vs. muchos registros; la anotación de stock combina `StockMovement` e `InventoryUnit` en una sola consulta (`Case/When`) para ambos tipos de producto a la vez.
- Bug de diseño real encontrado y corregido durante el desarrollo (no solo en producción): tests que verifican estado de BD tras una request HTTP deben usar `all_objects`, no `objects`/TenantManager (ContextVar ya reseteado) — el mismo patrón reapareció en `ProductForm.clean_inventory_tracking_type` (relación inversa `product.stock_movements`/`product.inventory_units`) y se corrigió de la misma forma. Ver `docs/inventory.md` y `KNOWN_ISSUES.md`.
- Panel (FASE 7) actualizado con datos reales de inventario, demostrando la extensibilidad para la que fue diseñado.
- Especificaciones de FASE 10 (Ventas), FASE 11 (POS), FASE 12 (Compras), FASE 13 (Gastos), FASE 14 (Reportes) y FASE 15 (API) actualizadas con la interfaz de inventario serializado que cada una debe consumir — documentación únicamente, ninguna de esas fases fue implementada.
- Ningún módulo de negocio adicional (ventas, POS, compras, gastos, API de Inventario, PayPal, Billing) fue construido.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 9 — Customers + Suppliers.

## Adenda de FASE 8: Importación/Exportación masiva de Productos vía Excel — CONSTRUIDA
El usuario ordenó una ampliación de esta fase (`ADENDUM_FASE_8_IMPORTACION_PRODUCTOS_EXCEL.md`, raíz del repositorio) para agregar carga/descarga masiva de productos vía `.xlsx`. Sincronizada primero en la documentación, luego implementada completa: `apps.inventory.product_import` (parseo/validación/aplicación), `ProductImportBatch` (nuevo modelo, migración `0008_productimportbatch`), 5 vistas nuevas (plantilla, subir, preview/confirmar, reporte de errores, exportar), permisos propios `products.import`/`products.export`, auditoría (`AuditLog.Action.PRODUCT_IMPORT_CONFIRMED`), 55 tests nuevos (incluyendo 4 de concurrencia con hilos reales contra PostgreSQL). Ver `docs/products.md` sección "Importación y exportación masiva de productos (Excel)" para la arquitectura completa y el reporte de cierre para el detalle hallazgo por hallazgo. Las dos columnas sin campo real ("moneda", "unidad de medida") se dejaron fuera de la plantilla definitiva, sin inventar campos nuevos en `Product` — decisión documentada en `DECISIONS.md`.
