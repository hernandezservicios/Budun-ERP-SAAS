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

from ..models import BillingRefund, SaaSPayment, SaaSPaymentAllocation
from ._saas_audit import audit_event


class InvalidRefundOperation(ValidationError):
    pass


def _reembolsado_total(payment):
    """`all_objects` explícito — nunca `payment.refunds` (relación
    inversa tenant-scoped, ver
    `apps.billing.services.invoicing.get_invoice_balance_due`). Cuenta
    SOLO reembolsos COMPLETADOS — refleja lo que el pago YA devolvió de
    verdad (usado para decidir `REFUNDED` vs `PARTIALLY_REFUNDED`, nunca
    para el guard de "cuánto queda disponible para solicitar", ver
    `_comprometido_total` abajo)."""
    return sum(
        (r.amount for r in BillingRefund.all_objects.filter(payment=payment, status=BillingRefund.Status.COMPLETED)), Decimal("0"),
    )


def _comprometido_total(payment):
    """FASE DE CORRECCIÓN 3 (Lifecycle integral, sección "concurrencia"):
    antes de esta corrección, `request_billing_refund` validaba el monto
    disponible contra `_reembolsado_total` (solo COMPLETADOS) — dos
    solicitudes de reembolso simultáneas sobre el MISMO pago, ninguna
    todavía completada, leían ambas "0 ya reembolsado" (el
    `select_for_update()` de `SaaSPayment` las serializa, pero un
    `BillingRefund` recién creado queda en `PENDING`, no `COMPLETED`) y
    juntas podían comprometer más de lo que el pago tenía disponible.
    Suma PENDING + COMPLETED — un reembolso `FAILED` libera de nuevo su
    monto (nunca cuenta aquí), igual que un reembolso todavía sin
    resolver del lado de PayPal (`REFUND_PENDING`, que en `BillingRefund`
    sigue siendo `PENDING` hasta que el webhook/reconciliación lo mueva
    a un estado terminal)."""
    return sum(
        (r.amount for r in BillingRefund.all_objects.filter(
            payment=payment, status__in=[BillingRefund.Status.PENDING, BillingRefund.Status.COMPLETED],
        )), Decimal("0"),
    )


def request_billing_refund(payment, *, amount=None, reason="", user=None):
    with transaction.atomic():
        payment = SaaSPayment.all_objects.select_for_update().get(pk=payment.pk)
        if payment.status != SaaSPayment.Status.CONFIRMED and payment.status != SaaSPayment.Status.PARTIALLY_REFUNDED:
            raise InvalidRefundOperation("Solo se puede reembolsar un pago confirmado.")
        ya_comprometido = _comprometido_total(payment)
        monto = Decimal(amount) if amount is not None else (payment.amount - ya_comprometido)
        if monto <= 0 or ya_comprometido + monto > payment.amount:
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


def _reverse_allocations_for_refund(payment, amount, *, user=None, reason=""):
    """FASE DE CORRECCIÓN 3 (Lifecycle integral, sección "refund"): antes
    de esta corrección, completar un reembolso nunca tocaba
    `SaaSPaymentAllocation` — la(s) factura(s) que ese pago había
    cubierto quedaban `PAID`/`PARTIALLY_PAID` para siempre aunque el
    dinero ya hubiera vuelto al cliente. Revierte las asignaciones
    ACTIVAS de `payment` (más recientes primero) hasta liberar `amount`
    — nunca "parte" una asignación in-place (append-only, mismo
    principio que todo el ledger de Billing): si la asignación revertida
    era mayor que lo efectivamente reembolsado, el remanente se
    re-asigna como una asignación NUEVA a la misma factura (reverso +
    reasignación, nunca una edición), así que solo el monto realmente
    devuelto deja de estar cubierto."""
    from . import payments as payment_services

    restante = amount
    allocations = list(SaaSPaymentAllocation.all_objects.filter(
        payment=payment, status=SaaSPaymentAllocation.Status.ACTIVE,
    ).order_by("-created_at"))
    for allocation in allocations:
        if restante <= 0:
            break
        invoice = allocation.invoice
        monto_original = allocation.amount
        a_liberar = min(monto_original, restante)
        payment_services.reverse_allocation(allocation, user=user, reason=reason or "Reembolso")
        remanente = monto_original - a_liberar
        if remanente > 0:
            payment_services.apply_payment_to_invoices(payment, [(invoice, remanente)], user=user)
        restante -= a_liberar


def _complete_refund(refund, payment, *, user=None):
    from django.utils import timezone

    with transaction.atomic():
        refund.status = BillingRefund.Status.COMPLETED
        refund.completed_at = timezone.now()
        refund.save(update_fields=["status", "completed_at", "paypal_transaction"])
        # Revertir las asignaciones ANTES de cambiar `payment.status`:
        # `apply_payment_to_invoices` (usado para reasignar el remanente,
        # ver arriba) exige un pago todavía CONFIRMADO.
        _reverse_allocations_for_refund(payment, refund.amount, user=user, reason=f"Reembolso {refund.pk}")
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
