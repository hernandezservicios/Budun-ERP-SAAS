# Catalog API (`/api/v1/catalog/`)

> **Estado: CONSTRUIDO** (ampliación final de FASE 15). Capa
> **comercial**, conceptualmente independiente de la Inventory API
> administrativa (`/api/v1/`, ver `docs/api-inventory.md`). Ver
> `docs/integrations.md` para el modelo `Integration` que autentica
> estos endpoints.

## 1. Dos capas, nunca mezcladas

| | Inventory API (`/api/v1/`) | Catalog API (`/api/v1/catalog/`) |
|---|---|---|
| Audiencia | Administrativa (herramientas internas/ERP a ERP) | Comercial (CRM/agentes IA externos) |
| Credencial | `ApiKey` (una por tenant) | `Integration` (varias por tenant) |
| Autenticación | `ApiKeyAuthentication` | `IntegrationCredentialAuthentication` |
| Scopes | `inventory:read`, `products:read`, `categories:read`, `inventory_movements:read`, `serialized_inventory:read`, `health:read` | `catalog:read`, `catalog:availability:read`, `catalog:media:read` |
| Rate limit | `ApiKeyRateThrottle` (scope `api_key`) | `CatalogRateThrottle` (scope `integration`) |
| Identificadores | IMEI/serie enmascarados por defecto | **Nunca** expone IMEI/serie, ni siquiera enmascarados |
| Costos | Excluidos de los serializers | Excluidos de los serializers |

Ambas comparten el mismo sobre de respuesta
(`success`/`data`/`meta`/`errors`, `apps.api.responses`), la misma
paginación con tope (`apps.api.pagination.ApiV1Pagination`) y el mismo
principio de resolución de tenant (siempre desde la credencial, nunca
de un parámetro del cliente) — pero son dos ARQUITECTURAS DE
AUTORIZACIÓN separadas: una `Integration` nunca puede llamar a
`/api/v1/products/` (Inventory API) ni una `ApiKey` puede llamar a
`/api/v1/catalog/products/` (Catalog API); cada una solo reconoce su
propio tipo de credencial.

## 2. Endpoints

Todos de solo lectura, autenticados con
`Authorization: Bearer <secreto de Integration>` (scope indicado),
excepto `media/<uuid>/` (público, sin autenticación — ver sección 6).

| Endpoint | Scope | Descripción |
|---|---|---|
| `GET /api/v1/catalog/search/` | `catalog:read` | Busca por `q` (nombre/SKU/barcode), `brand`, `model`, `color`, `capacity` |
| `GET /api/v1/catalog/products/` | `catalog:read` | Lista paginada del catálogo activo |
| `GET /api/v1/catalog/products/{id}/` | `catalog:read` | Detalle de un producto, incluye `variants` (hermanas) |
| `GET /api/v1/catalog/availability/` | `catalog:availability:read` | Disponibilidad; `?product=<id>` para uno solo |
| `GET /api/v1/catalog/variants/` | `catalog:read` | Grupo de variantes de `?product=<id>` (obligatorio) |
| `GET /api/v1/catalog/media/` | `catalog:media:read` | Metadatos de imágenes de `?product=<id>` (obligatorio) |
| `GET /api/v1/catalog/media/{public_id}/` | — (público) | Sirve el archivo real de una imagen |

## 3. Búsqueda (sección 4 de la especificación)

Por nombre, SKU, barcode, marca, modelo (todos vía `q`, o `brand`/
`model` explícitos), y por variante/color (`?color=Negro`,
`?capacity=256GB` — filtros estructurados sobre el JSON
`variant_attributes`, más fiables que un `icontains` de texto libre
sobre JSONField, que Postgres/Django no soportan de forma directa).

**Nunca busca por IMEI/serial** — `search_catalog` (usado por la
búsqueda unificada interna, FASE 8/10/11) prioriza justamente ese tipo
de coincidencia exacta; la Catalog API deliberadamente NO lo reutiliza
para su búsqueda de texto — reutiliza en cambio
`list_products_with_stock` (búsqueda de texto sobre nombre/SKU/
barcode únicamente), verificado con un test dedicado
(`test_search_nunca_busca_por_imei_o_serial`).

## 4. Respuesta de producto — whitelist server-side

`CatalogProductSerializer` (`apps.api.catalog_serializers`) declara
EXPLÍCITAMENTE cada campo permitido — nunca serializa el modelo
Django crudo:

```
id, name, brand, model, sku, description, variants, colors, capacity,
size, price, currency, available, available_quantity, primary_image,
images
```

**Campos que NUNCA aparecen** (verificado con tests dedicados que
comprueban su AUSENCIA, no solo la presencia de los permitidos —
`apps.api.tests.test_catalog_views.CatalogWhitelistTests`):
`IMEI`/`IMEI_1`/`IMEI_2`/`serial`/`serial_number`, `unit_cost`/
`purchase_cost`/`cost`/`margin`, `supplier`/`supplier_id`,
`stock_movements`, `customer`/`customer_private_data`, `payments`,
`cash`, `accounting`, `payroll`, `hr_sensitive_data`. Ninguno de estos
existe como campo declarado en ningún serializer de este archivo — no
es una omisión de "no incluirlo en la respuesta", es que el
serializer no puede devolver lo que nunca se le enseñó a leer.

`purchase_price` (existe en `Product`, es un campo real) se excluye
deliberadamente por ser información de costo/margen — nunca expuesta
por diseño, no por un chequeo adicional en tiempo de ejecución.

## 5. Disponibilidad — misma fuente de verdad, nunca un contador paralelo

`available`/`available_quantity` provienen de `current_stock`, la
MISMA anotación que ya calcula
`apps.inventory.services.list_products_with_stock` para la Inventory
API y para el panel interno — QUANTITY vía `StockMovement`,
SERIALIZED vía `InventoryUnit` (`get_current_stock`/subquery
existente desde FASE 8). La Catalog API nunca crea un segundo
contador ni expone las `InventoryUnit` individuales — solo el
resultado comercial agregado (un número), tal como exige la
especificación.

## 6. Variantes

`Product` ganó tres campos comerciales opcionales (ampliación de
`apps.inventory.models`, migración aditiva): `brand`, `model_name`,
`variant_attributes` (JSON flexible — nunca columnas fijas `color`/
`capacity`/`size`, las dimensiones de variante son abiertas y varían
por rubro). Dos productos son "variantes entre sí"
(`apps.inventory.services.get_variant_group`) si comparten
`tenant`+`brand`+`model_name` (ambos no vacíos) — cada variante sigue
siendo un `Product` normal, con su propio SKU y su propia
disponibilidad real; agrupar variantes es una vista de PRESENTACIÓN,
nunca una segunda fuente de verdad de inventario.

`GET /api/v1/catalog/products/{id}/` incluye `variants` (las
hermanas, sin incluirse a sí mismo); `GET
/api/v1/catalog/variants/?product=<id>` devuelve el grupo COMPLETO
(incluyendo el propio producto) con su disponibilidad — reproduce
exactamente el ejemplo de la especificación ("Samsung S25 256GB —
Negro → 4 disponibles, Azul → 3, Verde → 1").

## 7. Imágenes de catálogo

Nuevo modelo `ProductImage` (`apps.inventory.models`), almacenado en
`settings.CATALOG_MEDIA_ROOT` (carpeta física **distinta** de
`media-private/` — este contenido es explícitamente público/
publicable, nunca reutiliza documentos privados de Clientes/
Proveedores). Cada imagen tiene un `public_id` (UUID) — el único
identificador usado para servirla externamente, nunca el `id`
secuencial (evita enumerar imágenes de otro tenant adivinando la
URL).

- `GET /api/v1/catalog/media/?product=<id>` (autenticado, scope
  `catalog:media:read`): metadatos + URL absoluta ya resuelta.
- `GET /api/v1/catalog/media/{public_id}/` (**público, sin
  autenticación**): sirve los bytes reales. Un `<img src>` embebido en
  la página de un CRM externo no puede enviar un `Authorization:
  Bearer` — por diseño, el contenido que el propio tenant marcó como
  público se sirve sin credencial, protegido únicamente por lo
  no-adivinable del UUID.

`CATALOG_MEDIA_ROOT` (igual que `media-private/`) forma parte del
backup de media pendiente de implementación real en FASE 20 (ver
`docs/backup-recovery.md`).

Gestión desde `apps/inventory` (subir/eliminar/marcar principal,
sección "Imágenes de catálogo" en el detalle de producto) — reutiliza
la MISMA validación de archivos ya usada para documentos de Clientes/
Proveedores (`apps.customers.file_validation.validar_archivo_adjunto`,
import diferido: `apps.inventory` es anterior a `apps.customers` en
la cadena de dependencias del proyecto), restringida además a
PNG/JPG únicamente para catálogo.

## 8. Scopes — ver `docs/integrations.md` sección 5

## 9. Rate limiting — ver `docs/integrations.md` sección 7

## 10. Auditoría de acceso

El ciclo de vida de cada `Integration` se audita completo (ver
`docs/integrations.md` sección 8). El acceso a cada endpoint de
LECTURA de la Catalog API no se audita individualmente (mismo
criterio ya documentado para Inventory API en `docs/audit.md`).

## 11. Multi-Tenant y seguridad

El tenant se resuelve siempre desde `Integration` (nunca un parámetro
del cliente); cada `get_queryset()` filtra explícitamente por ese
tenant. Verificado: credencial inválida/revocada/deshabilitada/
expirada → 401; scope insuficiente → 403; producto de otro tenant →
404; dos tenants con dos integraciones independientes nunca ven datos
cruzados (`CatalogMultiTenantIsolationTests`).

## 12. Pendiente / explícitamente NO construido en esta ampliación

- Ningún endpoint de escritura (crear/modificar/vender/cobrar) en la
  Catalog API — exigido explícitamente por la especificación.
- Ninguna implementación funcional de un provider `OTHER_ERP` — el
  valor existe en el catálogo, sin código asociado.
- Ninguna *tool* de agente IA (`search_catalog`, etc.) — esas viven en
  el consumidor (WACRM), nunca en este proyecto.
- OpenAPI/Swagger no se agrega (mismo criterio que Inventory API:
  condicionado a una dependencia nueva aprobada, no solicitada aquí).
