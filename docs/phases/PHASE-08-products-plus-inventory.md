# FASE 8 — Products + Inventory

## Objetivo
Productos, categorías, SKU, barcode, precios, impuestos, stock, movimientos y alertas.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] CRUD completo — Categorías y Productos, con búsqueda, filtros, paginación y estados vacíos.
- [x] stock consistente — calculado siempre desde el libro mayor `StockMovement` (nunca un campo desnormalizado); operaciones inválidas rechazadas antes de crear ningún movimiento.
- [x] tests pasan — 129/129 (suite completa del proyecto).

## Verificación
- [x] `python manage.py check` o la validación equivalente está en verde.
- [x] Tests relevantes ejecutados. — 129/129 (`manage.py test`, suite completa del proyecto: 53 nuevos de `apps.inventory` + regresión de FASE 3-7 sin cambios de lógica de negocio).
- [x] Smoke test realizado cuando aplique. — HTTP real con login, creación de producto y movimiento de stock.
- [x] Seguridad revisada para el alcance de la fase. — `TenantRequiredMixin` + `LoginRequiredMixin` en todas las vistas; ningún `tenant_id` aceptado del cliente; `all_objects` solo en `services.py`/`admin.py` (nunca en vistas de negocio).
- [x] Documentación actualizada. — `docs/products.md`, `docs/inventory.md` (nuevos).
- [x] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [x] Git commit creado. — Ver historial de Git.

## Evidencia (FASE 8)
- Arquitectura separada: `models.py` (datos/constraints), `services.py` (reglas de negocio), `forms.py` (validación), `views.py` (delgadas), `templates/` (presentación) — ninguna lógica de inventario vive en las vistas.
- PostgreSQL: `UniqueConstraint` (SKU y código de barras por tenant, barcode parcial), `CheckConstraint` (precios/stock/cantidad nunca negativos — verificado incluso saltándose el formulario, directo a BD), índices compuestos (`tenant+is_active+order/name`, `tenant+sku`, `tenant+product+created_at`).
- Definido explícitamente qué ocurre en cada caso pedido: stock aumenta/disminuye/llega a 0/por debajo del mínimo/ajuste/operación inválida — ver tabla en `docs/inventory.md`.
- Auditoría completa en cada `StockMovement`: tenant, producto, tipo, cantidad, stock anterior, stock posterior, usuario, fecha, notas.
- Multi-Tenant: tests explícitos de lectura, modificación, eliminación, búsquedas, filtros, URLs e IDs manipulados (Tenant A nunca accede a datos de Tenant B), incluyendo regresión de manipulación de sesión (FASE 3).
- Performance: `select_related`/subquery correlacionada para stock anotado (sin N+1), verificado comparando el número de queries con pocos vs. muchos registros.
- Bug de diseño real encontrado y corregido durante el desarrollo (no solo en producción): tests que verifican estado de BD tras una request HTTP deben usar `all_objects`, no `objects`/TenantManager (ContextVar ya reseteado). Ver `docs/inventory.md` y `KNOWN_ISSUES.md`.
- Panel (FASE 7) actualizado con datos reales de inventario, demostrando la extensibilidad para la que fue diseñado.
- Ningún módulo de negocio adicional (ventas, POS, compras, gastos, API de Inventario, PayPal, Billing) fue construido.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 9 — Customers + Suppliers.
