# API de Inventario v1 (`apps.api`)

> **Estado: CONSTRUIDO en FASE 15** (commit "API de Inventario v1").
> Reemplaza la especificación anterior de este documento — todo lo
> descrito aquí abajo ya existe en el código, no es un plan.

## 1. Principio central

Integración de solo lectura para agentes CRM/IA externos, bajo
`Configuración → API de Inventario` (la UI de gestión de la clave se
agrega en el siguiente commit — "Configuración UI + integración
final"). El agente nunca accede directamente a PostgreSQL — solo a
través de `/api/v1/`, autenticado con una API Key propia por tenant.

## 2. `ApiKey` (`apps.api.models`)

Un tenant tiene **como máximo una** `ApiKey` (`UniqueConstraint`) —
"regenerar"/"rotar" reescribe el hash de la MISMA fila, nunca crea una
segunda: nunca hay dos claves activas a la vez para un tenant.

- `key_prefix`: lo único que se muestra permanentemente después de la
  creación/rotación (p. ej. `bk_a1b2c3d4`), enmascarado en cualquier
  vista vía `apps.core.utils.mask_secret` (mismo criterio ya usado
  para IMEI/serie en `InventoryUnitAdmin`, ahora generalizado).
- `key_hash`: SHA-256 del secreto completo. El secreto en texto plano
  **nunca se guarda** — solo existe como valor de retorno de
  `generate_api_key`/`rotate_api_key`, mostrado UNA vez.
- `scopes` (JSON, lista validada contra `apps.api.scopes.SCOPE_CHOICES`):
  `health:read`, `products:read`, `categories:read`, `inventory:read`,
  `inventory_movements:read`, `serialized_inventory:read`. **Ningún
  scope financiero** (ventas/pagos/nómina/contabilidad/RRHH) existe
  todavía — regla permanente del catálogo.
- `status` (`ACTIVE`/`REVOKED`), `expires_at` (nulable, nunca expira
  por defecto), `created_at`/`created_by`, `rotated_at`,
  `revoked_at`/`revoked_by`, `last_tested_at`/`last_test_ok`/
  `last_test_error`, `last_used_at` (actualizado en cada request
  autenticada).

`apps.api.services` es la única vía sancionada: `generate_api_key`,
`rotate_api_key`, `revoke_api_key`, `set_api_key_scopes`,
`authenticate_api_key` (resuelve por hash, nunca por prefijo/tenant
enviado por el cliente), `touch_last_used`, `test_connection`. Toda
operación de ciclo de vida se audita vía `apps.audit`
(`API_KEY_CREATED`/`ROTATED`/`REVOKED`, dominio `"api"`).

## 3. Autenticación (`apps.api.authentication.ApiKeyAuthentication`)

`Authorization: Bearer <clave>` — única forma de autenticarse ante
`/api/v1/` (`REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = []`
globalmente; cada vista fija esta clase explícitamente). El tenant se
resuelve **siempre** desde la clave (`request.tenant`/`request.api_key`)
— nunca de un parámetro de la URL/query string, mismo principio de
FASE 3. Sin encabezado → 401 (`NotAuthenticated`, automático de DRF);
clave inválida/revocada/expirada → 401 (`AuthenticationFailed`
explícito). `request.user` queda `None` deliberadamente: no hay un
usuario humano detrás de una API Key.

## 4. Scopes (`apps.api.permissions.HasScope`)

Un único permiso DRF genérico lee `view.required_scope` (declarado por
cada vista) contra `api_key.scopes` — scope insuficiente (clave válida
pero sin el scope) → 403. La distinción entre roles humanos
(`apps.permissions`) y scopes de API es total: una `ApiKey` **nunca**
hereda los permisos de ningún usuario — son dos sistemas de
autorización completamente independientes, tal como exige la
especificación.

## 5. Sobre de respuesta consistente (`apps.api.responses`)

Toda respuesta (éxito o error) tiene la forma:

```json
{"success": true, "data": ..., "meta": {...}, "errors": null}
{"success": false, "data": null, "meta": {}, "errors": [{"code": "...", "detail": "..."}]}
```

`api_exception_handler` (`REST_FRAMEWORK["EXCEPTION_HANDLER"]`)
reformatea cualquier excepción de DRF al sobre estándar (400/401/403/
404/405/409/429 mapeados a un código legible) y captura cualquier
excepción no manejada como 500 genérico, **sin** exponer traceback ni
mensaje interno — se registra en el log del servidor, nunca en la
respuesta.

## 6. Paginación (`apps.api.pagination.ApiV1Pagination`)

`page`/`page_size` en la query string, `page_size` máximo 100 (nunca
"sin límite" aunque el cliente lo pida). `meta` de toda lista trae
`page`/`page_size`/`total`/`next`/`previous`.

## 7. Rate limiting (`apps.api.throttling.ApiKeyRateThrottle`)

`SimpleRateThrottle` de DRF, cacheado vía `LocMemCache`
(`CACHES["default"]`, adecuado para un solo proceso — Redis queda
deferido hasta que una fase futura demuestre necesidad real, ver
`CLAUDE.md`). Límite configurable a nivel de **proyecto**
(`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["api_key"]`, hoy
`120/min`) — un límite distinto por API Key individual queda
documentado como extensión futura simple, no construida en esta fase.
Excedido → 429.

> Nota de testing: `SimpleRateThrottle.THROTTLE_RATES` se calcula UNA
> VEZ como atributo de clase al importar `rest_framework.throttling`
> — `override_settings(REST_FRAMEWORK=...)` dispara la recarga de
> `api_settings`, pero nunca vuelve a tocar ese atributo de clase ya
> fijado. Los tests que necesitan un límite distinto parchean
> `ApiKeyRateThrottle.THROTTLE_RATES` directamente
> (`unittest.mock.patch.object`).

## 8. Endpoints (`/api/v1/`)

Todos de solo lectura (**GET únicamente** — ningún POST/PUT/DELETE en
ningún endpoint de esta fase). Reutilizan literalmente
`apps.inventory.services` (`list_products_with_stock`,
`get_low_stock_products`) — nunca reimplementan esas consultas aquí.

| Endpoint | Scope | Reutiliza | Filtros |
|---|---|---|---|
| `GET /api/v1/health/` | `health:read` | — | — |
| `GET /api/v1/products/` | `products:read` | `list_products_with_stock` | `search`, `sku`, `barcode`, `category`, `tracking_type`, `only_active`, `low_stock`, `updated_since` |
| `GET /api/v1/products/{id}/` | `products:read` | ídem | — |
| `GET /api/v1/categories/` | `categories:read` | `Category` | — |
| `GET /api/v1/inventory/` | `inventory:read` | `list_products_with_stock` | — |
| `GET /api/v1/inventory/low-stock/` | `inventory:read` | `get_low_stock_products` | — |
| `GET /api/v1/inventory/movements/` | `inventory_movements:read` | `StockMovement` | `product`, `updated_since` |
| `GET /api/v1/inventory/serialized/` | `serialized_inventory:read` | `InventoryUnit` | `product`, `state`, `serial`, `imei` |

`products/`/`inventory/` devuelven `purchase_price`/`unit_cost`
**excluidos** deliberadamente (información de costo/margen —
financiera, fuera de los scopes de esta fase). `inventory/serialized/`
enmascara `serial`/`imei_1`/`imei_2` por defecto (`serial_masked`/
`imei_1_masked`/`imei_2_masked`, vía `mask_secret`) — no existe
todavía un scope que permita verlos completos.

## 9. Aislamiento Multi-Tenant

El tenant viene SIEMPRE de `request.tenant` (resuelto por
`ApiKeyAuthentication` desde la clave) — cada `get_queryset()` filtra
explícitamente por ese tenant; un ID de otro tenant en
`products/{id}/` da 404, nunca el contenido. Verificado con dos
tenants y dos claves independientes (ver
`apps.api.tests.test_views.ApiMultiTenantIsolationTests`).

## 10. Auditoría de acceso

Cada operación de ciclo de vida de la clave se audita
(`apps.audit`, dominio `"api"`, `object_id` = `key_prefix` — nunca la
clave completa). El acceso a cada endpoint de lectura todavía no
audita individualmente cada request (alto volumen esperado, bajo
valor por evento) — decisión documentada, revisable si el volumen
real de uso lo justifica.

## 11. Pendiente (siguiente commit de esta misma fase)

UI de Configuración → API de Inventario (Base URL, clave enmascarada,
Generar/Regenerar/Revocar/Copiar, Probar Conexión, estado/última
prueba/último error) — el backend completo ya existe
(`apps.api.services`), solo falta la vista/formulario/plantilla.
OpenAPI/Swagger explícitamente no se agrega sin una dependencia nueva
aprobada (la propia especificación lo condicionaba a "si encaja con
la arquitectura y dependencias aprobadas").
