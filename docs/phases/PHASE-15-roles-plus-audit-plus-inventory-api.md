# FASE 15 — Roles + Audit + Inventory API

> **Estado: CONSTRUIDO.** Tres subsistemas, cinco commits de dominio:
> Roles + Permisos (`apps.permissions`), Auditoría transversal
> (`apps.audit`), API de Inventario v1 (`apps.api`, backend +
> Configuración UI), cierre de documentación. Ver `docs/roles-permissions.md`,
> `docs/audit.md`, `docs/api-inventory.md` para el diseño completo de
> cada uno.

## Objetivo
Roles/permisos, audit log y API de Inventario para CRM IA. Ver `docs/api-inventory.md` para el resumen arquitectónico de la API.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] roles efectivos en backend — `Membership.Role` (OWNER/ADMIN/MANAGER/CASHIER/EMPLOYEE/MEMBER) + `apps.permissions.services.has_permission` (jerarquía usuario→rol→tenant→negar, mismo patrón que `apps.approvals.get_effective_policy`)
- [x] audit log — `apps.audit.AuditLog` + búsqueda federada (`search_audit_events`, UNION SQL sobre 9 orígenes)
- [x] `/api/v1/health/`
- [x] products/categories/inventory endpoints
- [x] API Key por tenant — `ApiKey` (`UniqueConstraint` por tenant, una sola clave activa a la vez)
- [x] regenerate/revoke
- [x] connection test
- [x] status/last test
- [x] read-only — ningún POST/PUT/DELETE en ningún endpoint de `/api/v1/`
- [x] scopes/rate limit
- [x] API docs — `docs/api-inventory.md` (reescrito de especificación a construido)
- [x] A/B API isolation — verificado con dos tenants y dos claves independientes

## Verificación
- [x] `python manage.py check` en verde en cada uno de los 4 commits de código.
- [x] Tests nuevos: 30 (`apps.permissions`) + 27 (`apps.audit`) + 37 (`apps.api`, incluyendo Configuración UI) = 94 tests nuevos.
- [x] Regresión completa ejecutada tras cada commit: 813 → 840 → 877/877 (877 = 783 de FASE 14 + 94 de esta fase), sin fallas reales (los 2 tracebacks impresos —`RuntimeError` mockeado de un test de FASE 7, `PermissionError` de Windows al borrar un adjunto de gasto ya eliminado— son los ya documentados como esperados).
- [x] Seguridad revisada: tenant SIEMPRE resuelto desde la credencial (membresía de sesión para roles, hash de la API Key para `/api/v1/`), nunca de un parámetro enviado por el cliente; secretos (API Key) nunca en texto plano; contraseñas nunca auditadas (login fallido redacta `credentials` explícitamente).
- [x] Documentación: `docs/roles-permissions.md`/`docs/audit.md` (nuevos), `docs/api-inventory.md` (reescrito), `CLAUDE.md`/`docs/MASTER-PROMPT.md`/`ARCHITECTURE.md`/`FASES_OFICIALES_0_24_ACTUALIZADAS.md` actualizados.
- [x] `docs/project-status/CURRENT_PHASE.md`/`PHASE_HISTORY.md`/`KNOWN_ISSUES.md`/`DECISIONS.md` actualizados.
- [x] Git: 5 commits de dominio (Roles+Permisos, Auditoría, API de Inventario backend, Configuración UI, cierre de documentación).

## Alcance deliberadamente NO exhaustivo (documentado, no una brecha)

Retrofit de `require_permission` limitado a las superficies de mayor
riesgo (datos sensibles de RRHH/Nómina, operaciones contables post/
reverse/close/reopen, operaciones de caja, Auditoría, Configuración,
más Clientes/Proveedores como dominio CRUD representativo) — el resto
de las vistas del proyecto sigue protegido por
`require_tenant`/`require_role` (binario OWNER/MEMBER, nunca
retirado), un rollout deliberado por fases. Auditoría de acceso a
`/api/v1/` no registra cada request individual todavía (alto volumen
esperado, bajo valor por evento) — solo el ciclo de vida de la clave.
OpenAPI/Swagger no se agregó (la propia especificación lo condicionaba
a una dependencia nueva aprobada, que no se pidió). Ambos documentados
en `docs/roles-permissions.md`/`docs/api-inventory.md`.

## Nota de FASE 8 — Interfaz de Inventario Serializado a consumir

La API de Inventario (`/api/v1/...`, ver también `CLAUDE.md`) debe
exponer el inventario serializado agregado en FASE 8 respetando el
mismo principio READ-ONLY y de aislamiento por API Key/tenant definido
para el resto de la API:

- `GET /api/v1/products/{id}/` debe incluir `inventory_tracking_type`.
- Un scope/endpoint adicional (p. ej. `GET /api/v1/inventory/units/` o
  bajo `/api/v1/products/{id}/units/`) debe exponer las `InventoryUnit`
  del producto, filtradas siempre por el tenant dueño de la API Key —
  nunca por un `tenant_id` recibido en la petición.
- Nunca exponer el IMEI/serie completo si el scope de la API Key no lo
  requiere explícitamente; cuando se exponga (p. ej. para que un CRM IA
  pueda buscar por IMEI), debe ser una decisión de scope explícita, no
  el comportamiento por defecto — mismo principio de seguridad ya
  aplicado en `apps/inventory/services.py` (nunca exponer el
  identificador completo innecesariamente en logs o errores).
- Reutilizar `services.search_catalog`/`services.get_current_stock` como
  la fuente de datos de estos endpoints, no reimplementar las consultas.

> **Construido**: `GET /api/v1/inventory/serialized/` (no
> `/products/{id}/units/` — nombre final decidido durante la
> construcción, documentado en `docs/api-inventory.md`), enmascara
> `serial`/`imei_1`/`imei_2` por defecto vía `apps.core.utils.mask_secret`;
> no existe todavía un scope que permita verlos completos. Reutiliza
> `InventoryUnit.all_objects` filtrado por `request.tenant`
> (resuelto desde la API Key), no `search_catalog` directamente (ese
> servicio prioriza una sola coincidencia exacta, distinto del listado
> paginado que necesita este endpoint).

## Nota de FASE 9 — Clientes/Proveedores: auditoría y permisos futuros

FASE 9 agregó una bitácora **mínima y acotada** a su propio módulo
(`apps.customers.models.ActivityLog`, ver `docs/customers.md`) —
explícitamente NO es el sistema de auditoría transversal que esta fase
debe construir para todo el proyecto. Al implementar el audit log real
de FASE 15:

- Evaluar si `ActivityLog` de `apps.customers` se generaliza/reemplaza
  por el sistema transversal, o si se deja como una bitácora
  especializada que además alimenta al audit log global — decisión de
  diseño de esta fase, no anticipada aquí.
- No exponer datos de clientes/proveedores (incluyendo sus documentos)
  sin permisos explícitos: los roles/permisos de esta fase deben poder
  restringir el acceso a Clientes/Proveedores igual que a cualquier
  otro módulo de negocio.
- Si la API de Inventario se extiende para exponer datos de
  clientes/proveedores en el futuro, debe preparar scopes propios
  (`customers:read`, `suppliers:read`, etc.), nunca reutilizar los
  scopes de inventario para datos de un módulo distinto.

> **Construido**: `ActivityLog` de `apps.customers` se dejó como
> bitácora especializada (decisión tomada) y se **federó** —
> `apps.audit.services.search_audit_events` la incluye como uno de
> los 9 orígenes de la búsqueda transversal vía `UNION` SQL, sin
> reemplazarla ni duplicarla. Clientes/Proveedores es además el
> dominio CRUD representativo elegido para probar el retrofit de
> `apps.permissions` de punta a punta (`customers.*`/`suppliers.*`).

## Nota de FASE 10 — Ventas: auditoría y scopes futuros

FASE 10 agregó otra bitácora **mínima y acotada a su propio módulo**
(`apps.sales.models.SalesActivityLog`, ver `docs/sales.md`) — mismo
patrón que `apps.customers.models.ActivityLog` (FASE 9), explícitamente
NO el audit log transversal que esta fase debe construir. Al
implementarlo:

- Evaluar igual que con `apps.customers.models.ActivityLog` si
  `SalesActivityLog` se generaliza/reemplaza o se deja como bitácora
  especializada que alimenta al audit log global.
- No exponer datos de Cotizaciones/Proformas/Ventas/Pagos sin permisos
  explícitos.
- Si la futura API expone datos de ventas, preparar scopes propios
  (`sales:read`, `quotations:read`, ver el punto 40 del mensaje de
  autorización de FASE 10), nunca reutilizar los scopes de inventario.
- Los "permisos por rol para descuentos altos" (mencionados
  explícitamente en el alcance de FASE 10, no implementados allí — ver
  `docs/sales.md`) son responsabilidad de esta fase: decidir el umbral
  y qué rol puede autorizar un descuento por encima de él.

> **Construido**: `SalesActivityLog` se dejó como bitácora
> especializada y federada (mismo tratamiento que `apps.customers`).
> "Permisos por rol para descuentos altos" **no** se retomó en esta
> fase — sigue siendo `ApprovalPolicy` (FASE 11), un sistema distinto
> y deliberadamente separado (umbral de aprobación, no permiso de
> acción); ambos coexisten, ver `docs/roles-permissions.md` sección 1.
> Ningún scope de ventas se agregó a la API — sigue siendo
> exclusivamente Inventario, tal como exigía la especificación.

## Nota de sincronización — Recursos financieros y de caja para Audit/API

Cuando esta fase construya el audit log transversal y extienda la API,
debe contemplar explícitamente (todos estos modelos ya están
construidos y en producción desde FASE 10/11 — esta fase decide cómo
exponerlos/auditarlos, no si construirlos):

- **`Payment`/`PaymentAllocation`** (FASE 10, `apps.sales`) como
  entidades auditables/expuestas bajo su propio scope
  (`payments:read`), nunca mezcladas con `inventory:read`.
- **`CreditNote`/`CreditNoteApplication`** (FASE 11, `apps.sales`, ver
  `docs/accounts-receivable.md`) bajo un scope propio.
- **`ApprovalPolicy`/`ApprovalRequest`** (FASE 11, `apps.approvals`,
  ver `docs/approvals.md`) — el historial de aprobaciones es
  información sensible; exponerlo por API (si alguna vez se decide)
  requiere su propio scope explícito, nunca heredado de otro módulo.
- **`CashRegister`/`CashSession`/`CashMovement`** (FASE 11, `apps.pos`,
  ver `docs/cash-registers.md`) — igual que arriba, un scope propio si
  se decide exponerlos.
- La futura API **solo podrá exponer recursos financieros mediante
  scopes explícitos** — nunca por defecto, nunca reutilizando el scope
  de otro dominio (mismo principio ya aplicado a `customers:read`/
  `suppliers:read`/`sales:read` en las notas de FASE 9/10 de este
  documento).
- Extender el modelo de roles (`Membership.Role`, FASE 3, y
  `ApprovalPolicy`, FASE 11) con las políticas de autorización por
  rol/usuario más ricas que un RBAC completo necesitaría — FASE 11 ya
  construyó una versión mínima funcional (`ApprovalPolicy` por
  usuario/rol/tenant); esta fase es responsable de generalizarla si el
  proyecto necesita roles más allá de OWNER/MEMBER.

> **Construido**: ningún scope financiero se agregó — regla permanente
> confirmada, no relajada. `apps.permissions` generaliza el modelo de
> roles (5 roles no-OWNER nuevos); `ApprovalPolicy` no se tocó, sigue
> siendo el sistema de umbrales de aprobación, ahora explícitamente
> documentado como distinto de los permisos de acción de
> `apps.permissions` (`docs/roles-permissions.md` sección 1).

## Nota de sincronización — Moneda, caja y denominaciones (Audit/API)

Doctrina oficial agregada en `docs/currency.md`: cuando esta fase
extienda el audit log transversal y la API, `Currency`/
`CurrencyDenomination`/`CurrencyConfiguration`/`CashClosing`/
`CashDenominationCount` (especificación, no construidos) deben seguir
el mismo principio ya aplicado a `Payment`/`CashRegister` en este
documento: entidades auditables/expuestas bajo su propio scope, nunca
por defecto ni heredando el scope de otro dominio. No exponer
configuraciones sensibles de moneda/caja sin scopes explícitos.

## Nota de sincronización — Roles granulares para información sensible de RRHH (FASE 13, ya construido)

`apps.hr` (FASE 13) introdujo una distinción de acceso a información
sensible (salario, datos bancarios de `Employee`) mediante
`services.can_view_sensitive_employee_data` — hoy, con solo dos roles
en el sistema (`Membership.Role.OWNER`/`MEMBER`), la única regla
posible es "solo el propietario". Esta fase (Roles granulares) es el
lugar diseñado explícitamente para introducir un permiso dedicado
(ej. "puede ver información salarial") sin romper esa función — nunca
reemplazar `can_view_sensitive_employee_data` por una lógica paralela,
generalizarla para consultar el nuevo sistema de permisos. La regla
de auditoría ya construida (`HRActivityLog.SENSITIVE_DATA_VIEWED`, que
registra cada lectura sensible) debe seguir aplicándose sin cambios.

> **Construido exactamente como se anticipó**:
> `can_view_sensitive_employee_data` ahora delega en
> `has_permission(tenant, user, "hr.sensitive.view")` — el propietario
> sigue autorizado incondicionalmente, `HRActivityLog.SENSITIVE_DATA_VIEWED`
> no se tocó. El mismo patrón se replicó para Nómina
> (`can_view_sensitive_payroll_data`, permiso `payroll.sensitive.view`,
> nuevo `PayrollActivityLog.SENSITIVE_DATA_VIEWED` — y además
> replicado en `apps.audit` por ser una lectura sensible de alto
> valor, a diferencia de RRHH que ya tenía su propia bitácora antes de
> que `apps.audit` existiera).

## Nota de sincronización — Contabilidad General y Reportes (FASE 14, ya construidos)

`apps.accounting`/`apps.reports` (FASE 14) ya están construidos y en
producción — esta fase (Roles granulares + Audit + API de Inventario)
debe respetarlos, nunca duplicarlos:

- **Roles granulares y contabilidad**: `Account`/`AccountingPeriod`/
  `JournalEntry` no tienen hoy un permiso dedicado más allá de
  OWNER/MEMBER (misma limitación que RRHH sensible, ver la nota
  anterior) — el permiso "puede contabilizar"/"puede cerrar un
  período"/"puede reabrir un período" es candidato natural para el
  sistema de permisos granulares de esta fase, generalizando las
  vistas de `apps.accounting` sin reemplazar la lógica de servicio ya
  construida (`open_period`/`close_period`/`reopen_period`/
  `post_journal_entry`).
- **Audit transversal**: `AccountingActivityLog` (FASE 14) ya sigue el
  mismo patrón que `HRActivityLog`/`SalesActivityLog`/etc. — esta fase
  debe integrarlo al audit log transversal sin crear un segundo
  registro de auditoría paralelo.
- **API de Inventario**: `apps.accounting`/`apps.reports` no exponen
  ni deben exponer endpoints en `/api/v1/` — esa API sigue siendo
  exclusivamente de Inventario (scopes `inventory:read`/
  `products:read`/`categories:read`), nunca ampliada a cifras
  financieras/contables sin una decisión explícita y un scope nuevo
  dedicado.

**Actualización (ampliación de cierre de FASE 14)**: además de
`Account`/`AccountingPeriod`/`JournalEntry`, esta fase hereda
candidatos de permiso granular equivalentes para `TaxCode`
(configuración de impuestos, hoy solo el propietario puede crearlos)
y para las nuevas integraciones de Compras/AP/Cierre de caja
(`AccountingActivityLog` ya registra sus fallos de contabilización
bajo el mismo patrón, sin necesitar un segundo tipo de auditoría).

> **Construido**: `accounting.post`/`accounting.reverse`/
> `accounting.close_period`/`accounting.reopen_period` conectados a
> `JournalEntryCreateView`/`JournalEntryReverseView`/
> `AccountingPeriodCloseView`/`AccountingPeriodReopenView`.
> `AccountingActivityLog` se federó en `apps.audit` (uno de los 9
> orígenes), sin segundo registro de auditoría. `TaxCode` y las
> integraciones de Compras/AP/Cierre de caja **no** recibieron un
> permiso granular dedicado en esta fase (fuera del Tier 1 acordado,
> documentado como trabajo incremental futuro en
> `docs/roles-permissions.md` sección 9) — siguen protegidas por
> `require_tenant`/`require_role` binario, sin brecha de seguridad.
> Ningún endpoint de `/api/v1/` expone datos contables/financieros.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
Fase cerrada con evidencia (94 tests nuevos, regresión completa 877/877, `manage.py check` limpio en los 4 commits de código, documentación sincronizada). No se avanza a FASE 16 — se detiene aquí, a la espera de autorización explícita del usuario, tal como exigía la instrucción de inicio de esta fase.
