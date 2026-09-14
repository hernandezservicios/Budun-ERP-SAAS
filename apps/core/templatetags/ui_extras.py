"""
Template tags del Design System (FASE 5; ampliado en la FASE DE
REDISEÑO VISUAL SaaS con `estado_badge`/`monto` — presentación pura,
nunca reglas de negocio).
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

_MAPA_TOAST = {
    "success": "exito",
    "error": "peligro",
    "warning": "advertencia",
    "info": "info",
    "debug": "info",
}


@register.filter
def clase_toast(tags):
    """Convierte las etiquetas de `django.contrib.messages` (en inglés)
    a la variante en español del componente Toast (ver
    static/css/design-system.css)."""
    primera_etiqueta = (tags or "info").split(" ")[0]
    return _MAPA_TOAST.get(primera_etiqueta, "info")


# Mapa único de código crudo de estado -> variante semántica del badge
# (ver "Human-readable SaaS Status Pattern",
# docs/project-status/SAAS_PLATFORM_KNOWLEDGE_KIT.md). Los códigos
# provienen de los `TextChoices` reales de `apps.billing`/`apps.tenants`
# (Tenant.BillingStatus, Subscription.Status, SaaSInvoice.Status,
# SaaSPayment.Status, PaymentProof.Status, BillingRefund.Status,
# SaaSPaymentAllocation.Status, CreditNoteApplication.Status). Ningún
# código se repite con un significado distinto entre modelos, así que
# un único mapa global es seguro (verificado leyendo cada `TextChoices`
# real antes de escribir este mapa, nunca inventado).
_MAPA_BADGE_ESTADO = {
    # Verde — estado vigente/exitoso.
    "active": "verde",
    "paid": "verde",
    "confirmed": "verde",
    "approved": "verde",
    "completed": "verde",
    "processed": "verde",
    # Ámbar — requiere atención o está en curso, todavía no es un error.
    "past_due": "advertencia",
    "pending": "advertencia",
    "pending_payment": "advertencia",
    "open": "advertencia",
    "partially_paid": "advertencia",
    "partially_refunded": "advertencia",
    "submitted": "advertencia",
    "under_review": "advertencia",
    "created": "advertencia",
    "pending_capture": "advertencia",
    "refund_pending": "advertencia",
    "received": "advertencia",
    # Rojo — estado terminal negativo o que interrumpe el servicio/cobro.
    "suspended": "peligro",
    "cancelled": "peligro",
    "expired": "peligro",
    "failed": "peligro",
    "rejected": "peligro",
    "refund_failed": "peligro",
    "error": "peligro",
    # Azul — informativo (dinero devuelto, pero no es ni éxito ni error).
    "refunded": "azul",
    # Gris — administrativo/histórico, sin urgencia.
    "pending_setup": "neutro",
    "draft": "neutro",
    "void": "neutro",
    "reversed": "neutro",
    "duplicate": "neutro",
    "ignored": "neutro",
}


@register.filter
def estado_badge(codigo_crudo):
    """Devuelve la variante del componente `.badge` (verde/advertencia/
    peligro/azul/neutro) para un código crudo de estado (`objeto.status`,
    `tenant.billing_status`, nunca el texto ya traducido de
    `get_..._display`). Un código no reconocido cae a "neutro" — nunca
    revienta el render de una plantilla por un estado no mapeado."""
    return _MAPA_BADGE_ESTADO.get(str(codigo_crudo or "").lower(), "neutro")


# Estados crudos de la Subscriptions API de PayPal
# (`Subscription.paypal_subscription_status`, ver
# `apps.billing.services.recurring`) — un vocabulario en inglés propio
# de PayPal, DISTINTO de los `TextChoices` de Budun, nunca mezclado con
# `_MAPA_BADGE_ESTADO`. Solo traduce el TEXTO mostrado al tenant en el
# Portal; el valor real guardado nunca cambia (sigue siendo el string
# exacto que PayPal reportó, necesario para reconciliación).
_MAPA_ESTADO_PAYPAL = {
    "APPROVAL_PENDING": "esperando tu aprobación en PayPal",
    "APPROVED": "aprobada, activándose",
    "ACTIVE": "activa",
    "SUSPENDED": "suspendida",
    "CANCELLED": "cancelada",
    "EXPIRED": "expirada",
}


@register.filter
def estado_paypal(codigo_crudo):
    """Traduce un estado crudo de la Subscriptions API de PayPal a un
    texto humano en español para el Portal del tenant. Un código no
    reconocido se muestra tal cual (nunca oculta información real)."""
    return _MAPA_ESTADO_PAYPAL.get(str(codigo_crudo or ""), codigo_crudo)


@register.filter
def valor_absoluto(numero):
    """Valor absoluto — usado junto a una flecha de tendencia (↑/↓) que
    ya comunica el signo, para no mostrar un "-8%" redundante junto a
    una flecha hacia abajo."""
    try:
        return abs(numero)
    except TypeError:
        return numero


@register.filter
def iniciales(texto):
    """Hasta 2 iniciales en mayúscula para un avatar circular — a
    partir de un nombre completo ("Super Admin" → "SA") o, si no hay
    nombre, de la parte local de un correo ("super.admin@..." → "SA")."""
    texto = (texto or "").strip()
    if not texto:
        return "?"
    parte_local = texto.split("@")[0] if "@" in texto and " " not in texto else texto
    partes = [p for p in parte_local.replace(".", " ").replace("_", " ").split() if p]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


@register.filter
def monto(valor):
    """Formatea un número/Decimal como monto legible: separador de miles
    y dos decimales fijos (ej. 1234.5 -> "1,234.50"). Puramente
    presentacional — el valor real usado en cualquier cálculo sigue
    siendo el Decimal original del modelo/servicio, nunca este string."""
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return valor
    return f"{numero:,.2f}"
