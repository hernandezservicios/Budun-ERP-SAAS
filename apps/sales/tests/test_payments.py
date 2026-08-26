from decimal import Decimal

from django.urls import reverse

from apps.customers.models import Customer
from apps.inventory import services as inv_services
from apps.sales import services
from apps.sales.models import Payment, PaymentAllocation, Sale, SalesActivityLog

from ._helpers import SalesTestCase


class PaymentServiceTests(SalesTestCase):
    """`record_payment_for_sale` es el atajo atómico (crear Payment +
    aplicarlo por completo a una sola venta) que reemplaza al antiguo
    `record_payment` — ver `apps/sales/services.py` para el diseño
    completo del ledger `PaymentAllocation`."""

    def setUp(self):
        super().setUp()
        self.sale = services.create_sale(self.tenant, user=self.user, customer=self.customer)
        services.add_sale_item(self.sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)  # total = 23.60
        self.sale = services.confirm_sale(self.sale, self.user)

    def test_no_se_puede_pagar_una_venta_no_confirmada(self):
        sale_borrador = services.create_sale(self.tenant, user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_payment_for_sale(sale_borrador, method="cash", amount=Decimal("10"), user=self.user)

    def test_pago_parcial_deja_estado_partially_paid(self):
        services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("10"), user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PARTIALLY_PAID)

    def test_pago_completo_deja_estado_paid(self):
        services.record_payment_for_sale(self.sale, method="cash", amount=self.sale.total, user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PAID)

    def test_multiples_pagos_suman_hasta_completar(self):
        services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("10"), user=self.user)
        services.record_payment_for_sale(self.sale, method="card", amount=Decimal("13.60"), user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PAID)
        self.assertEqual(
            PaymentAllocation.all_objects.filter(tenant=self.tenant, sale=self.sale, status=PaymentAllocation.Status.ACTIVE).count(),
            2,
        )

    def test_pago_con_idempotency_key_repetida_no_duplica(self):
        p1 = services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("5"), user=self.user, idempotency_key="clave-x")
        p2 = services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("5"), user=self.user, idempotency_key="clave-x")
        self.assertEqual(p1.pk, p2.pk)
        self.assertEqual(Payment.all_objects.filter(tenant=self.tenant, idempotency_key="clave-x").count(), 1)
        # Tampoco debe duplicarse la aplicación a la venta en el reintento.
        self.assertEqual(
            PaymentAllocation.all_objects.filter(tenant=self.tenant, payment=p1, status=PaymentAllocation.Status.ACTIVE).count(),
            1,
        )
        self.assertEqual(services.get_sale_paid_amount(self.sale), Decimal("5"))

    def test_pago_monto_cero_o_negativo_es_rechazado(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("0"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("-1"), user=self.user)

    def test_anular_pago_recalcula_estado(self):
        pago = services.record_payment_for_sale(self.sale, method="cash", amount=self.sale.total, user=self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.PAID)
        services.void_payment(pago, self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.UNPAID)

    def test_anular_pago_es_idempotente(self):
        pago = services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("5"), user=self.user)
        services.void_payment(pago, self.user)
        pago_repetido = services.void_payment(pago, self.user)
        self.assertEqual(pago_repetido.status, Payment.Status.VOIDED)

    def test_saldo_pendiente_se_calcula_correctamente(self):
        self.assertEqual(services.get_sale_balance_due(self.sale), self.sale.total)
        services.record_payment_for_sale(self.sale, method="cash", amount=Decimal("10"), user=self.user)
        self.assertEqual(services.get_sale_balance_due(self.sale), self.sale.total - Decimal("10"))

    def test_auditoria_registra_pago_y_aplicacion_como_eventos_distintos(self):
        services.record_payment_for_sale(self.sale, method="cash", amount=self.sale.total, user=self.user)
        acciones = set(
            SalesActivityLog.all_objects.filter(tenant=self.tenant, entity_type="sale", entity_id=self.sale.pk).values_list("action", flat=True)
        )
        self.assertIn(SalesActivityLog.Action.PAYMENT_ALLOCATED, acciones)
        acciones_pago = set(
            SalesActivityLog.all_objects.filter(tenant=self.tenant, entity_type="payment").values_list("action", flat=True)
        )
        self.assertIn(SalesActivityLog.Action.PAYMENT_RECORDED, acciones_pago)


class PaymentAllocationServiceTests(SalesTestCase):
    """Cobertura directa de la extensión "Payment / PaymentAllocation":
    un pago aplicado a varias facturas del mismo cliente, límites de
    sobre-aplicación, aislamiento por cliente y saldo a favor."""

    def setUp(self):
        super().setUp()
        self.factura_a = self._crear_venta_confirmada(Decimal("10000"))
        self.factura_b = self._crear_venta_confirmada(Decimal("7500"))
        self.factura_c = self._crear_venta_confirmada(Decimal("12000"))

    def _crear_venta_confirmada(self, total_deseado):
        # Un producto de precio 1 sin impuesto simplifica fijar el total exacto de la venta.
        producto = self.producto_cantidad
        inv_services.register_stock_in(product=producto, quantity=total_deseado, user=self.user)
        venta = services.create_sale(self.tenant, user=self.user, customer=self.customer)
        services.add_sale_item(venta, product=producto, quantity=total_deseado, user=self.user, unit_price=Decimal("1"), tax_rate=Decimal("0"))
        return services.confirm_sale(venta, self.user)

    def test_un_pago_se_aplica_a_varias_facturas_del_mismo_cliente(self):
        # Ejemplo exacto pedido por el usuario: pago de 20,000 sobre
        # facturas de 10,000 / 7,500 / 12,000 → 10,000 / 7,500 / 2,500.
        pago = services.create_payment(self.tenant, customer=self.customer, method="transfer", amount=Decimal("20000"), user=self.user)
        asignaciones = services.apply_payment_to_sales(
            pago,
            [
                {"sale": self.factura_a, "amount": Decimal("10000")},
                {"sale": self.factura_b, "amount": Decimal("7500")},
                {"sale": self.factura_c, "amount": Decimal("2500")},
            ],
            self.user,
        )
        self.assertEqual(len(asignaciones), 3)
        self.assertEqual(services.get_sale_balance_due(self.factura_a), Decimal("0"))
        self.assertEqual(services.get_sale_balance_due(self.factura_b), Decimal("0"))
        self.assertEqual(services.get_sale_balance_due(self.factura_c), Decimal("9500"))
        self.assertEqual(services.get_unallocated_payment_amount(pago), Decimal("0"))
        self.assertEqual(services.recompute_payment_status(self.factura_a), Sale.PaymentStatus.PAID)
        self.assertEqual(services.recompute_payment_status(self.factura_b), Sale.PaymentStatus.PAID)
        self.assertEqual(services.recompute_payment_status(self.factura_c), Sale.PaymentStatus.PARTIALLY_PAID)

    def test_una_factura_puede_recibir_pagos_de_varios_pagos_distintos(self):
        pago_1 = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("4000"), user=self.user)
        pago_2 = services.create_payment(self.tenant, customer=self.customer, method="card", amount=Decimal("6000"), user=self.user)
        services.allocate_payment(pago_1, self.factura_a, Decimal("4000"), self.user)
        services.allocate_payment(pago_2, self.factura_a, Decimal("6000"), self.user)
        self.assertEqual(services.get_sale_paid_amount(self.factura_a), Decimal("10000"))
        self.assertEqual(services.get_sale_balance_due(self.factura_a), Decimal("0"))

    def test_no_se_puede_sobre_aplicar_mas_alla_del_saldo_disponible_del_pago(self):
        pago = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("100"), user=self.user)
        services.allocate_payment(pago, self.factura_a, Decimal("60"), self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.allocate_payment(pago, self.factura_b, Decimal("50"), self.user)  # 60 + 50 > 100 disponibles

    def test_no_se_puede_sobre_aplicar_mas_alla_del_saldo_pendiente_de_la_factura(self):
        pago = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("50000"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.allocate_payment(pago, self.factura_a, Decimal("10001"), self.user)  # factura_a solo debe 10,000

    def test_apply_payment_to_sales_es_todo_o_nada_si_el_total_excede_lo_disponible(self):
        pago = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("15000"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.apply_payment_to_sales(
                pago,
                [{"sale": self.factura_a, "amount": Decimal("10000")}, {"sale": self.factura_b, "amount": Decimal("7500")}],
                self.user,
            )
        # Nada debió aplicarse: la validación agregada se hace antes de aplicar cualquier asignación.
        self.assertEqual(services.get_unallocated_payment_amount(pago), Decimal("15000"))
        self.assertEqual(services.get_sale_paid_amount(self.factura_a), Decimal("0"))

    def test_no_se_puede_aplicar_un_pago_a_factura_de_otro_cliente(self):
        otro_cliente = Customer.objects.create(tenant=self.tenant, first_name="Otro", last_name="Cliente")
        pago_otro_cliente = services.create_payment(self.tenant, customer=otro_cliente, method="cash", amount=Decimal("500"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.allocate_payment(pago_otro_cliente, self.factura_a, Decimal("100"), self.user)

    def test_reversar_asignacion_libera_saldo_de_factura_y_de_pago(self):
        pago = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("10000"), user=self.user)
        asignacion = services.allocate_payment(pago, self.factura_a, Decimal("10000"), self.user)
        self.assertEqual(services.recompute_payment_status(self.factura_a), Sale.PaymentStatus.PAID)

        services.reverse_allocation(asignacion, self.user)
        self.assertEqual(services.recompute_payment_status(self.factura_a), Sale.PaymentStatus.UNPAID)
        self.assertEqual(services.get_unallocated_payment_amount(pago), Decimal("10000"))

        # Reversar dos veces es un no-op idempotente.
        asignacion_repetida = services.reverse_allocation(asignacion, self.user)
        self.assertEqual(asignacion_repetida.status, PaymentAllocation.Status.REVERSED)

    def test_anular_pago_reversa_todas_sus_asignaciones_activas(self):
        pago = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("17500"), user=self.user)
        services.apply_payment_to_sales(
            pago,
            [{"sale": self.factura_a, "amount": Decimal("10000")}, {"sale": self.factura_b, "amount": Decimal("7500")}],
            self.user,
        )
        services.void_payment(pago, self.user)
        self.assertEqual(services.recompute_payment_status(self.factura_a), Sale.PaymentStatus.UNPAID)
        self.assertEqual(services.recompute_payment_status(self.factura_b), Sale.PaymentStatus.UNPAID)
        self.assertEqual(
            PaymentAllocation.all_objects.filter(tenant=self.tenant, payment=pago, status=PaymentAllocation.Status.ACTIVE).count(),
            0,
        )

    def test_saldo_a_favor_del_cliente_es_la_suma_de_sus_pagos_sin_aplicar(self):
        services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("500"), user=self.user)
        pago_parcial = services.create_payment(self.tenant, customer=self.customer, method="card", amount=Decimal("1000"), user=self.user)
        services.allocate_payment(pago_parcial, self.factura_a, Decimal("300"), self.user)
        # 500 sin aplicar + (1000 - 300) sin aplicar = 1200.
        self.assertEqual(services.get_customer_credit_balance(self.customer), Decimal("1200"))

    def test_ventas_pendientes_del_cliente_excluye_las_pagadas_por_completo(self):
        pago = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("10000"), user=self.user)
        services.allocate_payment(pago, self.factura_a, Decimal("10000"), self.user)
        pendientes = services.get_customer_pending_sales(self.customer)
        self.assertNotIn(self.factura_a, pendientes)
        self.assertIn(self.factura_b, pendientes)
        self.assertIn(self.factura_c, pendientes)

    # -- Moneda (ver docs/currency.md sección 7 y docs/accounts-receivable.md): --
    # sin un motor de FX completo, un pago solo puede aplicarse a una
    # factura en la MISMA moneda; nunca se mezcla ni se convierte
    # automáticamente.

    def test_mismo_cliente_misma_moneda_permite_aplicar_pago(self):
        pago = services.create_payment(
            self.tenant, customer=self.customer, method="cash", amount=Decimal("100"),
            user=self.user, currency=self.factura_a.currency,
        )
        asignacion = services.allocate_payment(pago, self.factura_a, Decimal("100"), self.user)
        self.assertEqual(asignacion.amount, Decimal("100"))

    def test_moneda_distinta_entre_pago_y_factura_es_rechazada(self):
        pago_dop = services.create_payment(
            self.tenant, customer=self.customer, method="cash", amount=Decimal("5000"),
            user=self.user, currency="DOP",
        )
        with self.assertRaises(services.InvalidSalesOperation):
            services.allocate_payment(pago_dop, self.factura_a, Decimal("100"), self.user)
        # Nada debió aplicarse: la factura sigue sin pagos.
        self.assertEqual(services.get_sale_paid_amount(self.factura_a), Decimal("0"))

    def test_apply_payment_to_sales_rechaza_todo_si_una_factura_tiene_otra_moneda(self):
        factura_dop = services.create_sale(self.tenant, user=self.user, customer=self.customer, currency="DOP")
        inv_services.register_stock_in(product=self.producto_cantidad, quantity=Decimal("100"), user=self.user)
        services.add_sale_item(factura_dop, product=self.producto_cantidad, quantity=Decimal("100"), user=self.user, unit_price=Decimal("1"), tax_rate=Decimal("0"))
        factura_dop = services.confirm_sale(factura_dop, self.user)
        pago = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("200"), user=self.user)  # USD (moneda por defecto)
        with self.assertRaises(services.InvalidSalesOperation):
            services.apply_payment_to_sales(
                pago,
                [{"sale": self.factura_a, "amount": Decimal("100")}, {"sale": factura_dop, "amount": Decimal("100")}],
                self.user,
            )
        # Todo o nada: la asignación a factura_a (misma moneda, hubiera sido válida)
        # también debe revertirse porque la transacción completa falla.
        self.assertEqual(services.get_sale_paid_amount(self.factura_a), Decimal("0"))
        self.assertEqual(services.get_unallocated_payment_amount(pago), Decimal("200"))

    def test_saldo_en_dop_no_incluye_pagos_en_usd(self):
        cliente_dop = Customer.objects.create(tenant=self.tenant, first_name="Cliente", last_name="DOP", currency="DOP")
        services.create_payment(self.tenant, customer=cliente_dop, method="cash", amount=Decimal("1000"), user=self.user, currency="DOP")
        services.create_payment(self.tenant, customer=cliente_dop, method="cash", amount=Decimal("500"), user=self.user, currency="USD")
        self.assertEqual(services.get_customer_credit_balance(cliente_dop), Decimal("1000"))

    def test_saldo_en_usd_no_incluye_pagos_en_dop(self):
        cliente_usd = Customer.objects.create(tenant=self.tenant, first_name="Cliente", last_name="USD", currency="USD")
        services.create_payment(self.tenant, customer=cliente_usd, method="cash", amount=Decimal("200"), user=self.user, currency="USD")
        services.create_payment(self.tenant, customer=cliente_usd, method="cash", amount=Decimal("900"), user=self.user, currency="DOP")
        self.assertEqual(services.get_customer_credit_balance(cliente_usd), Decimal("200"))


class RefundServiceTests(SalesTestCase):
    """Un reembolso solo puede salir del saldo SIN APLICAR de un pago
    (`get_unallocated_payment_amount`): si el dinero ya está aplicado a
    una factura, primero hay que revertir esa aplicación con
    `reverse_allocation` — refinamiento deliberado sobre el diseño
    original de FASE 10 (donde el reembolso derivaba directamente el
    estado REFUNDED de la venta), documentado explícitamente en
    docs/payments.md."""

    def setUp(self):
        super().setUp()
        self.sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(self.sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        self.sale = services.confirm_sale(self.sale, self.user)
        self.pago = services.record_payment_for_sale(self.sale, method="cash", amount=self.sale.total, user=self.user)

    def _asignacion_del_pago(self):
        return PaymentAllocation.all_objects.get(tenant=self.tenant, payment=self.pago)

    def test_reembolso_sin_saldo_sin_aplicar_es_rechazado(self):
        # El pago está aplicado en su totalidad a la venta: no hay nada
        # sin aplicar todavía, así que reembolsar directamente se rechaza.
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_refund(self.pago, amount=Decimal("1"), user=self.user)

    def test_reversar_la_asignacion_deja_la_venta_sin_pagar_y_libera_el_pago(self):
        services.reverse_allocation(self._asignacion_del_pago(), self.user)
        self.assertEqual(services.recompute_payment_status(self.sale), Sale.PaymentStatus.UNPAID)
        self.assertEqual(services.get_unallocated_payment_amount(self.pago), self.pago.amount)

    def test_reembolso_total_tras_reversar_la_asignacion(self):
        services.reverse_allocation(self._asignacion_del_pago(), self.user)
        services.record_refund(self.pago, amount=self.pago.amount, user=self.user)
        self.assertEqual(services.get_unallocated_payment_amount(self.pago), Decimal("0"))

    def test_reembolso_mayor_al_saldo_sin_aplicar_es_rechazado(self):
        services.reverse_allocation(self._asignacion_del_pago(), self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_refund(self.pago, amount=self.pago.amount + Decimal("1"), user=self.user)

    def test_reembolsos_acumulados_no_pueden_superar_el_saldo_sin_aplicar(self):
        services.reverse_allocation(self._asignacion_del_pago(), self.user)
        services.record_refund(self.pago, amount=Decimal("10"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.record_refund(self.pago, amount=self.pago.amount, user=self.user)

    def test_auditoria_registra_reversa_y_reembolso_como_eventos_distintos(self):
        asignacion = self._asignacion_del_pago()
        services.reverse_allocation(asignacion, self.user)
        services.record_refund(self.pago, amount=Decimal("1"), user=self.user)
        acciones_venta = set(
            SalesActivityLog.all_objects.filter(tenant=self.tenant, entity_type="sale", entity_id=self.sale.pk).values_list("action", flat=True)
        )
        self.assertIn(SalesActivityLog.Action.PAYMENT_ALLOCATION_REVERSED, acciones_venta)
        acciones_pago = set(
            SalesActivityLog.all_objects.filter(tenant=self.tenant, entity_type="payment", entity_id=self.pago.pk).values_list("action", flat=True)
        )
        self.assertIn(SalesActivityLog.Action.REFUNDED, acciones_pago)


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

    def test_revertir_pago_via_http(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.confirm_sale(sale, self.user)
        pago = services.record_payment_for_sale(sale, method="cash", amount=sale.total, user=self.user)
        asignacion = PaymentAllocation.all_objects.get(tenant=self.tenant, payment=pago)
        respuesta = self.client.post(reverse("sales:sale_payment_reverse", args=[sale.pk, asignacion.pk]))
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))
        asignacion.refresh_from_db()
        self.assertEqual(asignacion.status, PaymentAllocation.Status.REVERSED)
        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, Sale.PaymentStatus.UNPAID)

    def test_detalle_de_venta_muestra_saldo_pendiente(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.confirm_sale(sale, self.user)
        services.record_payment_for_sale(sale, method="cash", amount=Decimal("10"), user=self.user)
        respuesta = self.client.get(reverse("sales:sale_detail", args=[sale.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Saldo pendiente")
