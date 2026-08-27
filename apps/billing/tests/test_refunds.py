from decimal import Decimal

from django.test import TestCase

from apps.billing import services
from apps.billing.models import PayPalTransaction

from ._helpers import BillingTestCase, fake_provider


class RefundTests(BillingTestCase, TestCase):
    def setUp(self):
        self._crear_base()

    def _transaccion_confirmada(self):
        with fake_provider():
            txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
            txn = services.capture_checkout(txn, user=self.superadmin)
        return txn

    def test_reembolso_total_exitoso(self):
        txn = self._transaccion_confirmada()
        with fake_provider() as fake:
            txn = services.request_refund(txn, user=self.superadmin, reason="prueba")
        self.assertEqual(txn.status, PayPalTransaction.Status.REFUNDED)
        self.assertTrue(txn.external_refund_id)
        self.assertIsNotNone(txn.refunded_at)
        self.assertEqual(fake.calls[-1][0], "refund_capture")

    def test_reembolso_parcial_pendiente(self):
        txn = self._transaccion_confirmada()
        with fake_provider(next_refund_status="PENDING"):
            txn = services.request_refund(txn, user=self.superadmin, amount=Decimal("10.00"))
        self.assertEqual(txn.status, PayPalTransaction.Status.REFUND_PENDING)

    def test_no_se_puede_reembolsar_una_transaccion_no_confirmada(self):
        with fake_provider():
            txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
        with self.assertRaises(services.InvalidBillingOperation):
            services.request_refund(txn, user=self.superadmin)

    def test_no_se_puede_reembolsar_dos_veces(self):
        txn = self._transaccion_confirmada()
        with fake_provider():
            txn = services.request_refund(txn, user=self.superadmin)
        with self.assertRaises(services.InvalidBillingOperation):
            services.request_refund(txn, user=self.superadmin)

    def test_fallo_de_reembolso_marca_refund_failed(self):
        txn = self._transaccion_confirmada()
        with fake_provider(should_fail_refund=True):
            txn = services.request_refund(txn, user=self.superadmin)
        self.assertEqual(txn.status, PayPalTransaction.Status.REFUND_FAILED)
        self.assertTrue(txn.failure_reason)
