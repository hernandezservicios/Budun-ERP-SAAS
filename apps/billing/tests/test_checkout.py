from decimal import Decimal

from django.test import TestCase

from apps.billing import services
from apps.billing.models import PayPalTransaction, PlanVersion, SaaSInvoice, SaaSPayment
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import subscriptions as subscription_services
from apps.sales.models import Payment as SalesPayment

from ._helpers import BillingTestCase, fake_provider
from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


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


class CreateCheckoutForInvoiceTests(TestCase):
    """FASE DE CORRECCIÓN 2B — Integridad del monto de factura en
    PayPal (ver `KNOWN_ISSUES.md` #131, `DECISIONS.md` #111):
    `create_checkout_for_invoice` es la única vía real para el Portal
    del tenant — el monto/moneda enviados a PayPal SIEMPRE deben salir
    del snapshot contractual de la `SaaSInvoice`, nunca del precio
    vigente del plan."""

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(
            self.tenant, saas_customer=self.saas_customer, plan_version=self.version,
        )
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)

    def _iniciar(self):
        return services.create_checkout_for_invoice(
            invoice=self.invoice, user=self.owner,
            return_url="https://example.test/return", cancel_url="https://example.test/cancel",
        )

    def test_a_paypal_recibe_exactamente_el_monto_y_moneda_de_la_factura(self):
        with fake_provider() as fake:
            pago, txn, approve_url = self._iniciar()
        self.assertEqual(txn.amount, Decimal("29.00"))
        self.assertEqual(txn.currency, "USD")
        self.assertEqual(pago.amount, Decimal("29.00"))
        self.assertEqual(pago.currency, "USD")
        self.assertTrue(approve_url.startswith("https://sandbox.paypal.test/approve/"))
        self.assertEqual(len([c for c in fake.calls if c[0] == "create_order"]), 1)

    def test_b_un_cambio_de_precio_del_plan_tras_emitir_la_factura_no_afecta_el_monto_cobrado(self):
        # El precio VIGENTE del plan cambia DESPUÉS de que la factura ya
        # se emitió — mismo patrón real que `PlansListView.post()` usa
        # para versionar un precio (nunca edita la fila existente, ver
        # `apps/billing/admin_views.py`).
        PlanVersion.objects.filter(plan=self.plan, frequency=self.version.frequency, is_current=True).update(is_current=False)
        PlanVersion.objects.create(
            plan=self.plan, frequency=self.version.frequency, price_amount=Decimal("39.00"), price_currency="USD", is_current=True,
        )
        with fake_provider():
            pago, txn, _url = self._iniciar()
        # PayPal debe recibir el monto DE LA FACTURA (29.00) — nunca el
        # nuevo precio vigente del plan (39.00). Este es el hallazgo
        # real que originó esta corrección.
        self.assertEqual(txn.amount, Decimal("29.00"))
        self.assertEqual(pago.amount, Decimal("29.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total, Decimal("29.00"))  # el historial de la factura nunca cambia.

    def test_c_una_factura_ya_pagada_rechaza_un_nuevo_checkout(self):
        self.invoice.status = SaaSInvoice.Status.PAID
        self.invoice.save(update_fields=["status"])
        with fake_provider() as fake:
            with self.assertRaises(services.InvalidBillingOperation):
                self._iniciar()
        self.assertEqual(len(fake.calls), 0)  # nunca llegó a llamar al proveedor.
        self.assertEqual(PayPalTransaction.objects.filter(tenant=self.tenant).count(), 0)
        self.assertEqual(SaaSPayment.all_objects.filter(tenant=self.tenant).count(), 0)

    def test_d_moneda_de_factura_invalida_rechaza_el_checkout_antes_de_llamar_a_paypal(self):
        self.invoice.currency = ""
        self.invoice.save(update_fields=["currency"])
        with fake_provider() as fake:
            with self.assertRaises(services.InvalidBillingOperation):
                self._iniciar()
        self.assertEqual(len(fake.calls), 0)

    def test_monto_de_factura_invalido_rechaza_el_checkout_antes_de_llamar_a_paypal(self):
        self.invoice.total = Decimal("0.00")
        self.invoice.save(update_fields=["total"])
        with fake_provider() as fake:
            with self.assertRaises(services.InvalidBillingOperation):
                self._iniciar()
        self.assertEqual(len(fake.calls), 0)

    def test_e_repetir_la_misma_operacion_mientras_hay_un_checkout_en_curso_no_duplica(self):
        with fake_provider():
            self._iniciar()
        with fake_provider() as fake:
            with self.assertRaises(services.InvalidBillingOperation):
                self._iniciar()
        self.assertEqual(len(fake.calls), 0)  # el segundo intento nunca llegó a llamar al proveedor.
        self.assertEqual(PayPalTransaction.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(SaaSPayment.all_objects.filter(tenant=self.tenant).count(), 1)

    def test_g_este_flujo_nunca_crea_un_apps_sales_payment(self):
        with fake_provider():
            self._iniciar()
        self.assertEqual(SalesPayment.all_objects.filter(tenant=self.tenant).count(), 0)
