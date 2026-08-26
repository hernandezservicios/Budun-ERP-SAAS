"""
Configuración → Integraciones (ampliación final de FASE 15, ver
`docs/integrations.md`). Vistas humanas normales (nunca DRF) —
gestiona `Integration` (credenciales de la Catalog API), separado de
`config_views.py` (que gestiona `ApiKey`, la Inventory API
administrativa): dos capas, dos pantallas de Configuración."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.permissions.services import require_permission
from apps.tenants.permissions import TenantRequiredMixin

from . import integration_services
from .integration_forms import IntegrationCreateForm, IntegrationScopesForm
from .models import Integration


class IntegrationListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_permission(request, "api.integration.view")
        return render(request, "api/integration_list.html", {
            "integrations": integration_services.list_integrations(request.tenant),
            "form": IntegrationCreateForm(),
        })


class IntegrationCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        require_permission(request, "api.integration.create")
        form = IntegrationCreateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa el nombre y los scopes seleccionados.")
            return redirect("api_integrations:list")
        try:
            integration, secreto = integration_services.create_integration(
                request.tenant, user=request.user, name=form.cleaned_data["name"],
                provider=form.cleaned_data["provider"], scopes=form.cleaned_data["scopes"],
            )
        except integration_services.InvalidIntegrationOperation as error:
            messages.error(request, str(error))
            return redirect("api_integrations:list")
        return render(request, "api/integration_detail.html", {
            "integration": integration, "scopes_form": IntegrationScopesForm(initial={"scopes": integration.scopes}),
            "secreto_nuevo": secreto,
        })


class IntegrationDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        require_permission(request, "api.integration.view")
        integration = get_object_or_404(Integration, pk=pk, tenant=request.tenant)
        return render(request, "api/integration_detail.html", {
            "integration": integration, "scopes_form": IntegrationScopesForm(initial={"scopes": integration.scopes}),
        })


class IntegrationRotateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        require_permission(request, "api.integration.rotate")
        integration = get_object_or_404(Integration, pk=pk, tenant=request.tenant)
        integration, secreto = integration_services.rotate_integration_credential(integration, user=request.user)
        messages.success(request, "Credencial rotada correctamente — cópiala ahora, no se mostrará de nuevo.")
        return render(request, "api/integration_detail.html", {
            "integration": integration, "scopes_form": IntegrationScopesForm(initial={"scopes": integration.scopes}),
            "secreto_nuevo": secreto,
        })


class IntegrationRevokeView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        require_permission(request, "api.integration.revoke")
        integration = get_object_or_404(Integration, pk=pk, tenant=request.tenant)
        integration_services.revoke_integration(integration, user=request.user)
        messages.success(request, "Integración revocada — su credencial ya no puede usarse para autenticar.")
        return redirect("api_integrations:detail", pk=pk)


class IntegrationToggleView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        require_permission(request, "api.integration.update")
        integration = get_object_or_404(Integration, pk=pk, tenant=request.tenant)
        integration_services.set_integration_enabled(integration, is_enabled=not integration.is_enabled, user=request.user)
        messages.success(request, "Integración habilitada." if integration.is_enabled else "Integración deshabilitada.")
        return redirect("api_integrations:detail", pk=pk)


class IntegrationScopesUpdateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        require_permission(request, "api.integration.update")
        integration = get_object_or_404(Integration, pk=pk, tenant=request.tenant)
        form = IntegrationScopesForm(request.POST)
        if form.is_valid():
            integration_services.set_integration_scopes(integration, scopes=form.cleaned_data["scopes"], user=request.user)
            messages.success(request, "Scopes actualizados correctamente.")
        else:
            messages.error(request, "Selecciona al menos un scope válido.")
        return redirect("api_integrations:detail", pk=pk)


class IntegrationTestConnectionView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        require_permission(request, "api.integration.test")
        integration = get_object_or_404(Integration, pk=pk, tenant=request.tenant)
        ok, error = integration_services.test_integration_connection(integration, user=request.user)
        if ok:
            messages.success(request, "Conectado — la integración es válida.")
        else:
            messages.error(request, f"No conectado: {error}")
        return redirect("api_integrations:detail", pk=pk)
