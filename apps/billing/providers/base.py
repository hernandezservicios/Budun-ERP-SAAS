"""
Interfaz genérica que todo proveedor de pagos de Billing SaaS debe
implementar (FASE 16). `apps.billing.services` solo conoce esta
interfaz — nunca un detalle de PayPal (nombres de campos JSON, URLs,
headers) fuera de `.paypal`. Esto permite agregar Transferencia
Bancaria (FASE 17) u otro proveedor sin modificar el núcleo de
Billing, tal como exige `docs/paypal.md` sección 3.

Todos los montos son `Decimal`; todas las operaciones que crean o
modifican estado en el proveedor externo reciben `idempotency_key`
(string) — la implementación concreta decide cómo la usa (para PayPal,
el header `PayPal-Request-Id`)."""

from dataclasses import dataclass, field
from decimal import Decimal


class PaymentProviderError(Exception):
    """Error de comunicación/negocio con el proveedor externo. El
    mensaje NUNCA debe incluir client secret, access token ni el
    cuerpo crudo de una request/response que pudiera contenerlos."""


@dataclass
class CreatedOrder:
    external_order_id: str
    approve_url: str
    status: str
    raw_status: str = ""


@dataclass
class CaptureResult:
    external_capture_id: str
    status: str
    amount: Decimal
    currency: str
    raw_status: str = ""


@dataclass
class RefundResult:
    external_refund_id: str
    status: str
    raw_status: str = ""


@dataclass
class WebhookVerification:
    verified: bool
    verification_status: str = ""


class PaymentProvider:
    """Puerto abstracto. Cada método lanza `PaymentProviderError` en
    caso de fallo — nunca deja escapar una excepción de bajo nivel
    (HTTP, JSON) hacia `apps.billing.services`."""

    def create_order(self, *, amount: Decimal, currency: str, reference_id: str,
                      description: str, return_url: str, cancel_url: str,
                      idempotency_key: str) -> CreatedOrder:
        raise NotImplementedError

    def capture_order(self, *, external_order_id: str, idempotency_key: str) -> CaptureResult:
        raise NotImplementedError

    def get_order(self, *, external_order_id: str) -> dict:
        raise NotImplementedError

    def refund_capture(self, *, external_capture_id: str, amount: Decimal, currency: str,
                        idempotency_key: str) -> RefundResult:
        raise NotImplementedError

    def verify_webhook_signature(self, *, headers: dict, raw_body: bytes) -> WebhookVerification:
        raise NotImplementedError

    def test_connection(self) -> tuple[bool, str]:
        """Verifica credenciales sin realizar ninguna operación de
        negocio (nunca una compra real, ver `docs/phases/PHASE-16-paypal-sandbox.md`
        sección 9) — típicamente solo obtiene un access token."""
        raise NotImplementedError
