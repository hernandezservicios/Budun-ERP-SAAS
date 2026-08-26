"""
Manejadores de las señales de autenticación de Django — conectados en
`apps.py` (`ready()`). Nunca se registra una contraseña, ni siquiera
en `credentials` de `user_login_failed` (que Django no redacta por
defecto): `_credenciales_seguras` descarta explícitamente cualquier
clave que suene a secreto antes de guardarla en `metadata`."""

from apps.tenants.models import Membership

from . import services
from .models import AuditLog


def _resolver_tenant_para_login(request, user):
    """El tenant activo (`request.tenant`) todavía no existe en el
    momento de este evento: `TenantMiddleware` ya corrió para esta
    request ANTES de que la vista de login autenticara al usuario, así
    que resolvió con un `AnonymousUser`. Se repite aquí, ahora con el
    usuario real: sesión ya seleccionada, si no la primera membresía
    activa, si no ninguna (se audita sin tenant, nunca se inventa uno)."""
    membresias = list(Membership.objects.filter(user=user, is_active=True, tenant__is_active=True))
    if not membresias:
        return None
    return membresias[0].tenant


def _credenciales_seguras(credentials):
    """Nunca se guarda una contraseña/token/secreto — ni siquiera si
    llegara en `credentials` (Django no lo garantiza redactado)."""
    prohibidas = ("pass", "secret", "token", "clave")
    return {
        clave: valor for clave, valor in credentials.items()
        if not any(fragmento in clave.lower() for fragmento in prohibidas)
    }


def on_user_logged_in(sender, request, user, **kwargs):
    # La auditoría nunca debe poder romper un login real — mismo
    # principio que los `try_record_*` de `apps.accounting`.
    try:
        tenant = getattr(request, "tenant", None) or _resolver_tenant_para_login(request, user)
        services.log_event_from_request(request, action=AuditLog.Action.LOGIN, domain="auth", tenant=tenant, user=user)
    except Exception:  # noqa: BLE001
        pass


def on_user_logged_out(sender, request, user, **kwargs):
    if user is None:
        return
    try:
        tenant = getattr(request, "tenant", None)
        services.log_event_from_request(request, action=AuditLog.Action.LOGOUT, domain="auth", tenant=tenant, user=user)
    except Exception:  # noqa: BLE001
        pass


def on_user_login_failed(sender, credentials, request=None, **kwargs):
    try:
        metadata = _credenciales_seguras(credentials)
        if request is not None:
            services.log_event_from_request(
                request, action=AuditLog.Action.LOGIN_FAILED, domain="auth", tenant=None, user=None, metadata=metadata,
            )
        else:
            services.log_event(None, action=AuditLog.Action.LOGIN_FAILED, domain="auth", metadata=metadata)
    except Exception:  # noqa: BLE001
        pass
