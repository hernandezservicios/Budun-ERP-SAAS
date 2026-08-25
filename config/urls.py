"""
URLs raíz del proyecto.

FASE 7 agrega el Panel (`/panel/`). Cada fase futura agregará sus propias
rutas (p. ej. `/api/v1/` en FASE 15) sin anticiparlas aquí.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuentas/", include("apps.accounts.urls")),
    path("panel/", include("apps.dashboard.urls")),
    path("", include("apps.core.urls")),
]
