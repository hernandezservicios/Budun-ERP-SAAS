"""
`BillingStatusMiddleware` (FASE 17, ver `docs/billing.md` sección
"Estado del tenant"). Único punto centralizado que bloquea la
operación completa del ERP mientras `Tenant.billing_status` no sea
`ACTIVE`/`PAST_DUE` (sección 36 de la fase) — deliberadamente un
MIDDLEWARE nuevo, NO una modificación de `apps.tenants.permissions.
require_tenant`/`TenantRequiredMixin` (el choke point ya usado por
~100 vistas existentes): así el retrofit es de bajo riesgo (nunca
lanza una excepción que el código existente no espere, solo un
redirect suave) y el `default=ACTIVE` de `Tenant.billing_status`
garantiza que absolutamente NINGÚN tenant preexistente (ni fixture de
test) cambia de comportamiento — la redirección solo puede dispararse
para un tenant cuyo estado de Billing sea explícitamente distinto de
ACTIVE/PAST_DUE, lo cual solo ocurre a partir de esta fase."""

from django.shortcuts import redirect

# Prefijos exentos: el propio Portal de Billing (para que el tenant
# pueda ver su estado/pagar), cuentas (login/logout/registro/perfil),
# plataforma/webhooks/admin (actores distintos de un tenant operando) y
# estáticos.
_PREFIJOS_EXENTOS = ("/facturacion/", "/cuentas/", "/plataforma/", "/webhooks/", "/admin/", "/static/")


class BillingStatusMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is not None and tenant.billing_status_blocks_operation:
            if not any(request.path.startswith(prefijo) for prefijo in _PREFIJOS_EXENTOS):
                return redirect("billing_portal:status")
        return self.get_response(request)
