"""
Notificaciones de Billing SaaS (FASE 17, sección 35). No existe todavía
ningún centro de notificaciones in-app en el proyecto (búsqueda
explícita sin resultados) — construir uno completo sería un subsistema
nuevo y de alcance no definido, más allá de lo que esta fase pide.
Se reutiliza la infraestructura de correo YA configurada desde FASE 4
(`EMAIL_BACKEND`/`DEFAULT_FROM_EMAIL`, consola en desarrollo) —
`django.core.mail.send_mail`, sin dependencia nueva. Mismo patrón
resiliente que la auditoría: una notificación nunca debe poder romper
la operación de negocio que la dispara."""

from django.conf import settings
from django.core.mail import send_mail

from apps.tenants.models import Membership


def _enviar(*, to_email, subject, message):
    if not to_email:
        return
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=True)
    except Exception:  # noqa: BLE001 — una notificación nunca debe romper la operación.
        pass


def _tenant_owner_email(tenant):
    membership = Membership.objects.filter(tenant=tenant, role=Membership.Role.OWNER, is_active=True).select_related("user").first()
    return membership.user.email if membership else ""


def _admin_email():
    """Correo del Super Admin de plataforma para notificaciones
    administrativas — OPCIONAL (`PLATFORM_ADMIN_EMAIL`, vacío por
    defecto): el dashboard de Billing ya muestra los pendientes en vivo,
    así que un correo de administrador es una conveniencia adicional,
    nunca el único canal."""
    return getattr(settings, "PLATFORM_ADMIN_EMAIL", "")


def notify_payment_proof_submitted(proof):
    _enviar(
        to_email=_admin_email(),
        subject=f"Nuevo comprobante de transferencia — {proof.reference}",
        message=f"Tenant: {proof.tenant}\nMonto declarado: {proof.declared_amount} {proof.declared_currency}\nReferencia: {proof.reference}",
    )


def notify_payment_approved(payment):
    _enviar(
        to_email=_tenant_owner_email(payment.tenant),
        subject="Tu pago fue aprobado",
        message=f"Tu pago de {payment.amount} {payment.currency} fue confirmado.",
    )


def notify_payment_rejected(proof):
    _enviar(
        to_email=_tenant_owner_email(proof.tenant),
        subject="Tu comprobante fue rechazado",
        message=f"Motivo: {proof.rejection_reason}\nPuedes subir un nuevo comprobante para la referencia {proof.reference}.",
    )


def notify_invoice_upcoming(invoice):
    _enviar(
        to_email=_tenant_owner_email(invoice.tenant),
        subject=f"Tu factura {invoice.number} vence pronto",
        message=f"Vence el {invoice.due_date}. Monto: {invoice.total} {invoice.currency}.",
    )


def notify_invoice_overdue(invoice):
    _enviar(
        to_email=_tenant_owner_email(invoice.tenant),
        subject=f"Tu factura {invoice.number} está vencida",
        message=f"Venció el {invoice.due_date}. Monto: {invoice.total} {invoice.currency}.",
    )


def notify_subscription_past_due(subscription):
    _enviar(
        to_email=_tenant_owner_email(subscription.tenant),
        subject="Tu suscripción tiene un pago vencido",
        message="Tu cuenta está en período de gracia. Regulariza tu pago para evitar la suspensión.",
    )


def notify_subscription_suspended(subscription):
    _enviar(
        to_email=_tenant_owner_email(subscription.tenant),
        subject="Tu suscripción fue suspendida",
        message="Tu cuenta fue suspendida por falta de pago. Contacta a soporte para reactivarla.",
    )


def notify_subscription_reactivated(subscription):
    _enviar(
        to_email=_tenant_owner_email(subscription.tenant),
        subject="Tu suscripción fue reactivada",
        message="Tu cuenta ha sido reactivada. ¡Bienvenido de vuelta!",
    )


def notify_renewal(subscription):
    _enviar(
        to_email=_tenant_owner_email(subscription.tenant),
        subject="Tu suscripción se renovó",
        message=f"Nuevo período: {subscription.current_period_start} — {subscription.current_period_end}.",
    )


def notify_payment_failed(tenant, *, detail=""):
    _enviar(
        to_email=_tenant_owner_email(tenant),
        subject="No pudimos procesar tu pago",
        message=f"Hubo un problema procesando tu pago. {detail}",
    )
