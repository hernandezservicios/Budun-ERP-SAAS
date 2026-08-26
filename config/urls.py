"""
URLs raíz del proyecto.

FASE 8 agregó Productos e Inventario (`/inventario/...`). FASE 9 agregó
Clientes y Proveedores (`/clientes/...`, `/proveedores/...`, montado en
la raíz porque el propio `apps.customers.urls` ya define esos prefijos).
FASE 10 agrega el motor comercial (`/cotizaciones/...`, `/proformas/...`,
`/ventas/...`, `/reservas/...`, mismo patrón de montaje en la raíz). Cada
fase futura agregará sus propias rutas (p. ej. `/api/v1/` en FASE 15)
sin anticiparlas aquí.

Deliberadamente NO se sirve `MEDIA_URL`/`MEDIA_ROOT` aquí (ni en
desarrollo ni en producción): los documentos de Clientes/Proveedores y
los adjuntos de Cotizaciones/Proformas/Ventas solo se descargan a través
de una vista protegida (tenant + login + pertenencia verificados), nunca
como archivo estático público — ver `apps/customers/views.py`,
`apps/sales/views.py` y `docs/customer-documents.md`.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuentas/", include("apps.accounts.urls")),
    path("panel/", include("apps.dashboard.urls")),
    path("inventario/", include("apps.inventory.urls")),
    path("", include("apps.customers.urls")),
    path("", include("apps.sales.urls")),
    path("", include("apps.approvals.urls")),
    path("pos/", include("apps.pos.urls")),
    path("compras/", include("apps.purchases.urls")),
    path("gastos/", include("apps.expenses.urls")),
    path("rrhh/", include("apps.hr.urls")),
    path("nomina/", include("apps.payroll.urls")),
    path("contabilidad/", include("apps.accounting.urls")),
    path("reportes/", include("apps.reports.urls")),
    path("configuracion/permisos/", include("apps.permissions.urls")),
    path("configuracion/auditoria/", include("apps.audit.urls")),
    path("api/v1/", include("apps.api.urls")),
    path("", include("apps.core.urls")),
]
