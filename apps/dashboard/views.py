from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView

from .services import obtener_datos_del_panel


class DashboardView(LoginRequiredMixin, TemplateView):
    """Panel administrativo (FASE 7).

    Seguridad (verificado también en `tests.py`):
    - `LoginRequiredMixin` exige un usuario autenticado.
    - Si el usuario autenticado no tiene un tenant activo todavía
      (`request.tenant` es `None`, resuelto por `TenantMiddleware` en
      FASE 3), se redirige a onboarding en vez de mostrar un panel vacío
      sin sentido o un error. No se usa `TenantRequiredMixin` (que
      respondería 403) porque, en el flujo normal del producto, llegar
      aquí sin tenant significa que falta completar el onboarding, no
      que se intente acceder a algo prohibido.
    - Todas las consultas de `services.py` reciben `tenant` de forma
      explícita y filtran por él; el Panel nunca ejecuta una consulta
      global de datos tenant-aware.
    """

    template_name = "dashboard/panel.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and getattr(request, "tenant", None) is None:
            return redirect("accounts:onboarding")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(obtener_datos_del_panel(self.request.tenant))
        context["tenant"] = self.request.tenant
        context["membership"] = getattr(self.request, "membership", None)
        return context
