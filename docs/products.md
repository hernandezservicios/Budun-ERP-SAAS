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
