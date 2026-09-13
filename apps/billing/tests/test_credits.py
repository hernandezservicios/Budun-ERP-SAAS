from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.billing.models import SaaSInvoice, SaaSPayment
from apps.billing.services import credits as services
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import payments as payment_services
from apps.billing.services import subscriptions as subscription_services

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


class CreditNoteTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)

    def test_emitir_nota_de_credito_notifica_al_tenant(self):
        # FASE DE CORRECCIÓN 5: antes de esta corrección, ninguna
        # notificación avisaba al tenant que recibió una nota de crédito.
        from django.core import mail

        mail.outbox.clear()
        services.issue_credit_note(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            amount=Decimal("10.00"), currency="USD", reason="ajuste",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.owner.email, mail.outbox[0].to)

    def test_emitir_nota_de_credito(self):
        nota = services.issue_credit_note(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            amount=Decimal("10.00"), currency="USD", reason="ajuste",
        )
        self.assertTrue(nota.number.startswith("NC-SAAS-"))
        self.assertEqual(services.get_unapplied_credit_note_amount(nota), Decimal("10.00"))

    def test_aplicar_nota_de_credito_a_factura(self):
        nota = services.issue_credit_note(
            tenant=self.tenant, saas_customer=self.saas_customer, amount=Decimal("10.00"), currency="USD", reason="ajuste",
        )
        services.apply_credit_note_to_invoice(nota, self.invoice, Decimal("10.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PARTIALLY_PAID)
        self.assertEqual(invoicing_services.get_invoice_balance_due(self.invoice), Decimal("19.00"))

    def test_no_se_puede_exceder_el_saldo_de_la_nota(self):
        nota = services.issue_credit_note(
            tenant=self.tenant, saas_customer=self.saas_customer, amount=Decimal("5.00"), currency="USD", reason="ajuste",
        )
        with self.assertRaises(services.InvalidCreditOperation):
            services.apply_credit_note_to_invoice(nota, self.invoice, Decimal("10.00"))

    def test_reversar_aplicacion_reabre_la_factura(self):
        nota = services.issue_credit_note(
            tenant=self.tenant, saas_customer=self.saas_customer, amount=self.invoice.total, currency="USD", reason="ajuste",
        )
        application = services.apply_credit_note_to_invoice(nota, self.invoice, self.invoice.total)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PAID)
        services.reverse_credit_note_application(application, reason="corrección")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.OPEN)


class AutoApplyCreditNoteOnNewInvoiceTests(TestCase):
    """FASE DE CORRECCIÓN 3 (Lifecycle integral, sección "crédito"): antes
    de esta corrección, `apply_credit_note_to_invoice` solo se ejercitaba
    desde pruebas — ninguna factura nueva consumía automáticamente una
    nota de crédito existente."""

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("30.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)
        self.subscription.current_period_start = date(2026, 1, 1)
        self.subscription.current_period_end = date(2026, 1, 31)
        self.subscription.save(update_fields=["current_period_start", "current_period_end"])

    def test_downgrade_aplica_la_nota_de_credito_a_la_siguiente_factura_de_renovacion(self):
        _plan_nuevo, version_basica = crear_plan_con_version(slug="basico-auto", precio=Decimal("10.00"))
        _subscription, desglose, nota_credito, _factura_cargo = subscription_services.change_plan(
            self.subscription, new_plan_version=version_basica, change_date=date(2026, 1, 16),
        )
        self.assertIsNotNone(nota_credito)
        self.assertEqual(services.get_unapplied_credit_note_amount(nota_credito), nota_credito.amount)

        siguiente_factura, creada = invoicing_services.ensure_next_renewal_invoice(self.subscription)
        self.assertTrue(creada)
        siguiente_factura.refresh_from_db()
        self.assertEqual(services.get_unapplied_credit_note_amount(nota_credito), Decimal("0.00"))
        self.assertLess(invoicing_services.get_invoice_balance_due(siguiente_factura), siguiente_factura.total)

    def test_nota_de_credito_de_otra_suscripcion_nunca_se_aplica(self):
        otra_subscription = subscription_services.create_subscription(
            self.tenant.__class__.objects.create(name="Otro Tenant Billing", slug="otro-tenant-billing"),
            saas_customer=self.saas_customer, plan_version=self.version,
        )
        services.issue_credit_note(
            tenant=otra_subscription.tenant, saas_customer=self.saas_customer, subscription=otra_subscription,
            amount=Decimal("10.00"), currency="USD", reason="ajuste de otra suscripción",
        )
        factura_de_esta_suscripcion, _creada = invoicing_services.generate_invoice_for_subscription(
            self.subscription, period_start=date(2026, 2, 1), period_end=date(2026, 3, 3),
        )
        self.assertEqual(invoicing_services.get_invoice_balance_due(factura_de_esta_suscripcion), factura_de_esta_suscripcion.total)


class CreditBalanceTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)

    def test_saldo_a_favor_combina_pago_sin_aplicar_y_nota_sin_aplicar(self):
        pago = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, method=SaaSPayment.Method.MANUAL_OTHER,
            amount=Decimal("15.00"), currency="USD",
        )
        payment_services.confirm_payment(pago)
        services.issue_credit_note(tenant=self.tenant, saas_customer=self.saas_customer, amount=Decimal("5.00"), currency="USD", reason="ajuste")
        saldo = services.get_subscription_credit_balance(tenant=self.tenant)
        self.assertEqual(saldo, Decimal("20.00"))

    def test_convertir_pago_aplicado_a_saldo_a_favor(self):
        invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        pago = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            method=SaaSPayment.Method.MANUAL_OTHER, amount=invoice.total, currency="USD",
        )
        payment_services.confirm_payment(pago)
        payment_services.apply_payment_to_invoices(pago, [(invoice, invoice.total)])
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SaaSInvoice.Status.PAID)

        services.convert_payment_to_credit(pago, reason="reembolso convertido a crédito")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SaaSInvoice.Status.OPEN, "Al reversar la aplicación, la factura reabre.")
        saldo = services.get_subscription_credit_balance(tenant=self.tenant)
        self.assertEqual(saldo, invoice.total)
