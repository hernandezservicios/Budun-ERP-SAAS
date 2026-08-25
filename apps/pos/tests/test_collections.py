from decimal import Decimal

from django.urls import reverse

from apps.pos import services
from apps.sales import services as sales_services
from apps.sales.models import CreditNote, Payment, Sale

from ._helpers import PosTestCase


class CollectionsServiceTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))

    def _venta_confirmada(self, total_deseado):
        from apps.inventory import services as inv_services

        inv_services.register_stock_in(product=self.producto, quantity=total_deseado, user=self.owner)
        venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.customer)
        sales_services.add_sale_item(venta, product=self.producto, quantity=total_deseado, user=self.owner, unit_price=Decimal("1"), tax_rate=Decimal("0"))
        return sales_services.confirm_sale(venta, self.owner)

    def test_cobrar_una_sola_factura_pendiente(self):
        factura = self._venta_confirmada(Decimal("100"))
        payment, asignaciones = services.collect_customer_payment(
            self.tenant, customer=self.customer, method="transfer", amount=Decimal("100"), user=self.owner,
            allocations=[{"sale": factura, "amount": Decimal("100")}],
        )
        self.assertEqual(len(asignaciones), 1)
        self.assertEqual(sales_services.get_sale_balance_due(factura), Decimal("0"))

    def test_cobrar_varias_facturas_con_un_solo_pago_en_efectivo_genera_movimiento(self):
        factura_a = self._venta_confirmada(Decimal("100"))
        factura_b = self._venta_confirmada(Decimal("50"))
        services.collect_customer_payment(
            self.tenant, customer=self.customer, method="cash", amount=Decimal("150"), user=self.cajero,
            allocations=[{"sale": factura_a, "amount": Decimal("100")}, {"sale": factura_b, "amount": Decimal("50")}],
            cash_session=self.sesion,
        )
        self.assertEqual(sales_services.get_sale_balance_due(factura_a), Decimal("0"))
        self.assertEqual(sales_services.get_sale_balance_due(factura_b), Decimal("0"))
        self.assertEqual(services.get_expected_cash(self.sesion), Decimal("150"))

    def test_anticipo_no_es_una_venta(self):
        pago = services.register_customer_advance(
            self.tenant, customer=self.customer, method="cash", amount=Decimal("500"), user=self.cajero,
            cash_session=self.sesion,
        )
        self.assertIsNone(Sale.all_objects.filter(tenant=self.tenant, total=Decimal("500")).first())
        self.assertEqual(sales_services.get_unallocated_payment_amount(pago), Decimal("500"))

    def test_anticipo_en_efectivo_genera_cash_movement(self):
        services.register_customer_advance(
            self.tenant, customer=self.customer, method="cash", amount=Decimal("200"), user=self.cajero,
            cash_session=self.sesion,
        )
        self.assertEqual(services.get_expected_cash(self.sesion), Decimal("200"))

    def test_anticipo_requiere_cliente(self):
        with self.assertRaises(services.InvalidPosOperation):
            services.register_customer_advance(
                self.tenant, customer=None, method="cash", amount=Decimal("200"), user=self.cajero,
            )

    def test_aplicar_saldo_a_favor_agota_pagos_sin_aplicar_primero(self):
        services.register_customer_advance(self.tenant, customer=self.customer, method="cash", amount=Decimal("100"), user=self.cajero, cash_session=self.sesion)
        factura = self._venta_confirmada(Decimal("150"))
        aplicaciones = services.apply_customer_credit_to_sale(self.customer, factura, Decimal("100"), self.owner)
        self.assertEqual(len(aplicaciones), 1)
        self.assertEqual(sales_services.get_sale_balance_due(factura), Decimal("50"))

    def test_aplicar_saldo_a_favor_combina_pagos_y_notas_de_credito(self):
        services.register_customer_advance(self.tenant, customer=self.customer, method="cash", amount=Decimal("60"), user=self.cajero, cash_session=self.sesion)
        services.issue_customer_credit_note(self.tenant, customer=self.customer, amount=Decimal("60"), user=self.owner, reason="ajuste")
        factura = self._venta_confirmada(Decimal("100"))
        aplicaciones = services.apply_customer_credit_to_sale(self.customer, factura, Decimal("100"), self.owner)
        self.assertEqual(len(aplicaciones), 2)
        self.assertEqual(sales_services.get_sale_balance_due(factura), Decimal("0"))

    def test_aplicar_mas_saldo_del_disponible_es_rechazado(self):
        factura = self._venta_confirmada(Decimal("100"))
        with self.assertRaises(services.InvalidPosOperation):
            services.apply_customer_credit_to_sale(self.customer, factura, Decimal("50"), self.owner)

    def test_emitir_y_aplicar_nota_de_credito(self):
        nota = services.issue_customer_credit_note(self.tenant, customer=self.customer, amount=Decimal("40"), user=self.owner, reason="cortesía")
        self.assertEqual(nota.status, CreditNote.Status.ISSUED)
        factura = self._venta_confirmada(Decimal("100"))
        services.apply_credit_note_to_sale(nota, factura, Decimal("40"), self.owner)
        self.assertEqual(sales_services.get_sale_balance_due(factura), Decimal("60"))

    def test_refund_efectivo_requiere_sesion_y_genera_movimiento(self):
        pago = sales_services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("300"), user=self.owner)
        services.refund_payment_cash(pago, Decimal("100"), self.cajero, cash_session=self.sesion)
        self.assertEqual(services.get_expected_cash(self.sesion), Decimal("-100"))
        self.assertEqual(sales_services.get_unallocated_payment_amount(pago), Decimal("200"))

    def test_refund_efectivo_de_pago_no_efectivo_es_rechazado(self):
        pago = sales_services.create_payment(self.tenant, customer=self.customer, method="card", amount=Decimal("300"), user=self.owner)
        with self.assertRaises(services.InvalidPosOperation):
            services.refund_payment_cash(pago, Decimal("100"), self.cajero, cash_session=self.sesion)

    def test_refund_a_credito_no_afecta_caja(self):
        pago = sales_services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("300"), user=self.owner)
        nota = services.refund_payment_to_credit(pago, Decimal("100"), self.owner, reason="prefiero crédito")
        self.assertEqual(nota.source_type, CreditNote.SourceType.REFUND)
        self.assertEqual(services.get_expected_cash(self.sesion), Decimal("0"))


class CollectionsHttpViewTests(PosTestCase):
    def setUp(self):
        super().setUp()
        services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))

    def test_pantalla_de_cobros_muestra_facturas_pendientes(self):
        from apps.inventory import services as inv_services

        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner)
        venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.customer)
        sales_services.add_sale_item(venta, product=self.producto, quantity=Decimal("10"), user=self.owner, unit_price=Decimal("5"), tax_rate=Decimal("0"))
        venta = sales_services.confirm_sale(venta, self.owner)

        respuesta = self.client.get(reverse("pos:customer_collections", args=[self.customer.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, venta.number)

    def test_buscar_cliente_en_cobros(self):
        respuesta = self.client.get(reverse("pos:collections_search"), {"q": "Cliente"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.customer.display_name)
