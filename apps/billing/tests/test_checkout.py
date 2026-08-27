from decimal import Decimal

from django.test import TestCase

from apps.billing import services
from apps.billing.models import PayPalTransaction

from ._helpers import BillingTestCase, fake_provider


class CreateCheckoutTests(BillingTestCase, TestCase):
    def setUp(self):
        self._crear_base()

    def test_crea_transaccion_y_orden_para_un_plan_con_precio(self):
        with fake_provider() as fake:
            txn, approve_url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
        self.assertEqual(txn.status, PayPalTransaction.Status.CREATED)
        self.assertEqual(txn.amount, Decimal("29.00"))
        self.assertTrue(txn.external_order_id)
        self.assertTrue(approve_url.startswith("https://sandbox.paypal.test/approve/"))
        self.assertEqual(fake.calls[0][0], "create_order")

    def test_rechaza_plan_sin_precio_de_autoservicio(self):
        with fake_provider():
            with self.assertRaises(services.InvalidBillingOperation):
                services.create_checkout(
                    tenant=self.tenant, plan_id="starter", purpose=PayPalTransaction.Purpose.SIGNUP,
                    user=self.superadmin, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
                )

    def test_rechaza_plan_desconocido(self):
        with fake_provider():
            with self.assertRaises(services.InvalidBillingOperation):
                services.create_checkout(
                    tenant=self.tenant, plan_id="no-existe", purpose=PayPalTransaction.Purpose.SIGNUP,
                    user=self.superadmin, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
                )

    def test_rechaza_checkout_si_gateway_deshabilitado(self):
        services.set_gateway_enabled(is_enabled=False, user=self.superadmin)
        with fake_provider():
            with self.assertRaises(services.InvalidBillingOperation):
                services.create_checkout(
                    tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                    user=self.superadmin, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
                )

    def test_falla_de_paypal_al_crear_marca_la_transaccion_como_fallida_y_no_pierde_el_registro(self):
        with fake_provider(should_fail_create=True):
            with self.assertRaises(services.InvalidBillingOperation):
                services.create_checkout(
                    tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                    user=self.superadmin, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
                )
        txn = PayPalTransaction.objects.get(tenant=self.tenant)
        self.assertEqual(txn.status, PayPalTransaction.Status.FAILED)
        self.assertTrue(txn.failure_reason)


class CaptureCancelCheckoutTests(BillingTestCase, TestCase):
    def setUp(self):
        self._crear_base()

    def _crear_transaccion(self, **overrides):
        with fake_provider(**overrides) as fake:
            txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
        return txn, fake

    def test_captura_exitosa_confirma_la_transaccion(self):
        txn, _fake = self._crear_transaccion()
        with fake_provider() as fake:
            txn = services.capture_checkout(txn, user=self.superadmin)
        self.assertEqual(txn.status, PayPalTransaction.Status.CONFIRMED)
        self.assertTrue(txn.external_capture_id)
        self.assertIsNotNone(txn.confirmed_at)
        self.assertEqual(fake.calls[0][0], "capture_order")

    def test_captura_es_idempotente_no_captura_dos_veces(self):
        txn, _fake = self._crear_transaccion()
        with fake_provider() as fake:
            txn = services.capture_checkout(txn, user=self.superadmin)
            capture_id_original = txn.external_capture_id
            # Segunda llamada (p. ej. el usuario recarga la página de retorno):
            # debe ser un no-op, nunca una segunda captura en PayPal.
            txn = services.capture_checkout(txn, user=self.superadmin)
        self.assertEqual(txn.external_capture_id, capture_id_original)
        llamadas_captura = [c for c in fake.calls if c[0] == "capture_order"]
        self.assertEqual(len(llamadas_captura), 1)

    def test_captura_pendiente_dejar_transaccion_en_pending_capture(self):
        txn, _fake = self._crear_transaccion()
        with fake_provider(next_capture_status="PENDING") as fake:
            txn = services.capture_checkout(txn, user=self.superadmin)
        self.assertEqual(txn.status, PayPalTransaction.Status.PENDING_CAPTURE)

    def test_captura_fallida_marca_failed(self):
        txn, _fake = self._crear_transaccion()
        with fake_provider(should_fail_capture=True):
            txn = services.capture_checkout(txn, user=self.superadmin)
        self.assertEqual(txn.status, PayPalTransaction.Status.FAILED)
        self.assertTrue(txn.failure_reason)

    def test_cancelar_checkout_creado(self):
        txn, _fake = self._crear_transaccion()
        txn = services.cancel_checkout(txn, user=self.superadmin)
        self.assertEqual(txn.status, PayPalTransaction.Status.CANCELLED)
        self.assertIsNotNone(txn.cancelled_at)

    def test_cancelar_despues_de_confirmar_no_hace_nada(self):
        txn, _fake = self._crear_transaccion()
        with fake_provider():
            txn = services.capture_checkout(txn, user=self.superadmin)
        txn = services.cancel_checkout(txn, user=self.superadmin)
        self.assertEqual(txn.status, PayPalTransaction.Status.CONFIRMED)
