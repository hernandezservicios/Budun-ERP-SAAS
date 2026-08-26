# Auditoría transversal (`apps.audit`)

> **Estado: CONSTRUIDO en FASE 15** (commit "Auditoría transversal").
> Complementa — nunca reemplaza — los 7 registros de actividad por
> dominio ya existentes desde fases anteriores.

## 1. Principio central: complementa, no reemplaza

Antes de este commit ya existían 7 modelos `*ActivityLog`
(`SalesActivityLog`, `ActivityLog` de `apps.customers`,
`AccountingActivityLog`, `ExpensesActivityLog`, `HRActivityLog`,
`PayrollActivityLog`, `PurchasesActivityLog`), todos con la misma
forma común (`entity_type`/`entity_id`/`entity_label`/`action`/`user`/
`details`/`created_at` + `tenant` heredado) — varios llevan un
docstring explícito diciendo "NO es el sistema de auditoría
transversal de FASE 15". Ese comentario anticipaba exactamente este
commit: en vez de copiar/migrar esos 7 registros a una tabla nueva
(que perdería su función operativa dentro de cada módulo, donde cada
pantalla de detalle ya lee su propio log), se los **federa**.

`AuditLog` (nuevo, `apps.audit`) es el 8º origen, y captura
específicamente lo que ningún log por-dominio puede: eventos que no
pertenecen a un solo módulo de negocio (login/logout/login fallido,
cambios de permisos/roles, acceso a la API de Inventario, y lecturas
sensibles nuevas que no tenían dónde vivir). `StockMovement`
(`apps.inventory`) se suma como 9º origen de solo lectura (los
movimientos de inventario ya son, por diseño, un libro mayor
append-only — la auditoría solo los expone en la búsqueda federada,
nunca los duplica).

## 2. `AuditLog`

`tenant` es **nulable** — a diferencia de `TenantScopedModel` (donde
toda entidad de negocio pertenece siempre a exactamente un tenant), un
login fallido con un email que no pertenece a ningún tenant (o que ni
siquiera existe como usuario) no tiene tenant que asignarle. Mismo
principio que `apps.tenants.Membership` (tampoco hereda
`TenantScopedModel`, por una razón relacionada: es el modelo que se
usa para *determinar* el tenant).

Campos: `user` (nulable, `SET_NULL`), `action` (`TextChoices`:
`LOGIN`/`LOGOUT`/`LOGIN_FAILED`/`PERMISSION_CHANGED`/`ROLE_CHANGED`/
`API_KEY_CREATED`/`ROTATED`/`REVOKED`/`API_ACCESS`/
`SENSITIVE_DATA_VIEWED`/`EXPORT_PERFORMED`/`GENERIC`), `domain` (texto
libre: `"auth"`/`"permissions"`/`"payroll"`/`"reports"`/`"api"`/...),
`object_type`/`object_id` (texto, para admitir tanto IDs numéricos
como identificadores compuestos — p. ej. `"rol:employee"`),
`request_id`, `ip_address`, `user_agent`, `before`/`after` (JSON,
**nunca contraseñas/tokens/claves de API completas**), `reason`,
`metadata` (JSON), `created_at`.

**Inmutable**: `services.py` no define ninguna función de
actualización o borrado — una corrección es un evento nuevo, nunca
una edición del histórico (mismo principio que
`reverse_journal_entry`). El admin (`AuditLogAdmin`, patrón
`_ReadOnlyAdmin` ya usado en `apps.accounting`/`apps.hr`/
`apps.payroll`) bloquea alta y edición.

## 3. Escritura (`services.log_event`)

Única vía sancionada para crear un evento — nunca
`AuditLog.objects.create(...)` directo desde otro módulo.
`log_event_from_request(request, ...)` deriva IP/user agent/tenant/
usuario de una request HTTP real cuando estén disponibles.

Toda integración automática sigue el mismo patrón resiliente que
`apps.accounting`'s `try_record_*`: la auditoría **nunca** debe poder
romper la operación que audita. Conectado hoy:

- **Señales de autenticación** (`apps/audit/signals.py`, conectadas en
  `apps.py.ready()`): `user_logged_in`/`user_logged_out`/
  `user_login_failed` de Django, envueltas en `try/except` completo.
  El tenant de un login se resuelve de nuevo en el propio handler
  (`_resolver_tenant_para_login`) porque `TenantMiddleware` ya corrió
  ANTES de que la vista autenticara al usuario (usando el
  `AnonymousUser` de esa misma request) — `request.tenant` está
  siempre vacío en el momento exacto de este evento, tanto en
  producción como en tests. Un login fallido jamás guarda la
  contraseña (`_credenciales_seguras` descarta cualquier clave de
  `credentials` que contenga "pass"/"secret"/"token"/"clave", ya que
  Django no garantiza que ese diccionario venga redactado).
- **Cambios de permisos** (`apps.permissions.services.
  _audit_permission_change`, ya conectado desde el commit anterior vía
  import diferido — este commit solo lo activa al existir `apps.audit`
  de verdad).
- **Lecturas sensibles de nómina** (`apps.payroll.services.
  log_sensitive_payroll_access`): además de su registro operativo ya
  existente en `PayrollActivityLog` (que las pantallas de nómina siguen
  leyendo sin cambios), replica el evento aquí — es exactamente el
  tipo de lectura sensible de alto valor para el que existe la
  auditoría transversal. `HRActivityLog.SENSITIVE_DATA_VIEWED` (FASE
  13) **no se toca ni se duplica** — sigue siendo la única fuente para
  RRHH, tal como pedía la especificación.
- **Exportación de reportes** (`apps.reports.views._audit_export`):
  cada exportación CSV/PDF/XLSX de Ventas/Cuentas por Cobrar/Cuentas
  por Pagar/Gastos/Estados de Cuenta registra `EXPORT_PERFORMED`
  (dominio `"reports"`, metadata con el formato).
- **Exportación de la propia auditoría** (`apps.audit.views.
  AuditExportView`): se audita a sí misma.

Pendiente de conectar (documentado, no bloqueante para el cierre de
este commit): eventos de aprobación (`apps.approvals`), reversos/
reembolsos de ventas, movimientos/apertura/cierre de caja como
eventos de auditoría transversal explícitos (hoy ya se ven vía el
9º origen `StockMovement`/vía `PayrollActivityLog` según el caso, pero
no como `AuditLog.domain="pos"` dedicado) — extensión futura simple
sobre el mismo `log_event`, sin cambiar el diseño.

## 4. Búsqueda federada (`services.search_audit_events`)

Proyecta cada uno de los 9 orígenes a una forma común (`source`,
`tenant_id`, `row_id`, `domain`, `action`, `object_type`, `object_id`,
`label`, `summary`, `user_id`, `created_at`) vía `.annotate()` +
`.values()`, y los combina con `.union(..., all=True)` de Django (SQL
`UNION ALL` real). Todos los filtros (tenant, fuente, dominio, acción,
usuario, rango de fechas, IP, texto libre) se aplican **por rama antes
de unir** — Django no garantiza que `.filter()` sea fiable sobre el
resultado ya combinado, así que nunca se intenta. Paginación
(`limit`/`offset`) resuelta en la base de datos (`.count()` +
slicing), nunca cargando todo a Python.

`get_event_detail(tenant, source, row_id)` recupera la fila COMPLETA
(todos sus campos originales, no solo la proyección común) desde su
modelo real — usado por la vista de detalle para mostrar antes/después
(solo disponible en eventos `source="audit"`) o los campos propios de
cada log legado.

## 5. UI (`/configuracion/auditoria/`)

- **Búsqueda** (`audit:search`): formulario GET (origen, dominio,
  acción, usuario, rango de fechas, IP, texto libre), tabla paginada
  (50 por página), enlace "Exportar CSV" solo si el usuario tiene
  `audit.export`.
- **Detalle** (`audit:detail`): antes/después completos para eventos
  `AuditLog`; campos propios para eventos de un log legado o de
  inventario.
- **Exportación** (`audit:export`): CSV de hasta 10 000 filas con los
  filtros activos — audita su propia ejecución.

Enlazada desde el hub de Configuración (`core:settings`, junto a
Roles y Permisos).

## 6. Permisos

`audit.view` (buscar/ver detalle), `audit.export` (exportar CSV),
`audit.sensitive.view` (reservado para cuando la búsqueda distinga
eventos sensibles de los operativos — hoy todo evento visible con
`audit.view` ya pasó su propio control de acceso en el módulo de
origen, así que no hay todavía un evento "extra sensible" que ocultar
dentro de la propia auditoría). Solo `OWNER`/`ADMIN`/superusuario
tienen `audit.view`/`audit.export` por defecto (`MANAGER`/`CASHIER`/
`EMPLOYEE` no) — un empleado normal nunca lee la auditoría completa
por defecto, tal como pedía la especificación.

## 7. Aislamiento Multi-Tenant

Cada rama de la búsqueda federada filtra `tenant=` explícitamente
antes de unir. `get_event_detail` también filtra por tenant — un
`row_id` de otro tenant nunca se resuelve (la vista de detalle
responde 404, nunca el contenido).

## 8. Retención

Documentada, no un cron activo todavía (sin infraestructura de tareas
en segundo plano en el proyecto — mismo criterio que reportes
programados en FASE 14): se recomienda una política de N meses según
la regulación aplicable al tenant; implementarla como un comando de
management cuando el proyecto incorpore tareas programadas, nunca
borrando eventos "a mano" desde una vista.
