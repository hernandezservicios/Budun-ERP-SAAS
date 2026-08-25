# Estado actual del proyecto

```text
Fase actual: 8
Estado: PASS (cerrada, pendiente de autorización para FASE 9)
Última fase cerrada: FASE 8 — Products + Inventory
Próxima acción: esperar autorización explícita del usuario para iniciar FASE 9 — Customers + Suppliers
```

## Regla
Claude debe actualizar este archivo al inicio y al cierre de cada fase.

## Resumen de FASE 8
Primer dominio de negocio real del proyecto: `apps/inventory` (Categorías, Productos, Movimientos de stock). `Category` y `Product` heredan `TenantScopedModel` (FASE 3): aislamiento automático por tenant. El stock NUNCA es un campo desnormalizado: se calcula siempre a partir del libro mayor append-only `StockMovement` (stock actual = `stock_after` del movimiento más reciente), lo que hace imposible por diseño que el stock mostrado contradiga el historial. Capa de servicios (`services.py`) como única vía para crear movimientos (entrada/salida/ajuste), con `transaction.atomic()` + `select_for_update()` para evitar condiciones de carrera, y rechazo explícito de operaciones inválidas (cantidad ≤ 0, salida que dejaría stock negativo, ajuste sin cambios). PostgreSQL con `UniqueConstraint` (SKU y código de barras únicos por tenant, barcode parcial para permitir vacíos), `CheckConstraint` (precios/stock nunca negativos, cantidad de movimiento siempre positiva, stock posterior nunca negativo) e índices compuestos. Bug de diseño real encontrado y corregido durante el desarrollo: los tests que verifican estado de BD después de una request HTTP deben usar `all_objects` (no `objects`/TenantManager, que depende del ContextVar de la request ya finalizada) — el mismo principio ya aplicado en `services.py`. CRUD completo de productos/categorías con búsqueda, filtros, paginación, estados vacíos, y "eliminar" como borrado suave (producto) o bloqueo con mensaje claro si tiene referencias (categoría). El Panel (FASE 7) ahora muestra datos reales de inventario (conteo de productos, alerta de stock bajo) en vez del placeholder "vacío". Todos los tests de aislamiento Multi-Tenant explícitos pasan (lectura, modificación, eliminación, búsquedas, filtros, URLs e IDs manipulados). Sin N+1 verificado con comparación de queries. Documentado en `docs/products.md` y `docs/inventory.md`. Ningún módulo de negocio adicional (ventas, POS, compras, gastos, API, PayPal, Billing) fue construido.
