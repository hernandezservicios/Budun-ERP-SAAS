"""
`Permissions-Policy` (FASE 18 — Security Hardening).

Django no tiene un setting nativo para esta cabecera (a diferencia de
`SECURE_REFERRER_POLICY`/`SECURE_CROSS_ORIGIN_OPENER_POLICY`, que ya
Django aplica por defecto — ver `docs/security.md`), así que se añade
como middleware propio en vez de una dependencia nueva
(`django-permissions-policy` u otra) sin necesidad demostrada, mismo
criterio que el resto del proyecto (CLAUDE.md: "Redis solo si una
fase posterior demuestra necesidad real", extendido aquí a cualquier
paquete de terceros).

Política deliberadamente conservadora: deshabilita únicamente
capacidades de navegador que esta aplicación jamás usa (cámara,
micrófono, geolocalización, USB, sensores, cobro vía Payment Request
API del navegador — PayPal se integra aquí exclusivamente por el flujo
Orders API server-to-server + redirect, nunca por esa API del
navegador). Nunca restringe nada que la UI actual utilice — no hay
CSP en esta fase (ver `docs/security.md`, sección "HTTP Security"):
una política de capacidades del navegador es de bajo riesgo porque
solo puede DESHABILITAR APIs no usadas, nunca romper HTML/CSS/JS
existente (a diferencia de CSP, que si se configura mal SÍ puede
bloquear scripts/estilos inline ya usados en las plantillas)."""

_POLICY = (
    "camera=(), microphone=(), geolocation=(), usb=(), "
    "payment=(), magnetometer=(), gyroscope=(), accelerometer=()"
)


class PermissionsPolicyMiddleware:
    """Middleware mínimo (una sola cabecera, sin estado, sin tocar
    `request`) — se registra en `MIDDLEWARE` junto al resto de
    endurecimiento HTTP de `django.middleware.security.SecurityMiddleware`."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", _POLICY)
        return response
