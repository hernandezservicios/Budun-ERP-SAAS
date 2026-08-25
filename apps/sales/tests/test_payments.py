from decimal import Decimal

from django.urls import reverse

from apps.sales import services
from apps.sales.models import Payment, Sale

from ._helpers import SalesTestCase


class PaymentServiceTests(SalesTestCase):
    def setUp(self):
        super().setUp()
        self.sale = services.create_sale(self.tenant, user=self.user, customer=self.customer)
        services.add_sale_item(self.sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)  # total = 23.60
        self.sale = services.confirm_sale(self.sale, self.user)

    def test_no_se_puede_pagar_una_venta_no_confirmada(self):
        sale_borrador = services.create_sale(self.tenant, user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_payment(sale_borrador, method="cash", amount=Decimal("10"), user=self.user)

    def test_pago_parcial_deja_estado_partially_paid(self):
        services.record_payment(self.sale, method="cash", amount=Decimal("10"), user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PARTIALLY_PAID)

    def test_pago_completo_deja_estado_paid(self):
        services.record_payment(self.sale, method="cash", amount=self.sale.total, user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PAID)

    def test_multiples_pagos_suman_hasta_completar(self):
        services.record_payment(self.sale, method="cash", amount=Decimal("10"), user=self.user)
        services.record_payment(self.sale, method="card", amount=Decimal("13.60"), user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PAID)
        self.assertEqual(Payment.all_objects.filter(sale=self.sale).count(), 2)

    def test_pago_con_idempotency_key_repetida_no_duplica(self):
        p1 = services.record_payment(self.sale, method="cash", amount=Decimal("5"), user=self.user, idempotency_key="clave-x")
        p2 = services.record_payment(self.sale, method="cash", amount=Decimal("5"), user=self.user, idempotency_key="clave-x")
        self.assertEqual(p1.pk, p2.pk)
        self.assertEqual(Payment.all_objects.filter(sale=self.sale).count(), 1)

    def test_pago_monto_cero_o_negativo_es_rechazado(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_payment(self.sale, method="cash", amount=Decimal("0"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_payment(self.sale, method="cash", amount=Decimal("-1"), user=self.user)

    def test_anular_pago_recalcula_estado(self):
        pago = services.record_payment(self.sale, method="cash", amount=self.sale.total, user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PAID)
        services.void_payment(pago, self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.UNPAID)

    def test_anular_pago_es_idempotente(self):
        pago = services.record_payment(self.sale, method="cash", amount=Decimal("5"), user=self.user)
        services.void_payment(pago, self.user)
        pago_repetido = services.void_payment(pago, self.user)
        self.assertEqual(pago_repetido.status, Payment.Status.VOIDED)


class RefundServiceTests(SalesTestCase):
    def setUp(self):
        super().setUp()
        self.sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(self.sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        self.sale = services.confirm_sale(self.sale, self.user)
        self.pago = services.record_payment(self.sale, method="cash", amount=self.sale.total, user=self.user)

    def test_reembolso_total_deja_estado_refunded(self):
        services.record_refund(self.pago, amount=self.pago.amount, user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.REFUNDED)

    def test_reembolso_parcial_deja_estado_partially_refunded(self):
        services.record_refund(self.pago, amount=Decimal("1.00"), user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PARTIALLY_REFUNDED)

    def test_reembolso_mayor_al_pago_es_rechazado(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_refund(self.pago, amount=self.pago.amount + Decimal("1"), user=self.user)

    def test_reembolsos_acumulados_no_pueden_superar_el_pago(self):
        services.record_refund(self.pago, amount=Decimal("10"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_refund(self.pago, amount=self.pago.amount, user=self.user)


class PaymentHttpViewTests(SalesTestCase):
    def test_registrar_pago_via_http(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.confirm_sale(sale, self.user)
        respuesta = self.client.post(reverse("sales:sale_payment_add", args=[sale.pk]), {
            "method": "cash", "amount": str(sale.total), "reference": "", "notes": "",
        })
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))
        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.PAID)

    def test_anular_pago_via_http(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.confirm_sale(sale, self.user)
        pago = services.record_payment(sale, method="cash", amount=sale.total, user=self.user)
        respuesta = self.client.post(reverse("sales:sale_payment_void", args=[sale.pk, pago.pk]))
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))
        pago.refresh_from_db()
        self.assertEqual(pago.status, Payment.Status.VOIDED)
