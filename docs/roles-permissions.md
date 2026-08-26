# Roles y Permisos (`apps.permissions`)

> **Estado: CONSTRUIDO en FASE 15** (commit "Roles + Permisos"). Este
> documento cubre el sistema de permisos granulares. La auditoría
> transversal y la API de Inventario v1 (también parte de FASE 15) se
> documentan en `docs/audit.md` y `docs/api-inventory.md` cuando se
> construyan (commits 2 y 3 de la misma fase).

## 1. Principio central: generaliza, no reemplaza

Antes de FASE 15, `apps.tenants.Membership` solo distinguía dos roles
(`OWNER`/`MEMBER`) y la autorización era binaria
(`apps.tenants.permissions.require_role`). FASE 15 no elimina nada de
eso — lo generaliza:

- `Membership.Role` gana cuatro roles nuevos (`ADMIN`, `MANAGER`,
  `CASHIER`, `EMPLOYEE`) como opciones **adicionales**. `OWNER` sigue
  siendo el rol con autorización incondicional. `MEMBER` se conserva
  sin cambios — todas las membresías creadas antes de FASE 15 siguen
  siendo válidas exactamente como estaban, y se trata igual que
  `EMPLOYEE` en los permisos de fábrica (el mínimo común denominador
  seguro: solo lectura).
- `require_tenant`/`require_role` (`apps.tenants.permissions`) **no se
  retiran** — siguen protegiendo tenant/rol binario en todas las
  vistas que ya los usaban. `apps.permissions` añade una capa de
  granularidad *encima*, no la reemplaza.
- La jerarquía de resolución (usuario → rol → tenant → negar) es
  exactamente la misma que `apps.approvals.services.get_effective_policy`
  ya usa para umbrales de aprobación — un problema distinto (¿cuánto
  puede autorizar?) resuelto con la misma forma. Los overrides
  específicos por usuario que ya existían vía `ApprovalPolicy.Scope.USER`
  no se tocan; `UserPermissionOverride` es la misma idea generalizada a
  permisos de acción, no un reemplazo.

**`SUPER_ADMIN`** (mencionado en la especificación de FASE 15) no se
modela como un `Membership.Role`: un "super admin" es un concepto de
PLATAFORMA (staff de Budun ERP con acceso operativo, no un rol dentro
de la empresa cliente), así que se adapta a `User.is_superuser` —ya
existe en `AbstractUser`, sin campo nuevo—, documentado aquí como la
adaptación explícita que permitía la especificación ("los nombres
pueden adaptarse a la arquitectura existente").

## 2. Catálogo de permisos (`catalog.PERMISSION_CATALOG`)

Los permisos son funcionalidad del **código**, no datos de negocio
configurables por el tenant — a diferencia de `ExpenseCategory`/
`LeaveType`/`TaxCode` (que sí son tablas tenant-configurables), el
catálogo es una constante Python (`PERMISSION_CATALOG`, lista de
`(código, etiqueta, dominio)`) con ~85 permisos agrupados por dominio:
`dashboard`, `customers`, `suppliers`, `products`, `inventory`,
`sales`, `quotations`, `pos`, `payments`, `purchases`, `expenses`,
`hr`, `payroll`, `accounting`, `reports`, `api`, `audit`, `settings`.

Lo que SÍ es configurable por tenant es *quién* tiene cada permiso:

- **`RolePermission`** (`tenant`, `role`, `permission_code`,
  `is_granted`): personalización por tenant de qué trae un rol.
  Ausencia de fila para (tenant, rol, código) significa "usa el
  default de fábrica" (`catalog.DEFAULT_ROLE_PERMISSIONS`), **nunca**
  "denegado" — la fila explícita es la única forma de apartarse del
  default, en cualquier dirección (conceder algo que el default no da,
  o denegar algo que el default sí da).
- **`UserPermissionOverride`** (`tenant`, `user`, `permission_code`,
  `is_granted`, `reason`): excepción específica de un usuario,
  máxima prioridad en la resolución.

## 3. Permisos de fábrica por rol (`DEFAULT_ROLE_PERMISSIONS`)

| Rol | Alcance de fábrica |
|---|---|
| `OWNER` | Todo, incondicionalmente (regla especial en `has_permission`, no aparece en el diccionario). |
| `ADMIN` | Todos los permisos del catálogo **excepto** `accounting.close_period`, `accounting.reopen_period`, `api.inventory.manage`/`rotate`/`revoke`, `settings.manage`. |
| `MANAGER` | CRUD/operación de la mayoría de dominios (clientes, proveedores, productos, inventario, ventas, cotizaciones, POS/caja, pagos, compras, gastos, RRHH básico, ver contabilidad/reportes) — sin contabilización/reversa/cierre contable, sin datos sensibles de RRHH/Nómina, sin gestión de API. |
| `CASHIER` | `pos.use`, `cash.open/close/move/view`, `sales.create`, `payments.create`, `credit.view`, `credit_note.view/apply`, más lectura de clientes/productos/inventario/cotizaciones/reportes. |
| `EMPLOYEE` | Solo lectura (`*.view`) en la mayoría de dominios, más `expenses.create`. |
| `MEMBER` (histórico) | Igual que `EMPLOYEE` — preserva el comportamiento seguro mínimo para membresías creadas antes de FASE 15. |

El propietario del tenant siempre está autorizado — regla permanente
ya establecida en el proyecto (`apps.approvals`, `apps.hr`), aquí
generalizada a permisos de acción.

## 4. Resolución (`services.has_permission`)

```python
def has_permission(tenant, user, code):
    if not is_valid_permission_code(code):
        raise InvalidPermissionOperation(...)
    if user is not None and user.is_superuser:
        return True
    membership = _get_membership(tenant, user)  # Membership.objects — ver nota
    if membership is None:
        return False
    if membership.role == Membership.Role.OWNER:
        return True
    override = UserPermissionOverride.all_objects.filter(...).first()
    if override is not None:
        return override.is_granted
    fila_rol = RolePermission.all_objects.filter(...).first()
    if fila_rol is not None:
        return fila_rol.is_granted
    return code in DEFAULT_ROLE_PERMISSIONS.get(membership.role, set())
```

Nota sobre `Membership.objects`: a diferencia de los modelos de
negocio (`TenantScopedModel`, donde `objects` es el `TenantManager`
filtrado por el ContextVar del tenant activo y `all_objects` es el
escape explícito), `Membership` usa el manager por defecto de Django a
propósito — es el modelo que se consulta para *determinar* el tenant
activo de una request, así que no puede depender de que ya exista uno
resuelto. `Membership.objects.filter(tenant=..., user=..., is_active=True)`
funciona igual dentro y fuera de una request HTTP real.

`require_permission(request, code)` (mismo estilo que `require_role`)
lanza `PermissionDenied` (HTTP 403) si no está autorizado.
`PermissionRequiredMixin` (`permission_code = "..."`) se combina con
`TenantRequiredMixin` en vistas basadas en clase — nunca lo
reemplaza, y en el `MRO` va **después** de `LoginRequiredMixin`/
`TenantRequiredMixin` para que login y tenant se resuelvan primero.

## 5. Datos sensibles

`hr.sensitive.view`, `payroll.sensitive.view`/`.export`,
`accounting.export`, `customers.financial.*`, `reports.sensitive.export`
son permisos separados de la vista/edición general del dominio —
nunca se concede acceso financiero/sensible solo porque el usuario
pertenece al tenant:

- `apps.hr.services.can_view_sensitive_employee_data` (existente desde
  FASE 13) ahora delega en `has_permission(tenant, user,
  "hr.sensitive.view")` — el propietario sigue autorizado
  incondicionalmente (la regla ya estaba en `has_permission`), y
  además el tenant puede conceder el permiso a otro rol/usuario sin
  tocar código. Cada lectura se sigue auditando
  (`HRActivityLog.SENSITIVE_DATA_VIEWED`, sin cambios).
- `apps.payroll.services.can_view_sensitive_payroll_data` (nuevo en
  FASE 15, mismo patrón) protege `PayrollDetailView` (el desglose
  línea por línea) completo, y enmascara las columnas de monto
  (bruto/deducciones/neto) en `PayrollPeriodDetailView` cuando el
  usuario no tiene el permiso — decidido en el servidor
  (`puede_ver_sensible` en el contexto de la plantilla), nunca oculto
  solo con CSS/JS. Cada lectura del desglose se audita
  (`PayrollActivityLog.SENSITIVE_DATA_VIEWED`, nuevo).

## 6. Superficies retrofit en el commit "Roles + Permisos"

La especificación de FASE 15 pide autorización granular en el
backend de las vistas de mayor riesgo, no una reescritura de las
~100 vistas del proyecto en un solo commit (ver `CLAUDE.md`,
"Construcción incremental"). Este commit conecta:

- **RRHH sensible**: `can_view_sensitive_employee_data` (sin cambios
  de superficie, ver sección 5).
- **Nómina sensible**: `PayrollDetailView`, más `payroll.view` en
  listado/detalle de período, `payroll.process` en crear período/
  cancelar/calcular/agregar línea, `payroll.approve` en aprobar/cerrar
  período, `payroll.pay` en registrar/anular pago.
- **Contabilidad**: `accounting.post` (crear asiento),
  `accounting.reverse` (reversar), `accounting.close_period`/
  `accounting.reopen_period` (cierre/reapertura de período).
- **Caja**: `cash.open`/`cash.close`/`cash.move` en
  `CashSessionOpenView`/`CashSessionCloseView`/`CashMovementCreateView`
  (`apps.pos`) — `CashRegisterListView` sigue protegida por
  `require_role(OWNER)`, sin cambios.
- **Clientes y Proveedores** (dominio CRUD representativo): las vistas
  base compartidas (`_ContactListView`/`_ContactDetailView`/
  `_ContactCreateView`/`_ContactUpdateView`/`_ContactStatusView`/
  `_ContactDocument*View`) ganan `PermissionRequiredMixin`, con
  `permission_code` fijado por cada subclase concreta
  (`customers.view`/`.create`/`.update`/`.delete` para Clientes,
  `suppliers.*` para Proveedores; subir/eliminar documentos usa el
  mismo permiso que editar, no hay un código de catálogo dedicado a
  documentos).
- **Configuración**: `SettingsHomeView` (`apps.core`) exige
  `settings.view`; `RolesIndexView`/`RolePermissionsView`/
  `UserOverridesView` (`apps.permissions`) exigen `settings.manage`.

El resto de las vistas del proyecto sigue protegido únicamente por
`require_tenant`/`require_role` — un rollout deliberado por fases,
documentado aquí y en `docs/project-status/KNOWN_ISSUES.md`, no una
brecha de seguridad: la multi-tenencia y el login siguen intactos en
el 100% de las vistas.

## 7. UI: Configuración → Roles y Permisos

`/configuracion/` (`core:settings`) es el hub de Configuración —
enlaza a Roles y Permisos hoy; la sección "API de Inventario" se
agrega ahí mismo cuando se construya `apps.api` (commit 3 de FASE 15),
nunca una segunda página de configuración paralela.

`/configuracion/permisos/` (`apps.permissions`):

- **Índice** (`permissions:index`): lista los roles no-OWNER y las
  membresías activas del tenant.
- **Permisos de un rol** (`permissions:role_permissions`): un
  checkbox por permiso del catálogo, agrupado por dominio,
  inicializado con los valores EFECTIVOS actuales
  (`get_effective_role_permissions` — default de fábrica + lo que el
  tenant ya haya personalizado). Al guardar, solo se crean/actualizan
  filas `RolePermission` para los permisos que realmente cambiaron.
- **Overrides de un usuario** (`permissions:user_overrides`): lista
  los overrides existentes y un formulario para conceder/denegar/
  quitar uno.

Nota técnica: los códigos de permiso (`"customers.view"`) no se
pueden usar como nombre de campo de formulario en una plantilla vía
`{{ form.customers.view }}` — Django interpreta el punto como una
cadena de acceso a atributo/clave/índice, no como parte literal del
nombre. La vista resuelve esto construyendo `sections` (una lista de
`(dominio, [BoundField, ...])`) con `form[codigo]` (válido en Python),
y la plantilla solo itera `sections` con `{% for %}` simple — nunca
intenta un acceso con punto.

## 8. Aislamiento Multi-Tenant

`RolePermission`/`UserPermissionOverride` son `TenantScopedModel`
—aislamiento automático—, y además cada consulta en `services.py`
filtra `tenant=` explícitamente (defensa adicional, mismo principio
que el resto del proyecto). Las vistas de Configuración usan
`get_object_or_404(Membership, tenant=request.tenant, ...)` para
resolver el usuario objetivo — un ID de membresía de otro tenant da
404, nunca el contenido.

## 9. Pendiente (commits siguientes de FASE 15)

- Auditoría transversal (`apps.audit`) — evento `PERMISSION_CHANGED`
  ya se emite desde `services.py` vía import diferido, listo para
  cuando `apps.audit` exista.
- API de Inventario v1 (`apps.api`) — permisos `api.inventory.*` ya
  están en el catálogo, sin conectar todavía.
- Retrofit de permisos en el resto de dominios (ventas, compras,
  gastos, reportes) — el catálogo ya cubre esos códigos; conectarlos
  a sus vistas es trabajo incremental futuro, no bloqueante para el
  cierre de este commit.
