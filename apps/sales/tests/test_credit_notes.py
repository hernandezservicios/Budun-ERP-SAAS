"""Notas de crédito (FASE 11, ver docs/accounts-receivable.md):
estructuralmente análogas a Payment/PaymentAllocation — misma
disciplina de validación (nunca sobre-aplica, nunca cruza tenant/
cliente, corrige con reversa nunca con edición)."""

from decimal import Decimal

from apps.customers.models import Customer
from apps.sales import services
from apps.sales.models import CreditNote, CreditNoteApplication, PaymentAllocation, Sale

from ._helpers import SalesTestCase


class CreditNoteServiceTests(SalesTestCase):
    def setUp(self):
        super().setUp()
        self.sale = services.create_sale(self.tenant, user=self.user, customer=self.customer)
        services.add_sale_item(self.sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)  # total = 23.60
        self.sale = services.confirm_sale(self.sale, self.user)

    def test_crear_nota_de_credito_en_draft(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("10"), user=self.user, reason="ajuste")
        self.assertEqual(nota.status, CreditNote.Status.DRAFT)
        self.assertTrue(nota.number.startswith("NC-"))

    def test_nota_en_draft_no_genera_saldo_a_favor(self):
        services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("10"), user=self.user)
        self.assertEqual(services.get_customer_credit_balance(self.customer), Decimal("0"))

    def test_emitir_nota_genera_saldo_a_favor(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("10"), user=self.user)
        services.issue_credit_note(nota, self.user)
        self.assertEqual(services.get_customer_credit_balance(self.customer), Decimal("10"))

    def test_emitir_es_idempotente(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("10"), user=self.user)
        services.issue_credit_note(nota, self.user)
        nota_repetida = services.issue_credit_note(nota, self.user)
        self.assertEqual(nota_repetida.status, CreditNote.Status.ISSUED)

    def test_crear_nota_sin_cliente_es_rechazado(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.create_credit_note(self.tenant, customer=None, amount=Decimal("10"), user=self.user)

    def test_aplicar_nota_reduce_saldo_pendiente(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("23.60"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        services.apply_credit_note(nota, self.sale, Decimal("23.60"), self.user)
        self.assertEqual(services.get_sale_balance_due(self.sale), Decimal("0"))
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PAID)

    def test_aplicar_nota_parcialmente_dej_partially_applied(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("23.60"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        services.apply_credit_note(nota, self.sale, Decimal("10"), self.user)
        nota.refresh_from_db()
        self.assertEqual(nota.status, CreditNote.Status.PARTIALLY_APPLIED)

    def test_aplicar_nota_por_completo_deja_fully_applied(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("23.60"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        services.apply_credit_note(nota, self.sale, Decimal("23.60"), self.user)
        nota.refresh_from_db()
        self.assertEqual(nota.status, CreditNote.Status.FULLY_APPLIED)

    def test_no_se_puede_sobre_aplicar_mas_alla_del_saldo_de_la_nota(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("10"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.apply_credit_note(nota, self.sale, Decimal("10.01"), self.user)

    def test_no_se_puede_sobre_aplicar_mas_alla_del_saldo_de_la_factura(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("100"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.apply_credit_note(nota, self.sale, Decimal("23.61"), self.user)

    def test_no_se_puede_aplicar_a_factura_de_otro_cliente(self):
        otro_cliente = Customer.objects.create(tenant=self.tenant, first_name="Otro", last_name="Cliente")
        nota = services.create_credit_note(self.tenant, customer=otro_cliente, amount=Decimal("10"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.apply_credit_note(nota, self.sale, Decimal("1"), self.user)

    def test_reversar_aplicacion_libera_saldo(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("23.60"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        aplicacion = services.apply_credit_note(nota, self.sale, Decimal("23.60"), self.user)
        services.reverse_credit_note_application(aplicacion, self.user)
        self.assertEqual(services.get_sale_balance_due(self.sale), self.sale.total)
        nota.refresh_from_db()
        self.assertEqual(nota.status, CreditNote.Status.ISSUED)

    def test_reversar_es_idempotente(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("23.60"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        aplicacion = services.apply_credit_note(nota, self.sale, Decimal("23.60"), self.user)
        services.reverse_credit_note_application(aplicacion, self.user)
        repetida = services.reverse_credit_note_application(aplicacion, self.user)
        self.assertEqual(repetida.status, CreditNoteApplication.Status.REVERSED)

    def test_cancelar_nota_sin_aplicaciones(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("10"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        cancelada = services.cancel_credit_note(nota, self.user, reason="error de captura")
        self.assertEqual(cancelada.status, CreditNote.Status.CANCELED)
        self.assertEqual(services.get_customer_credit_balance(self.customer), Decimal("0"))

    def test_no_se_puede_cancelar_nota_con_aplicaciones_activas(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("23.60"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        services.apply_credit_note(nota, self.sale, Decimal("10"), self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.cancel_credit_note(nota, self.user)

    def test_convert_refund_to_credit_genera_nota_de_credito(self):
        pago = services.record_payment_for_sale(self.sale, method="cash", amount=self.sale.total, user=self.user)
        asignacion = PaymentAllocation.all_objects.get(tenant=self.tenant, payment=pago)
        services.reverse_allocation(asignacion, self.user)
        nota = services.convert_refund_to_credit(pago, Decimal("10"), self.user, reason="prefiero crédito")
        self.assertEqual(nota.source_type, CreditNote.SourceType.REFUND)
        self.assertEqual(nota.source_payment, pago)
        self.assertEqual(services.get_unallocated_payment_amount(pago), self.sale.total - Decimal("10"))

    def test_convert_refund_to_credit_sin_cliente_es_rechazado(self):
        sale_sin_cliente = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale_sin_cliente, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale_sin_cliente = services.confirm_sale(sale_sin_cliente, self.user)
        pago = services.record_payment_for_sale(sale_sin_cliente, method="cash", amount=sale_sin_cliente.total, user=self.user)
        asignacion = PaymentAllocation.all_objects.get(tenant=self.tenant, payment=pago)
        services.reverse_allocation(asignacion, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.convert_refund_to_credit(pago, Decimal("1"), self.user)

    def test_get_customer_credit_balance_suma_pagos_y_notas(self):
        services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("5"), user=self.user)
        pago_anticipo = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("20"), user=self.user)
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("15"), user=self.user)
        services.issue_credit_note(nota, self.user)
        # 20 del anticipo (sin aplicar) + 15 de la nota = 35.
        self.assertEqual(services.get_customer_credit_balance(self.customer), Decimal("35"))

    def test_get_sale_paid_amount_incluye_notas_de_credito(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("10"), user=self.user)
        nota = services.issue_credit_note(nota, self.user)
        services.apply_credit_note(nota, self.sale, Decimal("10"), self.user)
        services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("5"), user=self.user)
        self.assertEqual(services.get_sale_paid_amount(self.sale), Decimal("15"))

    # -- Moneda (ver docs/currency.md sección 7): misma disciplina que
    # Payment/PaymentAllocation — sin motor de FX, nunca se aplica una
    # nota de crédito a una factura en otra moneda.

    def test_nota_sin_moneda_explicita_usa_la_moneda_del_cliente(self):
        nota = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("10"), user=self.user)
        self.assertEqual(nota.currency, self.customer.currency)

    def test_moneda_distinta_entre_nota_y_factura_es_rechazada(self):
        nota_dop = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("100"), user=self.user, currency="DOP")
        nota_dop = services.issue_credit_note(nota_dop, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.apply_credit_note(nota_dop, self.sale, Decimal("10"), self.user)
        self.assertEqual(services.get_sale_paid_amount(self.sale), Decimal("0"))

    def test_saldo_a_favor_excluye_notas_de_credito_en_otra_moneda(self):
        nota_usd = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("10"), user=self.user)  # USD (cliente)
        nota_dop = services.create_credit_note(self.tenant, customer=self.customer, amount=Decimal("500"), user=self.user, currency="DOP")
        services.issue_credit_note(nota_usd, self.user)
        services.issue_credit_note(nota_dop, self.user)
        # Solo la nota en USD (moneda del cliente) cuenta para este saldo.
        self.assertEqual(services.get_customer_credit_balance(self.customer), Decimal("10"))
