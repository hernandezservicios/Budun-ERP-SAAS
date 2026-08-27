"""
Utilidades de prueba de `apps.billing` (FASE 16).

`FakePayPalProvider` implementa EXACTAMENTE el mismo contrato que
`PayPalProvider` (mismas dataclasses de retorno, mismos parámetros) —
la razón de que sea "falso" es solo evitar red real en pruebas
unitarias, nunca ocultar un bug estructural de `apps.billing.services`
(sección 28 de la fase): toda la lógica de idempotencia/estado/
concurrencia de `services.py` corre de verdad contra este doble,
exactamente como correría contra el proveedor real. La prueba de la
propia adaptación HTTP de PayPal (`PayPalProvider`) vive aparte, en
`test_provider_paypal.py`, simulando únicamente la capa `urllib`."""

import itertools
import json
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model

from apps.billing.providers.base import (
    CaptureResult,
    CreatedOrder,
    PaymentProvider,
    PaymentProviderError,
    RefundResult,
    WebhookVerification,
)
from apps.tenants.models import Tenant

User = get_user_model()


class FakePayPalProvider(PaymentProvider):
    def __init__(self):
        self._order_ids = (f"ORDER-{i}" for i in itertools.count(1))
        self._capture_ids = (f"CAPTURE-{i}" for i in itertools.count(1))
        self._refund_ids = (f"REFUND-{i}" for i in itertools.count(1))
        self.next_capture_status = "COMPLETED"
        self.next_refund_status = "COMPLETED"
        self.capture_amount = Decimal("29.00")
        self.capture_currency = "USD"
        self.should_fail_create = False
        self.should_fail_capture = False
        self.should_fail_refund = False
        self.should_fail_test_connection = False
        self.next_verification = True
        self.calls = []

    def create_order(self, *, amount, currency, reference_id, description, return_url, cancel_url, idempotency_key):
        self.calls.append(("create_order", idempotency_key))
        if self.should_fail_create:
            raise PaymentProviderError("fallo simulado de create_order")
        order_id = next(self._order_ids)
        return CreatedOrder(external_order_id=order_id, approve_url=f"https://sandbox.paypal.test/approve/{order_id}", status="CREATED")

    def capture_order(self, *, external_order_id, idempotency_key):
        self.calls.append(("capture_order", idempotency_key))
        if self.should_fail_capture:
            raise PaymentProviderError("fallo simulado de capture_order")
        capture_id = next(self._capture_ids)
        return CaptureResult(
            external_capture_id=capture_id, status=self.next_capture_status,
            amount=self.capture_amount, currency=self.capture_currency,
        )

    def get_order(self, *, external_order_id):
        return {"id": external_order_id, "status": "COMPLETED"}

    def refund_capture(self, *, external_capture_id, amount, currency, idempotency_key):
        self.calls.append(("refund_capture", idempotency_key))
        if self.should_fail_refund:
            raise PaymentProviderError("fallo simulado de refund_capture")
        refund_id = next(self._refund_ids)
        return RefundResult(external_refund_id=refund_id, status=self.next_refund_status)

    def verify_webhook_signature(self, *, headers, raw_body):
        estado = "SUCCESS" if self.next_verification else "FAILURE"
        return WebhookVerification(verified=self.next_verification, verification_status=estado)

    def test_connection(self):
        if self.should_fail_test_connection:
            return False, "credenciales inválidas (simulado)"
        return True, ""


@contextmanager
def fake_provider(**overrides):
    fake = FakePayPalProvider()
    for key, value in overrides.items():
        setattr(fake, key, value)
    with patch("apps.billing.services.get_default_provider", return_value=fake):
        yield fake


def build_webhook_body(*, event_id, event_type, resource):
    return json.dumps({"id": event_id, "event_type": event_type, "resource": resource}).encode("utf-8")


class BillingTestCase:
    """Mixin con el `setUp` común — no hereda de `TestCase` directamente
    para poder combinarse tanto con `TestCase` (pruebas normales) como
    con `TransactionTestCase` (concurrencia)."""

    def _crear_base(self):
        self.tenant = Tenant.objects.create(name="Empresa Billing", slug="empresa-billing")
        self.superadmin = User.objects.create_superuser(email="super.billing@example.com", password="clave-de-prueba-987")
        self.usuario_normal = User.objects.create_user(email="normal.billing@example.com", password="clave-de-prueba-987")

        self.superadmin_client = self.client_class()
        self.superadmin_client.login(username="super.billing@example.com", password="clave-de-prueba-987")
        self.normal_client = self.client_class()
        self.normal_client.login(username="normal.billing@example.com", password="clave-de-prueba-987")
