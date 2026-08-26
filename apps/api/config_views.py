"""
Configuración → API de Inventario (FASE 15, commit "Configuración UI +
integración final"). Vistas humanas normales (nunca DRF) — separadas
de `views.py` (los endpoints REST de `/api/v1/`) a propósito: dos
audiencias completamente distintas, misma app."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.permissions.services import require_permission
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import ApiKeyScopesForm
from .models import ApiKey


class ApiKeyConfigView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_permission(request, "api.inventory.read")
        api_key = services.get_api_key(request.tenant)
        return render(request, "api/config.html", {
            "api_key": api_key, "form": ApiKeyScopesForm(initial={"scopes": api_key.scopes if api_key else []}),
            "base_url": "/api/v1/",
        })


class ApiKeyGenerateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        require_permission(request, "api.inventory.manage")
        form = ApiKeyScopesForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Selecciona al menos un scope válido.")
            return redirect("api_config:config")
        try:
            api_key, secreto = services.generate_api_key(request.tenant, user=request.user, scopes=form.cleaned_data["scopes"])
        except services.InvalidApiKeyOperation as error:
            messages.error(request, str(error))
            return redirect("api_config:config")
        return render(request, "api/config.html", {
            "api_key": api_key, "form": ApiKeyScopesForm(initial={"scopes": api_key.scopes}),
            "base_url": "/api/v1/", "secreto_nuevo": secreto,
        })


class ApiKeyRotateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        require_permission(request, "api.inventory.rotate")
        api_key = get_object_or_404(ApiKey, tenant=request.tenant)
        api_key, secreto = services.rotate_api_key(api_key, user=request.user)
        messages.success(request, "Clave rotada correctamente — cópiala ahora, no se mostrará de nuevo.")
        return render(request, "api/config.html", {
            "api_key": api_key, "form": ApiKeyScopesForm(initial={"scopes": api_key.scopes}),
            "base_url": "/api/v1/", "secreto_nuevo": secreto,
        })


class ApiKeyRevokeView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        require_permission(request, "api.inventory.revoke")
        api_key = get_object_or_404(ApiKey, tenant=request.tenant)
        services.revoke_api_key(api_key, user=request.user)
        messages.success(request, "Clave revocada — ya no puede usarse para autenticar.")
        return redirect("api_config:config")


class ApiKeyScopesUpdateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        require_permission(request, "api.inventory.manage")
        api_key = get_object_or_404(ApiKey, tenant=request.tenant)
        form = ApiKeyScopesForm(request.POST)
        if form.is_valid():
            services.set_api_key_scopes(api_key, scopes=form.cleaned_data["scopes"], user=request.user)
            messages.success(request, "Scopes actualizados correctamente.")
        else:
            messages.error(request, "Selecciona al menos un scope válido.")
        return redirect("api_config:config")


class ApiKeyTestConnectionView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        require_permission(request, "api.inventory.read")
        api_key = get_object_or_404(ApiKey, tenant=request.tenant)
        ok, error = services.test_connection(api_key, user=request.user)
        if ok:
            messages.success(request, "Conectado — la clave es válida.")
        else:
            messages.error(request, f"No conectado: {error}")
        return redirect("api_config:config")
