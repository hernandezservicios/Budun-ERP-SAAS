"""
Pruebas de la adaptación REAL de PayPal (`PayPalProvider`) — simulan
únicamente la capa HTTP (`urllib.request.urlopen`), nunca la lógica de
negocio de `apps.billing.services` (esa se prueba aparte con
`FakePayPalProvider`, ver `_helpers.py`). Verifican que el adaptador
compone correctamente las requests oficiales (OAuth2, Orders v2,
Payments v2 refund, verify-webhook-signature) y que nunca expone el
client secret ni el access token en un mensaje de error."""

import io
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.core.cache import cache
from django.test import TestCase

from apps.billing.providers.base import PaymentProviderError
from apps.billing.providers.paypal import PayPalProvider


def _fake_response(status, payload):
    mock = MagicMock()
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    mock.status = status
    mock.read.return_value = json.dumps(payload).encode("utf-8")
    return mock


def _fake_http_error(code, payload):
    body = json.dumps(payload).encode("utf-8")
    return HTTPError(url="https://api-m.sandbox.paypal.com/x", code=code, msg="error", hdrs=None, fp=io.BytesIO(body))


class PayPalProviderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.provider = PayPalProvider(client_id="cid-de-prueba", client_secret="secreto-de-prueba", environment="SANDBOX", webhook_id="WH-ID")

    @patch("apps.billing.providers.paypal.urllib.request.urlopen")
    def test_create_order_compone_request_oficial_y_parsea_approve_url(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response(200, {"access_token": "tok-123", "expires_in": 32000}),
            _fake_response(201, {"id": "ORDER-XYZ", "status": "CREATED", "links": [
                {"rel": "self", "href": "https://api/orders/ORDER-XYZ"},
                {"rel": "approve", "href": "https://sandbox.paypal.test/approve?token=ORDER-XYZ"},
            ]}),
        ]
        resultado = self.provider.create_order(
            amount=Decimal("29.00"), currency="USD", reference_id="1", description="Plan Profesional",
            return_url="https://x.test/return", cancel_url="https://x.test/cancel", idempotency_key="idem-crear-1",
        )
        self.assertEqual(resultado.external_order_id, "ORDER-XYZ")
        self.assertEqual(resultado.approve_url, "https://sandbox.paypal.test/approve?token=ORDER-XYZ")

        oauth_request = mock_urlopen.call_args_list[0][0][0]
        self.assertEqual(oauth_request.full_url, "https://api-m.sandbox.paypal.com/v1/oauth2/token")
        self.assertTrue(oauth_request.get_header("Authorization").startswith("Basic "))

        orden_request = mock_urlopen.call_args_list[1][0][0]
        self.assertEqual(orden_request.full_url, "https://api-m.sandbox.paypal.com/v2/checkout/orders")
        self.assertEqual(orden_request.get_header("Paypal-request-id"), "idem-crear-1")
        self.assertEqual(orden_request.get_header("Authorization"), "Bearer tok-123")
        cuerpo = json.loads(orden_request.data.decode("utf-8"))
        self.assertEqual(cuerpo["purchase_units"][0]["amount"]["value"], "29.00")
        self.assertEqual(cuerpo["purchase_units"][0]["amount"]["currency_code"], "USD")

    @patch("apps.billing.providers.paypal.urllib.request.urlopen")
    def test_capture_order_extrae_la_captura_del_primer_purchase_unit(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response(200, {"access_token": "tok-abc", "expires_in": 32000}),
            _fake_response(201, {
                "status": "COMPLETED",
                "purchase_units": [{"payments": {"captures": [
                    {"id": "CAPTURE-1", "status": "COMPLETED", "amount": {"value": "29.00", "currency_code": "USD"}},
                ]}}],
            }),
        ]
        resultado = self.provider.capture_order(external_order_id="ORDER-XYZ", idempotency_key="idem-cap-1")
        self.assertEqual(resultado.external_capture_id, "CAPTURE-1")
        self.assertEqual(resultado.status, "COMPLETED")
        self.assertEqual(resultado.amount, Decimal("29.00"))

    @patch("apps.billing.providers.paypal.urllib.request.urlopen")
    def test_refund_capture_envia_monto_cuando_es_parcial(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response(200, {"access_token": "tok-def", "expires_in": 32000}),
            _fake_response(201, {"id": "REFUND-1", "status": "COMPLETED"}),
        ]
        resultado = self.provider.refund_capture(external_capture_id="CAPTURE-1", amount=Decimal("10.00"), currency="USD", idempotency_key="idem-ref-1")
        self.assertEqual(resultado.external_refund_id, "REFUND-1")
        refund_request = mock_urlopen.call_args_list[1][0][0]
        cuerpo = json.loads(refund_request.data.decode("utf-8"))
        self.assertEqual(cuerpo["amount"]["value"], "10.00")

    @patch("apps.billing.providers.paypal.urllib.request.urlopen")
    def test_verify_webhook_signature_envia_headers_oficiales_y_webhook_id(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _fake_response(200, {"access_token": "tok-ghi", "expires_in": 32000}),
            _fake_response(200, {"verification_status": "SUCCESS"}),
        ]
        headers = {
            "PAYPAL-TRANSMISSION-ID": "tid-1", "PAYPAL-TRANSMISSION-TIME": "2026-01-01T00:00:00Z",
            "PAYPAL-CERT-URL": "https://api.paypal.com/cert", "PAYPAL-AUTH-ALGO": "SHA256withRSA",
            "PAYPAL-TRANSMISSION-SIG": "firma-simulada",
        }
        cuerpo_evento = json.dumps({"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"}).encode("utf-8")
        resultado = self.provider.verify_webhook_signature(headers=headers, raw_body=cuerpo_evento)
        self.assertTrue(resultado.verified)
        verify_request = mock_urlopen.call_args_list[1][0][0]
        cuerpo_enviado = json.loads(verify_request.data.decode("utf-8"))
        self.assertEqual(cuerpo_enviado["webhook_id"], "WH-ID")
        self.assertEqual(cuerpo_enviado["transmission_id"], "tid-1")
        self.assertEqual(cuerpo_enviado["webhook_event"]["id"], "WH-1")

    @patch("apps.billing.providers.paypal.urllib.request.urlopen")
    def test_credenciales_invalidas_nunca_exponen_el_secreto_en_el_error(self, mock_urlopen):
        mock_urlopen.side_effect = _fake_http_error(401, {"error": "invalid_client", "error_description": "Client Authentication failed"})
        with self.assertRaises(PaymentProviderError) as ctx:
            self.provider._get_access_token(force_refresh=True)
        mensaje = str(ctx.exception)
        self.assertIn("401", mensaje)
        self.assertNotIn("secreto-de-prueba", mensaje)
        self.assertNotIn("cid-de-prueba", mensaje)

    @patch("apps.billing.providers.paypal.urllib.request.urlopen")
    def test_test_connection_devuelve_false_sin_lanzar_con_credenciales_invalidas(self, mock_urlopen):
        mock_urlopen.side_effect = _fake_http_error(401, {"error": "invalid_client"})
        ok, error = self.provider.test_connection()
        self.assertFalse(ok)
        self.assertTrue(error)
        self.assertNotIn("secreto-de-prueba", error)

    @patch("apps.billing.providers.paypal.urllib.request.urlopen")
    def test_token_expirado_se_reintenta_una_vez_con_token_fresco(self, mock_urlopen):
        # Token viejo ya en cache (simulado): la primera llamada real
        # falla con 401, se refresca el token UNA vez, y la segunda
        # llamada real con el token nuevo sí funciona.
        cache.set(self.provider._cache_key(), "token-viejo", timeout=300)
        mock_urlopen.side_effect = [
            _fake_http_error(401, {"error": "invalid_token"}),
            _fake_response(200, {"access_token": "token-nuevo", "expires_in": 32000}),
            _fake_response(201, {"id": "ORDER-RETRY", "status": "CREATED", "links": [{"rel": "approve", "href": "https://x/approve"}]}),
        ]
        resultado = self.provider.create_order(
            amount=Decimal("29.00"), currency="USD", reference_id="1", description="Plan",
            return_url="https://x/return", cancel_url="https://x/cancel", idempotency_key="idem-retry",
        )
        self.assertEqual(resultado.external_order_id, "ORDER-RETRY")
        self.assertEqual(mock_urlopen.call_count, 3)
