"""
`PayPalProvider` — única implementación real de `PaymentProvider`
(FASE 16). Usa la API REST oficial vigente de PayPal (Orders v2 +
Payments v2 + Webhooks v1), consultada en `developer.paypal.com`
durante esta fase — ver el resumen de endpoints/flujo en
`docs/paypal.md`. No se agrega el SDK oficial de PayPal como
dependencia nueva: se usa `urllib` (librería estándar, sin
dependencias de sistema operativo) para las pocas llamadas HTTP que
esta integración necesita, siguiendo el mismo criterio de mínima
dependencia que ya rigió `reportlab`/`openpyxl`/`Pillow` (cada
dependencia nueva se justifica explícitamente, nunca se agrega "por si
acaso") — documentado como decisión en `docs/paypal.md`.

Endpoints oficiales usados (Sandbox: `api-m.sandbox.paypal.com`, Live:
`api-m.paypal.com`):
- `POST /v1/oauth2/token` — OAuth2 client_credentials.
- `POST /v2/checkout/orders` — crear orden (Orders API v2).
- `POST /v2/checkout/orders/{id}/capture` — capturar/confirmar pago.
- `GET  /v2/checkout/orders/{id}` — consultar una orden.
- `POST /v2/payments/captures/{id}/refund` — reembolsar una captura.
- `POST /v1/notifications/verify-webhook-signature` — verificación
  oficial de firma de webhook (método recomendado por PayPal: reenviar
  transmission-id/time/cert-url/auth-algo/transmission-sig +
  webhook_id + el evento a este endpoint, en vez de reimplementar la
  verificación criptográfica de certificados nosotros mismos).

El access token de OAuth2 NUNCA se persiste en base de datos ni se
audita (ver `docs/phases/PHASE-16-paypal-sandbox.md` sección 10) — se
cachea únicamente en el cache de Django (`LocMemCache`, mismo backend
que `apps.api.throttling`) con el TTL que PayPal reporta menos un
margen de seguridad, y se vuelve a pedir cuando expira o el cache
está frío (p. ej. tras reiniciar el proceso)."""

import base64
import json
import urllib.error
import urllib.request
from decimal import Decimal

from django.core.cache import cache

from .base import (
    CaptureResult,
    CreatedBillingPlan,
    CreatedOrder,
    CreatedProduct,
    CreatedRecurringSubscription,
    PaymentProvider,
    PaymentProviderError,
    RecurringSubscriptionStatus,
    RefundResult,
    WebhookVerification,
)

_SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
_LIVE_BASE = "https://api-m.paypal.com"
_TIMEOUT_SECONDS = 20
_TOKEN_CACHE_PREFIX = "billing:paypal:oauth_token:"


class PayPalProvider(PaymentProvider):
    def __init__(self, *, client_id, client_secret, environment, webhook_id):
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""
        self.environment = (environment or "SANDBOX").strip().upper()
        self.webhook_id = webhook_id or ""

    # -- infraestructura HTTP -------------------------------------------------

    def _base_url(self):
        return _LIVE_BASE if self.environment == "LIVE" else _SANDBOX_BASE

    def _cache_key(self):
        return f"{_TOKEN_CACHE_PREFIX}{self.environment}"

    def _request(self, method, path, *, body=None, headers=None, form=False):
        url = f"{self._base_url()}{path}"
        data = None
        request_headers = dict(headers or {})
        if body is not None:
            if form:
                data = body.encode("utf-8")
                request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            else:
                data = json.dumps(body).encode("utf-8")
                request_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as response:
                raw = response.read()
                return response.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                parsed = json.loads(raw) if raw else {}
            except ValueError:
                parsed = {}
            # El mensaje de error de PayPal nunca incluye las credenciales
            # que nosotros enviamos (no las "hace eco") — es seguro
            # propagar `name`/`message` para diagnóstico, nunca el cuerpo
            # crudo de nuestra propia request.
            motivo = parsed.get("message") or parsed.get("error_description") or parsed.get("name") or str(error.code)
            raise PaymentProviderError(f"PayPal respondió {error.code}: {motivo}") from None
        except urllib.error.URLError as error:
            raise PaymentProviderError(f"No se pudo conectar con PayPal: {error.reason}") from None
        except (TimeoutError, OSError) as error:
            raise PaymentProviderError(f"Tiempo de espera agotado al conectar con PayPal: {error}") from None

    def _get_access_token(self, *, force_refresh=False):
        if not force_refresh:
            cached = cache.get(self._cache_key())
            if cached:
                return cached
        if not self.client_id or not self.client_secret:
            raise PaymentProviderError("Faltan credenciales de PayPal (PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET).")
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("ascii")).decode("ascii")
        _status, payload = self._request(
            "POST", "/v1/oauth2/token",
            body="grant_type=client_credentials", form=True,
            headers={"Authorization": f"Basic {basic}"},
        )
        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in") or 0)
        if not token:
            raise PaymentProviderError("PayPal no devolvió un access token válido.")
        # Margen de seguridad de 60s para no operar con un token a punto
        # de expirar entre la lectura del cache y el uso real.
        cache.set(self._cache_key(), token, timeout=max(60, expires_in - 60))
        return token

    def _auth_headers(self, *, idempotency_key=None, force_refresh_token=False):
        token = self._get_access_token(force_refresh=force_refresh_token)
        headers = {"Authorization": f"Bearer {token}"}
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key
        return headers

    def _call_with_token_retry(self, do_call):
        """Reintenta UNA vez con un token fresco si PayPal responde 401
        (token vencido justo entre la lectura del cache y la llamada real)
        — nunca más de un reintento, para no ocultar un fallo real de
        credenciales detrás de reintentos infinitos."""
        try:
            return do_call(force_refresh_token=False)
        except PaymentProviderError as error:
            if "401" in str(error):
                return do_call(force_refresh_token=True)
            raise

    # -- Orders v2 -------------------------------------------------------------

    def create_order(self, *, amount, currency, reference_id, description, return_url, cancel_url, idempotency_key):
        def _do(force_refresh_token):
            headers = self._auth_headers(idempotency_key=idempotency_key, force_refresh_token=force_refresh_token)
            body = {
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": str(reference_id)[:256],
                    "description": (description or "")[:127],
                    "amount": {"currency_code": currency, "value": f"{Decimal(amount):.2f}"},
                }],
                "application_context": {
                    "brand_name": "Budun ERP",
                    "user_action": "PAY_NOW",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            }
            _status, payload = self._request("POST", "/v2/checkout/orders", body=body, headers=headers)
            return payload

        payload = self._call_with_token_retry(_do)
        approve_url = ""
        for link in payload.get("links", []):
            if link.get("rel") in ("approve", "payer-action"):
                approve_url = link.get("href", "")
                break
        return CreatedOrder(
            external_order_id=payload.get("id", ""),
            approve_url=approve_url,
            status=payload.get("status", ""),
            raw_status=payload.get("status", ""),
        )

    def capture_order(self, *, external_order_id, idempotency_key):
        def _do(force_refresh_token):
            headers = self._auth_headers(idempotency_key=idempotency_key, force_refresh_token=force_refresh_token)
            _status, payload = self._request(
                "POST", f"/v2/checkout/orders/{external_order_id}/capture", body={}, headers=headers,
            )
            return payload

        payload = self._call_with_token_retry(_do)
        captura = {}
        try:
            captura = payload["purchase_units"][0]["payments"]["captures"][0]
        except (KeyError, IndexError, TypeError):
            pass
        amount_info = captura.get("amount", {})
        return CaptureResult(
            external_capture_id=captura.get("id", ""),
            status=captura.get("status", payload.get("status", "")),
            amount=Decimal(amount_info.get("value", "0")) if amount_info.get("value") else Decimal("0"),
            currency=amount_info.get("currency_code", ""),
            raw_status=payload.get("status", ""),
        )

    def get_order(self, *, external_order_id):
        def _do(force_refresh_token):
            headers = self._auth_headers(force_refresh_token=force_refresh_token)
            _status, payload = self._request("GET", f"/v2/checkout/orders/{external_order_id}", headers=headers)
            return payload

        return self._call_with_token_retry(_do)

    # -- Payments v2 (refunds) --------------------------------------------------

    def refund_capture(self, *, external_capture_id, amount, currency, idempotency_key):
        def _do(force_refresh_token):
            headers = self._auth_headers(idempotency_key=idempotency_key, force_refresh_token=force_refresh_token)
            body = {}
            if amount is not None:
                body["amount"] = {"value": f"{Decimal(amount):.2f}", "currency_code": currency}
            _status, payload = self._request(
                "POST", f"/v2/payments/captures/{external_capture_id}/refund", body=body, headers=headers,
            )
            return payload

        payload = self._call_with_token_retry(_do)
        return RefundResult(
            external_refund_id=payload.get("id", ""),
            status=payload.get("status", ""),
            raw_status=payload.get("status", ""),
        )

    # -- Webhooks -----------------------------------------------------------

    def verify_webhook_signature(self, *, headers, raw_body):
        if not self.webhook_id:
            raise PaymentProviderError("PAYPAL_WEBHOOK_ID no está configurado — no se puede verificar la firma.")
        try:
            webhook_event = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return WebhookVerification(verified=False, verification_status="INVALID_BODY")

        def _do(force_refresh_token):
            auth_headers = self._auth_headers(force_refresh_token=force_refresh_token)
            body = {
                "transmission_id": headers.get("PAYPAL-TRANSMISSION-ID", ""),
                "transmission_time": headers.get("PAYPAL-TRANSMISSION-TIME", ""),
                "cert_url": headers.get("PAYPAL-CERT-URL", ""),
                "auth_algo": headers.get("PAYPAL-AUTH-ALGO", ""),
                "transmission_sig": headers.get("PAYPAL-TRANSMISSION-SIG", ""),
                "webhook_id": self.webhook_id,
                "webhook_event": webhook_event,
            }
            _status, payload = self._request(
                "POST", "/v1/notifications/verify-webhook-signature", body=body, headers=auth_headers,
            )
            return payload

        payload = self._call_with_token_retry(_do)
        estado = payload.get("verification_status", "")
        return WebhookVerification(verified=(estado == "SUCCESS"), verification_status=estado)

    # -- Cobro recurrente: Catalog Products + Billing Plans + Subscriptions
    # (FASE DE CORRECCIÓN 2C) -------------------------------------------------
    #
    # Endpoints oficiales consultados en developer.paypal.com (septiembre
    # 2026) para esta corrección:
    # - `POST /v1/catalogs/products` — crear el producto (una vez por
    #   `PlanVersion`, nunca por tenant).
    # - `POST /v1/billing/plans` — crear el plan de facturación (precio +
    #   frecuencia + `payment_failure_threshold`, también una vez por
    #   `PlanVersion`).
    # - `POST /v1/billing/subscriptions` — crear la suscripción real para
    #   UN tenant (`application_context.return_url`/`cancel_url`, mismo
    #   patrón de aprobación por redirect que Orders API v2).
    # - `GET /v1/billing/subscriptions/{id}` — reconciliar el estado
    #   síncronamente al volver del checkout (nunca depender solo del
    #   webhook, que no puede llegar a localhost — ver docs/paypal.md).
    # - `POST /v1/billing/subscriptions/{id}/cancel` — cancelar del lado
    #   de PayPal cuando el tenant cancela en Budun.

    def create_product(self, *, name, description, idempotency_key):
        def _do(force_refresh_token):
            headers = self._auth_headers(idempotency_key=idempotency_key, force_refresh_token=force_refresh_token)
            body = {"name": name[:127], "description": (description or "")[:256], "type": "SERVICE", "category": "SOFTWARE"}
            _status, payload = self._request("POST", "/v1/catalogs/products", body=body, headers=headers)
            return payload

        payload = self._call_with_token_retry(_do)
        return CreatedProduct(external_product_id=payload.get("id", ""))

    def create_billing_plan(self, *, product_id, name, amount, currency, frequency, payment_failure_threshold, idempotency_key):
        interval_unit = "YEAR" if frequency == "annual" else "MONTH"

        def _do(force_refresh_token):
            headers = self._auth_headers(idempotency_key=idempotency_key, force_refresh_token=force_refresh_token)
            body = {
                "product_id": product_id,
                "name": name[:127],
                "billing_cycles": [{
                    "frequency": {"interval_unit": interval_unit, "interval_count": 1},
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,  # 0 = indefinido, hasta que se cancele.
                    "pricing_scheme": {"fixed_price": {"value": f"{Decimal(amount):.2f}", "currency_code": currency}},
                }],
                "payment_preferences": {
                    "auto_bill_outstanding": True,
                    "payment_failure_threshold": int(payment_failure_threshold),
                },
            }
            _status, payload = self._request("POST", "/v1/billing/plans", body=body, headers=headers)
            return payload

        payload = self._call_with_token_retry(_do)
        return CreatedBillingPlan(external_plan_id=payload.get("id", ""))

    def create_recurring_subscription(self, *, plan_id, reference_id, return_url, cancel_url, idempotency_key):
        def _do(force_refresh_token):
            headers = self._auth_headers(idempotency_key=idempotency_key, force_refresh_token=force_refresh_token)
            body = {
                "plan_id": plan_id,
                "custom_id": str(reference_id)[:127],
                "application_context": {
                    "brand_name": "Budun ERP",
                    "user_action": "SUBSCRIBE_NOW",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            }
            _status, payload = self._request("POST", "/v1/billing/subscriptions", body=body, headers=headers)
            return payload

        payload = self._call_with_token_retry(_do)
        approve_url = ""
        for link in payload.get("links", []):
            if link.get("rel") == "approve":
                approve_url = link.get("href", "")
                break
        return CreatedRecurringSubscription(
            external_subscription_id=payload.get("id", ""), approve_url=approve_url, status=payload.get("status", ""),
        )

    def get_recurring_subscription(self, *, external_subscription_id):
        def _do(force_refresh_token):
            headers = self._auth_headers(force_refresh_token=force_refresh_token)
            _status, payload = self._request("GET", f"/v1/billing/subscriptions/{external_subscription_id}", headers=headers)
            return payload

        payload = self._call_with_token_retry(_do)
        return RecurringSubscriptionStatus(
            external_subscription_id=payload.get("id", external_subscription_id), status=payload.get("status", ""), raw=payload,
        )

    def cancel_recurring_subscription(self, *, external_subscription_id, reason, idempotency_key):
        def _do(force_refresh_token):
            headers = self._auth_headers(idempotency_key=idempotency_key, force_refresh_token=force_refresh_token)
            body = {"reason": (reason or "Cancelado por el tenant")[:128]}
            self._request(
                "POST", f"/v1/billing/subscriptions/{external_subscription_id}/cancel", body=body, headers=headers,
            )

        self._call_with_token_retry(_do)

    # -- Test Connection ------------------------------------------------------

    def test_connection(self):
        try:
            self._get_access_token(force_refresh=True)
            return True, ""
        except PaymentProviderError as error:
            return False, str(error)
