# Inventory (FASE 8)

Movimientos de stock, historial y alertas de `apps/inventory`. Ver
`docs/products.md` para Productos/Categorías.

## Diseño central: el stock es un libro mayor, no un campo

`Product` **no tiene** un campo `current_stock`. El stock actual de un
producto se calcula siempre a partir de `StockMovement`, su libro mayor
append-only:

> stock actual = `stock_after` del movimiento más reciente del producto
> (o 0 si nunca tuvo ninguno).

Esto hace **imposible por diseño** que el stock mostrado contradiga el
historial: no hay dos fuentes de verdad que se puedan desincronizar,
solo una. La alternativa (un campo `current_stock` actualizado a mano)
es la fuente más común de bugs de inventario en sistemas reales
(condiciones de carrera, actualizaciones parciales, migraciones que lo
dejan desincronizado) — se evitó deliberadamente.

## `StockMovement`: el registro de auditoría

Cada movimiento registra como mínimo (pedido explícitamente): `tenant`,
`product`, `movement_type` (entrada/salida/ajuste), `quantity`,
`stock_before`, `stock_after`, `user`, `created_at` (fecha) y `notes`
(motivo, opcional). Es append-only: la capa de servicios nunca actualiza
ni borra un movimiento ya creado; `on_delete=PROTECT` en
`StockMovement.product` impide borrar un producto que tiene historial
(solo se puede desactivar, ver `docs/products.md`).

## `services.py`: única vía para tocar el stock

Ninguna vista crea un `StockMovement` directamente. Todo pasa por:

| Función | Qué hace |
|---|---|
| `register_stock_in(product, quantity, user, notes)` | Entrada: suma `quantity` |
| `register_stock_out(product, quantity, user, notes)` | Salida: resta `quantity`; rechaza si dejaría el stock negativo |
| `register_stock_adjustment(product, new_stock, user, notes)` | Ajuste: fija el stock a un valor exacto (p. ej. tras un conteo físico); rechaza un ajuste igual al valor actual (no hay nada que registrar) |
| `get_current_stock(product)` | Stock actual (ver arriba) |
| `list_products_with_stock(tenant, ...)` | Listado con stock anotado por subquery (sin N+1), con búsqueda/filtro/stock bajo |
| `get_low_stock_products(tenant)` | Productos con stock ≤ su `min_stock` |
| `get_product_movements(product, limit)` | Historial, más reciente primero |

### Qué ocurre en cada caso (definido explícitamente, pedido por el usuario)

| Situación | Comportamiento |
|---|---|
| **Stock aumenta** (entrada) | `stock_after = stock_before + cantidad`. Cantidad debe ser > 0. |
| **Stock disminuye** (salida) | `stock_after = stock_before − cantidad`. Se **rechaza** (`InvalidInventoryOperation`) si `stock_after` quedaría negativo. |
| **Stock llega a 0** | Permitido explícitamente: una salida que deja el stock en exactamente 0 es válida (probado). |
| **Stock por debajo del mínimo** | No bloquea ninguna operación; se refleja como alerta visual ("Stock bajo") en el listado, el detalle del producto y el Panel (FASE 7). |
| **Ajuste** | Fija el stock a un valor exacto. Rechaza valores negativos y ajustes "sin cambio" (nuevo valor == valor actual). |
| **Operación inválida** (cantidad ≤ 0, salida que deja negativo, ajuste negativo o sin cambio) | Se lanza `InvalidInventoryOperation` (subclase de `ValidationError`) **antes** de crear ningún movimiento — no queda ningún rastro inconsistente en la base de datos. La vista captura la excepción y muestra el error en el formulario (nunca un 500). |

## `on_delete=PROTECT` también protege a nivel de tenant

`StockMovement.product` usa `on_delete=PROTECT`: un producto con
historial de movimientos nunca puede borrarse físicamente (solo
desactivarse, ver `docs/products.md`). Efecto secundario deliberado:
esto también impide borrar un `Tenant` que tenga cualquier movimiento de
inventario, porque el borrado en cascada de sus productos chocaría con
esa protección. Para limpiar datos de prueba (o en una futura baja real
de cuenta) hay que borrar en orden: `StockMovement` → `Product` →
`Category` → `Tenant`. Es el comportamiento correcto para proteger el
historial de auditoría, no un error.

## Corrección de UX encontrada con el smoke test: formato de cantidades

Las cantidades (`DecimalField` con 3 decimales) se mostraban con los
ceros de relleno (p. ej. "13,000" para 13 unidades exactas — la coma es
el separador decimal del locale `es`, no de miles). Un lector podía
confundirlo con "trece mil". Se corrigió aplicando
`{{ valor|floatformat:"-3" }}` en todas las plantillas de inventario:
muestra hasta 3 decimales pero recorta los ceros sobrantes ("13,000" →
"13"; "5.125" se sigue mostrando como "5,125").

## Concurrencia: `select_for_update`

Cada función de escritura corre dentro de `transaction.atomic()` y hace
`Product.all_objects.select_for_update().get(...)` antes de leer el
stock actual: la fila del producto queda bloqueada durante toda la
transacción, así que dos movimientos concurrentes del mismo producto
(p. ej. dos ventas simultáneas) nunca leen el mismo "stock anterior" ni
producen un resultado incorrecto por condición de carrera.

## Nota de diseño: `all_objects` dentro de `services.py`

Todas las consultas de `services.py` usan `all_objects` (no
`objects`/`TenantManager`), filtrando siempre `tenant`/`product` de
forma explícita. Motivo: `TenantManager` depende de un `ContextVar` que
solo `TenantMiddleware` fija durante una request HTTP real; un servicio
debe funcionar igual de correcto llamado desde un test unitario, un
comando de administración o una tarea en segundo plano, donde ese
`ContextVar` no está fijado. Esto es distinto de "usar `all_objects` en
una vista" (prohibido): aquí el filtro por tenant sigue siendo
obligatorio y explícito en cada consulta, solo que no depende del estado
ambiental de la request. Se descubrió como un problema de diseño real
durante el desarrollo (antes de escribir los tests) y se corrigió antes
de que causara fallos silenciosos en pruebas unitarias.

## Alertas de stock bajo → integradas al Panel (FASE 7)

Ahora que existe inventario real, `apps/dashboard/services.py` se
actualizó (tal como estaba diseñado para hacerlo desde FASE 7, sin tocar
el layout): el KPI "Productos en inventario" muestra el conteo real de
productos activos, y aparece una alerta cuando hay productos en o por
debajo de su stock mínimo.

## Performance

- `list_products_with_stock` anota el stock actual con una **subquery
  correlacionada** (`Subquery`/`OuterRef` + `Coalesce`), no con una
  consulta por producto — verificado con un test que compara el número
  de queries con 3 vs. 15 productos (debe ser idéntico).
- El conteo de productos por categoría se anota con `Count`, no con
  `category.products.count()` en la plantilla (ese patrón sí sería N+1;
  se detectó y corrigió durante el desarrollo).
- El historial de movimientos usa `select_related("user")`.
- Índices compuestos en `StockMovement`: `(tenant, product, created_at)`
  para el historial de un producto, `(tenant, created_at)` para
  consultas generales por fecha.

## Multi-Tenancy: cobertura de tests (`apps/inventory/tests/test_isolation.py`)

Lectura, modificación, eliminación, búsquedas, filtros, URLs e IDs
manipulados — Tenant A nunca puede, sobre datos de Tenant B: verlos,
editarlos, eliminarlos, encontrarlos por búsqueda, filtrarlos por
categoría, acceder por URL directa con el ID real, ni registrar un
movimiento de stock. Incluye una regresión directa de FASE 3
(manipular `active_tenant_id` en la sesión no filtra datos de
inventario de otro tenant).

## Qué NO se construyó en esta fase (deliberado)
Motor de ventas, POS, compras, gastos, API de Inventario para CRM IA
(FASE 15), PayPal, Billing.
