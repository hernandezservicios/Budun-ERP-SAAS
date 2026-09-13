from decimal import Decimal

from django.test import TestCase

from apps.billing.models import BillingRefund, SaaSInvoice, SaaSPayment, SaaSPaymentAllocation
from apps.billing.services import refunds as services
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import payments as payment_services
from apps.billing.services import subscriptions as subscription_services

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


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

    def test_no_se_puede_solicitar_otro_reembolso_mientras_uno_sigue_pendiente_si_excede_lo_disponible(self):
        # FASE DE CORRECCIÓN 3 (Lifecycle integral, sección "concurrencia"):
        # antes de esta corrección, el guard de monto disponible solo
        # contaba reembolsos COMPLETADOS — un reembolso todavía PENDING
        # (aún no confirmado) no "reservaba" su monto, así que dos
        # solicitudes de 30.00 sobre un pago de 50.00 pasaban ambas.
        services.request_billing_refund(self.payment, amount=Decimal("30.00"))  # queda PENDING, nunca se completa.
        with self.assertRaises(services.InvalidRefundOperation):
            services.request_billing_refund(self.payment, amount=Decimal("30.00"))

    def test_no_se_puede_reembolsar_un_pago_no_confirmado(self):
        pago_pendiente = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, method=SaaSPayment.Method.MANUAL_OTHER,
            amount=Decimal("10.00"), currency="USD",
        )
        with self.assertRaises(services.InvalidRefundOperation):
            services.request_billing_refund(pago_pendiente)


class RefundReversesAllocationTests(TestCase):
    """FASE DE CORRECCIÓN 3 (Lifecycle integral, sección "refund"): antes
    de esta corrección, completar un reembolso nunca revertía la
    `SaaSPaymentAllocation` del pago — la factura quedaba `PAID` para
    siempre aunque el dinero ya hubiera vuelto al cliente (ver
    KNOWN_ISSUES.md #133)."""

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("100.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        pago = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            method=SaaSPayment.Method.MANUAL_OTHER, amount=self.invoice.total, currency="USD",
        )
        self.payment = payment_services.confirm_payment(pago)
        payment_services.apply_payment_to_invoices(self.payment, [(self.invoice, self.invoice.total)])
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PAID)

    def test_reembolso_total_revierte_la_asignacion_y_reabre_la_factura(self):
        refund = services.request_billing_refund(self.payment, reason="reembolso total")
        services.complete_manual_refund(refund)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.OPEN)
        self.assertEqual(invoicing_services.get_invoice_balance_due(self.invoice), self.invoice.total)
        self.assertFalse(SaaSPaymentAllocation.all_objects.filter(payment=self.payment, status=SaaSPaymentAllocation.Status.ACTIVE).exists())

    def test_reembolso_parcial_revierte_solo_el_monto_reembolsado(self):
        refund = services.request_billing_refund(self.payment, amount=Decimal("30.00"), reason="reembolso parcial")
        services.complete_manual_refund(refund)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PARTIALLY_PAID)
        self.assertEqual(invoicing_services.get_invoice_balance_due(self.invoice), Decimal("30.00"))
        # El remanente (70.00) sigue cubriendo la factura vía una nueva
        # asignación activa — nunca se "parte" la original in-place.
        activas = SaaSPaymentAllocation.all_objects.filter(payment=self.payment, status=SaaSPaymentAllocation.Status.ACTIVE)
        self.assertEqual(sum((a.amount for a in activas), Decimal("0")), Decimal("70.00"))

    def test_reembolso_no_afecta_asignaciones_de_otras_facturas(self):
        segunda_factura, _creada = invoicing_services.generate_invoice_for_subscription(
            self.subscription, period_start=self.invoice.period_end, period_end=self.invoice.period_end,
        )
        segundo_pago = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            method=SaaSPayment.Method.MANUAL_OTHER, amount=segunda_factura.total, currency="USD",
        )
        segundo_pago = payment_services.confirm_payment(segundo_pago)
        payment_services.apply_payment_to_invoices(segundo_pago, [(segunda_factura, segunda_factura.total)])

        refund = services.request_billing_refund(self.payment, reason="reembolso total")
        services.complete_manual_refund(refund)

        segunda_factura.refresh_from_db()
        self.assertEqual(segunda_factura.status, SaaSInvoice.Status.PAID)
