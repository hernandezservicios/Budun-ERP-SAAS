"""
Única vía sancionada para resolver/gestionar permisos granulares (ver
docs/roles-permissions.md). Generaliza a permisos de ACCIÓN la misma
jerarquía usuario→rol→tenant→negar que `apps.approvals.services.
get_effective_policy` ya usa para UMBRALES de aprobación — un
problema distinto, misma forma de resolución.

Mismos principios que el resto del proyecto: `all_objects` (nunca
`objects`/TenantManager) en toda consulta, filtrando siempre `tenant`
explícitamente.
"""

from django.core.exceptions import PermissionDenied

from apps.tenants.models import Membership

from .catalog import DEFAULT_ROLE_PERMISSIONS, is_valid_permission_code
from .models import RolePermission, UserPermissionOverride


class InvalidPermissionOperation(Exception):
    """Código de permiso desconocido (no está en el catálogo)."""


def _get_membership(tenant, user):
    if user is None or getattr(user, "is_authenticated", True) is False:
        return None
    # `Membership` NO hereda de `TenantScopedModel` (ver su propio
    # docstring en `apps.tenants.models`): usa el manager por defecto
    # de Django a propósito, porque es el modelo que se consulta para
    # *determinar* el tenant activo — no tiene `all_objects`, y
    # `.objects` aquí ya no está filtrado por ningún ContextVar (por
    # eso funciona igual dentro y fuera de una request HTTP real).
    return Membership.objects.filter(tenant=tenant, user=user, is_active=True).first()


def has_permission(tenant, user, code):
    """Resuelve si `user` puede hacer `code` en `tenant`. Jerarquía:
    OWNER/superusuario → siempre True (regla permanente, igual que en
    `apps.approvals`); si no, override de usuario → permiso de rol
    (personalizado por el tenant) → default de rol (código-definido)
    → False."""
    if not is_valid_permission_code(code):
        raise InvalidPermissionOperation(f"«{code}» no es un permiso reconocido.")
    if user is not None and getattr(user, "is_superuser", False):
        return True
    membership = _get_membership(tenant, user)
    if membership is None:
        return False
    if membership.role == Membership.Role.OWNER:
        return True

    override = UserPermissionOverride.all_objects.filter(tenant=tenant, user=user, permission_code=code).first()
    if override is not None:
        return override.is_granted

    fila_rol = RolePermission.all_objects.filter(tenant=tenant, role=membership.role, permission_code=code).first()
    if fila_rol is not None:
        return fila_rol.is_granted

    return code in DEFAULT_ROLE_PERMISSIONS.get(membership.role, set())


def require_permission(request, code):
    """Exige el permiso `code` para la request actual — mismo estilo
    que `apps.tenants.permissions.require_role`, se usa JUNTO a él
    (nunca en su lugar): `require_tenant`/`require_role` siguen
    protegiendo tenant/rol binario, esto añade granularidad. Lanza
    `PermissionDenied` (HTTP 403) si no está autorizado."""
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        raise PermissionDenied("No hay un tenant activo para este usuario.")
    if not has_permission(tenant, request.user, code):
        raise PermissionDenied(f"No tienes el permiso «{code}» para realizar esta acción.")
    return True


class PermissionRequiredMixin:
    """Mixin para Class-Based Views — declarar `permission_code = "..."`
    en la vista. Se combina con `TenantRequiredMixin` (nunca lo
    reemplaza): `class MiVista(LoginRequiredMixin, TenantRequiredMixin,
    PermissionRequiredMixin, View): permission_code = "customers.view";`."""

    permission_code = None

    def dispatch(self, request, *args, **kwargs):
        if self.permission_code:
            require_permission(request, self.permission_code)
        return super().dispatch(request, *args, **kwargs)


# ------------------------------------------------------------------
# Gestión (Configuración → Roles y Permisos)
# ------------------------------------------------------------------


def get_effective_role_permissions(tenant, role):
    """Permisos efectivos de un rol en este tenant: default de fábrica
    con las personalizaciones del tenant aplicadas encima — para
    pintar la UI de configuración (qué está marcado, qué no)."""
    efectivos = set(DEFAULT_ROLE_PERMISSIONS.get(role, set()))
    for fila in RolePermission.all_objects.filter(tenant=tenant, role=role):
        if fila.is_granted:
            efectivos.add(fila.permission_code)
        else:
            efectivos.discard(fila.permission_code)
    return efectivos


def set_role_permission(tenant, *, role, code, is_granted, user=None):
    if not is_valid_permission_code(code):
        raise InvalidPermissionOperation(f"«{code}» no es un permiso reconocido.")
    fila, _creada = RolePermission.all_objects.update_or_create(
        tenant=tenant, role=role, permission_code=code, defaults={"is_granted": is_granted, "updated_by": user},
    )
    _audit_permission_change(tenant, user, domain_object=f"rol:{role}", code=code, is_granted=is_granted)
    return fila


def set_user_permission_override(tenant, *, target_user, code, is_granted, reason="", user=None):
    if not is_valid_permission_code(code):
        raise InvalidPermissionOperation(f"«{code}» no es un permiso reconocido.")
    fila, _creada = UserPermissionOverride.all_objects.update_or_create(
        tenant=tenant, user=target_user, permission_code=code,
        defaults={"is_granted": is_granted, "reason": reason, "created_by": user},
    )
    _audit_permission_change(tenant, user, domain_object=f"usuario:{target_user.pk}", code=code, is_granted=is_granted)
    return fila


def remove_user_permission_override(tenant, *, target_user, code):
    UserPermissionOverride.all_objects.filter(tenant=tenant, user=target_user, permission_code=code).delete()


def list_role_permission_overrides(tenant, role):
    return RolePermission.all_objects.filter(tenant=tenant, role=role).order_by("permission_code")


def list_user_permission_overrides(tenant, target_user):
    return UserPermissionOverride.all_objects.filter(tenant=tenant, user=target_user).order_by("permission_code")


def _audit_permission_change(tenant, user, *, domain_object, code, is_granted):
    """Registra el cambio en la auditoría transversal — import
    diferido (apps.audit se construye como una app nueva independiente,
    nunca un import a nivel de módulo aquí para no acoplar el orden de
    carga de apps)."""
    try:
        from apps.audit.services import log_event
        from apps.audit.models import AuditLog

        log_event(
            tenant, user=user, action=AuditLog.Action.PERMISSION_CHANGED, domain="permissions",
            object_type="permission", object_id=None,
            details=f"{domain_object} → {code} = {'concedido' if is_granted else 'denegado'}",
        )
    except Exception:  # noqa: BLE001 — la auditoría nunca debe romper el cambio de permiso.
        pass
