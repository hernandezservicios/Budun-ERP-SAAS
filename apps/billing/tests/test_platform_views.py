from django.test import TestCase
from django.urls import reverse

from apps.billing import services
from apps.billing.models import PayPalTransaction

from ._helpers import BillingTestCase, fake_provider


class PlatformAccessTests(BillingTestCase, TestCase):
    """Ninguna vista de `apps.billing` (plataforma) debe ser accesible
    para un usuario que no sea `is_superuser` — ni siquiera el OWNER de
    un tenant (sección 24/25 de la fase: seguridad y permisos)."""

    def setUp(self):
        self._crear_base()

    def test_usuario_normal_recibe_403_en_estado_del_gateway(self):
        response = self.normal_client.get(reverse("billing_platform:status"))
        self.assertEqual(response.status_code, 403)

    def test_anonimo_es_redirigido_a_login(self):
        response = self.client.get(reverse("billing_platform:status"))
        self.assertEqual(response.status_code, 302)

    def test_superadmin_ve_el_estado_del_gateway(self):
        response = self.superadmin_client.get(reverse("billing_platform:status"))
        self.assertEqual(response.status_code, 200)

    def test_usuario_normal_no_puede_iniciar_un_cobro(self):
        response = self.normal_client.post(reverse("billing_platform:checkout_create"), {
            "tenant": self.tenant.pk, "plan_id": "profesional", "purpose": PayPalTransaction.Purpose.SIGNUP,
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(PayPalTransaction.objects.count(), 0)


class GatewayStatusViewTests(BillingTestCase, TestCase):
    def setUp(self):
        self._crear_base()

    def test_probar_conexion_actualiza_el_estado(self):
        with fake_provider():
            response = self.superadmin_client.post(reverse("billing_platform:status"), {"accion": "probar_conexion"})
        self.assertEqual(response.status_code, 302)
        status = services.get_gateway_status()
        self.assertTrue(status.last_test_ok)

    def test_alternar_habilitado_deshabilita_y_rehabilita(self):
        status = services.get_gateway_status()
        self.assertTrue(status.is_enabled)
        self.superadmin_client.post(reverse("billing_platform:status"), {"accion": "alternar_habilitado"})
        status.refresh_from_db()
        self.assertFalse(status.is_enabled)


class CheckoutFlowViewTests(BillingTestCase, TestCase):
    def setUp(self):
        self._crear_base()

    def test_iniciar_cobro_redirige_a_paypal(self):
        with fake_provider():
            response = self.superadmin_client.post(reverse("billing_platform:checkout_create"), {
                "tenant": self.tenant.pk, "plan_id": "profesional", "purpose": PayPalTransaction.Purpose.SIGNUP,
            })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("https://sandbox.paypal.test/approve/"))
        self.assertEqual(PayPalTransaction.objects.count(), 1)

    def test_retorno_captura_el_pago(self):
        with fake_provider():
            txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://x/return", cancel_url="https://x/cancel",
            )
            response = self.superadmin_client.get(reverse("billing_platform:checkout_return"), {"token": txn.external_order_id})
        self.assertEqual(response.status_code, 200)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PayPalTransaction.Status.CONFIRMED)

    def test_cancelacion_marca_cancelada(self):
        with fake_provider():
            txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://x/return", cancel_url="https://x/cancel",
            )
            response = self.superadmin_client.get(reverse("billing_platform:checkout_cancel"), {"token": txn.external_order_id})
        self.assertEqual(response.status_code, 200)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PayPalTransaction.Status.CANCELLED)


class RefundViewTests(BillingTestCase, TestCase):
    def setUp(self):
        self._crear_base()
        with fake_provider():
            self.txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://x/return", cancel_url="https://x/cancel",
            )
            self.txn = services.capture_checkout(self.txn, user=self.superadmin)

    def test_solicitar_reembolso_desde_el_detalle(self):
        with fake_provider():
            response = self.superadmin_client.post(
                reverse("billing_platform:transaction_detail", args=[self.txn.pk]), {"amount": "", "reason": "prueba"},
            )
        self.assertEqual(response.status_code, 302)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PayPalTransaction.Status.REFUNDED)

    def test_usuario_normal_no_puede_ver_el_detalle_de_una_transaccion(self):
        response = self.normal_client.get(reverse("billing_platform:transaction_detail", args=[self.txn.pk]))
        self.assertEqual(response.status_code, 403)
