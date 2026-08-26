# FASE 13 — Expenses + Human Resources + Payroll

## Objetivo (ampliado por el usuario tras aprobar FASE 12 y su corrección funcional)

La especificación original de esta fase cubría solo Gastos. El usuario
amplió el alcance explícitamente antes de iniciarla a tres dominios
relacionados pero separados: **Expenses** (`apps.expenses`), **Human
Resources** (`apps.hr`) y **Payroll** (`apps.payroll`) — "No construir
un CRUD básico", manteniendo Design System, `ApprovalService`,
`CashRegister`/`CashSession`, doctrina de Moneda, sistema seguro de
documentos y auditoría ya construidos, sin duplicar ninguno. No se
implementa Contabilidad general (FASE 14) todavía.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación

### Expenses (`apps.expenses`) — CONSTRUIDO
- [x] `ExpenseCategory` tenant-configurable (nunca una lista cerrada en código; sugeridas bajo demanda)
- [x] `Expense`: categoría, proveedor opcional, monto/impuesto/descuento/total, método previsto, fecha, vencimiento, moneda, estado, documentos adjuntos — tenant-scoped
- [x] Máquina de estados: `DRAFT → PENDING_APPROVAL → APPROVED → PARTIALLY_PAID/PAID`, `REJECTED`, `CANCELED`
- [x] Autorización de gasto sobre el límite (`ApprovalPolicy.max_expense_amount`) y gasto excepcional (`Expense.is_exceptional`), reutilizando `apps.approvals` — nunca lógica de autorización duplicada
- [x] `ExpensePayment` (ledger append-only): en efectivo exige `CashSession` abierta y genera `CashMovement` (`EXPENSE_PAYMENT_CASH`); otros métodos no afectan el efectivo físico; rechaza moneda distinta a la del gasto
- [x] `ExpenseRecurrence`: generación idempotente por diseño (nunca duplica un gasto del mismo período, incluso bajo concurrencia)
- [x] Documentos adjuntos reutilizando literalmente FASE 9

### Human Resources (`apps.hr`) — CONSTRUIDO
- [x] `Department`/`Position` tenant-configurables
- [x] `Employee`: máquina de estados `ACTIVE/INACTIVE/ON_LEAVE/SUSPENDED/TERMINATED` (terminal)
- [x] `EmploymentContract`: nunca dos contratos `ACTIVE` a la vez por empleado
- [x] `EmployeeDocument` reutilizando literalmente FASE 9 (categorías ya cubren identificación/contrato/certificado/comprobante/documento bancario/otro)
- [x] `WorkSchedule`/`Attendance`: entrada/salida, retraso y horas trabajadas calculados contra el horario
- [x] `LeaveType` (tenant-configurable)/`Leave`: solicitud/aprobación/rechazo reutilizando `apps.approvals` (autoridad, no monto)
- [x] `Incident`: tipo/severidad/estado/resolución
- [x] Información sensible (salario, datos bancarios): nunca restringida solo en la UI — gateada y auditada en el servidor (`can_view_sensitive_employee_data`, `HRActivityLog.SENSITIVE_DATA_VIEWED`)

### Payroll (`apps.payroll`) — CONSTRUIDO
- [x] `PayrollPeriod`: `DRAFT → PROCESSING → APPROVED → PAID → CLOSED`, `CANCELED`
- [x] `Payroll` (snapshot histórico por empleado y período — nunca recalculado si el empleado cambia después)
- [x] `PayrollLine` única con `category`/`concept` (simplificación deliberada y documentada, ver `docs/payroll.md` sección 1, en vez de 4 tablas casi idénticas)
- [x] Aprobación de período por autoridad (`can_user_approve`), no por monto — distinto del criterio de Gastos, documentado el porqué
- [x] `PayrollPayment` (ledger append-only): en efectivo exige `CashSession` abierta y genera `CashMovement` (`PAYROLL_PAYMENT_CASH`); rechaza moneda distinta; período pasa a `PAID` automáticamente cuando todas las nóminas quedan pagadas; `close_period` exige todo pagado/cancelado

### Transversal
- [x] Multi-Tenant verificado exhaustivamente en los tres dominios (IDs manipulados → 404, aislamiento de categorías/empleados/períodos)
- [x] Concurrencia por diseño: recurrencia de gastos (select_for_update sobre la propia fila), contrato activo único, nómina única por (período, empleado) — todos vía `IntegrityError` traducido o lock, nunca una condición de carrera silenciosa

## Verificación
- [x] `python manage.py check` en verde en cada commit
- [x] Tests: 46 (`apps.expenses`) + 42 (`apps.hr`) + tests de `apps.payroll` (ver `docs/project-status/PHASE_HISTORY.md` para el conteo final) — servicios, HTTP, Multi-Tenant, seguridad, concurrencia por diseño
- [ ] Smoke test HTTP dedicado a Gastos/RRHH/Nómina contra PostgreSQL de desarrollo — pendiente antes del cierre
- [x] Seguridad revisada: información sensible de RRHH nunca expuesta solo por ocultarla en la plantilla (ver `docs/hr.md` sección 8)
- [x] Documentación: `docs/expenses.md`, `docs/hr.md`, `docs/payroll.md` (nuevos)
- [ ] `docs/project-status/CURRENT_PHASE.md`/`PHASE_HISTORY.md`/`KNOWN_ISSUES.md`/`DECISIONS.md` — pendientes antes del cierre
- [ ] Regresión completa de FASE 3–12 sin cambios de lógica — pendiente antes del cierre
- [ ] Git commit final de cierre (los tres dominios ya tienen su propio commit: ver `PHASE_HISTORY.md`)

## Nota de FASE 8 — Inventario Serializado (revisado, sin cambios de diseño necesarios)

Gastos/RRHH/Nómina no consumen `InventoryUnit` — ningún gasto, empleado
ni nómina representa una unidad de inventario. Se documenta aquí solo
para dejar constancia de que se revisó.

## Nota de FASE 9 — Documentos y Proveedores (ya consumidos)

`Expense.supplier` reutiliza literalmente `apps.customers.models.Supplier`;
`ExpenseDocument`/`EmployeeDocument` reutilizan literalmente
`DocumentoBaseMixin`/`DocumentCategory`/`EXTENSIONES_DOCUMENTO_PERMITIDAS`
— las categorías de `DocumentCategory` (identificación/documento
fiscal/contrato/certificado/comprobante/documento bancario/otro) ya
cubrían exactamente lo pedido para documentos de empleado, sin
necesitar un catálogo nuevo.

## Nota de sincronización — Caja y Autorizaciones (FASE 11, ya consumidas)

Los tres dominios reutilizan literalmente `apps.pos.services`
(`ensure_open_session_for_checkout`/`record_cash_movement`, dos tipos
de `CashMovement` nuevos: `EXPENSE_PAYMENT_CASH`/`PAYROLL_PAYMENT_CASH`)
y `apps.approvals.services` (cuatro `ActionType` nuevos:
`EXPENSE_OVER_THRESHOLD`/`EXPENSE_EXCEPTIONAL`/`LEAVE_REQUEST`/
`PAYROLL_APPROVAL`; un campo nuevo en `ApprovalPolicy`:
`max_expense_amount`) — nunca una segunda lógica de caja o
autorización. Documentado el criterio de cuándo gatear por MONTO
(Gastos, como Compras/POS) vs. por AUTORIDAD pura (Ausencias/Nómina,
como resolver una `ApprovalRequest`) en `docs/hr.md`/`docs/payroll.md`.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
