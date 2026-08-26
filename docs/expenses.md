# Gastos (FASE 13)

`apps/expenses` es el dominio de gastos operativos del tenant —
independiente de Cuentas por Pagar (`apps.purchases`, que cubre lo que
se le debe a un proveedor por mercancía comprada), aunque comparte un
proveedor opcional. Orquesta sobre `apps.customers` (Supplier),
`apps.approvals` (autorización de gasto sobre el límite/excepcional),
`apps.pos` (caja para pagos en efectivo) y `apps.customers.file_validation`
(documentos adjuntos) — nunca un segundo sistema de aprobaciones, caja
o archivos.

## 1. `ExpenseCategory` — configurable por tenant, nunca una lista cerrada

`ExpenseCategory` es una tabla real por tenant, no un `TextChoices` fijo
en código — el usuario puede agregar, desactivar o renombrar categorías
libremente. `services.DEFAULT_EXPENSE_CATEGORIES` (Operación, Servicios,
Alquiler, Electricidad, Internet, Telefonía, Transporte, Mantenimiento,
Marketing, Suministros, Impuestos, Otros) son sugerencias que
`create_default_expense_categories(tenant)` crea bajo demanda (botón
"Crear categorías sugeridas") — nunca automáticamente, nunca duplicando
una que el tenant ya haya creado (comparación case-insensitive).

## 2. `Expense` — máquina de estados

```
DRAFT ──submit──> PENDING_APPROVAL ──approve──> APPROVED ──pago parcial──> PARTIALLY_PAID ──pago completo──> PAID
  │                      │
  │                      └──reject──> REJECTED ──edit (vuelve a DRAFT)──> DRAFT
  │
  └──cancel──> CANCELED (también desde PENDING_APPROVAL/APPROVED, nunca con pagos ya registrados)
```

- Solo se edita en `DRAFT`/`REJECTED` (`update_expense`) — editar un
  `REJECTED` lo regresa a `DRAFT` para reenviarlo, nunca lo dispensa de
  pasar por aprobación de nuevo.
- `total = amount + tax_amount − discount_amount`, recalculado siempre
  en `services.py`, nunca asignado a mano desde un formulario.
- Cada gasto tiene: número (`GAS-000001`, vía la misma `DocumentSequence`
  de Ventas/Compras), categoría, proveedor opcional, descripción, fecha,
  fecha de vencimiento opcional, moneda, monto/impuesto/descuento/total,
  método de pago previsto, estado, usuario, notas — histórico conservado
  siempre (nunca se borra un `Expense`, solo se cancela).

## 3. Autorización — reutiliza `apps.approvals`, dos escenarios

Mismas primitivas reutilizables que ya usan POS y Compras
(`request_approval`/`resolve_approval`/`mark_consumed`/
`get_usable_approved_request`), jerarquía usuario → rol → tenant →
negar, propietario siempre autorizado:

1. **Gasto sobre el límite** (`ApprovalPolicy.max_expense_amount`,
   `ActionType.EXPENSE_OVER_THRESHOLD`): si el total excede lo que este
   usuario puede aprobar por sí mismo, `approve_expense` lanza
   `ExpenseOverThresholdRequiresApproval` — la vista crea la
   `ApprovalRequest` automáticamente y pide reintentar tras la
   aprobación de un supervisor.
2. **Gasto excepcional/sensible** (`Expense.is_exceptional` +
   `exceptional_reason`, `ActionType.EXPENSE_EXCEPTIONAL`): exige
   autorización SIN IMPORTAR EL MONTO — cubre en una sola bandera los
   tres casos que el usuario nombró como "gasto excepcional",
   "cambio sensible" y "pago excepcional" (simplificación deliberada:
   cuatro escenarios nombrados, dos primitivas de autorización reales,
   mismo criterio que Compras cubrió sus 6 escenarios con 2
   `ActionType` nuevos).

"Aprobar"/"rechazar" un gasto es la acción de negocio en sí (como
"enviar" una orden de compra o "confirmar" una venta en POS) —
cualquier miembro del tenant puede intentarla; el servicio decide según
el límite propio de ESE usuario. Resolver la `ApprovalRequest`
resultante es una acción DISTINTA, gestionada íntegramente por
`apps.approvals` (permiso `can_user_approve`, ya existente).

## 4. `ExpensePayment` — ledger append-only

Mismo principio que `apps.sales.Payment`/`apps.purchases.SupplierPayment`:
`Expense` nunca guarda `paid_amount`/`balance_due` — se calculan siempre
agregando sobre `ExpensePayment` (`get_expense_paid_amount`/
`get_expense_balance_due`). Reglas:

- Solo se paga un gasto `APPROVED`/`PARTIALLY_PAID` (nunca uno sin
  aprobar).
- El pago nunca puede exceder el saldo pendiente.
- El pago debe compartir la MISMA moneda del gasto — sin motor de FX
  (ver `docs/currency.md`), se rechaza con un error de negocio claro en
  vez de mezclar monedas.
- En efectivo, exige una `CashSession` abierta
  (`apps.pos.services.ensure_open_session_for_checkout`) y genera un
  `CashMovement` propio (`EXPENSE_PAYMENT_CASH`) — otros métodos no
  afectan la caja física.
- Idempotente por `idempotency_key`; anular un pago (`void_expense_payment`)
  recalcula el estado del gasto (nunca deja `PAID` con un pago anulado).
- Un gasto con pagos registrados nunca puede cancelarse (reversar el
  pago primero).

## 5. `ExpenseRecurrence` — gastos recurrentes, idempotentes por diseño

Plantilla de gasto que se repite (semanal/quincenal/mensual/anual).
`generate_due_expense` genera el `Expense` DRAFT del próximo período
vencido y avanza `next_run_date` — **nunca genera dos gastos para el
mismo período, incluso bajo dos llamadas concurrentes**: el mismo truco
que `generate_document_number` (`select_for_update()` sobre la propia
fila de la recurrencia, en su propia transacción) garantiza que la
segunda llamada concurrente siempre vea el `next_run_date` ya avanzado
por la primera antes de decidir qué período generar.

- `pause_recurrence`/`resume_recurrence`/`cancel_recurrence`: pausar
  impide generar (sin perder el progreso); cancelar es terminal.
- Si `next_run_date` supera `end_date`, la recurrencia se cancela
  automáticamente (con su propia transacción, para que el cambio de
  estado persista aunque la llamada termine rechazada).
- Sin infraestructura de tareas en segundo plano todavía (ver
  `CLAUDE.md`: Redis/Celery solo si una fase futura demuestra necesidad
  real) — un botón "Generar vencidas" en la UI (`list_due_recurrences`
  + `generate_due_expense` por cada una) es la vía profesional
  disponible hoy; una fase futura podría automatizarlo con un scheduler
  real sin cambiar esta lógica de idempotencia.

## 6. Documentos adjuntos

Reutiliza literalmente `apps.customers.file_validation`/
`DocumentoBaseMixin`/`DocumentCategory` (FASE 9) — mismo patrón que
`SalesDocumentAttachment`/`PurchaseDocumentAttachment`: extensión +
firma binaria + tamaño máximo 10 MB, nombre de archivo aleatorio en
disco, descarga solo vía vista protegida (tenant + login), limpieza del
archivo físico ante cualquier camino de borrado.

## 7. Moneda (ver `docs/currency.md`)

`Expense.currency`/`ExpensePayment.currency`/`ExpenseRecurrence.currency`
son snapshots de texto simple (`CharField(max_length=3)`, sin catálogo
real todavía) — mismo criterio que `Sale.currency`/`Payment.currency`.
Sin un motor de tipos de cambio completo, un pago NUNCA puede tener una
moneda distinta a la del gasto que paga (`InvalidExpenseOperation`
explícito) — mismo principio recién aplicado a `allocate_payment`/
`apply_credit_note` en Cuentas por Cobrar.

## 8. Auditoría

`ExpensesActivityLog` (mínima, acotada a este módulo — mismo principio
que `PurchasesActivityLog`/`SalesActivityLog`, explícitamente distinta
del audit log transversal de FASE 15) registra creación, edición,
envío/aprobación/rechazo/cancelación, pagos, eventos de recurrencia y
adjuntos.

## 9. Multi-Tenancy y Seguridad

Todo modelo hereda `TenantScopedModel`; todo servicio filtra `tenant`
explícitamente y usa `all_objects` (nunca `objects`/TenantManager fuera
de una request real). Categoría/proveedor de otro tenant se rechazan
explícitamente en `create_expense`. Vistas usan `get_object_or_404(...,
tenant=request.tenant)` — un ID de otro tenant siempre 404, nunca un
403 que confirme su existencia.

## 10. Qué NO se construyó en esta fase (deliberado)

- **Motor de tipos de cambio (FX)**: preparado conceptualmente (ver
  `docs/currency.md`), nunca construido — un pago en otra moneda se
  rechaza, nunca se convierte automáticamente.
- **Tareas en segundo plano/scheduler real** para generar gastos
  recurrentes automáticamente: la generación es idempotente y está
  lista para conectarse a un scheduler futuro, pero hoy se dispara
  manualmente (botón "Generar vencidas").
- **Contabilidad general (asientos contables)**: preparación explícita
  para FASE 14 (los campos de `Expense`/`ExpensePayment` ya traen todo
  lo necesario: categoría, proveedor, moneda, método, período, estado,
  impuesto, aprobación, pago) — ningún asiento contable se genera
  todavía, por diseño (FASE 13 no construye Contabilidad general).
