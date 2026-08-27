"""
Controles de autorización tenant-aware (FASE 3, objetivo 8).

Estos helpers son deliberadamente pequeños y agnósticos de framework (no
dependen de Django REST Framework, que se introduce recién en FASE 15):
funcionan tanto para vistas basadas en función como en clase, y las fases
futuras (FASE 4 en adelante) los reutilizarán en vistas reales.
"""

from django.core.exceptions import PermissionDenied


def require_tenant(request):
    """Exige que la request tenga un tenant activo (resuelto por
    `TenantMiddleware`). Lanza `PermissionDenied` (HTTP 403) si no."""
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        raise PermissionDenied("No hay un tenant activo para este usuario.")
    return tenant


def require_role(request, roles):
    """Exige que la membresía activa tenga uno de los roles indicados.

    `roles` puede ser un único valor de `Membership.Role` (o su string) o
    una colección de ellos. Lanza `PermissionDenied` si la membresía no
    cumple, o si no hay tenant/membresía activa.
    """
    require_tenant(request)
    membership = getattr(request, "membership", None)
    if membership is None:
        raise PermissionDenied("No hay una membresía activa para este usuario.")

    allowed = {roles} if isinstance(roles, str) else set(roles)
    if membership.role not in allowed:
        raise PermissionDenied("El rol de la membresía no autoriza esta acción.")
    return membership


class TenantRequiredMixin:
    """Mixin para Class-Based Views: exige un tenant activo antes de
    despachar la vista. Las mixins de rol específico (p. ej. solo OWNER)
    se construirán reutilizando `require_role` cuando FASE 4/7 agreguen
    vistas reales protegidas por rol."""

    def dispatch(self, request, *args, **kwargs):
        require_tenant(request)
        return super().dispatch(request, *args, **kwargs)


def require_superuser(request):
    """Exige `request.user.is_superuser` — el gate de las vistas de
    PLATAFORMA (`apps.billing`, FASE 16), que administran algo que no
    pertenece a ningún tenant (la configuración/credenciales de PayPal
    del propio operador del SaaS). Deliberadamente NO se usa
    `apps.permissions.require_permission` aquí: ese motor resuelve
    permisos POR TENANT (`RolePermission` es "qué puede hacer el rol
    ADMIN en el tenant X"), lo cual no tiene sentido para un recurso que
    no es de ningún tenant en particular. `is_superuser` ya es, en ese
    mismo motor, el primer escalón de la jerarquía ("OWNER/superusuario
    → siempre autorizado", ver `apps.permissions.services.has_permission`)
    — aquí simplemente es la ÚNICA condición, porque no hay un tenant de
    quien depender. Lanza `PermissionDenied` (HTTP 403) si no."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False) or not getattr(user, "is_superuser", False):
        raise PermissionDenied("Esta sección es exclusiva del Super Admin de la plataforma.")
    return user


class SuperuserRequiredMixin:
    """Mixin para Class-Based Views de plataforma — ver `require_superuser`.
    Se usa SOLO (nunca junto a `TenantRequiredMixin`): las vistas de
    plataforma no tienen ni necesitan un tenant activo."""

    def dispatch(self, request, *args, **kwargs):
        require_superuser(request)
        return super().dispatch(request, *args, **kwargs)
