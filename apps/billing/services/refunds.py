"""
`BillingRefund` (FASE 17, sección 23) — el registro de NEGOCIO "este
pago SaaS fue reembolsado", distinto del seguimiento interno de
PayPal (`PayPalTransaction`, FASE 16, que sigue siendo la única fuente
de verdad de los IDs/estado externos de PayPal) y de `apps.sales.Refund`
(ERP del tenant, dominio completamente distinto). Cuando el método es
PayPal, este módulo reutiliza EXACTAMENTE `apps.billing.services.
request_refund` de FASE 16 — nunca reimplementa OAuth/credenciales/
llamadas HTTP (sección 12 de la fase: "reutilizar exactamente el
provider creado en FASE 16")."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import AuditLog

from ..models import BillingRefund, SaaSPayment
from ._saas_audit import audit_event


class InvalidRefundOperation(ValidationError):
    pass


def _reembolsado_total(payment):
    """`all_objects` explícito — nunca `payment.refunds` (relación
    inversa tenant-scoped, ver
    `apps.billing.services.invoicing.get_invoice_balance_due`)."""
    return sum(
        (r.amount for r in BillingRefund.all_objects.filter(payment=payment, status=BillingRefund.Status.COMPLETED)), Decimal("0"),
    )


def request_billing_refund(payment, *, amount=None, reason="", user=None):
    with transaction.atomic():
        payment = SaaSPayment.all_objects.select_for_update().get(pk=payment.pk)
        if payment.status != SaaSPayment.Status.CONFIRMED and payment.status != SaaSPayment.Status.PARTIALLY_REFUNDED:
            raise InvalidRefundOperation("Solo se puede reembolsar un pago confirmado.")
        ya_reembolsado = _reembolsado_total(payment)
        monto = Decimal(amount) if amount is not None else (payment.amount - ya_reembolsado)
        if monto <= 0 or ya_reembolsado + monto > payment.amount:
            raise InvalidRefundOperation("El monto del reembolso excede lo disponible para reembolsar.")

        refund = BillingRefund.all_objects.create(
            tenant=payment.tenant, payment=payment, amount=monto, currency=payment.currency,
            reason=reason, created_by=user,
        )
        audit_event(payment.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="billing_refund", object_id=refund.pk,
                    after={"amount": str(monto)}, reason=reason)

        if payment.method == SaaSPayment.Method.PAYPAL and payment.paypal_transaction_id:
            from . import request_refund as paypal_request_refund  # FASE 16, apps.billing.services.__init__

            txn = paypal_request_refund(payment.paypal_transaction, user=user, amount=monto, reason=reason)
            refund.paypal_transaction = txn
            if txn.status == txn.Status.REFUNDED:
                _complete_refund(refund, payment, user=user)
            elif txn.status == txn.Status.REFUND_FAILED:
                _fail_refund(refund, user=user)
            else:
                refund.save(update_fields=["paypal_transaction"])
        return refund


def _complete_refund(refund, payment, *, user=None):
    from django.utils import timezone

    refund.status = BillingRefund.Status.COMPLETED
    refund.completed_at = timezone.now()
    refund.save(update_fields=["status", "completed_at", "paypal_transaction"])
    nuevo_total_reembolsado = _reembolsado_total(payment)
    payment.status = SaaSPayment.Status.REFUNDED if nuevo_total_reembolsado >= payment.amount else SaaSPayment.Status.PARTIALLY_REFUNDED
    payment.save(update_fields=["status"])
    audit_event(refund.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="billing_refund", object_id=refund.pk,
                after={"status": "completed"})


def _fail_refund(refund, *, user=None):
    refund.status = BillingRefund.Status.FAILED
    refund.save(update_fields=["status", "paypal_transaction"])
    audit_event(refund.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="billing_refund", object_id=refund.pk,
                after={"status": "failed"})


def complete_manual_refund(refund, *, user=None):
    """Reembolso manual (no-PayPal, p. ej. una devolución bancaria
    procesada fuera de línea) — el Super Admin confirma manualmente que
    el dinero ya salió."""
    with transaction.atomic():
        refund = BillingRefund.all_objects.select_for_update().get(pk=refund.pk)
        if refund.status == BillingRefund.Status.COMPLETED:
            return refund
        payment = SaaSPayment.all_objects.select_for_update().get(pk=refund.payment_id)
        _complete_refund(refund, payment, user=user)
        return refund
