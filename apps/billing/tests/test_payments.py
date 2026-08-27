from decimal import Decimal

from django.test import TestCase

from apps.billing.models import SaaSInvoice, SaaSPayment
from apps.billing.services import credits as credit_services
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import payments as services
from apps.billing.services import subscriptions as subscription_services

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


class PaymentAllocationTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)

    def _pago_confirmado(self, monto):
        pago = services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            method=SaaSPayment.Method.MANUAL_OTHER, amount=monto, currency="USD",
        )
        return services.confirm_payment(pago)

    def test_aplicar_pago_exacto_marca_factura_pagada(self):
        pago = self._pago_confirmado(self.invoice.total)
        services.apply_payment_to_invoices(pago, [(self.invoice, self.invoice.total)])
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PAID)
        self.assertEqual(invoicing_services.get_invoice_balance_due(self.invoice), Decimal("0"))

    def test_aplicar_pago_parcial_marca_parcialmente_pagada(self):
        pago = self._pago_confirmado(Decimal("10.00"))
        services.apply_payment_to_invoices(pago, [(self.invoice, Decimal("10.00"))])
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PARTIALLY_PAID)
        self.assertEqual(invoicing_services.get_invoice_balance_due(self.invoice), Decimal("19.00"))

    def test_no_se_puede_exceder_el_saldo_pendiente_de_la_factura(self):
        pago = self._pago_confirmado(Decimal("100.00"))
        with self.assertRaises(services.InvalidPaymentOperation):
            services.apply_payment_to_invoices(pago, [(self.invoice, Decimal("100.00"))])

    def test_no_se_puede_exceder_lo_disponible_del_pago(self):
        pago = self._pago_confirmado(Decimal("10.00"))
        with self.assertRaises(services.InvalidPaymentOperation):
            services.apply_payment_to_invoices(pago, [(self.invoice, Decimal("20.00"))])

    def test_sobrepago_deja_saldo_a_favor_sin_perder_el_sobrante(self):
        """Ejemplo exacto de la especificación: factura 29.00, pago 40.00
        → 29.00 a la factura, 11.00 de saldo a favor."""
        pago = self._pago_confirmado(Decimal("40.00"))
        creadas = services.auto_apply_payment(pago)
        self.assertEqual(len(creadas), 1)
        self.assertEqual(creadas[0].amount, Decimal("29.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PAID)
        saldo_a_favor = credit_services.get_subscription_credit_balance(tenant=self.tenant)
        self.assertEqual(saldo_a_favor, Decimal("11.00"))

    def test_pago_multi_factura_en_orden(self):
        """Ejemplo de la especificación: un pago cubre varias facturas."""
        invoice_b, _c = invoicing_services.generate_invoice_for_subscription(
            self.subscription, period_start=self.subscription.current_period_end,
            period_end=self.subscription.current_period_end, description="Factura B",
        )
        pago = self._pago_confirmado(self.invoice.total + invoice_b.total)
        creadas = services.auto_apply_payment(pago)
        self.assertEqual(len(creadas), 2)
        self.invoice.refresh_from_db()
        invoice_b.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PAID)
        self.assertEqual(invoice_b.status, SaaSInvoice.Status.PAID)

    def test_reversar_asignacion_reabre_la_factura(self):
        pago = self._pago_confirmado(self.invoice.total)
        allocation = services.apply_payment_to_invoices(pago, [(self.invoice, self.invoice.total)])[0]
        services.reverse_allocation(allocation, reason="corrección")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.OPEN)
        self.assertEqual(invoicing_services.get_invoice_balance_due(self.invoice), self.invoice.total)

    def test_pago_no_confirmado_no_se_puede_aplicar(self):
        pago = services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            method=SaaSPayment.Method.MANUAL_OTHER, amount=self.invoice.total, currency="USD",
        )
        with self.assertRaises(services.InvalidPaymentOperation):
            services.apply_payment_to_invoices(pago, [(self.invoice, self.invoice.total)])
