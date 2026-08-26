"""
Única vía sancionada para operar sobre Nómina (ver `docs/payroll.md`).
Ninguna vista debe escribir estos modelos directamente.

Mismos principios que `apps.expenses.services`/`apps.hr.services`:
- `all_objects` (nunca `objects`/TenantManager) en toda consulta,
  filtrando siempre `tenant` explícitamente.
- `transaction.atomic()` + `select_for_update()` en toda operación que
  lea-y-luego-escriba; `IntegrityError` de una `UniqueConstraint` bajo
  concurrencia se traduce siempre a `InvalidPayrollOperation`, nunca se
  deja escapar sin traducir (mismo patrón que
  `apps.hr.services.create_employment_contract`).
- `Payroll`/`PayrollLine` congelan un snapshot histórico del empleado
  al calcularse — modificar `Employee.base_salary`/departamento/cargo
  DESPUÉS nunca altera una nómina ya calculada.
- Sin un motor de tipos de cambio completo (ver `docs/currency.md`),
  un pago nunca puede tener una moneda distinta a la de la nómina que
  paga.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum

from apps.approvals import services as approvals_services
from apps.approvals.models import ApprovalRequest
from apps.pos.models import CashMovement
from apps.pos.services import ensure_open_session_for_checkout, record_cash_movement
from apps.sales.models import DocumentSequence, PaymentMethod
from apps.sales.services import generate_document_number

from .models import Payroll, PayrollActivityLog, PayrollLine, PayrollPayment, PayrollPeriod


class InvalidPayrollOperation(ValidationError):
    """Operación de nómina inválida: transición de estado no permitida,
    doble cálculo del mismo empleado en el mismo período, cierre con
    nóminas pendientes, autorización insuficiente, etc."""


# ------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo)
# ------------------------------------------------------------------


def log_activity(tenant, *, entity_type, entity_id, action, user, entity_label="", details=""):
    return PayrollActivityLog.all_objects.create(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id, entity_label=entity_label,
        action=action, user=user, details=details,
    )


def get_activity_log(tenant, *, entity_type, entity_id, limit=20):
    return PayrollActivityLog.all_objects.filter(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id
    ).select_related("user")[:limit]


# ------------------------------------------------------------------
# Período de nómina
# ------------------------------------------------------------------


def list_payroll_periods(tenant):
    return PayrollPeriod.all_objects.filter(tenant=tenant).order_by("-start_date")


@transaction.atomic
def create_payroll_period(tenant, *, start_date, end_date, pay_date, user, currency=None, notes=""):
    if end_date < start_date:
        raise InvalidPayrollOperation("La fecha de fin no puede ser anterior a la fecha de inicio.")
    numero = generate_document_number(tenant, DocumentSequence.DocumentType.PAYROLL_PERIOD)
    periodo = PayrollPeriod.all_objects.create(
        tenant=tenant, number=numero, start_date=start_date, end_date=end_date, pay_date=pay_date,
        currency=currency or "USD", created_by=user, notes=notes,
    )
    log_activity(
        tenant, entity_type="payroll_period", entity_id=periodo.pk, entity_label=numero,
        action=PayrollActivityLog.Action.PERIOD_CREATED, user=user,
    )
    return periodo


@transaction.atomic
def approve_period(period, user):
    """Aprobar un período es puramente una cuestión de AUTORIDAD (mismo
    criterio que `apps.hr.services.approve_leave` — no hay una
    dimensión de "monto dentro de mi límite" que aplique a un período
    completo con muchos empleados), gatea por `can_user_approve` y dej
    a un registro auditable vía `ApprovalRequest` (`PAYROLL_APPROVAL`)."""
    locked = PayrollPeriod.all_objects.select_for_update().get(pk=period.pk, tenant=period.tenant)
    if locked.status not in (PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.PROCESSING):
        raise InvalidPayrollOperation(f"Un período en estado «{locked.get_status_display()}» no puede aprobarse.")
    if not approvals_services.can_user_approve(locked.tenant, user):
        raise InvalidPayrollOperation("No tienes permiso para aprobar períodos de nómina.")
    if not Payroll.all_objects.filter(tenant=locked.tenant, period=locked).exists():
        raise InvalidPayrollOperation("No se puede aprobar un período sin ninguna nómina calculada.")
    locked.status = PayrollPeriod.Status.APPROVED
    locked.save(update_fields=["status"])
    approvals_services.request_approval(
        locked.tenant, action_type=ApprovalRequest.ActionType.PAYROLL_APPROVAL, requested_by=user,
        document_type="payroll_period", document_id=locked.pk, reason=f"Aprobación del período {locked.number}",
    )
    log_activity(
        locked.tenant, entity_type="payroll_period", entity_id=locked.pk, entity_label=locked.number,
        action=PayrollActivityLog.Action.PERIOD_APPROVED, user=user,
    )
    return locked


@transaction.atomic
def cancel_period(period, user):
    locked = PayrollPeriod.all_objects.select_for_update().get(pk=period.pk, tenant=period.tenant)
    if locked.status not in (PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.PROCESSING):
        raise InvalidPayrollOperation(
            f"Un período en estado «{locked.get_status_display()}» no puede cancelarse (ya fue aprobado/pagado)."
        )
    locked.status = PayrollPeriod.Status.CANCELED
    locked.save(update_fields=["status"])
    log_activity(
        locked.tenant, entity_type="payroll_period", entity_id=locked.pk, entity_label=locked.number,
        action=PayrollActivityLog.Action.PERIOD_CANCELED, user=user,
    )
    return locked


@transaction.atomic
def close_period(period, user):
    locked = PayrollPeriod.all_objects.select_for_update().get(pk=period.pk, tenant=period.tenant)
    if locked.status not in (PayrollPeriod.Status.APPROVED, PayrollPeriod.Status.PAID):
        raise InvalidPayrollOperation(f"Un período en estado «{locked.get_status_display()}» no puede cerrarse.")
    pendientes = Payroll.all_objects.filter(
        tenant=locked.tenant, period=locked,
    ).exclude(status__in=[Payroll.Status.PAID, Payroll.Status.CANCELED]).exists()
    if pendientes:
        raise InvalidPayrollOperation("No se puede cerrar un período con nóminas de empleado sin pagar.")
    locked.status = PayrollPeriod.Status.CLOSED
    locked.save(update_fields=["status"])
    log_activity(
        locked.tenant, entity_type="payroll_period", entity_id=locked.pk, entity_label=locked.number,
        action=PayrollActivityLog.Action.PERIOD_CLOSED, user=user,
    )
    return locked


# ------------------------------------------------------------------
# Cálculo de nómina por empleado (snapshot histórico)
# ------------------------------------------------------------------


def _totales_desde_lineas(payroll):
    lineas = PayrollLine.all_objects.filter(tenant=payroll.tenant, payroll=payroll)
    ingresos = lineas.filter(category=PayrollLine.Category.EARNING).aggregate(suma=Sum("amount"))["suma"] or Decimal("0")
    deducciones = lineas.filter(category=PayrollLine.Category.DEDUCTION).aggregate(suma=Sum("amount"))["suma"] or Decimal("0")
    return ingresos, deducciones


def _recompute_payroll_totals(payroll):
    ingresos, deducciones = _totales_desde_lineas(payroll)
    Payroll.all_objects.filter(pk=payroll.pk).update(
        gross_total=ingresos, deductions_total=deducciones, net_total=ingresos - deducciones,
    )


@transaction.atomic
def calculate_payroll_for_employee(tenant, period, employee, *, user, extra_lines=None):
    """Crea la fila `Payroll` (snapshot de nombre/departamento/cargo/
    salario del empleado, congelado para siempre) más una línea
    `BASE_SALARY` automática por `employee.base_salary`, y cualquier
    línea adicional indicada (`extra_lines`: lista de
    `{"category":, "concept":, "description":, "amount":}`). Nunca dos
    filas de `Payroll` para el mismo (período, empleado) — ni siquiera
    bajo dos llamadas concurrentes (`UniqueConstraint` +
    `IntegrityError` traducido)."""
    if employee.tenant_id != tenant.id or period.tenant_id != tenant.id:
        raise InvalidPayrollOperation("El empleado o el período no pertenece a este tenant.")
    locked_period = PayrollPeriod.all_objects.select_for_update().get(pk=period.pk, tenant=tenant)
    if locked_period.status not in (PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.PROCESSING):
        raise InvalidPayrollOperation(f"Un período en estado «{locked_period.get_status_display()}» no admite nuevos cálculos.")

    try:
        with transaction.atomic():
            nomina = Payroll.all_objects.create(
                tenant=tenant, period=locked_period, employee=employee,
                employee_name_snapshot=employee.display_name,
                department_snapshot=employee.department.name if employee.department else "",
                position_snapshot=employee.position.name if employee.position else "",
                base_salary_snapshot=employee.base_salary, currency=employee.currency,
            )
    except IntegrityError as error:
        raise InvalidPayrollOperation(
            f"{employee.display_name} ya tiene una nómina calculada en el período {locked_period.number}."
        ) from error

    PayrollLine.all_objects.create(
        tenant=tenant, payroll=nomina, category=PayrollLine.Category.EARNING,
        concept=PayrollLine.Concept.BASE_SALARY, description="Salario base", amount=employee.base_salary,
    )
    for linea in extra_lines or []:
        PayrollLine.all_objects.create(
            tenant=tenant, payroll=nomina, category=linea["category"], concept=linea["concept"],
            description=linea.get("description", ""), amount=linea["amount"],
        )
    _recompute_payroll_totals(nomina)
    nomina.refresh_from_db()

    if locked_period.status == PayrollPeriod.Status.DRAFT:
        locked_period.status = PayrollPeriod.Status.PROCESSING
        locked_period.save(update_fields=["status"])

    log_activity(
        tenant, entity_type="payroll_period", entity_id=locked_period.pk, entity_label=locked_period.number,
        action=PayrollActivityLog.Action.PAYROLL_CALCULATED, user=user, details=employee.display_name,
    )
    return nomina


@transaction.atomic
def add_payroll_line(payroll, *, category, concept, amount, description=""):
    locked_period = PayrollPeriod.all_objects.select_for_update().get(pk=payroll.period_id, tenant=payroll.tenant)
    if locked_period.status not in (PayrollPeriod.Status.DRAFT, PayrollPeriod.Status.PROCESSING):
        raise InvalidPayrollOperation(
            f"El período «{locked_period.number}» está «{locked_period.get_status_display()}» — "
            "no admite más líneas (corrige con un ajuste en un período nuevo)."
        )
    if amount is None or amount <= 0:
        raise InvalidPayrollOperation("El monto de la línea debe ser mayor que cero.")
    linea = PayrollLine.all_objects.create(
        tenant=payroll.tenant, payroll=payroll, category=category, concept=concept, description=description, amount=amount,
    )
    _recompute_payroll_totals(payroll)
    return linea


def get_payroll_lines(payroll):
    return PayrollLine.all_objects.filter(tenant=payroll.tenant, payroll=payroll).order_by("id")


def list_period_payrolls(period):
    return Payroll.all_objects.filter(tenant=period.tenant, period=period).select_related("employee").order_by("employee_name_snapshot")


# ------------------------------------------------------------------
# Pagos de nómina (ledger append-only)
# ------------------------------------------------------------------


def get_payroll_paid_amount(payroll):
    total = PayrollPayment.all_objects.filter(
        tenant=payroll.tenant, payroll=payroll, status=PayrollPayment.Status.CONFIRMED
    ).aggregate(suma=Sum("amount"))["suma"]
    return total or Decimal("0")


def get_payroll_balance_due(payroll):
    return payroll.net_total - get_payroll_paid_amount(payroll)


def _recompute_payroll_payment_status(payroll):
    pagado = get_payroll_paid_amount(payroll)
    if pagado <= 0:
        nuevo_estado = Payroll.Status.PENDING
    elif pagado < payroll.net_total:
        nuevo_estado = Payroll.Status.PARTIALLY_PAID
    else:
        nuevo_estado = Payroll.Status.PAID
    Payroll.all_objects.filter(pk=payroll.pk).update(status=nuevo_estado)

    if nuevo_estado == Payroll.Status.PAID:
        periodo = PayrollPeriod.all_objects.get(pk=payroll.period_id)
        falta_alguna = Payroll.all_objects.filter(
            tenant=payroll.tenant, period=periodo,
        ).exclude(status__in=[Payroll.Status.PAID, Payroll.Status.CANCELED]).exists()
        if not falta_alguna and periodo.status == PayrollPeriod.Status.APPROVED:
            periodo.status = PayrollPeriod.Status.PAID
            periodo.save(update_fields=["status"])
    return nuevo_estado


@transaction.atomic
def record_payroll_payment(tenant, payroll, *, method, amount, user, currency=None, reference="", notes="", idempotency_key="", cash_session=None):
    if idempotency_key:
        existente = PayrollPayment.all_objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
        if existente:
            return existente
    if amount is None or amount <= 0:
        raise InvalidPayrollOperation("El monto del pago debe ser mayor que cero.")

    locked_payroll = Payroll.all_objects.select_for_update().get(pk=payroll.pk, tenant=tenant)
    locked_period = PayrollPeriod.all_objects.get(pk=locked_payroll.period_id, tenant=tenant)
    if locked_period.status not in (PayrollPeriod.Status.APPROVED, PayrollPeriod.Status.PAID):
        raise InvalidPayrollOperation("Solo se puede pagar una nómina de un período ya aprobado.")
    if locked_payroll.status not in (Payroll.Status.PENDING, Payroll.Status.PARTIALLY_PAID):
        raise InvalidPayrollOperation(f"Una nómina en estado «{locked_payroll.get_status_display()}» no puede recibir pagos.")

    moneda_pago = currency or locked_payroll.currency
    if moneda_pago != locked_payroll.currency:
        raise InvalidPayrollOperation(
            f"El pago está en {moneda_pago} y la nómina está en {locked_payroll.currency} — "
            "no se puede pagar en una moneda distinta."
        )
    saldo = get_payroll_balance_due(locked_payroll)
    if amount > saldo:
        raise InvalidPayrollOperation(f"El monto excede el saldo pendiente de la nómina ({saldo}).")

    sesion = cash_session
    if method == PaymentMethod.CASH and sesion is None:
        sesion = ensure_open_session_for_checkout(tenant, user)

    pago = PayrollPayment.all_objects.create(
        tenant=tenant, payroll=locked_payroll, method=method, amount=amount, currency=moneda_pago,
        cash_session=sesion if method == PaymentMethod.CASH else None, reference=reference, notes=notes,
        idempotency_key=idempotency_key, user=user,
    )
    if method == PaymentMethod.CASH:
        record_cash_movement(
            sesion, movement_type=CashMovement.MovementType.PAYROLL_PAYMENT_CASH, amount=amount, user=user,
            reason=f"Pago de nómina {locked_payroll.employee_name_snapshot} ({locked_period.number})",
            reference_type="payroll_payment", reference_id=pago.pk,
        )
    _recompute_payroll_payment_status(locked_payroll)
    log_activity(
        tenant, entity_type="payroll_period", entity_id=locked_period.pk, entity_label=locked_period.number,
        action=PayrollActivityLog.Action.PAYMENT_RECORDED, user=user,
        details=f"{locked_payroll.employee_name_snapshot}: {method} {amount}",
    )
    return pago


@transaction.atomic
def void_payroll_payment(payment, user):
    locked = PayrollPayment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    if locked.status == PayrollPayment.Status.VOIDED:
        return locked
    locked.status = PayrollPayment.Status.VOIDED
    locked.save(update_fields=["status"])
    nomina = Payroll.all_objects.select_for_update().get(pk=locked.payroll_id, tenant=locked.tenant)
    _recompute_payroll_payment_status(nomina)
    log_activity(
        locked.tenant, entity_type="payroll_period", entity_id=nomina.period_id, entity_label=nomina.employee_name_snapshot,
        action=PayrollActivityLog.Action.PAYMENT_VOIDED, user=user,
    )
    return locked


def get_payroll_payments(payroll):
    return PayrollPayment.all_objects.filter(tenant=payroll.tenant, payroll=payroll).select_related("user").order_by("-created_at")
