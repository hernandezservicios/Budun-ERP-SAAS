"""
Transiciones de `Tenant.billing_status` (FASE 17, ver `docs/billing.md`
sección 36: "El estado del tenant no debe cambiar arbitrariamente desde
un formulario. Debe provenir de eventos/reglas de Billing"). Estas son
las ÚNICAS funciones que escriben `Tenant.billing_status` en todo el
proyecto — ninguna vista/formulario lo edita directamente. Deliberadamente
NO tocan `Tenant.is_active` (significado histórico de FASE 3, sin
relación con Billing) — ver `apps.billing.middleware.BillingStatusMiddleware`,
que es lo que realmente bloquea la operación según este campo."""

from django.db import transaction

from apps.tenants.models import Tenant

from ._saas_audit import AuditLog, audit_event


def _set_status(tenant, status, *, user=None, reason=""):
    """Bloquea la fila del propio `Tenant` (`select_for_update`) —
    defensivo: esta función se llama tanto desde código que ya sostiene
    un lock sobre `Subscription` (que no bloquea `Tenant` por sí solo)
    como desde flujos que no bloquean nada todavía (aprobación de
    transferencia)."""
    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
        anterior = tenant.billing_status
        if anterior == status:
            return tenant
        tenant.billing_status = status
        tenant.save(update_fields=["billing_status"])
    audit_event(
        tenant, action=AuditLog.Action.GENERIC, user=user, object_type="tenant", object_id=tenant.pk,
        before={"billing_status": anterior}, after={"billing_status": status}, reason=reason,
    )
    return tenant


def activate_tenant(tenant, *, user=None):
    return _set_status(tenant, Tenant.BillingStatus.ACTIVE, user=user)


def mark_tenant_past_due(tenant, *, user=None):
    return _set_status(tenant, Tenant.BillingStatus.PAST_DUE, user=user)


def suspend_tenant(tenant, *, user=None, reason=""):
    return _set_status(tenant, Tenant.BillingStatus.SUSPENDED, user=user, reason=reason)


def reactivate_tenant(tenant, *, user=None):
    return _set_status(tenant, Tenant.BillingStatus.ACTIVE, user=user)


def cancel_tenant(tenant, *, user=None, reason=""):
    return _set_status(tenant, Tenant.BillingStatus.CANCELLED, user=user, reason=reason)


def mark_tenant_expired(tenant, *, user=None):
    return _set_status(tenant, Tenant.BillingStatus.EXPIRED, user=user)


def mark_tenant_pending_payment(tenant, *, user=None):
    return _set_status(tenant, Tenant.BillingStatus.PENDING_PAYMENT, user=user)
