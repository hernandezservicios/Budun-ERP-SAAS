"""
Configuración → Roles y Permisos (FASE 15). Solo el propietario del
tenant administra esto por defecto (`settings.manage` no está en el
catálogo de fábrica de ningún otro rol) — evita el problema de
"quién controla el control de acceso" en el caso general, mismo
criterio que el resto del proyecto (el propietario siempre está
autorizado, ver `apps.approvals.services`)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.tenants.models import Membership
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .catalog import PERMISSIONS_BY_DOMAIN
from .forms import RolePermissionsForm, UserOverrideForm
from .services import require_permission


class RolesIndexView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_permission(request, "settings.manage")
        roles = [r for r in Membership.Role.choices if r[0] != Membership.Role.OWNER]
        miembros = Membership.objects.filter(tenant=request.tenant, is_active=True).select_related("user").order_by("user__email")
        return render(request, "permissions/roles_index.html", {"roles": roles, "miembros": miembros})


def _sections_for(form):
    """Agrupa los campos del formulario (uno por permiso) por dominio,
    para la plantilla — evita el problema de que los nombres de campo
    contienen puntos (`customers.view`), que la sintaxis de plantillas
    de Django interpretaría como una cadena de atributos si se
    intentara acceder con `{{ form.customers.view }}`."""
    return [
        (dominio, [form[codigo] for codigo, _etiqueta in permisos])
        for dominio, permisos in PERMISSIONS_BY_DOMAIN.items()
    ]


class RolePermissionsView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, role):
        require_permission(request, "settings.manage")
        efectivos = services.get_effective_role_permissions(request.tenant, role)
        form = RolePermissionsForm(efectivos=efectivos)
        return render(request, "permissions/role_permissions.html", {
            "role": role, "role_label": dict(Membership.Role.choices).get(role, role),
            "sections": _sections_for(form),
        })

    def post(self, request, role):
        require_permission(request, "settings.manage")
        efectivos = services.get_effective_role_permissions(request.tenant, role)
        form = RolePermissionsForm(request.POST, efectivos=efectivos)
        if form.is_valid():
            for code in form.fields:
                marcado = form.cleaned_data[code]
                if marcado != (code in efectivos):
                    services.set_role_permission(request.tenant, role=role, code=code, is_granted=marcado, user=request.user)
            messages.success(request, "Permisos del rol actualizados.")
            return redirect("permissions:role_permissions", role=role)
        return render(request, "permissions/role_permissions.html", {
            "role": role, "role_label": dict(Membership.Role.choices).get(role, role),
            "sections": _sections_for(form),
        })


class UserOverridesView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, user_id):
        require_permission(request, "settings.manage")
        membresia = get_object_or_404(Membership, tenant=request.tenant, user_id=user_id)
        overrides = services.list_user_permission_overrides(request.tenant, membresia.user)
        return render(request, "permissions/user_overrides.html", {
            "membresia": membresia, "overrides": overrides, "form": UserOverrideForm(),
        })

    def post(self, request, user_id):
        require_permission(request, "settings.manage")
        membresia = get_object_or_404(Membership, tenant=request.tenant, user_id=user_id)
        form = UserOverrideForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["permission_code"]
            decision = form.cleaned_data["decision"]
            if decision == "clear":
                services.remove_user_permission_override(request.tenant, target_user=membresia.user, code=code)
                messages.success(request, "Override eliminado — el usuario vuelve a usar los permisos de su rol.")
            else:
                services.set_user_permission_override(
                    request.tenant, target_user=membresia.user, code=code,
                    is_granted=(decision == "grant"), reason=form.cleaned_data["reason"], user=request.user,
                )
                messages.success(request, "Override de usuario guardado.")
            return redirect("permissions:user_overrides", user_id=user_id)
        overrides = services.list_user_permission_overrides(request.tenant, membresia.user)
        return render(request, "permissions/user_overrides.html", {
            "membresia": membresia, "overrides": overrides, "form": form,
        })
