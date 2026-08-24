# Multi-Tenancy

Single database PostgreSQL con aislamiento estricto por tenant a nivel de
aplicación (ver ADR-003). Este documento describe la arquitectura
implementada en **FASE 3 — Multi-Tenancy** y las reglas que toda fase
futura (desde FASE 8 en adelante) debe seguir al agregar modelos de
negocio.

## Componentes

### `apps/accounts` — Custom User Model
`AUTH_USER_MODEL = "accounts.User"`. Se introdujo en FASE 3 (no después)
porque Django exige fijar el modelo de usuario personalizado antes de la
primera migración real; cambiarlo más tarde requiere reconstruir la base
de datos. `User` extiende `AbstractUser` y solo añade `email` único; los
flujos de autenticación (registro, login, logout, recuperación, perfil)
son alcance de **FASE 4 — Authentication**, todavía no implementados.

### `apps/tenants` — Tenant, Membership y aislamiento

| Módulo | Responsabilidad |
|---|---|
| `models.py` | `Tenant`, `Membership` (relación User↔Tenant con rol), `TenantScopedModel` (base abstracta) e `IsolationSample` (modelo de referencia, ver más abajo) |
| `scoping.py` | "Tenant Context": guarda el tenant activo en un `contextvars.ContextVar` (seguro con hilos/async) |
| `managers.py` | `TenantQuerySet`/`TenantManager`: filtran automáticamente por el tenant activo |
| `middleware.py` | `TenantMiddleware`: determina el tenant activo de cada request |
| `permissions.py` | `require_tenant`, `require_role`, `TenantRequiredMixin`: controles de autorización |
| `services.py` | Ejemplo de capa de servicios (ver `ARCHITECTURE.md`) que depende del manager tenant-aware |
| `views.py` | `whoami_view`: vista interna de verificación (no registrada en URLs públicas, ver más abajo) |
| `tests.py` | 16 pruebas automatizadas de aislamiento (detalle al final) |

### Tenant Context (`scoping.py`)
El tenant activo se guarda en un `ContextVar`, no en un global mutable ni
en un thread-local clásico: es seguro con múltiples requests concurrentes
y compatible con código async futuro. Se accede con:

- `get_current_tenant()` — lee el tenant activo (o `None`).
- `set_current_tenant(tenant)` / `reset_current_tenant(token)` — lo fija
  y lo restaura (usado por el middleware).
- `tenant_context(tenant)` — context manager de conveniencia para tests y
  comandos internos.

### Resolución del tenant (`TenantMiddleware`)
Se ejecuta después de `AuthenticationMiddleware` (necesita `request.user`
ya resuelto). Algoritmo:

1. Si no hay usuario autenticado → `request.tenant = None`. Fin.
2. Se cargan las membresías **activas** del usuario (`Membership.objects`,
   con manager plano — ver nota abajo) hacia tenants también activos.
3. Si no tiene ninguna → `request.tenant = None`. Fin.
4. Si la sesión indica un `active_tenant_id`, se valida contra la lista
   real de membresías del usuario; si coincide, se usa. Si NO coincide
   (manipulada, obsoleta, o de otro usuario), se descarta silenciosamente
   y se recalcula — **nunca se confía en el valor de sesión sin
   verificarlo contra la base de datos**.
5. Si no hay valor de sesión válido, se usa la membresía activa más
   antigua del usuario (orden determinista).
6. Se fija `request.tenant`, `request.membership` y el `TenantContext`
   (para que managers/servicios que no reciben `request` directamente
   también puedan resolver el tenant activo).

**Regla de seguridad central (ver CLAUDE.md): el backend determina el
tenant; el frontend nunca puede elegirlo.** El middleware **no lee en
ningún momento** query params, headers ni body — un `?tenant_id=...`
enviado por un cliente se ignora por completo (verificado en
`test_tenant_id_en_querystring_es_completamente_ignorado`).

### Modelos tenant-aware (`TenantScopedModel` / `TenantManager`)
Cualquier modelo de negocio futuro (productos, ventas, movimientos de
inventario, etc., desde **FASE 8 — Products + Inventory**) debe heredar de
`TenantScopedModel`:

```python
from tenants.models import TenantScopedModel

class Product(TenantScopedModel):
    name = models.CharField(max_length=200)
    # tenant, objects y all_objects ya vienen de TenantScopedModel
```

- `Modelo.objects` (manager por defecto) **solo** devuelve filas del
  tenant activo (`get_current_tenant()`). Sin tenant activo, devuelve un
  queryset vacío — nunca "todos los tenants" por accidente.
- `Modelo.all_objects` es una vía de escape **explícita y consciente**,
  reservada para tareas internas (auditoría, comandos de administración,
  Django Admin). Nunca debe usarse en vistas, serializers o servicios que
  atienden una request de un tenant específico.

`Membership` es una excepción deliberada: usa el manager plano de Django
(no `TenantManager`), porque es precisamente el modelo que el middleware
consulta para *determinar* cuál es el tenant activo — si estuviera
filtrado por tenant activo no se podría resolver nada la primera vez.

### `IsolationSample` — modelo de referencia (no es una entidad de negocio)
Para poder probar `TenantScopedModel`/`TenantManager` con datos reales en
PostgreSQL sin construir prematuramente un módulo de negocio (productos,
ventas, etc. son fases futuras), FASE 3 incluye `IsolationSample`: un
modelo mínimo (`tenant`, `label`) que **no se expone en ninguna vista, URL
ni funcionalidad de negocio**. Su único propósito es servir de sujeto de
prueba para las 16 pruebas de aislamiento. Las apps de negocio reales
heredarán de `TenantScopedModel` directamente, no de este modelo.

### Autorización (`permissions.py`)
- `require_tenant(request)` — exige un tenant activo (`PermissionDenied`
  si no).
- `require_role(request, roles)` — exige que la membresía activa tenga
  uno de los roles indicados (`Membership.Role.OWNER` / `MEMBER`).
- `TenantRequiredMixin` — mixin para Class-Based Views.

Estos helpers son agnósticos de framework (no dependen de Django REST
Framework, que se introduce en FASE 15) y están pensados para que FASE 4
en adelante los reutilice en vistas reales.

### Vista de verificación (`views.whoami_view`)
Ejercita el stack completo (middleware → permisos → servicio → manager)
devolviendo el tenant resuelto y los datos visibles. **No está registrada
en `config/urls.py`**: todavía no existe ningún flujo de login real (FASE
4), así que no tendría sentido exponer una URL pública que solo un
usuario autenticado podría usar. Los tests la invocan directamente con
`django.test.RequestFactory`.

## Evidencia de aislamiento (FASE 3)

Escenario de prueba: **Tenant A** y **Tenant B**, cada uno con su propio
usuario dueño (`OWNER`) y su propio dato privado en `IsolationSample`
("dato-privado-A" / "dato-privado-B"). 16 tests en
`apps/tenants/tests.py`, todos verdes contra PostgreSQL real:

| Verificado | Test |
|---|---|
| Sin tenant activo, el manager no devuelve nada (nunca "todo" por error) | `test_sin_tenant_activo_el_manager_no_devuelve_nada` |
| Cada tenant solo ve su propio dato vía manager | `test_manager_solo_ve_los_datos_de_su_propio_tenant` |
| Tenant A no puede leer NI detectar la existencia de un registro de Tenant B por ID | `test_tenant_a_no_puede_leer_registro_de_tenant_b_por_id` |
| `all_objects` es una vía de escape separada y consciente | `test_all_objects_es_una_via_de_escape_consciente_y_separada` |
| La capa de servicios respeta el aislamiento | `test_servicio_lista_solo_el_tenant_activo` |
| El middleware resuelve el tenant correcto por usuario | `test_middleware_resuelve_el_tenant_correcto_por_usuario` |
| Usuario sin membresía → sin tenant | `test_usuario_sin_membresia_no_obtiene_ningun_tenant` |
| Usuario no autenticado → sin tenant | `test_usuario_no_autenticado_no_obtiene_ningun_tenant` |
| Un `tenant_id` en la querystring se ignora por completo | `test_tenant_id_en_querystring_es_completamente_ignorado` |
| Una sesión manipulada hacia el tenant de otro usuario se descarta | `test_sesion_manipulada_hacia_otro_tenant_es_descartada` |
| Una sesión con el tenant propio y válido sí se respeta | `test_sesion_con_tenant_propio_valido_si_se_respeta` |
| La vista completa (HTTP) devuelve solo los datos de su propio tenant | `test_vista_protegida_devuelve_solo_los_datos_de_su_propio_tenant` |
| La vista rechaza a quien no tiene tenant | `test_vista_protegida_rechaza_a_quien_no_tiene_tenant` |
| `require_role` permite al rol correcto | `test_require_role_permite_al_owner` |
| `require_role` bloquea al rol incorrecto | `test_require_role_bloquea_a_quien_no_tiene_el_rol_requerido` |
| `require_tenant` bloquea sin tenant activo | `test_require_tenant_bloquea_sin_tenant_activo` |

Comando para reproducir: `python manage.py test apps.tenants` (o
`python manage.py test` para la suite completa, 19 tests incluyendo FASE 1/2).

## Reglas para fases futuras
- Todo modelo de negocio (FASE 8 en adelante) hereda de
  `apps.tenants.models.TenantScopedModel`.
- Ninguna vista/servicio/serializer debe usar `all_objects` para
  responder a una request de un tenant.
- Ningún endpoint debe leer un `tenant_id` de query params, headers o
  body para decidir de qué tenant mostrar datos: el tenant siempre viene
  de `request.tenant` (resuelto por `TenantMiddleware`).
- La API de Inventario (FASE 15) reutilizará este mismo mecanismo: una
  API Key pertenece a un único tenant (ver `docs/api/api-inventory.md`).
