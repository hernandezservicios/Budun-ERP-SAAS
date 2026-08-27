"""
Auditoría compartida del dominio `"billing_saas"` (FASE 17) — dominio
DISTINTO de `"billing_paypal"` (FASE 16, `apps.billing.services.__init__._audit`),
nunca mezclados en la búsqueda federada de `apps.audit`. Mismo patrón
resiliente de siempre: la auditoría nunca debe poder romper una
operación de Billing real."""

from apps.audit.models import AuditLog


def audit_event(tenant, *, action, user=None, object_type="", object_id=None, before=None, after=None, metadata=None, reason=""):
    try:
        from apps.audit.services import log_event

        log_event(
            tenant, user=user, action=action, domain="billing_saas",
            object_type=object_type, object_id=("" if object_id is None else str(object_id)),
            before=before, after=after, metadata=metadata or {}, reason=reason,
        )
    except Exception:  # noqa: BLE001 — la auditoría nunca debe romper la operación.
        pass


__all__ = ["audit_event", "AuditLog"]
