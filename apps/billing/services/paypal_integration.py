"""
Puente entre las señales de PayPal de FASE 16 (`apps.billing.signals`)
y el núcleo de Billing SaaS de FASE 17 — el contrato estable que
`docs/paypal.md` (sección 12) anticipó: "FASE 17 solo debe conectar
PayPal con Subscription/SaaS Invoice/SaaS Payment/Payment Allocation".
Conectado en `apps.billing.apps.BillingConfig.ready()` (patrón estándar
de Django para registrar receptores de señales)."""

from .. import signals
from ..models import SaaSPayment, Subscription


def _find_saas_payment(paypal_transaction):
    return SaaSPayment.all_objects.filter(paypal_transaction=paypal_transaction).select_related("tenant", "subscription").first()


def _on_payment_confirmed(sender, transaction, **kwargs):
    from . import payments as payment_services
    from . import subscriptions as subscription_services

    payment = _find_saas_payment(transaction)
    if payment is None:
        return  # transacción de PayPal sin un SaaSPayment asociado (p. ej. la herramienta manual de FASE 16) — nada que hacer.
    payment_services.confirm_payment(payment, user=None)
    payment_services.auto_apply_payment(payment, user=None)
    if payment.subscription is not None:
        # FASE DE CORRECCIÓN 3 (Lifecycle integral): `ACTIVATE != REACTIVATE`
        # — antes de esta corrección, un pago único de PayPal confirmado
        # sobre una suscripción PAST_DUE/SUSPENDED llamaba siempre al
        # primitivo de activación INICIAL, saltándose el guard/auditoría/
        # notificación/restauración de período propios de `reactivate_
        # subscription`.
        estado = payment.subscription.status
        if estado == Subscription.Status.PENDING:
            subscription_services.activate_subscription(payment.subscription, user=None)
        elif estado in (Subscription.Status.PAST_DUE, Subscription.Status.SUSPENDED):
            subscription_services.reactivate_subscription(payment.subscription, user=None)


def _on_payment_failed(sender, transaction, **kwargs):
    from . import notifications

    payment = _find_saas_payment(transaction)
    if payment is None:
        return
    payment.status = SaaSPayment.Status.FAILED
    payment.save(update_fields=["status"])
    notifications.notify_payment_failed(payment.tenant, detail=transaction.failure_reason)


def _on_refund_completed(sender, transaction, **kwargs):
    from ..models import BillingRefund

    refund = BillingRefund.all_objects.filter(paypal_transaction=transaction).select_related("payment").first()
    if refund is None:
        return
    from . import refunds as refund_services

    refund_services._complete_refund(refund, refund.payment, user=None)


def _on_refund_failed(sender, transaction, **kwargs):
    from ..models import BillingRefund

    refund = BillingRefund.all_objects.filter(paypal_transaction=transaction).select_related("payment").first()
    if refund is None:
        return
    from . import refunds as refund_services

    refund_services._fail_refund(refund, user=None)


def connect():
    signals.payment_confirmed.connect(_on_payment_confirmed, dispatch_uid="billing_saas_payment_confirmed")
    signals.payment_failed.connect(_on_payment_failed, dispatch_uid="billing_saas_payment_failed")
    signals.refund_completed.connect(_on_refund_completed, dispatch_uid="billing_saas_refund_completed")
    signals.refund_failed.connect(_on_refund_failed, dispatch_uid="billing_saas_refund_failed")
