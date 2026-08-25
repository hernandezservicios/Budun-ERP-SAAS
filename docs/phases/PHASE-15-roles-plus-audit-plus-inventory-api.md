# FASE 15 — Roles + Audit + Inventory API

## Objetivo
Roles/permisos, audit log y API de Inventario para CRM IA. Ver `docs/api-inventory.md` para el resumen arquitectónico de la API.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] roles efectivos en backend
- [ ] audit log
- [ ] /api/v1/health/
- [ ] products/categories/inventory endpoints
- [ ] API Key por tenant
- [ ] regenerate/revoke
- [ ] connection test
- [ ] status/last test
- [ ] read-only
- [ ] scopes/rate limit
- [ ] API docs
- [ ] A/B API isolation

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

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

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
