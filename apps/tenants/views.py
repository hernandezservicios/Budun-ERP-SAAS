"""
Vista interna de verificación (FASE 3).

`whoami_view` NO está registrada en `config/urls.py`: todavía no existe
ningún flujo de login real (eso es FASE 4 — Authentication), así que no
tendría sentido exponer una URL pública que solo un usuario autenticado
podría usar. Existe únicamente para poder probar el aislamiento también a
nivel de vista (no solo de manager/queryset), tal como exige el criterio
de aceptación de FASE 3 — ver `tests.py`, que la invoca directamente con
`RequestFactory`.
"""

from django.http import JsonResponse

from .permissions import require_tenant
from .services import list_isolation_samples_for_current_tenant


def whoami_view(request):
    tenant = require_tenant(request)
    registros = [muestra.label for muestra in list_isolation_samples_for_current_tenant()]
    return JsonResponse({"tenant_slug": tenant.slug, "registros": registros})
