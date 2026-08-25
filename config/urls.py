"""
URLs raíz del proyecto.

FASE 8 agregó Productos e Inventario (`/inventario/...`). FASE 9 agrega
Clientes y Proveedores (`/clientes/...`, `/proveedores/...`, montado en
la raíz porque el propio `apps.customers.urls` ya define esos prefijos).
Cada fase futura agregará sus propias rutas (p. ej. `/api/v1/` en
FASE 15) sin anticiparlas aquí.

Deliberadamente NO se sirve `MEDIA_URL`/`MEDIA_ROOT` aquí (ni en
desarrollo ni en producción): los documentos de Clientes/Proveedores
solo se descargan a través de una vista protegida (tenant + login +
pertenencia verificados), nunca como archivo estático público — ver
`apps/customers/views.py` y `docs/customer-documents.md`.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuentas/", include("apps.accounts.urls")),
    path("panel/", include("apps.dashboard.urls")),
    path("inventario/", include("apps.inventory.urls")),
    path("", include("apps.customers.urls")),
    path("", include("apps.core.urls")),
]
