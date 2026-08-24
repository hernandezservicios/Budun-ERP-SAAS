"""
TenantMiddleware (FASE 3).

Determina el tenant activo de cada request a partir del usuario
autenticado por Django (`request.user`, ya resuelto por
AuthenticationMiddleware) y sus membresías reales en la base de datos.

Reglas de seguridad de este middleware (ver CLAUDE.md — Multi-tenancy):
- El backend determina el tenant; nunca se confía en un `tenant_id`
  enviado por el frontend (querystring, headers, body, cookies no
  firmadas). Este middleware ni siquiera lee esos valores.
- Si la sesión (firmada y gestionada por Django, no editable por el
  cliente sin la clave secreta) indica un tenant activo, ese valor se
  valida SIEMPRE contra las membresías reales del usuario antes de
  usarse. Un `active_tenant_id` que ya no corresponda a una membresía
  activa se descarta y se recalcula desde cero.
- Un usuario no autenticado, o autenticado pero sin ninguna membresía
  activa, nunca obtiene un tenant "por defecto": `request.tenant` queda
  en `None`.
"""

from .models import Membership
from .scoping import reset_current_tenant, set_current_tenant

ACTIVE_TENANT_SESSION_KEY = "active_tenant_id"


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        request.membership = None
        token = None

        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            membership = self._resolve_membership(request, user)
            if membership is not None:
                request.tenant = membership.tenant
                request.membership = membership
                token = set_current_tenant(membership.tenant)

        try:
            return self.get_response(request)
        finally:
            if token is not None:
                reset_current_tenant(token)

    def _resolve_membership(self, request, user):
        memberships = list(
            Membership.objects.select_related("tenant").filter(
                user=user, is_active=True, tenant__is_active=True
            )
        )
        if not memberships:
            return None

        session = getattr(request, "session", None)
        requested_id = session.get(ACTIVE_TENANT_SESSION_KEY) if session is not None else None

        if requested_id is not None:
            for membership in memberships:
                if membership.tenant_id == requested_id:
                    return membership
            # La sesión apuntaba a un tenant al que el usuario ya no
            # pertenece (o nunca perteneció): se descarta, nunca se confía
            # ciegamente en el valor guardado.
            if session is not None:
                session.pop(ACTIVE_TENANT_SESSION_KEY, None)

        memberships.sort(key=lambda m: m.created_at)
        return memberships[0]
