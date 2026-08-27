from decimal import Decimal

from django.test import TestCase

from apps.billing.models import Coupon, SaaSInvoice, SaaSInvoiceLine
from apps.billing.services import invoicing as services
from apps.billing.services import subscriptions as subscription_services

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


class InvoiceGenerationTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)

    def test_generar_factura_crea_numero_y_lineas(self):
        invoice, creada = services.generate_invoice_for_subscription(self.subscription)
        self.assertTrue(creada)
        self.assertTrue(invoice.number.startswith("INV-SAAS-"))
        self.assertEqual(invoice.total, Decimal("29.00"))
        self.assertEqual(SaaSInvoiceLine.all_objects.filter(invoice=invoice).count(), 1)

    def test_generar_dos_veces_para_el_mismo_periodo_nunca_duplica(self):
        invoice1, creada1 = services.generate_invoice_for_subscription(self.subscription)
        invoice2, creada2 = services.generate_invoice_for_subscription(self.subscription)
        self.assertTrue(creada1)
        self.assertFalse(creada2)
        self.assertEqual(invoice1.pk, invoice2.pk)
        self.assertEqual(SaaSInvoice.all_objects.filter(subscription=self.subscription, period_start=self.subscription.current_period_start).count(), 1)

    def test_generar_factura_con_cupon_aplica_descuento(self):
        cupon = Coupon.objects.create(code="DESC10", discount_type=Coupon.DiscountType.PERCENT, discount_value=Decimal("10"))
        self.subscription.coupon = cupon
        self.subscription.save(update_fields=["coupon"])
        invoice, _creada = services.generate_invoice_for_subscription(self.subscription)
        self.assertEqual(invoice.discount_total, Decimal("2.90"))
        self.assertEqual(invoice.total, Decimal("26.10"))
        self.assertEqual(invoice.coupon_code_snapshot, "DESC10")

    def test_balance_due_de_una_factura_recien_creada_es_el_total(self):
        invoice, _creada = services.generate_invoice_for_subscription(self.subscription)
        self.assertEqual(services.get_invoice_balance_due(invoice), invoice.total)

    def test_no_se_puede_anular_una_factura_con_pagos_aplicados(self):
        from apps.billing.services import payments as payment_services

        invoice, _creada = services.generate_invoice_for_subscription(self.subscription)
        pago = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, method="paypal", amount=invoice.total, currency="USD",
            status="confirmed",
        )
        payment_services.apply_payment_to_invoices(pago, [(invoice, invoice.total)])
        with self.assertRaises(services.InvalidInvoiceOperation):
            services.void_invoice(invoice, reason="prueba")

    def test_anular_factura_sin_pagos(self):
        invoice, _creada = services.generate_invoice_for_subscription(self.subscription)
        invoice = services.void_invoice(invoice, reason="error de cálculo")
        self.assertEqual(invoice.status, SaaSInvoice.Status.VOID)


class RenewalBatchTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)

    def test_no_genera_renovacion_si_el_periodo_no_ha_terminado(self):
        generadas = services.generate_due_renewal_invoices(today=self.subscription.current_period_start)
        self.assertEqual(len(generadas), 0)

    def test_genera_renovacion_cuando_el_periodo_termino_y_avanza_el_periodo(self):
        fin_original = self.subscription.current_period_end
        generadas = services.generate_due_renewal_invoices(today=fin_original)
        self.assertEqual(len(generadas), 1)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.current_period_start, fin_original)
        self.assertGreater(self.subscription.current_period_end, fin_original)

    def test_generar_renovacion_dos_veces_el_mismo_dia_no_duplica(self):
        fin_original = self.subscription.current_period_end
        services.generate_due_renewal_invoices(today=fin_original)
        generadas_de_nuevo = services.generate_due_renewal_invoices(today=fin_original)
        # La suscripción ya avanzó de período tras la primera corrida, así
        # que la segunda corrida el MISMO día no encuentra nada pendiente.
        self.assertEqual(len(generadas_de_nuevo), 0)
        self.assertEqual(SaaSInvoice.all_objects.filter(subscription=self.subscription).count(), 1)
