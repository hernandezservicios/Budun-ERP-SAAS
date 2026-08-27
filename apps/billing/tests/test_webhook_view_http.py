"""
FASE 18 — Security Hardening.

Hasta esta fase, ningún test ejercitaba la vista HTTP real del
webhook (`/webhooks/paypal/`, `apps.billing.webhook_views.PayPalWebhookView`)
— todos los tests existentes (`test_webhooks.py`) llaman directo a
`apps.billing.services.process_webhook_event`, la capa de servicio.
Estos tests cubren, a través del `Client` real (igual que PayPal
llamaría a la URL pública), lo que solo vive en la vista: extracción
de cabeceras desde `request.META`, `csrf_exempt` (necesario porque
PayPal nunca envía un token CSRF nuestro), el mapeo de status HTTP
(firma rechazada → 400, cualquier otro resultado → 200) y el rate
limiting por IP."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.billing.models import PayPalWebhookEvent

from ._helpers import build_webhook_body, fake_provider


class PayPalWebhookHttpTests(TestCase):
    def setUp(self):
        # `LocMemCache` persiste entre tests del mismo proceso — se
        # limpia explícitamente el contador de rate limiting (mismo
        # criterio ya usado en `test_provider_paypal.py`).
        cache.clear()

    def _post(self, body, headers=None):
        extra = {
            f"HTTP_{clave.replace('-', '_')}": valor
            for clave, valor in (headers or {}).items()
        }
        return self.client.post(
            reverse("billing_webhooks:paypal"), data=body, content_type="application/json", **extra,
        )

    def test_firma_rechazada_responde_400_sin_necesitar_csrf_token(self):
        """La vista es `csrf_exempt` (PayPal no puede enviar nuestro
        token) — el `Client` de Django por defecto NO envía CSRF, así
        que si la vista lo exigiera esto ya fallaría con 403 en vez de
        400. Confirma ambas cosas a la vez: exención de CSRF y rechazo
        real por firma inválida."""
        body = build_webhook_body(event_id="WH-http-1", event_type="PAYMENT.CAPTURE.COMPLETED", resource={"id": "CAP-http-1"})
        with fake_provider(next_verification=False):
            respuesta = self._post(body)
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(
            PayPalWebhookEvent.objects.get(event_id="WH-http-1").status, PayPalWebhookEvent.Status.REJECTED,
        )

    def test_sin_ninguna_cabecera_de_paypal_tambien_se_rechaza(self):
        """Si faltan TODAS las cabeceras de PayPal (no solo una firma
        incorrecta), la vista nunca debe tratarlo como válido — se
        comporta exactamente igual que una firma inválida, nunca un
        200 ni un 500 sin manejar."""
        body = build_webhook_body(event_id="WH-http-2", event_type="PAYMENT.CAPTURE.COMPLETED", resource={"id": "CAP-http-2"})
        with fake_provider(next_verification=False):
            respuesta = self.client.post(
                reverse("billing_webhooks:paypal"), data=body, content_type="application/json",
            )
        self.assertEqual(respuesta.status_code, 400)

    def test_evento_valido_responde_200(self):
        body = build_webhook_body(event_id="WH-http-3", event_type="PAYMENT.CAPTURE.COMPLETED", resource={"id": "CAP-http-3"})
        with fake_provider(next_verification=True):
            respuesta = self._post(body, headers={
                "PAYPAL-TRANSMISSION-ID": "t-1", "PAYPAL-TRANSMISSION-TIME": "2026-01-01T00:00:00Z",
                "PAYPAL-CERT-URL": "https://api.paypal.com/cert", "PAYPAL-AUTH-ALGO": "SHA256withRSA",
                "PAYPAL-TRANSMISSION-SIG": "firma-de-prueba",
            })
        self.assertEqual(respuesta.status_code, 200)

    def test_supera_el_limite_de_tasa_devuelve_429(self):
        body = build_webhook_body(event_id="WH-http-limite", event_type="PAYMENT.CAPTURE.COMPLETED", resource={"id": "CAP-http-limite"})
        with fake_provider(next_verification=True):
            for _ in range(60):
                self._post(body)
            respuesta_extra = self._post(body)
        self.assertEqual(respuesta_extra.status_code, 429)
