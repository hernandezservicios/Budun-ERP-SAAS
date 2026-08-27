"""
`SaaSPayment`/`SaaSPaymentAllocation` (FASE 17) — espejo estructural de
`apps.sales.services` (`record_payment`/`apply_payment_to_sales`/
`reverse_allocation`), mismas reglas: nunca excede lo disponible del
pago ni el saldo pendiente de la factura, `select_for_update()` sobre
AMBAS filas antes de aplicar, todo-o-nada al repartir un pago entre
varias facturas, reverso en vez de edición in-place."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import AuditLog

from ..models import SaaSInvoice, SaaSPayment, SaaSPaymentAllocation
from ._saas_audit import audit_event
from .invoicing import _recompute_invoice_status, get_invoice_balance_due


class InvalidPaymentOperation(ValidationError):
    pass


def record_payment(*, tenant, saas_customer, method, amount, currency, subscription=None,
                    external_reference="", paypal_transaction=None, payment_proof=None, user=None,
                    status=SaaSPayment.Status.PENDING):
    payment = SaaSPayment.all_objects.create(
        tenant=tenant, saas_customer=saas_customer, subscription=subscription, method=method,
        amount=amount, currency=currency, status=status, external_reference=external_reference,
        paypal_transaction=paypal_transaction, payment_proof=payment_proof, created_by=user,
    )
    audit_event(tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_payment", object_id=payment.pk,
                after={"method": method, "amount": str(amount), "currency": currency})
    return payment


def confirm_payment(payment, *, user=None):
    from django.utils import timezone

    with transaction.atomic():
        payment = SaaSPayment.all_objects.select_for_update().get(pk=payment.pk)
        if payment.status == SaaSPayment.Status.CONFIRMED:
            return payment
        payment.status = SaaSPayment.Status.CONFIRMED
        payment.received_at = timezone.now()
        payment.save(update_fields=["status", "received_at"])
        audit_event(payment.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_payment", object_id=payment.pk,
                    after={"status": "confirmed"})
        return payment


def get_unallocated_payment_amount(payment):
    """`all_objects` explícito — nunca `payment.allocations` (relación
    inversa tenant-scoped, ver `apps.billing.services.invoicing.
    get_invoice_balance_due`)."""
    aplicado = sum(
        (a.amount for a in SaaSPaymentAllocation.all_objects.filter(payment=payment, status=SaaSPaymentAllocation.Status.ACTIVE)),
        Decimal("0"),
    )
    return payment.amount - aplicado


def apply_payment_to_invoices(payment, allocations, *, user=None):
    """`allocations`: lista de `(invoice, amount)`. Todo-o-nada: si
    cualquier asignación excede lo disponible del pago o el saldo
    pendiente de la factura correspondiente, ninguna se aplica."""
    with transaction.atomic():
        payment = SaaSPayment.all_objects.select_for_update().get(pk=payment.pk)
        if payment.tenant_id is None or payment.status != SaaSPayment.Status.CONFIRMED:
            raise InvalidPaymentOperation("Solo un pago CONFIRMADO puede aplicarse a facturas.")

        disponible = get_unallocated_payment_amount(payment)
        total_solicitado = sum((Decimal(monto) for _factura, monto in allocations), Decimal("0"))
        if total_solicitado > disponible:
            raise InvalidPaymentOperation(f"El monto solicitado ({total_solicitado}) excede el saldo disponible del pago ({disponible}).")

        creadas = []
        for invoice, monto in allocations:
            monto = Decimal(monto)
            invoice_bloqueada = SaaSInvoice.all_objects.select_for_update().get(pk=invoice.pk)
            if invoice_bloqueada.tenant_id != payment.tenant_id:
                raise InvalidPaymentOperation("El pago y la factura deben pertenecer al mismo tenant.")
            saldo_factura = get_invoice_balance_due(invoice_bloqueada)
            if monto > saldo_factura:
                raise InvalidPaymentOperation(f"El monto ({monto}) excede el saldo pendiente de la factura {invoice_bloqueada.number} ({saldo_factura}).")
            allocation = SaaSPaymentAllocation.all_objects.create(
                tenant=payment.tenant, payment=payment, invoice=invoice_bloqueada, amount=monto,
            )
            _recompute_invoice_status(invoice_bloqueada)
            creadas.append(allocation)

        audit_event(payment.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_payment", object_id=payment.pk,
                    after={"aplicaciones": [{"invoice": a.invoice.number, "amount": str(a.amount)} for a in creadas]})
        return creadas


def auto_apply_payment(payment, *, user=None):
    """Aplica el pago a las facturas ABIERTAS más antiguas del tenant en
    orden, hasta agotar el monto disponible del pago o las facturas
    pendientes — el sobrante (si el pago excede todas las facturas
    pendientes) queda simplemente SIN APLICAR, lo cual ya es, por
    definición, el "saldo a favor" del tenant (ver
    `apps.billing.services.credits.get_subscription_credit_balance`) —
    nunca se pierde, nunca requiere un modelo nuevo."""
    disponible = get_unallocated_payment_amount(payment)
    if disponible <= 0:
        return []
    facturas_abiertas = SaaSInvoice.all_objects.filter(
        tenant=payment.tenant, status__in=[SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID],
    ).order_by("due_date", "id")
    if payment.subscription_id:
        facturas_abiertas = facturas_abiertas.filter(subscription_id=payment.subscription_id)

    asignaciones = []
    for invoice in facturas_abiertas:
        if disponible <= 0:
            break
        saldo = get_invoice_balance_due(invoice)
        if saldo <= 0:
            continue
        monto = min(saldo, disponible)
        asignaciones.append((invoice, monto))
        disponible -= monto
    if not asignaciones:
        return []
    return apply_payment_to_invoices(payment, asignaciones, user=user)


def reverse_allocation(allocation, *, user=None, reason=""):
    from django.utils import timezone

    with transaction.atomic():
        allocation = SaaSPaymentAllocation.all_objects.select_for_update().get(pk=allocation.pk)
        if allocation.status == SaaSPaymentAllocation.Status.REVERSED:
            return allocation
        allocation.status = SaaSPaymentAllocation.Status.REVERSED
        allocation.reversed_at = timezone.now()
        allocation.reversal_reason = reason
        allocation.save(update_fields=["status", "reversed_at", "reversal_reason"])
        _recompute_invoice_status(SaaSInvoice.all_objects.get(pk=allocation.invoice_id))
        audit_event(allocation.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_payment_allocation",
                    object_id=allocation.pk, reason=reason)
        return allocation
