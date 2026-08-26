"""
Permisos granulares (FASE 15, ver docs/roles-permissions.md).
Extiende — nunca reemplaza — el rol binario OWNER/MEMBER de
`apps.tenants.Membership` y la jerarquía usuario→rol→tenant→negar
ya establecida por `apps.approvals.ApprovalPolicy` (que resuelve
UMBRALES de aprobación, un problema distinto de "¿puede hacer X?").

El catálogo de permisos (`catalog.PERMISSION_CATALOG`) es
código-definido, no una tabla — lo que SÍ vive en la base de datos es
qué rol/usuario tiene cada permiso concedido o denegado.
"""

from django.conf import settings
from django.db import models

from apps.tenants.models import Membership, TenantScopedModel

from .catalog import PERMISSION_CATALOG


def _permission_code_choices():
    return [(code, label) for code, label, _domain in PERMISSION_CATALOG]


class RolePermission(TenantScopedModel):
    """Personalización POR TENANT de qué permiso tiene un rol —
    ausencia de fila para (tenant, rol, código) significa "usa el
    default de fábrica" (`catalog.DEFAULT_ROLE_PERMISSIONS`), nunca
    "denegado" — la fila explícita es la única forma de apartarse del
    default, en cualquier dirección (conceder algo que el default no
    da, o denegar algo que el default sí da)."""

    role = models.CharField("rol", max_length=20, choices=Membership.Role.choices)
    permission_code = models.CharField("permiso", max_length=50, choices=_permission_code_choices())
    is_granted = models.BooleanField("concedido", default=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="actualizado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "permiso de rol"
        verbose_name_plural = "permisos de rol"
        ordering = ["role", "permission_code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "role", "permission_code"], name="unique_roleperm_tenant_rol_codigo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "role"], name="idx_roleperm_tenant_rol"),
        ]

    def __str__(self):
        estado = "concedido" if self.is_granted else "denegado"
        return f"{self.get_role_display()} — {self.permission_code} ({estado})"


class UserPermissionOverride(TenantScopedModel):
    """Excepción específica de UN usuario — máxima prioridad en la
    jerarquía de resolución (`services.has_permission`), igual que
    `ApprovalPolicy.Scope.USER` para umbrales de aprobación. Nunca se
    elimina el concepto de override por usuario — esta es esa misma
    idea, generalizada a permisos de acción."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="permission_overrides",
    )
    permission_code = models.CharField("permiso", max_length=50, choices=_permission_code_choices())
    is_granted = models.BooleanField("concedido", default=True)
    reason = models.CharField("motivo", max_length=255, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "permiso de usuario (override)"
        verbose_name_plural = "permisos de usuario (overrides)"
        ordering = ["user_id", "permission_code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user", "permission_code"], name="unique_userperm_tenant_usuario_codigo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "user"], name="idx_userperm_tenant_usuario"),
        ]

    def __str__(self):
        estado = "concedido" if self.is_granted else "denegado"
        return f"{self.user} — {self.permission_code} ({estado})"
