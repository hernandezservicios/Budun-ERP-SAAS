# Products (FASE 8)

`apps/inventory` — catálogo de productos y categorías, primer dominio de
negocio real del ERP. Base para Ventas, POS, Compras y Reportes (FASE
10–14).

## Modelos

### `Category`
Hereda `TenantScopedModel` (FASE 3): aislamiento automático por tenant.

| Campo | Tipo | Notas |
|---|---|---|
| `name` | `CharField` | único por tenant (`unique_category_tenant_name`) |
| `order` | `PositiveIntegerField` | orden de visualización |
| `is_active` | `BooleanField` | CRUD completo; "eliminar" con productos asociados falla con mensaje claro (`on_delete=PROTECT` en `Product.category`) |

### `Product`
También `TenantScopedModel`. El stock **no** vive aquí — ver
`docs/inventory.md`.

| Campo | Tipo | Notas |
|---|---|---|
| `inventory_tracking_type` | `CharField` con choices | `QUANTITY` (por defecto) o `SERIALIZED` (IMEI/número de serie) — decide qué fuente de verdad calcula el stock del producto, ver `docs/inventory.md` |
| `name` | `CharField` | |
| `sku` | `CharField` | único por tenant (`unique_product_tenant_sku`) |
| `barcode` | `CharField`, opcional | único por tenant **solo cuando no está vacío** (`UniqueConstraint` con `condition=Q(barcode__gt="")` — varios productos sin código de barras no chocan entre sí) |
| `category` | `ForeignKey` a `Category`, opcional | `on_delete=PROTECT` |
| `description` | `TextField`, opcional | |
| `purchase_price` | `DecimalField(12,2)` | Decimal, nunca float (dinero) |
| `sale_price` | `DecimalField(12,2)` | Decimal |
| `tax_rate` | `DecimalField(5,2)` | porcentaje, p. ej. `16.00` = 16% |
| `min_stock` | `DecimalField(12,3)` | umbral para "stock bajo" (solo aplica de forma directa a productos `QUANTITY`) |
| `is_active` | `BooleanField` | "eliminar" un producto = desactivarlo (ver `docs/inventory.md`) |
| `brand` | `CharField`, opcional | marca comercial — agregado en la ampliación final de FASE 15 (Catalog API), documentado aquí recién ahora: esta tabla había quedado desactualizada desde entonces |
| `model_name` | `CharField`, opcional | modelo comercial — junto con `brand`, agrupa productos "variantes entre sí" cuando comparten `tenant`+`brand`+`model_name` (ver `docs/api-catalog.md`) |
| `variant_attributes` | `JSONField`, opcional | atributos de variante libres (color, capacidad, talla, presentación, ...) — deliberadamente JSON flexible, nunca columnas fijas por atributo |

`Product` **no tiene** un campo de moneda ni de unidad de medida — no
existe todavía ningún concepto de "moneda por producto" (el motor de
monedas real, `CurrencyConfiguration`, sigue especificado y no
construido, ver `docs/currency.md`) ni de "unidad de medida" (unidad/
caja/kg) en ningún modelo del proyecto. Relevante para la sección
"Importación y exportación masiva" más abajo.

Un producto SERIALIZADO no usa `StockMovement`: su disponibilidad viene
de `InventoryUnit`, una unidad física por fila (IMEI/número de serie).
Ver "Inventario SERIALIZADO" en `docs/inventory.md` para el modelo
completo, la máquina de estados, la búsqueda unificada
(`services.search_catalog`) y las reglas de venta. El tipo de
seguimiento no puede cambiarse una vez que el producto ya tiene
movimientos o unidades registradas (`ProductForm.clean_inventory_tracking_type`).

**Constraints de PostgreSQL** (no solo validación de formulario):
`CheckConstraint` para que `purchase_price`, `sale_price`, `tax_rate` y
`min_stock` nunca sean negativos a nivel de base de datos — verificado
con un test que intenta guardar un precio negativo saltándose el
formulario y confirma que PostgreSQL lo rechaza (`IntegrityError`).

**Índices**: `(tenant, is_active, name)` para listados filtrados;
`(tenant, sku)` para búsquedas por SKU.

## Arquitectura (separación de responsabilidades)

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Modelos | `models.py` | Estructura de datos, constraints, índices |
| Servicios | `services.py` | Reglas de negocio de inventario (ver `docs/inventory.md`) |
| Formularios | `forms.py` | Validación de entrada (SKU/nombre/código de barras únicos, precios no negativos) |
| Vistas | `views.py` | Deliberadamente delgadas: solo tenant/permiso + arman formulario/queryset + traducen a HTTP |
| Plantillas | `templates/inventory/*.html` | Presentación, Design System de FASE 5 |

Ninguna lógica de negocio vive en `views.py` — cada vista delega en
`services.py` o en la validación del formulario.

## CRUD y UI

- **Categorías**: listado con conteo de productos (anotado, sin N+1),
  crear, editar, eliminar (bloqueado con mensaje claro si tiene
  productos).
- **Productos**: listado con búsqueda (nombre/SKU/código de barras),
  filtro por categoría, filtro "solo stock bajo", paginación (20 por
  página), estados vacíos (sin productos / sin resultados de búsqueda).
  Detalle de producto con KPIs (stock actual, precios, stock mínimo),
  alerta de stock bajo, acciones rápidas (entrada/salida/ajuste) e
  historial de movimientos.
- **Nunca un borrado físico de producto**: "eliminar" desactiva
  (`is_active = False`), preservando el historial de movimientos
  (`StockMovement.product` usa `on_delete=PROTECT`, nunca podría
  apuntar a un producto borrado).

## Multi-Tenancy

Todo (`Category`, `Product`) hereda `TenantScopedModel`: el manager por
defecto (`objects`) ya filtra automáticamente por el tenant activo. Las
vistas, además, filtran explícitamente por `tenant=request.tenant` como
defensa adicional. Ver `docs/inventory.md` para la cobertura completa de
tests de aislamiento (lectura, modificación, eliminación, búsquedas,
filtros, URLs e IDs manipulados).

## UX y Design System
Usa exclusivamente los componentes de FASE 5 (`.tabla`, `.badge`,
`.estado-vacio`, `.kpi-grid`, `.encabezado-pagina`, `.migas`, `.alerta`).
Sin identidad visual nueva, sin exceso de tarjetas (los listados usan
tablas, no grids de cards).

## Importación y exportación masiva de productos (Excel) — CONSTRUIDO

> **Estado: construido e implementado** (extensión de FASE 8, ordenada
> en `ADENDUM_FASE_8_IMPORTACION_PRODUCTOS_EXCEL.md`, raíz del
> repositorio, preservado ahí tal cual). `apps.inventory.product_import`
> (nuevo módulo, ver también `apps.inventory.models.ProductImportBatch`,
> `apps.inventory.views`/`urls.py`, `apps.inventory.forms.
> ProductImportUploadForm`). Ver el reporte de cierre entregado al
> usuario para arquitectura completa, tests y resultado del smoke test.

**Objetivo**: capacidad de carga/descarga masiva de productos vía
`.xlsx` (nunca CSV) desde Inventario → Productos: `Nuevo`/`Editar` (ya
existentes) + `Importar Excel`/`Exportar Excel`/`Descargar plantilla`
(construidos en esta extensión, botones en `product_list.html`).

**Columnas definitivas de la plantilla** (`product_import.COLUMNAS`,
identificadas siempre por nombre de encabezado — nunca por posición
física, así que reordenar columnas en Excel no rompe la importación):

| Columna | Campo real de `Product` | Obligatoria |
|---|---|---|
| SKU * | `sku` | Sí |
| Nombre * | `name` (solo en CREATE — ver "Semántica de blanco") | Sí en CREATE |
| Código de barras | `barcode` | No |
| Categoría | `category` (FK, por nombre, case-insensitive) | No |
| Descripción | `description` | No |
| Marca | `brand` | No |
| Modelo | `model_name` | No |
| Tipo de seguimiento | `inventory_tracking_type` ("Por cantidad"/"Serializado") | No (default: Por cantidad) |
| Precio de venta * | `sale_price` | Sí en CREATE |
| Precio de compra | `purchase_price` | No |
| Impuesto (%) | `tax_rate` | No |
| Stock mínimo | `min_stock` | No |
| Activo | `is_active` ("Sí"/"No") | No (default: Sí) |
| Atributos de variante | `variant_attributes` (JSON) — formato `clave:valor;clave:valor` en una sola celda | No |

**Decisión de las dos columnas sin campo real** (hallazgo de la
sincronización documental previa, resuelto ahora en la implementación):
"moneda" y "unidad de medida" NO se incluyeron en la plantilla — ningún
modelo del proyecto tiene esos conceptos todavía (`docs/currency.md`
sigue especificado, no construido); agregarlos habría exigido inventar
campos nuevos en `Product` sin autorización explícita para ese cambio
de modelo, algo fuera del alcance de esta extensión. "Precio" se separó
en DOS columnas reales (`sale_price`/`purchase_price`, nunca una sola
columna ambigua) — ver `DECISIONS.md`.

**Matching CREATE/UPDATE**: SKU es el ÚNICO criterio principal
(`UniqueConstraint(tenant, sku)` ya existente) — SKU inexistente crea,
SKU existente actualiza; nunca el nombre. El código de barras se valida
por unicidad (contra otros productos, y duplicados dentro del mismo
archivo) pero nunca sustituye a SKU como identificador de actualización
— exactamente como pide el adendo.

**Semántica de una celda en blanco — decisión de diseño explícita**:
en un **CREATE**, una columna opcional en blanco usa el mismo default
que el modelo `Product` (`barcode=""`, `is_active=True`,
`inventory_tracking_type=QUANTITY`, etc.). En un **UPDATE**, una
columna en blanco significa **"no cambiar este campo"** — nunca
"vaciarlo" — así una fila que no repite todas las columnas para un
producto ya existente nunca borra sus datos actuales por accidente. Si
un UPDATE no cambia ningún campo (todas las columnas opcionales en
blanco, o los mismos valores ya guardados), se marca como
**advertencia** ("Sin cambios respecto al producto actual"), nunca
como error — no bloquea la confirmación.

**Separación estricta con inventario/stock** (regla ya central del
proyecto desde FASE 8, ver `docs/inventory.md`): la importación de
catálogo NUNCA toca `StockMovement`, `InventoryUnit`, IMEI/serial,
costos históricos, COGS ni contabilidad — verificado con tests
dedicados (`SerializedSeparationTests`). Cambiar
`inventory_tracking_type` de un producto que ya tiene movimientos/
unidades se rechaza con la MISMA regla que el formulario manual
(`services.product_has_inventory_history`, extraída del formulario a
un servicio reutilizable en esta misma extensión — nunca una
validación paralela). Una plantilla separada de unidades serializadas
(`Unidades-Serializadas.xlsx`) NO se construyó — fuera de alcance de
esta extensión, queda para una fase futura si se prioriza.

**Flujo real**: `Subir .xlsx → validar (apps.customers.file_validation
+ chequeo de macros) → parsear y validar filas en bloque (nunca N+1) →
crear ProductImportBatch con el resultado completo → mostrar preview
(total/nuevos/actualizaciones/advertencias/errores) → confirmar (POST
separado) → aplicar todo o nada → auditar`. Nunca se guarda nada al
subir — `build_preview` solo crea el `ProductImportBatch` con el
resultado ya validado, ningún `Product` se toca hasta la confirmación
explícita. Modo estricto real: `ProductImportBatch.can_confirm` es
`False` si `error_count > 0`, y la vista de confirmación lo rechaza
explícitamente — nunca una confirmación parcial.

**Diseño clave: nunca se persiste el archivo `.xlsx` subido.** Se
parsea y valida una sola vez al subir; el resultado ya normalizado
(`ProductImportBatch.preview_data`/`errors_data`/`warnings_data`, tres
`JSONField`) es lo único que usa la confirmación — evita por completo
el problema de "almacenamiento temporal seguro / eliminación de
temporales" que pedía el adendo revisar: no hay ningún archivo temporal
que gestionar ni limpiar, nunca queda un archivo huérfano en disco.

**Seguridad**: permisos propios `products.import`/`products.export`
(`apps.permissions.catalog`, MANAGER en adelante por defecto, nunca
ADMIN-excluido) — cada vista los exige vía `PermissionRequiredMixin`,
nunca solo ocultos en la plantilla. Tenant isolation: cada
`ProductImportBatch`/`Product` se filtra siempre por
`tenant=request.tenant`, un lote de otro tenant da 404 (nunca se
confirma cruzando tenant). Validación de archivo reutilizando
`apps.customers.file_validation` (extensión + firma binaria + tamaño,
mismo validador que `PaymentProof`, nunca un segundo) + un chequeo
adicional propio de macros (`.xlsm` renombrado a `.xlsx` comparte la
misma firma ZIP — se detecta por la presencia de `xl/vbaProject.bin`
dentro del contenido, sin importar la extensión declarada). Valores con
apariencia de fórmula (`=`/`@` al inicio) se RECHAZAN como error de
validación en cualquier columna de texto — nunca se guardan ni se
reexportan tal cual (la exportación además sanitiza cada celda vía
`apps.core.utils.sanitize_cell_value`, FASE 18, heredado gratis de
reutilizar `apps.reports.exports.xlsx_response`). Auditoría real vía
`apps.audit` (`AuditLog.Action.PRODUCT_IMPORT_CONFIRMED` al confirmar,
`EXPORT_PERFORMED`/dominio `"products"` al exportar — nunca un log
paralelo), import diferido + resiliente (nunca rompe la operación que
audita).

**Concurrencia**: la confirmación de un lote bloquea la fila del
propio `ProductImportBatch` (`select_for_update`) para que dos
confirmaciones del mismo lote (doble clic, dos pestañas) nunca lo
apliquen dos veces; cada `Product` existente se bloquea también
(`select_for_update`, orden determinístico por SKU) antes de
actualizarlo. Un `CREATE` que choca con un SKU/barcode creado por otra
transacción concurrente entre el preview y la confirmación queda
protegido por los `UniqueConstraint` ya existentes — se captura como
conflicto real vía un SAVEPOINT interno (`transaction.atomic()`
anidado): el lote completo se revierte y queda `FAILED`, nunca
parcialmente aplicado (verificado con 4 tests de concurrencia reales,
hilos + PostgreSQL real).

**Rendimiento**: `build_preview` resuelve SKUs/barcodes/categorías
existentes con consultas en BLOQUE (`filter(sku__in=...)`,
`filter(barcode__in=...)`, categorías del tenant cargadas una sola vez)
— nunca una consulta por fila, verificado con un test de conteo de
queries (`PerformanceTests`, constante entre 5 y 50 filas). Límite duro
de `MAX_FILAS_IMPORTACION = 5000` filas por archivo (constante, fácil
de ajustar si una medición real lo justifica).

**Integración con el catálogo único**: la importación actualiza el
MISMO `Product` que ya consumen Ventas, POS, Compras, Reportes y la
Catalog API — nunca un catálogo paralelo. Nunca reescribe una factura
histórica ni un `SaleItem`/`PurchaseOrderItem` ya emitido (esos ya
snapshotean el precio al momento de la operación, FASE 10/12) — solo
el `Product` maestro vigente hacia adelante.

**Relación con otras fases**:
- **FASE 14 (Reportes)**: los reportes de Inventario (`apps.reports`)
  siguen siendo exclusivamente de LECTURA/análisis — nunca el camino
  para crear/actualizar productos, ver también la nota en
  `docs/reports.md`.
- **FASE 19 (Performance)**: misma disciplina aplicada (medir antes de
  optimizar, batch/bulk seguro, sin N+1) — ver `docs/performance.md`.
- **FASE 22 (Data Migration)**: podrá reutilizar esta capacidad para
  cargas iniciales de catálogo; la migración completa de datos
  mantiene su propio procedimiento de reconciliación e integridad —
  la importación de Excel nunca sustituye ese proceso.

**Explícitamente NO construido en esta extensión**: plantilla dedicada
de unidades serializadas (`Unidades-Serializadas.xlsx`); un modo
tolerante (no estricto); moneda/unidad de medida como columnas (no
existen en el modelo); actualización de precio con preservación
automática de un historial de precios (no existe ese concepto en el
proyecto — `Product` siempre representa el precio VIGENTE, igual que
antes de esta extensión).
