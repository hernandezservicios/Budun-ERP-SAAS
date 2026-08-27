import json
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.billing import services
from apps.billing.models import PayPalTransaction

from ._helpers import BillingTestCase, fake_provider

_CADENAS_PROHIBIDAS = ("secreto-real-de-prueba", "tok-super-secreto", "PAYPAL_CLIENT_SECRET")


class SecretLeakageTests(BillingTestCase, TestCase):
    """Ningún evento de auditoría de `apps.billing` debe contener jamás
    el client secret, un access token, ni la firma cruda de un webhook
    (sección 26 de la fase: 'nunca registrar secretos')."""

    def setUp(self):
        self._crear_base()

    @override_settings(PAYPAL_CLIENT_SECRET="secreto-real-de-prueba")
    def test_prueba_de_conexion_fallida_no_deja_el_secreto_en_auditoria_ni_en_el_estado(self):
        with fake_provider(should_fail_test_connection=True):
            ok, error = services.test_paypal_connection(user=self.superadmin)
        self.assertFalse(ok)

        status = services.get_gateway_status()
        self.assertNotIn("secreto-real-de-prueba", status.last_test_error)

        eventos = AuditLog.objects.filter(domain="billing_paypal")
        self.assertTrue(eventos.exists())
        for evento in eventos:
            serializado = json.dumps({"before": evento.before, "after": evento.after, "metadata": evento.metadata, "reason": evento.reason})
            for cadena in _CADENAS_PROHIBIDAS:
                self.assertNotIn(cadena, serializado)

    def test_ciclo_completo_de_pago_y_reembolso_nunca_audita_secretos(self):
        with fake_provider():
            txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://x/return", cancel_url="https://x/cancel",
            )
            txn = services.capture_checkout(txn, user=self.superadmin)
            services.request_refund(txn, user=self.superadmin)

        eventos = AuditLog.objects.filter(domain="billing_paypal", tenant=self.tenant)
        self.assertTrue(eventos.exists())
        for evento in eventos:
            serializado = json.dumps({"before": evento.before, "after": evento.after, "metadata": evento.metadata, "reason": evento.reason})
            self.assertNotIn("Bearer ", serializado)
            self.assertNotIn("client_secret", serializado)


class MultiCurrencyTests(BillingTestCase, TestCase):
    """La moneda interna y la reportada por PayPal se conservan
    SEPARADAS — nunca se mezclan/sobrescriben entre sí (sección 11 y
    18 de la fase)."""

    def setUp(self):
        self._crear_base()

    def test_moneda_reportada_por_paypal_distinta_de_la_interna_se_conserva_sin_mezclar(self):
        with fake_provider():
            txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://x/return", cancel_url="https://x/cancel",
            )
        self.assertEqual(txn.currency, "USD")
        with fake_provider(capture_currency="EUR", capture_amount=Decimal("26.50")) as _fake:
            txn = services.capture_checkout(txn, user=self.superadmin)
        # La moneda/monto INTERNO (lo que decidió nuestro propio plan) no
        # cambia jamás; la moneda/monto reportado por el proveedor se
        # guarda aparte, nunca sobrescribiendo al interno.
        self.assertEqual(txn.currency, "USD")
        self.assertEqual(txn.amount, Decimal("29.00"))
        self.assertEqual(txn.provider_currency, "EUR")
        self.assertEqual(txn.provider_amount, Decimal("26.50"))
