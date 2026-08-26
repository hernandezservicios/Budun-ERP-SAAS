from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View

from apps.permissions.services import require_permission
from apps.tenants.permissions import TenantRequiredMixin

from .pricing import PLANS


def home(request):
    """Landing pública del producto (FASE 6 — Landing + Pricing).

    Reemplaza la página de verificación técnica de FASE 1 ("Fundación del
    proyecto lista"), que ya cumplió su propósito. La URL (`core:home`,
    `/`) y el nombre de la vista se mantienen sin cambios para no romper
    los enlaces/redirects existentes (logout, navbar, tests).
    """
    contexto = {
        "planes": PLANS,
    }
    return render(request, "core/landing.html", contexto)


def design_system(request):
    """Página de referencia interna del Design System (FASE 5).

    Muestra todos los componentes reutilizables con datos de ejemplo, para
    poder verificar consistencia visual, accesibilidad y responsive con
    evidencia real (HTML servido de verdad, no una maqueta aparte). No es
    una página de negocio ni se enlaza desde la navegación principal.
    """
    return render(request, "core/design_system.html")


class SettingsHomeView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Hub «Configuración» (FASE 15).

    Punto de entrada único para las secciones administrativas del
    tenant. Hoy enlaza Roles y Permisos (`apps.permissions`); la
    sección «API de Inventario» (`docs/api-inventory.md`) se agrega
    aquí mismo cuando se construya `apps.api` — nunca una segunda
    página de configuración paralela.

    El acceso de LECTURA a esta página exige `settings.view`; cada
    sección enlazada aplica su propio permiso más estricto
    (`settings.manage` para Roles y Permisos) al entrar.
    """

    def get(self, request):
        require_permission(request, "settings.view")
        return render(request, "core/settings_home.html")
