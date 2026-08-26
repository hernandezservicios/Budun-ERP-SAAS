"""
Única vía sancionada para operar sobre Gastos (ver `docs/expenses.md`).
Ninguna vista debe escribir estos modelos directamente.

Mismos principios que `apps.purchases.services`/`apps.sales.services`:
- `all_objects` (nunca `objects`/TenantManager) en toda consulta,
  filtrando siempre `tenant` explícitamente.
- `transaction.atomic()` + `select_for_update()` en toda operación que
  lea-y-luego-escriba.
- `Expense` nunca guarda `paid_amount`/`balance_due`: se calculan
  siempre agregando sobre `ExpensePayment` (mismo principio que
  `get_sale_paid_amount`/`get_current_stock`).
- Sin un motor de tipos de cambio (ver `docs/currency.md`), un pago
  nunca puede tener una moneda distinta a la del gasto que paga.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.approvals import services as approvals_services
from apps.approvals.models import ApprovalRequest
from apps.pos.models import CashMovement
from apps.pos.services import ensure_open_session_for_checkout, record_cash_movement
from apps.sales.models import DocumentSequence, PaymentMethod
from apps.sales.services import generate_document_number

from apps.customers.file_validation import nombre_original_seguro, validar_archivo_adjunto

from .models import (
    Expense,
    ExpenseCategory,
    ExpenseDocument,
    ExpensePayment,
    ExpenseRecurrence,
    ExpensesActivityLog,
)


class InvalidExpenseOperation(ValidationError):
    """Se lanza ante cualquier operación de gasto inválida: transición
    de estado no permitida, sobre-pago, moneda distinta, etc."""


class ExpenseOverThresholdRequiresApproval(InvalidExpenseOperation):
    """El total del gasto excede lo que este usuario puede aprobar por
    sí mismo (`ApprovalPolicy.max_expense_amount`) — requiere una
    `ApprovalRequest` resuelta antes de poder aprobarse. Mismo patrón
    que `apps.purchases` (`PurchaseOverThresholdRequiresApproval`) y
    `apps.pos` (`CreditOverageRequiresApproval`)."""

    def __init__(self, *, limit, overage_amount):
        self.limit = limit
        self.overage_amount = overage_amount
        super().__init__(
            f"Este gasto excede el límite autorizable ({limit}) por {overage_amount} — "
            "se solicitó autorización, pide a un supervisor que la apruebe."
        )


class ExpenseExceptionalRequiresApproval(InvalidExpenseOperation):
    """El gasto fue marcado como excepcional/sensible — exige una
    `ApprovalRequest` (`EXPENSE_EXCEPTIONAL`) resuelta, sin importar el
    monto, antes de poder aprobarse."""

    def __init__(self, *, reason):
        self.reason = reason
        super().__init__(
            f"Este gasto fue marcado como excepcional ({reason or 'sin motivo indicado'}) — "
            "se solicitó autorización, pide a un supervisor que la apruebe."
        )


# ------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo)
# ------------------------------------------------------------------


def log_activity(tenant, *, entity_type, entity_id, action, user, entity_label="", details=""):
    return ExpensesActivityLog.all_objects.create(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id, entity_label=entity_label,
        action=action, user=user, details=details,
    )


def get_activity_log(tenant, *, entity_type, entity_id, limit=20):
    return ExpensesActivityLog.all_objects.filter(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id
    ).select_related("user")[:limit]


# ------------------------------------------------------------------
# Categorías (tenant-configurable — nunca una lista cerrada en código)
# ------------------------------------------------------------------

DEFAULT_EXPENSE_CATEGORIES = [
    "Operación", "Servicios", "Alquiler", "Electricidad", "Internet", "Telefonía",
    "Transporte", "Mantenimiento", "Marketing", "Suministros", "Impuestos", "Otros",
]


def list_expense_categories(tenant, *, only_active=True):
    queryset = ExpenseCategory.all_objects.filter(tenant=tenant)
    if only_active:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


def create_expense_category(tenant, *, name, description="", user=None):
    nombre = (name or "").strip()
    if not nombre:
        raise InvalidExpenseOperation("El nombre de la categoría es obligatorio.")
    if ExpenseCategory.all_objects.filter(tenant=tenant, name__iexact=nombre).exists():
        raise InvalidExpenseOperation(f"Ya existe una categoría de gasto llamada «{nombre}».")
    return ExpenseCategory.all_objects.create(tenant=tenant, name=nombre, description=description)


@transaction.atomic
def create_default_expense_categories(tenant):
    """Crea las categorías sugeridas (ver `CLAUDE.md`/`docs/expenses.md`)
    que todavía no existan para este tenant — nunca duplica una ya
    creada (comparación case-insensitive), nunca sobrescribe una que el
    tenant ya haya personalizado. Es una CONVENIENCIA opcional, no una
    lista cerrada: el tenant puede agregar/desactivar categorías libremente."""
    existentes = {nombre.lower() for nombre in ExpenseCategory.all_objects.filter(tenant=tenant).values_list("name", flat=True)}
    creadas = []
    for nombre in DEFAULT_EXPENSE_CATEGORIES:
        if nombre.lower() in existentes:
            continue
        creadas.append(ExpenseCategory.all_objects.create(tenant=tenant, name=nombre))
    return creadas


def set_category_active(category, *, is_active):
    category.is_active = is_active
    category.save(update_fields=["is_active"])
    return category


# ------------------------------------------------------------------
# Cálculo de totales (misma matemática simple que el resto del proyecto:
# total = monto + impuesto - descuento, nunca negativo)
# ------------------------------------------------------------------


def _compute_total(*, amount, tax_amount, discount_amount):
    total = (amount or Decimal("0")) + (tax_amount or Decimal("0")) - (discount_amount or Decimal("0"))
    if total < 0:
        raise InvalidExpenseOperation("El descuento no puede superar monto + impuesto del gasto.")
    return total


# ------------------------------------------------------------------
# Ciclo de vida del gasto
# ------------------------------------------------------------------

_EDITABLE_STATUSES = (Expense.Status.DRAFT, Expense.Status.REJECTED)


@transaction.atomic
def create_expense(
    tenant, *, category, user, description, expense_date, amount, currency=None, tax_amount=Decimal("0"),
    discount_amount=Decimal("0"), supplier=None, due_date=None, preferred_payment_method="", notes="",
    is_exceptional=False, exceptional_reason="",
):
    if category.tenant_id != tenant.id:
        raise InvalidExpenseOperation("La categoría no pertenece a este tenant.")
    if supplier is not None and supplier.tenant_id != tenant.id:
        raise InvalidExpenseOperation("El proveedor no pertenece a este tenant.")
    if amount is None or amount <= 0:
        raise InvalidExpenseOperation("El monto del gasto debe ser mayor que cero.")

    total = _compute_total(amount=amount, tax_amount=tax_amount, discount_amount=discount_amount)
    numero = generate_document_number(tenant, DocumentSequence.DocumentType.EXPENSE)
    gasto = Expense.all_objects.create(
        tenant=tenant, number=numero, category=category, supplier=supplier, description=description,
        expense_date=expense_date, due_date=due_date, currency=currency or "USD", amount=amount,
        tax_amount=tax_amount, discount_amount=discount_amount, total=total,
        preferred_payment_method=preferred_payment_method, created_by=user, notes=notes,
        is_exceptional=is_exceptional, exceptional_reason=exceptional_reason,
    )
    log_activity(
        tenant, entity_type="expense", entity_id=gasto.pk, entity_label=numero,
        action=ExpensesActivityLog.Action.CREATED, user=user, details=description,
    )
    return gasto


@transaction.atomic
def update_expense(expense, user, **campos):
    """Solo puede editarse un gasto en DRAFT/REJECTED — una vez enviado
    a aprobación (o más allá), la edición requiere primero volver a
    DRAFT explícitamente (no implementado: se prefiere cancelar y crear
    uno nuevo, más simple y más auditable)."""
    locked = Expense.all_objects.select_for_update().get(pk=expense.pk, tenant=expense.tenant)
    if locked.status not in _EDITABLE_STATUSES:
        raise InvalidExpenseOperation(f"Un gasto en estado «{locked.get_status_display()}» no puede editarse.")

    for campo in (
        "category", "supplier", "description", "expense_date", "due_date", "currency",
        "preferred_payment_method", "notes", "is_exceptional", "exceptional_reason",
    ):
        if campo in campos:
            setattr(locked, campo, campos[campo])

    amount = campos.get("amount", locked.amount)
    tax_amount = campos.get("tax_amount", locked.tax_amount)
    discount_amount = campos.get("discount_amount", locked.discount_amount)
    if amount is None or amount <= 0:
        raise InvalidExpenseOperation("El monto del gasto debe ser mayor que cero.")
    locked.amount = amount
    locked.tax_amount = tax_amount
    locked.discount_amount = discount_amount
    locked.total = _compute_total(amount=amount, tax_amount=tax_amount, discount_amount=discount_amount)
    locked.status = Expense.Status.DRAFT  # reeditar un rechazado lo regresa a borrador para reenviar.
    locked.save()
    log_activity(
        locked.tenant, entity_type="expense", entity_id=locked.pk, entity_label=locked.number,
        action=ExpensesActivityLog.Action.UPDATED, user=user,
    )
    return locked


@transaction.atomic
def submit_expense_for_approval(expense, user):
    locked = Expense.all_objects.select_for_update().get(pk=expense.pk, tenant=expense.tenant)
    if locked.status not in _EDITABLE_STATUSES:
        raise InvalidExpenseOperation(f"Un gasto en estado «{locked.get_status_display()}» no puede enviarse a aprobación.")
    locked.status = Expense.Status.PENDING_APPROVAL
    locked.save(update_fields=["status", "updated_at"])
    log_activity(
        locked.tenant, entity_type="expense", entity_id=locked.pk, entity_label=locked.number,
        action=ExpensesActivityLog.Action.SUBMITTED, user=user,
    )
    return locked


@transaction.atomic
def approve_expense(expense, user, *, use_threshold_approval=None, use_exceptional_approval=None):
    """Aprueba un gasto PENDING_APPROVAL. Si el total excede lo que
    `user` puede aprobar por sí mismo, o si el gasto es excepcional,
    exige una `ApprovalRequest` ya aprobada y sin consumir — mismo
    flujo "bloquear → ApprovalRequest → supervisor aprueba →
    reintentar" que `apps.pos`/`apps.purchases`."""
    locked = Expense.all_objects.select_for_update().get(pk=expense.pk, tenant=expense.tenant)
    if locked.status != Expense.Status.PENDING_APPROVAL:
        raise InvalidExpenseOperation(f"Un gasto en estado «{locked.get_status_display()}» no puede aprobarse.")

    tenant = locked.tenant
    if locked.is_exceptional:
        aprobacion = use_exceptional_approval or approvals_services.get_usable_approved_request(
            tenant, action_type=ApprovalRequest.ActionType.EXPENSE_EXCEPTIONAL,
            document_type="expense", document_id=locked.pk,
        )
        if not _aprobacion_cubre(aprobacion, minimo=None) and not approvals_services.is_owner(tenant, user):
            raise ExpenseExceptionalRequiresApproval(reason=locked.exceptional_reason)
        if aprobacion is not None and not approvals_services.is_owner(tenant, user):
            approvals_services.mark_consumed(aprobacion, user)

    autorizado, limite = approvals_services.check_expense_authorization(tenant, user, amount=locked.total)
    if not autorizado:
        aprobacion = use_threshold_approval or approvals_services.get_usable_approved_request(
            tenant, action_type=ApprovalRequest.ActionType.EXPENSE_OVER_THRESHOLD,
            document_type="expense", document_id=locked.pk,
        )
        if not _aprobacion_cubre(aprobacion, minimo=locked.total - limite):
            raise ExpenseOverThresholdRequiresApproval(limit=limite, overage_amount=locked.total - limite)
        approvals_services.mark_consumed(aprobacion, user)

    locked.status = Expense.Status.APPROVED
    locked.save(update_fields=["status", "updated_at"])
    log_activity(
        tenant, entity_type="expense", entity_id=locked.pk, entity_label=locked.number,
        action=ExpensesActivityLog.Action.APPROVED, user=user,
    )
    return locked


def _aprobacion_cubre(aprobacion, *, minimo):
    if aprobacion is None:
        return False
    if aprobacion.status != ApprovalRequest.Status.APPROVED or aprobacion.consumed_at is not None:
        return False
    if minimo is None:
        return True
    return (aprobacion.approved_value or Decimal("0")) >= minimo


@transaction.atomic
def reject_expense(expense, user, *, reason=""):
    locked = Expense.all_objects.select_for_update().get(pk=expense.pk, tenant=expense.tenant)
    if locked.status != Expense.Status.PENDING_APPROVAL:
        raise InvalidExpenseOperation(f"Un gasto en estado «{locked.get_status_display()}» no puede rechazarse.")
    locked.status = Expense.Status.REJECTED
    locked.save(update_fields=["status", "updated_at"])
    log_activity(
        locked.tenant, entity_type="expense", entity_id=locked.pk, entity_label=locked.number,
        action=ExpensesActivityLog.Action.REJECTED, user=user, details=reason,
    )
    return locked


@transaction.atomic
def cancel_expense(expense, user, *, reason=""):
    locked = Expense.all_objects.select_for_update().get(pk=expense.pk, tenant=expense.tenant)
    if locked.status in (Expense.Status.PAID, Expense.Status.PARTIALLY_PAID, Expense.Status.CANCELED):
        raise InvalidExpenseOperation(
            f"Un gasto en estado «{locked.get_status_display()}» no puede cancelarse "
            "(ya tiene pagos registrados — reversa el pago primero)."
        )
    locked.status = Expense.Status.CANCELED
    locked.save(update_fields=["status", "updated_at"])
    log_activity(
        locked.tenant, entity_type="expense", entity_id=locked.pk, entity_label=locked.number,
        action=ExpensesActivityLog.Action.CANCELED, user=user, details=reason,
    )
    return locked


# ------------------------------------------------------------------
# Pagos de gasto (ledger append-only)
# ------------------------------------------------------------------


def get_expense_paid_amount(expense):
    total = ExpensePayment.all_objects.filter(
        tenant=expense.tenant, expense=expense, status=ExpensePayment.Status.CONFIRMED
    ).aggregate(suma=Sum("amount"))["suma"]
    return total or Decimal("0")


def get_expense_balance_due(expense):
    return expense.total - get_expense_paid_amount(expense)


def _recompute_expense_payment_status(expense):
    pagado = get_expense_paid_amount(expense)
    if pagado <= 0:
        nuevo_estado = Expense.Status.APPROVED
    elif pagado < expense.total:
        nuevo_estado = Expense.Status.PARTIALLY_PAID
    else:
        nuevo_estado = Expense.Status.PAID
    Expense.all_objects.filter(pk=expense.pk).update(status=nuevo_estado)
    return nuevo_estado


@transaction.atomic
def record_expense_payment(
    tenant, expense, *, method, amount, user, currency=None, reference="", notes="", idempotency_key="",
    cash_session=None,
):
    if idempotency_key:
        existente = ExpensePayment.all_objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
        if existente:
            return existente
    if amount is None or amount <= 0:
        raise InvalidExpenseOperation("El monto del pago debe ser mayor que cero.")

    locked_expense = Expense.all_objects.select_for_update().get(pk=expense.pk, tenant=tenant)
    if locked_expense.status not in (Expense.Status.APPROVED, Expense.Status.PARTIALLY_PAID):
        raise InvalidExpenseOperation(
            f"Un gasto en estado «{locked_expense.get_status_display()}» no puede recibir pagos "
            "(debe estar aprobado primero)."
        )
    moneda_pago = currency or locked_expense.currency
    if moneda_pago != locked_expense.currency:
        # Sin motor de FX (ver docs/currency.md): nunca mezclar monedas
        # distintas en un mismo pago de gasto.
        raise InvalidExpenseOperation(
            f"El pago está en {moneda_pago} y el gasto «{locked_expense.number}» está en "
            f"{locked_expense.currency} — no se puede registrar un pago en una moneda distinta."
        )
    saldo = get_expense_balance_due(locked_expense)
    if amount > saldo:
        raise InvalidExpenseOperation(f"El monto excede el saldo pendiente del gasto ({saldo}).")

    sesion = cash_session
    if method == PaymentMethod.CASH and sesion is None:
        sesion = ensure_open_session_for_checkout(tenant, user)

    pago = ExpensePayment.all_objects.create(
        tenant=tenant, expense=locked_expense, method=method, amount=amount, currency=moneda_pago,
        cash_session=sesion if method == PaymentMethod.CASH else None, reference=reference, notes=notes,
        idempotency_key=idempotency_key, user=user,
    )
    if method == PaymentMethod.CASH:
        record_cash_movement(
            sesion, movement_type=CashMovement.MovementType.EXPENSE_PAYMENT_CASH, amount=amount, user=user,
            reason=f"Pago de gasto {locked_expense.number}", reference_type="expense_payment", reference_id=pago.pk,
        )
    _recompute_expense_payment_status(locked_expense)
    log_activity(
        tenant, entity_type="expense", entity_id=locked_expense.pk, entity_label=locked_expense.number,
        action=ExpensesActivityLog.Action.PAYMENT_RECORDED, user=user, details=f"{method} {amount}",
    )
    return pago


@transaction.atomic
def void_expense_payment(payment, user):
    locked = ExpensePayment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    if locked.status == ExpensePayment.Status.VOIDED:
        return locked
    locked.status = ExpensePayment.Status.VOIDED
    locked.save(update_fields=["status"])
    gasto = Expense.all_objects.select_for_update().get(pk=locked.expense_id, tenant=locked.tenant)
    _recompute_expense_payment_status(gasto)
    log_activity(
        locked.tenant, entity_type="expense", entity_id=gasto.pk, entity_label=gasto.number,
        action=ExpensesActivityLog.Action.PAYMENT_VOIDED, user=user,
    )
    return locked


# ------------------------------------------------------------------
# Gastos recurrentes — idempotencia vía select_for_update sobre la
# propia fila de recurrencia (mismo truco que
# apps.sales.services.generate_document_number: la segunda llamada
# concurrente siempre ve el next_run_date ya avanzado por la primera).
# ------------------------------------------------------------------

_DIAS_POR_FRECUENCIA = {
    ExpenseRecurrence.Frequency.WEEKLY: 7,
    ExpenseRecurrence.Frequency.BIWEEKLY: 14,
    ExpenseRecurrence.Frequency.MONTHLY: 30,
    ExpenseRecurrence.Frequency.YEARLY: 365,
}


def _advance_date(fecha, frequency):
    from datetime import timedelta

    if frequency == ExpenseRecurrence.Frequency.MONTHLY:
        # Avance calendario real (no siempre 30 días exactos).
        mes = fecha.month + 1
        anio = fecha.year + (1 if mes > 12 else 0)
        mes = 1 if mes > 12 else mes
        dia = min(fecha.day, [31, 29 if anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1])
        return fecha.replace(year=anio, month=mes, day=dia)
    if frequency == ExpenseRecurrence.Frequency.YEARLY:
        try:
            return fecha.replace(year=fecha.year + 1)
        except ValueError:
            return fecha.replace(year=fecha.year + 1, day=28)  # 29-feb en año no bisiesto.
    return fecha + timedelta(days=_DIAS_POR_FRECUENCIA[frequency])


@transaction.atomic
def create_expense_recurrence(
    tenant, *, category, description, amount, frequency, start_date, user, currency=None,
    supplier=None, end_date=None, notes="",
):
    if amount is None or amount <= 0:
        raise InvalidExpenseOperation("El monto de la recurrencia debe ser mayor que cero.")
    return ExpenseRecurrence.all_objects.create(
        tenant=tenant, category=category, supplier=supplier, description=description, amount=amount,
        currency=currency or "USD", frequency=frequency, start_date=start_date, end_date=end_date,
        next_run_date=start_date, created_by=user, notes=notes,
    )


def is_recurrence_due(recurrence, *, as_of=None):
    fecha = as_of or timezone.localdate()
    return recurrence.status == ExpenseRecurrence.Status.ACTIVE and recurrence.next_run_date <= fecha


def generate_due_expense(recurrence, user):
    """Genera el `Expense` DRAFT del próximo período vencido y avanza
    `next_run_date` — nunca genera dos gastos para el mismo período
    incluso bajo dos llamadas concurrentes (el lock serializa).

    La detección de "ya venció por fecha de fin" se resuelve en su
    PROPIA transacción, para que el cambio a `CANCELED` quede
    persistido aunque la función termine lanzando una excepción — un
    `raise` dentro de la MISMA transacción que hizo el `save()`
    revertiría también ese cambio de estado (comportamiento normal de
    `transaction.atomic`, no un bug de PostgreSQL)."""
    with transaction.atomic():
        locked = ExpenseRecurrence.all_objects.select_for_update().get(pk=recurrence.pk, tenant=recurrence.tenant)
        if locked.status != ExpenseRecurrence.Status.ACTIVE:
            raise InvalidExpenseOperation(f"Esta recurrencia está «{locked.get_status_display()}», no puede generar gastos.")
        if locked.next_run_date > timezone.localdate():
            raise InvalidExpenseOperation("Esta recurrencia todavía no vence.")
        vencida_por_fecha_fin = bool(locked.end_date and locked.next_run_date > locked.end_date)
        if vencida_por_fecha_fin:
            locked.status = ExpenseRecurrence.Status.CANCELED
            locked.save(update_fields=["status"])
    if vencida_por_fecha_fin:
        raise InvalidExpenseOperation("Esta recurrencia ya venció (fecha de fin superada).")

    return _crear_gasto_de_recurrencia(locked, user)


@transaction.atomic
def _crear_gasto_de_recurrencia(recurrence, user):
    locked = ExpenseRecurrence.all_objects.select_for_update().get(pk=recurrence.pk, tenant=recurrence.tenant)
    run_date = locked.next_run_date
    numero = generate_document_number(locked.tenant, DocumentSequence.DocumentType.EXPENSE)
    gasto = Expense.all_objects.create(
        tenant=locked.tenant, number=numero, category=locked.category, supplier=locked.supplier,
        description=f"{locked.description} ({run_date.isoformat()})", expense_date=run_date,
        currency=locked.currency, amount=locked.amount, total=locked.amount,
        source_recurrence=locked, created_by=user, notes=locked.notes,
    )
    locked.next_run_date = _advance_date(run_date, locked.frequency)
    locked.save(update_fields=["next_run_date"])
    log_activity(
        locked.tenant, entity_type="expense", entity_id=gasto.pk, entity_label=gasto.number,
        action=ExpensesActivityLog.Action.RECURRENCE_GENERATED, user=user, details=locked.description,
    )
    return gasto


def pause_recurrence(recurrence, user):
    recurrence.status = ExpenseRecurrence.Status.PAUSED
    recurrence.save(update_fields=["status"])
    log_activity(
        recurrence.tenant, entity_type="expense_recurrence", entity_id=recurrence.pk,
        entity_label=recurrence.description, action=ExpensesActivityLog.Action.RECURRENCE_PAUSED, user=user,
    )
    return recurrence


def resume_recurrence(recurrence, user):
    recurrence.status = ExpenseRecurrence.Status.ACTIVE
    recurrence.save(update_fields=["status"])
    log_activity(
        recurrence.tenant, entity_type="expense_recurrence", entity_id=recurrence.pk,
        entity_label=recurrence.description, action=ExpensesActivityLog.Action.RECURRENCE_RESUMED, user=user,
    )
    return recurrence


def cancel_recurrence(recurrence, user):
    recurrence.status = ExpenseRecurrence.Status.CANCELED
    recurrence.save(update_fields=["status"])
    log_activity(
        recurrence.tenant, entity_type="expense_recurrence", entity_id=recurrence.pk,
        entity_label=recurrence.description, action=ExpensesActivityLog.Action.RECURRENCE_CANCELED, user=user,
    )
    return recurrence


def list_due_recurrences(tenant, *, as_of=None):
    fecha = as_of or timezone.localdate()
    return ExpenseRecurrence.all_objects.filter(
        tenant=tenant, status=ExpenseRecurrence.Status.ACTIVE, next_run_date__lte=fecha
    ).order_by("next_run_date")


# ------------------------------------------------------------------
# Consultas de listado
# ------------------------------------------------------------------


def list_expenses(tenant, *, status=None, category=None, supplier=None, search=""):
    queryset = Expense.all_objects.filter(tenant=tenant).select_related("category", "supplier")
    if status:
        queryset = queryset.filter(status=status)
    if category:
        queryset = queryset.filter(category=category)
    if supplier:
        queryset = queryset.filter(supplier=supplier)
    if search:
        queryset = queryset.filter(Q(number__icontains=search) | Q(description__icontains=search))
    return queryset.order_by("-expense_date", "-id")


def get_expense_payments(expense):
    return ExpensePayment.all_objects.filter(tenant=expense.tenant, expense=expense).select_related("user").order_by("-created_at")


def get_expense_documents(expense):
    return ExpenseDocument.all_objects.filter(tenant=expense.tenant, expense=expense).select_related("uploaded_by")


# ------------------------------------------------------------------
# Documentos adjuntos (reutiliza literalmente FASE 9 — mismo patrón
# que apps.purchases.services.register_attachment/delete_attachment)
# ------------------------------------------------------------------


def register_expense_document(expense, *, archivo, category, user, notes=""):
    _extension, content_type = validar_archivo_adjunto(archivo)
    adjunto = ExpenseDocument.all_objects.create(
        tenant=expense.tenant, expense=expense, category=category, file=archivo,
        original_filename=nombre_original_seguro(archivo.name), content_type=content_type, size_bytes=archivo.size,
        uploaded_by=user, notes=notes,
    )
    log_activity(
        expense.tenant, entity_type="expense", entity_id=expense.pk,
        action=ExpensesActivityLog.Action.ATTACHMENT_UPLOADED, user=user, details=adjunto.original_filename,
    )
    return adjunto


def delete_expense_document(document, user):
    tenant, expense_id, nombre = document.tenant, document.expense_id, document.original_filename
    document.delete()
    log_activity(
        tenant, entity_type="expense", entity_id=expense_id,
        action=ExpensesActivityLog.Action.ATTACHMENT_DELETED, user=user, details=nombre,
    )
