from decimal import Decimal

from django.test import TestCase

from apps.billing.models import BillingRefund, SaaSPayment
from apps.billing.services import refunds as services
from apps.billing.services import payments as payment_services

from ._helpers_saas import crear_saas_customer, crear_tenant_con_owner


class ManualRefundTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.saas_customer = crear_saas_customer()
        pago = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, method=SaaSPayment.Method.MANUAL_OTHER,
            amount=Decimal("50.00"), currency="USD",
        )
        self.payment = payment_services.confirm_payment(pago)

    def test_solicitar_reembolso_total_manual(self):
        refund = services.request_billing_refund(self.payment, reason="prueba")
        self.assertEqual(refund.amount, Decimal("50.00"))
        self.assertEqual(refund.status, BillingRefund.Status.PENDING)

    def test_completar_reembolso_manual_marca_pago_reembolsado(self):
        refund = services.request_billing_refund(self.payment, reason="prueba")
        services.complete_manual_refund(refund)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, SaaSPayment.Status.REFUNDED)

    def test_reembolso_parcial_marca_pago_parcialmente_reembolsado(self):
        refund = services.request_billing_refund(self.payment, amount=Decimal("20.00"), reason="parcial")
        services.complete_manual_refund(refund)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, SaaSPayment.Status.PARTIALLY_REFUNDED)

    def test_no_se_puede_reembolsar_mas_de_lo_disponible(self):
        with self.assertRaises(services.InvalidRefundOperation):
            services.request_billing_refund(self.payment, amount=Decimal("100.00"))

    def test_no_se_puede_reembolsar_dos_veces_el_monto_total(self):
        refund1 = services.request_billing_refund(self.payment, amount=Decimal("30.00"))
        services.complete_manual_refund(refund1)
        with self.assertRaises(services.InvalidRefundOperation):
            services.request_billing_refund(self.payment, amount=Decimal("30.00"))

    def test_no_se_puede_reembolsar_un_pago_no_confirmado(self):
        pago_pendiente = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, method=SaaSPayment.Method.MANUAL_OTHER,
            amount=Decimal("10.00"), currency="USD",
        )
        with self.assertRaises(services.InvalidRefundOperation):
            services.request_billing_refund(pago_pendiente)
