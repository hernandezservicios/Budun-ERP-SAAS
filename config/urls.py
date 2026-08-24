"""
URLs raíz del proyecto.

FASE 1: solo la app `core` (fundación). Cada fase futura agregará sus propias
rutas (p. ej. `/api/v1/` en FASE 15, autenticación en FASE 4, etc.) sin
anticiparlas aquí.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
]
