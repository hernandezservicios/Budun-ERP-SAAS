# Inventory (FASE 8)

Movimientos de stock, historial y alertas de `apps/inventory`. Ver
`docs/products.md` para Productos/Categorías.

> **Nota de transparencia**: el inventario serializado (IMEI/número de
> serie) descrito en este documento fue incorporado a FASE 8 a partir de
> una auditoría explícita del usuario, ya con la fase inicial cerrada.
> No se encontró ningún requisito de inventario serializado en
> `CLAUDE.md`, `docs/MASTER-PROMPT.md`, `docs/phases/PHASES.md` ni en la
> versión original de este documento — se buscó explícitamente
> (`grep` de "serial"/"imei"/"serializ" en todo el repositorio) antes de
> implementarlo. Se documenta aquí con la misma fidelidad que el resto
> de la fase, sin ocultar que fue una ampliación de alcance posterior.

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

## Costeo por promedio ponderado (ampliación de cierre de FASE 14)

`StockMovement` gana dos columnas nuevas, en el MISMO patrón que
`stock_before`/`stock_after` (calculadas y guardadas una sola vez por
movimiento, nunca editadas después): `unit_cost` (costo de ESE
movimiento — el costo del lote en una entrada, o el promedio vigente
consumido en una salida; `null` en un ajuste, un conteo físico no
trae un costo confiable) y `average_cost_after` (promedio ponderado
por unidad vigente DESPUÉS de este movimiento). "Costo promedio
actual de un producto" = `average_cost_after` del `StockMovement` más
reciente — exactamente como el stock actual = `stock_after` del más
reciente (`services.get_current_average_cost`). En una entrada con
costo conocido: `nuevo_promedio = (stock_anterior×promedio_anterior +
cantidad×costo_del_lote) / stock_posterior`. En una salida, el
promedio NO cambia — retirar unidades a su propio costo promedio
nunca altera el promedio de las que quedan; el costo consumido es el
promedio vigente en ese instante (base real de COGS, ver
`docs/accounting.md` sección 11).

Esta es la ÚNICA política de costeo para productos QUANTITY — nunca
FIFO en esta ampliación (descartado explícitamente por el usuario).
Los productos SERIALIZED siguen usando costo específico por unidad
(`InventoryUnit.unit_cost`, sin cambios, ver más abajo). Nuevo:
`get_inventory_valuation(tenant)` — valor total de inventario
(QUANTITY: stock actual × promedio; SERIALIZED: suma de `unit_cost`
de unidades `EN_STOCK`), usado por el reporte de Inventario y por la
reconciliación contable.

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

## Inventario SERIALIZADO (IMEI / número de serie)

### Dos tipos de seguimiento, un solo punto de verdad por producto

`Product.inventory_tracking_type` decide cómo se calcula su
stock/disponibilidad — nunca los dos a la vez para el mismo producto:

| Tipo | Fuente de verdad | Disponibilidad |
|---|---|---|
| `QUANTITY` (por defecto) | `StockMovement` | `stock_after` del movimiento más reciente |
| `SERIALIZED` | `InventoryUnit` | conteo de unidades con `status = EN_STOCK` |

`services.get_current_stock(product)` sigue siendo la única función que
cualquier llamador necesita: internamente decide la fuente según
`inventory_tracking_type`, así que nadie fuera de `services.py` necesita
saber cuál de las dos tablas consultar. `services.list_products_with_stock`
anota `current_stock` con un `Case/When` que combina ambas subqueries en
una sola consulta (sin N+1), para que el listado de productos no tenga
que tratar ambos tipos de forma distinta.

**Regla explícita**: un producto no puede cambiar de tipo de seguimiento
una vez que ya tiene movimientos o unidades registradas
(`ProductForm.clean_inventory_tracking_type`) — permitirlo crearía dos
fuentes de verdad parciales e inconsistentes para el mismo producto. Si
de verdad se necesita el otro tipo, se crea un producto nuevo.

### `InventoryUnit`: una fila por unidad física real

Equivalente de `StockMovement` para productos serializados: cada unidad
física (un teléfono con su IMEI, un equipo con su número de serie) es su
propia fila, y su disponibilidad es simplemente su `status` — nunca un
conteo desnormalizado aparte.

Campos: `tenant`, `product`, `serial`, `imei_1`, `imei_2`, `status`,
`unit_cost`, `entry_date`, `purchase_origin` (texto libre, provisional —
ver nota abajo), `sale_reference`/`customer_reference` (ídem,
provisionales), `warranty_until`, `notes`, `status_changed_by`,
`created_at`/`updated_at`.

**Constraints de PostgreSQL** (no solo de formulario):
- `serial`, `imei_1` e `imei_2` únicos por tenant, pero con
  `UniqueConstraint` **parcial** (`condition=Q(campo__gt="")`): varias
  unidades pueden compartir el valor vacío (no todas necesitan los tres
  identificadores), solo se exige unicidad entre valores no vacíos.
- `imei_1 != imei_2` cuando ambos están presentes (`CheckConstraint`).
- Al menos un identificador (`serial`, `imei_1` o `imei_2`) no puede
  estar vacío — una unidad sin ningún identificador no es rastreable.
- `unit_cost >= 0`.
- Índices compuestos `(tenant, product, status)` y `(tenant, status)`
  para listar/contar unidades por producto o por estado sin recorrer la
  tabla completa.

### Estados de unidad y máquina de estados

`EN_STOCK`, `RESERVADO`, `VENDIDO`, `DEVUELTO`, `REPARACION`,
`GARANTIA`, `DANADO`, `PERDIDO`. Las transiciones válidas están
centralizadas en `services.ALLOWED_UNIT_TRANSITIONS` y se aplican en
`services.transition_unit_status` — nunca se asigna `unit.status`
directamente desde una vista ni desde un módulo futuro. Ejemplos de
reglas: `VENDIDO` solo puede volver a `DEVUELTO` (nunca "revertirse" a
`RESERVADO`); `PERDIDO` es un estado terminal sin ninguna salida. Rechazar
una transición no permitida lanza `InvalidInventoryOperation` con un
mensaje que identifica el producto (SKU) y los dos estados — nunca el
IMEI/serie completo (ver "Seguridad" más abajo).

### Reglas de venta reutilizables por FASE 10/11

`services.ensure_unit_available_for_sale(unit)` es la única función que
FASE 10 (Ventas) y FASE 11 (POS) deben usar para decidir si una unidad
puede agregarse a una venta: rechaza explícitamente vender una unidad
que no está `EN_STOCK` (ya vendida, reservada, en reparación, en
garantía, dañada o perdida). Combinada con `services.search_catalog`
(ver abajo) y con el `select_for_update()` ya usado en el resto de
`services.py`, cubre los 5 casos que el usuario pidió bloquear
explícitamente: unidad inexistente (búsqueda sin resultados), unidad
vendida, reservada, en reparación, o duplicada en el carrito (esta
última la debe verificar el carrito de FASE 11 por `unit.pk`, ya que la
unidad es un objeto identificable único).

### Búsqueda unificada: `services.search_catalog(tenant, query)`

Un único punto de entrada para nombre, SKU, código de barras, número de
serie o IMEI (1 o 2) — pensado explícitamente para que FASE 10/11/15 no
reimplementen su propia búsqueda:

1. Primero intenta una coincidencia **exacta** de `serial`/`imei_1`/`imei_2`
   contra `InventoryUnit`. Si la hay, devuelve **solo esa unidad**
   (`SearchResult(product, unit)`): un IMEI/serie identifica una unidad
   física real, no tiene sentido mezclarlo con resultados de texto libre.
2. Si no hay coincidencia de unidad, busca productos activos por nombre
   (`icontains`), SKU (`iexact`) o código de barras (`exact`).

Un código QR no necesita un campo ni una búsqueda aparte: en la práctica
un QR solo codifica uno de estos mismos valores (típicamente un
SKU/código de barras/serie) como texto plano, así que se resuelve con la
misma función.

`SearchResult.requires_unit_selection` es `True` cuando el resultado es
un producto SERIALIZADO encontrado por nombre/SKU/barcode (no por
IMEI/serie exacto): la señal que FASE 11 (POS) necesita para saber que
debe pedir a continuación el IMEI/serie concreto antes de poder agregar
el producto al carrito, en vez de agregarlo directamente como haría con
un producto por cantidad.

### Multi-Tenancy

`search_catalog` recibe `tenant` explícito y nunca consulta otro tenant;
`InventoryUnit` hereda `TenantScopedModel` igual que el resto del
módulo. Cobertura de tests dedicada
(`apps/inventory/tests/test_serialized_inventory.py::SerializedInventoryIsolationTests`):
una búsqueda por el serial/IMEI exacto de otro tenant no encuentra nada
(ni confirma que el identificador existe en otro lado), acceso directo
por URL a una unidad de otro tenant devuelve 404, y el detalle de un
producto nunca lista unidades de otro tenant.

### Seguridad: nunca exponer el identificador completo innecesariamente

Ningún mensaje de error ni log de `services.py` incluye el IMEI/serie
completo de una unidad — solo el SKU del producto y el/los estado(s)
involucrados (verificado con tests explícitos). El listado de
`InventoryUnitAdmin` (Django Admin, solo lectura/staff) muestra el
identificador parcialmente enmascarado (`···1234`, últimos 4
caracteres) como defensa adicional, aunque la búsqueda exacta del admin
sigue funcionando sobre el valor completo. La ficha de producto de la
propia empresa (su UI normal, autenticada y tenant-scoped) sí muestra el
identificador completo de sus propias unidades: es una exposición
necesaria (el usuario necesita ver el IMEI para identificar el equipo
físico), no la "exposición innecesaria" que la regla busca evitar.

### Campos provisionales: `purchase_origin`, `sale_reference`, `customer_reference`

Son `CharField` de texto libre porque los modelos `Purchase` (FASE 12),
`Sale`/`SaleItem` (FASE 10) y `Customer` (FASE 9) todavía no existen —
construirlos ahora violaría la regla de construcción incremental de
`CLAUDE.md`. Cuando esas fases lleguen, lo natural es que esos modelos
referencien a `InventoryUnit` con su propia FK (p. ej.
`SaleItem.inventory_unit`), no al revés; estos campos de texto quedan
como referencia legible mientras tanto. Documentado también con
`help_text` en cada campo del modelo.

### Vistas y formularios

`UnitCreateView` (alta de una unidad, equivalente a `StockInView` para
productos por cantidad) y `UnitStatusChangeView` (cambio de estado, solo
POST). Ambas rechazan con un mensaje claro (no un 500) si se usan sobre
el tipo de producto equivocado: `UnitCreateView` sobre un producto por
CANTIDAD, o `StockInView`/`StockOutView`/`StockAdjustmentView` sobre un
producto SERIALIZADO (esta última validación vive en
`services._require_quantity_tracking`, así que también protege cualquier
otra vía de entrada futura, no solo la vista actual).

## Qué NO se construyó en esta fase (deliberado)
Motor de ventas, POS, compras, gastos, API de Inventario para CRM IA
(FASE 15), PayPal, Billing. Tampoco se construyó un endpoint HTTP de
búsqueda para `search_catalog` — solo el servicio reutilizable: el
endpoint/URL que lo consuma pertenece a FASE 10/11/15, según
corresponda.
