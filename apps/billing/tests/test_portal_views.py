from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.billing.models import PaymentProof, SaaSInvoice, Subscription
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import subscriptions as subscription_services

from ._helpers import fake_provider
from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


class PortalStatusViewTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_sin_suscripcion_muestra_estado_vacio(self):
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Elegir un plan")

    def test_anonimo_redirige_a_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertEqual(respuesta.status_code, 302)


class SelectPlanViewTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_elegir_plan_con_transferencia_crea_suscripcion_e_invoice(self):
        respuesta = self.client.post(reverse("billing_portal:select_plan"), {
            "plan_version": self.version.pk, "payment_method": "bank_transfer", "coupon_code": "",
        })
        self.assertEqual(Subscription.all_objects.filter(tenant=self.tenant).count(), 1)
        invoice = SaaSInvoice.all_objects.filter(tenant=self.tenant).first()
        self.assertIsNotNone(invoice)
        self.assertRedirects(respuesta, reverse("billing_portal:transfer_instructions", args=[invoice.pk]))

    def test_elegir_plan_con_paypal_redirige_a_iniciar_cobro(self):
        respuesta = self.client.post(reverse("billing_portal:select_plan"), {
            "plan_version": self.version.pk, "payment_method": "paypal", "coupon_code": "",
        })
        invoice = SaaSInvoice.all_objects.filter(tenant=self.tenant).first()
        # `fetch_redirect_response=False`: el destino en sí mismo es OTRO
        # redirect (a PayPal), nunca un 200 — no hay nada que renderizar ahí.
        self.assertRedirects(
            respuesta, reverse("billing_portal:checkout_paypal_initiate", args=[invoice.pk]), fetch_redirect_response=False,
        )

    def test_checkout_paypal_initiate_redirige_a_paypal(self):
        self.client.post(reverse("billing_portal:select_plan"), {
            "plan_version": self.version.pk, "payment_method": "paypal", "coupon_code": "",
        })
        invoice = SaaSInvoice.all_objects.filter(tenant=self.tenant).first()
        with fake_provider():
            respuesta = self.client.get(reverse("billing_portal:checkout_paypal_initiate", args=[invoice.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith("https://sandbox.paypal.test/approve/"))

    def test_checkout_paypal_return_confirma_pago_y_activa(self):
        with fake_provider():
            self.client.post(reverse("billing_portal:select_plan"), {
                "plan_version": self.version.pk, "payment_method": "paypal", "coupon_code": "",
            })
            invoice = SaaSInvoice.all_objects.filter(tenant=self.tenant).first()
            self.client.get(reverse("billing_portal:checkout_paypal_initiate", args=[invoice.pk]))
            from apps.billing.models import PayPalTransaction

            txn = PayPalTransaction.objects.filter(tenant=self.tenant).first()
            respuesta = self.client.get(
                reverse("billing_portal:checkout_paypal_return", args=[invoice.pk]), {"token": txn.external_order_id},
            )
        self.assertRedirects(respuesta, reverse("billing_portal:status"))
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, "active")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SaaSInvoice.Status.PAID)


class TransferInstructionsViewTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription)
        from apps.billing.models import BankAccount

        self.bank_account = BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD", account_holder="Budun ERP", account_number="0000",
        )
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_subir_comprobante_deja_pendiente_de_verificacion(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        respuesta = self.client.post(reverse("billing_portal:transfer_instructions", args=[self.invoice.pk]), {
            "bank_account": self.bank_account.pk, "declared_amount": "29.00", "declared_currency": "USD",
            "declared_bank_name": "Mi Banco", "file": SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        })
        self.assertRedirects(respuesta, reverse("billing_portal:status"))
        self.assertEqual(PaymentProof.all_objects.filter(tenant=self.tenant).count(), 1)


class ChangePlanAndCancelViewTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_cambiar_plan(self):
        _plan2, version2 = crear_plan_con_version(slug="otro-plan", precio=Decimal("60.00"))
        respuesta = self.client.post(reverse("billing_portal:change_plan"), {"plan_version": version2.pk})
        self.assertRedirects(respuesta, reverse("billing_portal:status"))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version, version2)

    def test_cancelar_al_finalizar_periodo(self):
        respuesta = self.client.post(reverse("billing_portal:cancel"), {"reason": "prueba"})
        self.assertRedirects(respuesta, reverse("billing_portal:status"))
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.cancel_at_period_end)
