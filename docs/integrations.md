# Integraciones externas (`Integration`, `apps.api`)

> **Estado: CONSTRUIDO** (ampliación final de FASE 15). Arquitectura
> genérica de aplicaciones externas conectadas a la Catalog API — ver
> `docs/api-catalog.md` para los endpoints que estas credenciales
> autentican.

## 1. Principio central: genérico, nunca acoplado a un consumidor

El ERP expone una **API**; no construye integraciones específicas de
ningún consumidor concreto. `WACRMIntegration` — o cualquier nombre
acoplado a un producto externo — nunca existe como concepto en este
proyecto. En su lugar, `Integration` es un concepto **genérico**:
cualquier aplicación externa (WACRM, otro CRM, otro agente IA, otro
ERP) se conecta de la misma forma, con las mismas credenciales, los
mismos scopes, la misma auditoría.

**WACRM no es una dependencia del ERP — es un consumidor externo.**
El contrato que WACRM (o cualquier otro consumidor) debe implementar
es: `Catalog API` + `Application Credentials` + `Scopes` + `Public
Media`. Las *tools* que un agente IA usa para invocar este contrato
(`search_catalog`, `get_product`, `get_availability`,
`get_product_media`) son responsabilidad de **WACRM**, nunca de este
proyecto — el ERP nunca implementa `search_budun()`/`get_budun_product()`
ni ninguna función acoplada a un consumidor. El *Provider* (ver
sección 3) es la única forma en que este proyecto reconoce "quién
construyó" un consumidor — nunca una integración de código con su
arquitectura interna.

## 2. `Integration` — espejo deliberado de `ApiKey`, nunca la misma tabla

Antes de esta ampliación, `ApiKey` (ver `docs/api-inventory.md`) ya
resolvía "una credencial de API por tenant" para la Inventory API
administrativa. Para la Catalog API comercial se necesitaba algo
estructuralmente similar pero con una diferencia esencial: **un
tenant puede tener varias integraciones** (una por cada
CRM/agente/consumidor que conecte), mientras que `ApiKey` sigue
siendo exactamente una por tenant.

En vez de forzar ambos conceptos a compartir una tabla (lo que habría
requerido, por ejemplo, renombrar `ApiKey.key_hash`, un cambio
innecesario a un modelo ya migrado y en producción — contrario a la
instrucción explícita de esta ampliación de "no cambiar
innecesariamente `ApiKey`"), `Integration` es un modelo **espejo
estructural** de `ApiKey` — mismo patrón exacto ya usado en el
proyecto para `SupplierPayment`/`Payment` (dos ledgers estructuralmente
casi idénticos que nunca comparten tabla porque son dominios distintos,
ver `CLAUDE.md`). Lo que SÍ se comparte, para no duplicar el
mecanismo de verdad (generación/hash del secreto), es
`apps.api.crypto` — un módulo de ~15 líneas usado por ambos modelos.

Campos de `Integration`:

- **`name`**: nombre legible, único por tenant (`UniqueConstraint`).
- **`provider`**: identifica QUIÉN construyó el consumidor — hoy solo
  `BUDUN` tiene soporte real (los valores `OTHER_ERP`/`FUTURE` existen
  en el catálogo para uso futuro, sin ninguna implementación asociada
  — nunca se construyó "otro ERP" funcional en esta ampliación, tal
  como pedía la instrucción).
- **`app_key`** ("App Key" / "Application ID"): identificador PÚBLICO,
  visible siempre (útil para logs/soporte/auditoría) — generado como
  `app_<16 caracteres hex>`. **Nunca se usa para resolver la
  autenticación** — ver sección 4.
- **`secret_hash`** ("App Secret", hasheado): SHA-256 del secreto
  completo — igual criterio que `ApiKey.key_hash` (el secreto ya es
  aleatorio de alta entropía vía `secrets.token_urlsafe`, un hash
  rápido es apropiado; nunca se guarda en texto plano, nunca se
  recupera después de mostrarse una vez).
- **`scopes`**: lista JSON validada contra
  `apps.api.scopes.CATALOG_SCOPE_CHOICES` — **nunca** los scopes de
  `ApiKey` (`inventory:read`, etc.): dos catálogos de scopes
  completamente separados, ver `docs/api-catalog.md` sección de
  scopes.
- **`status`** (`ACTIVE`/`REVOKED`, terminal) + **`is_enabled`**
  (interruptor reversible, activar/desactivar) — dos conceptos
  distintos a propósito: revocar es definitivo (no existe
  "reactivar"), deshabilitar es temporal y reversible. Ambos bloquean
  la autenticación mientras estén activos.
- `expires_at`, `created_at`/`created_by`, `rotated_at`,
  `revoked_at`/`revoked_by`, `last_tested_at`/`last_test_ok`/
  `last_test_error`, `last_used_at` — idéntico a `ApiKey`.

## 3. Provider ≠ Tool

Un **Provider** es quién construyó el software que consume la Catalog
API (Budun ERP mismo, otro ERP, un futuro tercero). Una **Tool** es
la función concreta que un agente IA invoca para llamar a un endpoint
(`search_catalog`, `get_product`, etc.) — las Tools **viven en el
consumidor** (WACRM tendrá su propio "Integration Resolver" que
selecciona qué Provider/Tool usar), nunca en este proyecto. Confundir
ambos conceptos llevaría a implementar lógica específica de un
consumidor dentro del ERP — exactamente lo que esta ampliación prohíbe
explícitamente.

## 4. Autenticación: App Key vs. App Secret vs. credencial de acceso

Mismo mecanismo que `ApiKeyAuthentication` (Inventory API):
`Authorization: Bearer <secreto>`. La request se autentica
**exclusivamente** por el hash del secreto completo
(`integration_services.authenticate_integration`) — el tenant se
resuelve siempre desde esa credencial, nunca de un parámetro enviado
por el cliente. El `app_key` **nunca participa de la autenticación**:
es puramente un identificador de visualización/soporte (p. ej. "¿qué
integración generó este log?"), que nunca cambia al rotar el secreto
(rotar solo reemplaza `secret_hash`, preservando `app_key` — la
identidad pública de la integración no cambia, solo su credencial).

Esto responde la pregunta que la especificación pedía resolver
explícitamente: **`ApiKey` no representa el access credential de una
`Integration`** — son modelos separados (uno por tenant vs. varios
por tenant), pero **sí comparten el mismo mecanismo** de generación y
verificación de secretos (`apps.api.crypto.generate_secret`/
`hash_secret`), evitando duplicar la lógica criptográfica sin forzar
una tabla compartida que habría requerido tocar `ApiKey`.

## 5. Scopes de la Catalog API

Catálogo separado de los scopes de Inventory API
(`apps.api.scopes.CATALOG_SCOPE_CHOICES`):

| Scope | Habilita |
|---|---|
| `catalog:read` | Buscar/listar/ver detalle del catálogo comercial (incluye disponibilidad inline, variantes) |
| `catalog:availability:read` | Endpoint dedicado de disponibilidad (`/api/v1/catalog/availability/`) |
| `catalog:media:read` | Metadatos de imágenes (`/api/v1/catalog/media/`) |

Una `Integration` **nunca** puede tener un scope de `ApiKey`
(`inventory:read`, `products:read`, etc.) ni viceversa — validado en
`is_valid_catalog_scope_list`/`is_valid_scope_list` (dos funciones
separadas, cada una contra su propio catálogo cerrado).

## 6. Permisos internos (gestión de integraciones)

`api.integration.view`/`create`/`update`/`rotate`/`revoke`/`test`
(`apps.permissions.catalog`, dominio `api`) — mismo patrón que
`api.inventory.*`: el propietario del tenant siempre está autorizado;
`ADMIN` tiene `view`/`test` por defecto pero no
`create`/`update`/`rotate`/`revoke` (solo el propietario administra
credenciales completas por defecto, el tenant puede conceder más vía
`RolePermission`/`UserPermissionOverride`).

## 7. Rate limiting separado

`apps.api.throttling.CatalogRateThrottle` (scope DRF `"integration"`,
clave de caché por `Integration.pk`) — completamente independiente de
`ApiKeyRateThrottle` (scope `"api_key"`): agotar el límite de una capa
nunca afecta a la otra. Configurable a nivel de proyecto
(`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["integration"]`), mismo
criterio que Inventory API (Redis deferido, `LocMemCache` suficiente
para un solo proceso).

## 8. Auditoría

Ciclo de vida completo auditado vía `apps.audit`
(`INTEGRATION_CREATED`/`ROTATED`/`REVOKED`/`ENABLED`/`DISABLED`,
dominio `"api"`, `object_id` = `app_key` — **nunca** el secreto
completo ni el `Bearer token` recibido). El acceso a cada endpoint de
lectura de la Catalog API no audita individualmente cada request
(mismo criterio ya documentado para Inventory API en `docs/audit.md`
— alto volumen esperado, bajo valor por evento).

## 9. UI (`/configuracion/integraciones/`)

Lista de integraciones del tenant (nombre, provider, App Key
enmascarado en logs, estado, última conexión) + detalle de cada una
(scopes, crear/rotar/revocar/habilitar-deshabilitar/probar conexión).
El secreto completo se muestra **una única vez**, renderizado
directamente en la misma respuesta de "crear"/"rotar" — nunca
recuperable después, nunca en un redirect (que lo perdería).

## 10. Aislamiento Multi-Tenant

Cada `Integration` pertenece a exactamente un tenant
(`TenantScopedModel`); `authenticate_integration` resuelve el tenant
desde el hash del secreto — nunca desde un parámetro. Verificado con
dos tenants y dos integraciones independientes (ver
`apps.api.tests.test_catalog_views.CatalogMultiTenantIsolationTests`).
