"""
Webhook público de PayPal (FASE 16). Sin autenticación por sesión/API
key — PayPal no puede enviar un Bearer token nuestro; la seguridad
reside enteramente en la verificación oficial de firma que hace
`apps.billing.services.process_webhook_event` (nunca en confiar en el
remitente por su IP o cualquier otra heurística). La vista NUNCA toca
el ORM directamente (sección 7 de la fase): solo captura
headers/cuerpo crudo y delega."""

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import PayPalWebhookEvent
from .services import process_webhook_event

_LIMITE_POR_MINUTO = 60


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "desconocida"


def _limite_excedido(request):
    """Throttle simple basado en el cache ya configurado (`LocMemCache`,
    mismo backend que `apps.api.throttling`) — un endpoint público sin
    autenticación no debe poder ser bombardeado sin límite alguno,
    aunque la verificación de firma ya rechace cualquier payload
    falsificado (defensa en profundidad, sección 31 de la fase:
    performance, sin N+1)."""
    key = f"billing:paypal:webhook_rate:{_client_ip(request)}"
    try:
        contador = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=60)
        contador = 1
    return contador > _LIMITE_POR_MINUTO


@method_decorator(csrf_exempt, name="dispatch")
class PayPalWebhookView(View):
    http_method_names = ["post"]

    def post(self, request):
        if _limite_excedido(request):
            return HttpResponse(status=429)

        headers = {
            "PAYPAL-TRANSMISSION-ID": request.META.get("HTTP_PAYPAL_TRANSMISSION_ID", ""),
            "PAYPAL-TRANSMISSION-TIME": request.META.get("HTTP_PAYPAL_TRANSMISSION_TIME", ""),
            "PAYPAL-CERT-URL": request.META.get("HTTP_PAYPAL_CERT_URL", ""),
            "PAYPAL-AUTH-ALGO": request.META.get("HTTP_PAYPAL_AUTH_ALGO", ""),
            "PAYPAL-TRANSMISSION-SIG": request.META.get("HTTP_PAYPAL_TRANSMISSION_SIG", ""),
        }
        evento = process_webhook_event(headers=headers, raw_body=request.body)

        # PayPal reintenta automáticamente cualquier respuesta que no sea
        # 2xx. Una firma inválida/rechazada (posible evento falsificado)
        # devuelve 400 — no es un evento que debamos "aceptar" nunca,
        # reintente o no. Cualquier otro resultado (procesado, duplicado,
        # ignorado por no tener transacción asociada, o un error interno
        # ya registrado) responde 200: la idempotencia real vive en la
        # base de datos (`PayPalWebhookEvent.event_id` único), así que un
        # reintento posterior de PayPal nunca duplica el efecto.
        status_http = 400 if evento.status == PayPalWebhookEvent.Status.REJECTED else 200
        return JsonResponse({"received": True, "status": evento.status}, status=status_http)
