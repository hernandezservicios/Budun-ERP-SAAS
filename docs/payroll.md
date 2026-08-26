# Nómina (FASE 13)

`apps/payroll` es el dominio de Nómina — consume `apps.hr.Employee`
como referencia (salario base, moneda, departamento, cargo), nunca lo
duplica como una segunda fuente de verdad de "quién es el empleado".
Reutiliza literalmente `apps.sales.models.DocumentSequence`/
`PaymentMethod` (numeración `NOM-000001`, mismo vocabulario de pago),
`apps.pos.services` (caja para pagos en efectivo) y
`apps.approvals.services` (aprobación de período).

## 1. Diseño: `PayrollLine` única, no cuatro tablas

La especificación menciona `PayrollItem`/`PayrollAdjustment`/
`PayrollDeduction`/`PayrollBonus` como entidades conceptuales — se
implementaron como **una sola tabla**, `PayrollLine`, con `category`
(`EARNING`/`DEDUCTION`, determina el signo en el cálculo) + `concept`
(salario base/horas extra/bono/comisión/retención/anticipo/descuento
por ausencia/ajuste/otro). Simplificación deliberada: las cuatro
tablas mencionadas son estructuralmente idénticas (descripción +
monto + tipo); duplicarlas violaría el mismo principio de
no-duplicación ya aplicado repetidas veces en el proyecto (ej.
`CustomerCreditLedger` nunca se construyó como una tercera fuente de
verdad en Cuentas por Cobrar). FASE 14 (Reportes) puede agrupar por
`category`+`concept` para obtener exactamente el desglose bruto/
deducciones/bonos/retenciones/neto pedido, sin necesitar tablas
separadas.

## 2. `PayrollPeriod` — estados

```
DRAFT ──(primer cálculo)──> PROCESSING ──aprobar──> APPROVED ──(todos pagados)──> PAID ──cerrar──> CLOSED
  │                              │
  └──cancelar──────────────────CANCELED (solo antes de aprobar)
```

- `calculate_payroll_for_employee` mueve el período de `DRAFT` a
  `PROCESSING` automáticamente en el primer cálculo.
- `approve_period` exige al menos una nómina calculada y
  `can_user_approve` (ver sección 3).
- El período pasa a `PAID` automáticamente cuando la última nómina de
  empleado pendiente se termina de pagar.
- `close_period` exige que TODAS las nóminas del período estén
  `PAID`/`CANCELED` — nunca se cierra con nóminas pendientes.
- Un período `CLOSED` es inmutable (mismo principio que
  `Return`/`PaymentAllocation` revertida): correcciones posteriores son
  una nueva línea de ajuste en un período NUEVO, nunca una edición del
  período histórico — `add_payroll_line`/`calculate_payroll_for_employee`
  se rechazan explícitamente fuera de `DRAFT`/`PROCESSING`.

## 3. Aprobación de período — autoridad, no monto

Igual que `apps.hr.services.approve_leave` (y a diferencia de
`apps.expenses.approve_expense`, que gatea por MONTO): un período de
nómina agrega a muchos empleados a la vez, así que no existe una
dimensión natural de "monto dentro de mi límite" por período.
`approve_period` gatea puramente por `can_user_approve` (mismo permiso
que resolver cualquier `ApprovalRequest`) y dejar un registro auditable
vía una `ApprovalRequest` (`PAYROLL_APPROVAL`) para el historial.

## 4. `Payroll` — snapshot histórico, nunca recalculado

Cada fila `Payroll` (una por empleado y período, `UniqueConstraint`)
congela `employee_name_snapshot`/`department_snapshot`/
`position_snapshot`/`base_salary_snapshot` en el momento del cálculo —
modificar el salario, departamento o cargo del empleado DESPUÉS nunca
altera una nómina ya calculada (mismo principio que
`apps.sales.SaleItem` snapshotea el producto al agregarse a una
venta). Nunca dos filas de `Payroll` para el mismo (período, empleado)
— ni siquiera bajo dos cálculos concurrentes: `IntegrityError` de la
`UniqueConstraint` se traduce siempre a `InvalidPayrollOperation`
(mismo patrón que `apps.hr.services.create_employment_contract`).

## 5. Pago de nómina — ledger append-only

Mismo principio que `ExpensePayment`/`Payment`: `Payroll` nunca guarda
`paid_amount`/`balance_due`, se calculan siempre agregando sobre
`PayrollPayment`. Reglas:

- Solo se paga una nómina de un período ya `APPROVED`/`PAID`.
- El pago nunca puede exceder el saldo pendiente (`net_total` menos lo
  ya pagado).
- El pago debe compartir la MISMA moneda que la nómina — sin motor de
  FX (ver `docs/currency.md`), se rechaza con un error de negocio claro.
- En efectivo, exige una `CashSession` abierta y genera un
  `CashMovement` propio (`PAYROLL_PAYMENT_CASH`) — otros métodos no
  afectan la caja física; no toda nómina se paga en efectivo.
- Idempotente por `idempotency_key`; anular un pago
  (`void_payroll_payment`) recalcula el estado de la nómina (y, si
  corresponde, revierte el período de `PAID` de vuelta — no
  implementado explícitamente: anular un pago de un período ya
  cerrado no está permitido porque cerrar exige todo pagado primero,
  así que esta secuencia solo puede darse en un período `PAID`
  todavía no `CLOSED`, y el estado del período no se revierte
  automáticamente en ese caso — queda como una operación manual
  documentada, no automática).

## 6. Moneda (ver `docs/currency.md`)

`PayrollPeriod.currency`/`Payroll.currency`/`PayrollPayment.currency`
son snapshots de texto simple, sin catálogo real todavía — mismo
criterio que el resto del proyecto. Sin motor de FX, nunca se mezcla
ni se convierte automáticamente.

## 7. Auditoría

`PayrollActivityLog` (mínima, acotada a este módulo) registra creación
de período, cálculo de cada nómina, aprobación/cierre/cancelación del
período, y pagos/anulaciones.

## 8. Multi-Tenancy y Seguridad

Todo modelo hereda `TenantScopedModel`; todo servicio filtra `tenant`
explícitamente y usa `all_objects`. Empleado/período de otro tenant se
rechazan explícitamente en `calculate_payroll_for_employee`. Vistas
usan `get_object_or_404(..., tenant=request.tenant)`.

## 9. Concurrencia

"Dos procesos de nómina" (dos cálculos simultáneos para el mismo
empleado en el mismo período): la `UniqueConstraint`
`unique_payroll_tenant_periodo_empleado` + el `IntegrityError`
traducido garantiza que exactamente uno gana, nunca dos filas
duplicadas — mismo mecanismo, sin necesidad de un `select_for_update`
adicional sobre una fila que todavía no existe.

## 10. Qué NO se construyó en esta fase (deliberado)

- **Reglas fiscales/laborales de un país específico**: ningún cálculo
  de impuesto/retención legal real se hardcodea — `PayrollLine` con
  `concept=TAX_WITHHOLDING` queda preparado para que el usuario indique
  el monto exacto según su propia normativa, nunca inventado por el
  sistema.
- **Recibo de nómina descargable / exportable**: preparación de datos
  completa (toda la información necesaria vive en
  `Payroll`/`PayrollLine`/`PayrollPayment`), sin una vista de
  impresión dedicada todavía — mismo patrón que otros documentos
  imprimibles de fases anteriores, puede agregarse sin cambiar el
  modelo de datos.
- **Asientos contables**: preparación para FASE 14 (ninguna
  Contabilidad general existe todavía).
- **Cálculo automático de horas extra desde `Attendance`**: la
  integración conceptual existe (`apps.hr.Attendance.worked_hours`),
  pero `calculate_payroll_for_employee` no la agrega automáticamente
  como línea de horas extra — hoy se agrega manualmente vía
  `add_payroll_line`/`PayrollLineForm`, evitando inventar una regla de
  "cuántas horas cuentan como extra" sin una definición explícita del
  usuario.
