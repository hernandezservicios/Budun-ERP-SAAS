# Recursos Humanos (FASE 13)

`apps/hr` es el dominio de Recursos Humanos — separado de Gastos
(`apps.expenses`) y Nómina (`apps.payroll`), aunque `apps.payroll`
consume `Employee` como referencia (salario base, moneda) sin
duplicarlo. Reutiliza literalmente `apps.customers.models.IdentificationType`
(mismo catálogo que Clientes/Proveedores), `DocumentoBaseMixin`/
`DocumentCategory`/`EXTENSIONES_DOCUMENTO_PERMITIDAS` (FASE 9) y
`apps.approvals.services` (autorización de ausencias) — nunca un
segundo sistema de identificación, archivos o aprobaciones.

## 1. Entidades

`Department`, `Position` (tenant-scoped, únicos por nombre),
`Employee` (empleado), `EmploymentContract` (contrato laboral),
`EmployeeDocument` (adjuntos), `WorkSchedule` (horario), `Attendance`
(asistencia diaria), `LeaveType`/`Leave` (tipos de ausencia y
solicitudes), `Incident` (incidentes), `HRActivityLog` (auditoría).

## 2. `Employee` — estados

```
ACTIVE ──┬──> ON_LEAVE ──> ACTIVE / TERMINATED
         ├──> SUSPENDED ──> ACTIVE / TERMINATED
         ├──> INACTIVE ──> ACTIVE / TERMINATED
         └──> TERMINATED (terminal)
```

`TERMINATED` es terminal (no hay reingreso automático — un reingreso
real es un empleado nuevo, con su propio historial). Pasar a
`TERMINATED` fija `termination_date` automáticamente si no se indicó.

## 3. Contratos laborales

Un empleado nunca tiene dos contratos `ACTIVE` a la vez
(`UniqueConstraint` parcial `unique_active_contract_per_employee`,
traducida a `InvalidHROperation` — nunca un `IntegrityError` de
PostgreSQL sin traducir, mismo patrón que la exclusividad de
`CashSession` por usuario en FASE 11). Terminar el contrato activo
libera el camino para crear uno nuevo.

## 4. Asistencia

`Attendance` es una fila por (tenant, empleado, fecha) — la entrada
crea la fila, la salida la actualiza (nunca dos filas por el mismo
día, `UniqueConstraint`). `late_minutes` se calcula contra
`WorkSchedule.start_time` si se indica un horario; `worked_hours` se
calcula al registrar la salida, descontando `break_minutes` del
horario. Preparado conceptualmente para integraciones futuras de
biometría/reloj (`Attendance.Source.SYSTEM`), **no implementadas**
todavía — hoy todo registro es manual (`Source.MANUAL`).

## 5. Ausencias/Vacaciones — autorización

A diferencia de Gastos (`apps.expenses`, que gatea por MONTO),
aprobar/rechazar una ausencia es puramente una cuestión de AUTORIDAD —
mismo permiso que resolver cualquier `ApprovalRequest`
(`can_user_approve`, ver `apps.approvals.services`), sin una dimensión
de umbral configurable. `LeaveType.requires_approval` decide el
flujo:

- **Requiere autorización** (la mayoría): `request_leave` crea la
  `Leave` en `REQUESTED` y una `ApprovalRequest` (`LEAVE_REQUEST`);
  `approve_leave`/`reject_leave` exigen `can_user_approve` y resuelven
  esa solicitud junto con el estado de la ausencia.
- **No requiere autorización** (ej. un tipo informal): `request_leave`
  la deja `APPROVED` de inmediato, sin crear ninguna `ApprovalRequest`.

`LeaveType` es tenant-configurable — `create_default_leave_types`
sugiere Vacaciones/Permiso/Enfermedad/Otro bajo demanda (mismo patrón
que `ExpenseCategory`), nunca una lista cerrada en código.

## 6. Incidentes

`Incident` (tipo/severidad/estado) es un registro simple con
resolución de texto libre — sin máquina de estados compleja
(`OPEN → IN_REVIEW → RESOLVED → CLOSED`, transición libre, cualquier
cambio se audita).

## 7. Documentos de empleado

Reutiliza literalmente `DocumentoBaseMixin`/`DocumentCategory` de
FASE 9 — las categorías ya cubren exactamente lo pedido
(identificación/documento fiscal/contrato/certificado/comprobante/
documento bancario/otro), sin necesidad de un catálogo nuevo.

## 8. Auditoría y Privacidad — información sensible

RRHH contiene información sensible (`Employee.base_salary`,
`bank_name`, `bank_account_number`). Regla permanente:
**nunca se restringe ocultando elementos de la UI únicamente**.

- `services.can_view_sensitive_employee_data(tenant, user)` es la
  única fuente de verdad. Hoy, con solo dos roles en el sistema
  (`Membership.Role.OWNER`/`MEMBER`, ver FASE 3), la única distinción
  real posible es "es el propietario del tenant" — un `MEMBER`
  (ej. un cajero) nunca ve salario/datos bancarios solo por pertenecer
  al tenant. FASE 15 (Roles granulares) podrá introducir un permiso
  dedicado sin romper este diseño.
- La vista (`EmployeeDetailView`) arma el formulario de edición
  **solo** si el usuario puede ver datos sensibles — un `MEMBER` ni
  siquiera recibe ese formulario en el HTML. La vista de guardado
  (`EmployeeEditView`) repite la misma verificación en el servidor
  (`PermissionDenied` si no corresponde) — nunca confía únicamente en
  que la plantilla no mostró el botón.
- Cada lectura de datos sensibles por el propietario se audita
  explícitamente (`HRActivityLog.Action.SENSITIVE_DATA_VIEWED`).

## 9. Multi-Tenancy y Seguridad

Todo modelo hereda `TenantScopedModel`; todo servicio filtra `tenant`
explícitamente y usa `all_objects`. Departamento/cargo/supervisor de
otro tenant se rechazan explícitamente en `create_employee`. Vistas
usan `get_object_or_404(..., tenant=request.tenant)` — un ID de otro
tenant siempre 404.

## 10. Qué NO se construyó en esta fase (deliberado)

- **Integraciones de biometría/reloj**: `Attendance.Source.SYSTEM`
  preparado conceptualmente, sin ninguna integración real.
- **Legislación laboral específica de un país**: `EmploymentContract`
  no hardcodea reglas fiscales/laborales de ningún país — eso
  corresponde a `apps.payroll` cuando exista una definición normativa
  válida, nunca inventada.
- **Permisos granulares por acción** (más allá de OWNER/MEMBER): la
  distinción binaria de datos sensibles es una simplificación
  explícita hasta FASE 15.
- **Jerarquía de departamentos**: `Department` es plano (con
  `manager` opcional), sin sub-departamentos anidados — no se
  encontró un requisito explícito que lo exigiera.
