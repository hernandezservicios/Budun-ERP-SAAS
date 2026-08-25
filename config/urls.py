"""
URLs raíz del proyecto.

FASE 4 agrega las rutas de autenticación (`/cuentas/...`). Cada fase
futura agregará sus propias rutas (p. ej. `/api/v1/` en FASE 15) sin
anticiparlas aquí.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuentas/", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
]
