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

## Importación y exportación masiva de productos (Excel) — ESPECIFICADO, NO CONSTRUIDO

> **Estado: especificación integrada, sin ningún código/modelo/
> migración/vista/servicio creado todavía.** Ordenada por el usuario en
> `ADENDUM_FASE_8_IMPORTACION_PRODUCTOS_EXCEL.md` (raíz del repositorio,
> preservado ahí tal cual, nunca copiado a `docs/`). Pertenece a FASE 8
> (extiende Productos/Inventario) — implementación pendiente de
> autorización explícita, no incluida en el cierre ya aprobado de FASE 8
> (ver `docs/phases/PHASE-08-products-plus-inventory.md`).

**Objetivo**: capacidad de carga/descarga masiva de productos vía
`.xlsx` (nunca CSV como formato principal) desde Inventario → Productos:
`Nuevo`/`Editar` (ya construidos) + `Importar Excel`/`Exportar Excel`/
`Descargar plantilla` (especificados aquí, no construidos).

**Columnas de la plantilla — evaluadas contra el modelo `Product` real**
(regla explícita del adendo: "no inventar columnas que el modelo no
soporte"):

| Columna de la plantilla | Campo real de `Product` | Estado |
|---|---|---|
| SKU | `sku` | soportado |
| Barcode | `barcode` | soportado |
| Nombre | `name` | soportado |
| Descripción | `description` | soportado |
| Marca | `brand` | soportado (FASE 15) |
| Modelo | `model_name` | soportado (FASE 15) |
| Categoría | `category` (FK, por nombre) | soportado |
| Tracking | `inventory_tracking_type` (`QUANTITY`/`SERIALIZED`) | soportado |
| Precio | `sale_price` (venta) y/o `purchase_price` (costo) | soportado — **a decidir en la implementación** cuál(es) de los dos expone la plantilla, ver "Contradicción encontrada" abajo |
| Impuesto | `tax_rate` | soportado |
| Stock mínimo | `min_stock` | soportado |
| Estado | `is_active` | soportado |
| Atributos de variante | `variant_attributes` (JSON) | soportado |
| Moneda | — | **NO soportado — ver "Contradicción encontrada"** |
| Unidad de medida | — | **NO soportado — ver "Contradicción encontrada"** |

**Contradicción real encontrada durante esta sincronización** (no
oculta, ni resuelta unilateralmente): el adendo pide columnas "moneda"
y "unidad de medida" como parte de la plantilla, pero `Product` no
tiene ningún campo de moneda ni de unidad de medida hoy — no existe ese
concepto en ningún modelo del proyecto (verificado por búsqueda
exhaustiva). Tampoco "precio" es un campo único: `Product` tiene DOS
precios (`sale_price`/`purchase_price`), y el adendo no especifica cuál
expone la plantilla. Ninguna de las tres cosas se decide ni se inventa
en esta sincronización documental — quedan como decisiones explícitas
que la fase de IMPLEMENTACIÓN real deberá resolver con el usuario
(¿agregar los campos al modelo primero, con su propia migración? ¿usar
`sale_price` únicamente? ¿ambos precios en dos columnas separadas?),
nunca asumidas en silencio.

**Matching CREATE/UPDATE**: SKU es el único criterio principal
(`UniqueConstraint(tenant, sku)` ya existente), respetando unicidad por
tenant — nunca el nombre. Barcode puede ser un criterio secundario
porque la arquitectura real ya lo soporta (`UniqueConstraint` parcial
por tenant sobre `barcode`), documentado explícitamente como algo a
decidir en el diseño de implementación (no ambiguo por el modelo, sí
pendiente de decisión de producto).

**Separación estricta con inventario/stock** (regla ya central del
proyecto desde FASE 8, ver `docs/inventory.md`): la importación de
catálogo NUNCA toca `StockMovement`, `InventoryUnit`, IMEI/serial,
costos históricos, COGS ni contabilidad — solo campos del catálogo
(`Product`). Cualquier carga de stock inicial futura deberá pasar por
`apps.inventory.services` (`register_stock_in`/`register_serialized_unit`),
nunca escribir esas tablas directamente desde el importador. Una
plantilla separada (`Unidades-Serializadas.xlsx`, NO especificada en
detalle todavía) queda para una fase de implementación futura si se
necesita carga masiva de unidades ya existentes.

**Flujo obligatorio**: `Subir .xlsx → validar → detectar CREATE/UPDATE
→ preview (total/nuevos/actualizaciones/advertencias/errores) → corregir
→ confirmar → guardar`. Nunca guardar directamente al subir. Modo
`STRICT` por defecto (un error bloquea la confirmación completa
—consistente con la disciplina de "todo o nada" ya usada en
`apply_payment_to_sales`/reconciliaciones del proyecto); un modo
tolerante queda para una extensión futura, nunca el comportamiento por
defecto.

**Seguridad y rendimiento** (a respetar en la implementación futura,
sin decidir aquí cómo): autorización server-side + tenant isolation
(mismo patrón que toda vista de negocio desde FASE 3); validación de
archivo reutilizando `apps.customers.file_validation` en vez de un
segundo validador (mismo criterio "no duplicar" ya aplicado a
`PaymentProof` en FASE 17/18); reporte de errores descargable en Excel;
auditoría (usuario, fecha, tenant, archivo, resultado) vía
`apps.audit`, nunca un log paralelo; batch/bulk seguro y sin N+1 para
catálogos grandes (mismo principio ya exigido por FASE 19, ver
`docs/performance.md`); idempotencia real ante reintentos (referencia
de importación única, mismo principio que `PayPal-Request-Id`/
`SaaSInvoice.UniqueConstraint(subscription, period_start)`).

**Integración con el catálogo único**: la importación actualiza el
MISMO `Product` que ya consumen Ventas, POS, Compras, Reportes y la
Catalog API — nunca un catálogo paralelo. Cambios de precio deben
preservar historial/snapshots donde ya existen (`SaleItem`/
`PurchaseOrderItem` ya snapshotean precio al momento de la operación,
ver FASE 10/12) — la importación nunca reescribe una factura histórica
ni un `SaleItem` ya emitido, solo el `Product` maestro vigente hacia
adelante.

**Relación con otras fases** (tal como las define el propio adendo):
- **FASE 14 (Reportes)**: los reportes de Inventario (`apps.reports`,
  CSV/XLSX ya construidos desde la ampliación de cierre de FASE 14)
  siguen siendo exclusivamente de LECTURA/análisis — nunca el camino
  para crear/actualizar productos. La importación/exportación operativa
  de maestros de productos es de Productos/Inventario, un dominio
  distinto aunque comparta el formato `.xlsx`.
- **FASE 19 (Performance)**: cualquier implementación futura deberá
  seguir la misma disciplina ya exigida y aplicada en esa fase —
  medición antes de optimizar, batch/bulk seguro, evitar N+1, ver
  `docs/performance.md`.
- **FASE 22 (Data Migration)**: podrá reutilizar esta capacidad para
  cargas iniciales de catálogo, pero la migración completa de datos
  mantiene su propio procedimiento de reconciliación e integridad — la
  importación de Excel nunca sustituye el proceso de FASE 22.

**Explícitamente fuera de esta sincronización** (ninguna palabra de
código): modelos, migraciones, vistas, servicios, endpoints, la
plantilla `.xlsx` real, ni ninguna lógica de parsing/validación. Todo
lo anterior es especificación integrada a la documentación, pendiente
de una autorización de implementación explícita y separada.
