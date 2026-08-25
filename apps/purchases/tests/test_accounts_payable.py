from decimal import Decimal

from apps.pos.models import CashMovement
from apps.pos.services import get_expected_cash
from apps.purchases import services
from apps.purchases.models import SupplierInvoice, SupplierPayment
from apps.sales.models import PaymentMethod

from ._helpers import PurchasesTestCase


def _factura_confirmada(self, total=Decimal("100")):
    factura = services.create_supplier_invoice(
        self.tenant, supplier=self.supplier, supplier_invoice_number="F-0001", user=self.owner,
    )
    services.add_supplier_invoice_item(
        factura, description="Mercancía", quantity=Decimal("1"), unit_cost=total, user=self.owner,
    )
    return services.confirm_supplier_invoice(factura, self.owner)


class SupplierInvoiceTests(PurchasesTestCase):
    def test_crear_y_confirmar_factura(self):
        factura = _factura_confirmada(self, Decimal("118"))
        self.assertEqual(factura.status, SupplierInvoice.Status.CONFIRMED)
        self.assertEqual(factura.total, Decimal("118.00"))

    def test_no_se_puede_confirmar_factura_sin_lineas(self):
        factura = services.create_supplier_invoice(
            self.tenant, supplier=self.supplier, supplier_invoice_number="F-0002", user=self.owner,
        )
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.confirm_supplier_invoice(factura, self.owner)

    def test_numero_de_factura_de_proveedor_duplicado_es_rechazado(self):
        _factura_confirmada(self, Decimal("50"))
        with self.assertRaises(Exception):
            services.create_supplier_invoice(
                self.tenant, supplier=self.supplier, supplier_invoice_number="F-0001", user=self.owner,
            )


class SupplierPaymentTests(PurchasesTestCase):
    def test_pago_completo_a_una_factura(self):
        factura = _factura_confirmada(self, Decimal("100"))
        pago = services.record_supplier_payment_for_invoice(
            factura, method=PaymentMethod.TRANSFER, amount=Decimal("100"), user=self.owner,
        )
        self.assertEqual(services.get_invoice_balance_due(factura), Decimal("0"))
        self.assertEqual(services.get_unallocated_supplier_payment_amount(pago), Decimal("0"))

    def test_pago_parcial_dos_veces_hasta_saldar(self):
        factura = _factura_confirmada(self, Decimal("100"))
        services.record_supplier_payment_for_invoice(factura, method=PaymentMethod.TRANSFER, amount=Decimal("40"), user=self.owner)
        services.record_supplier_payment_for_invoice(factura, method=PaymentMethod.TRANSFER, amount=Decimal("60"), user=self.owner)
        self.assertEqual(services.get_invoice_balance_due(factura), Decimal("0"))

    def test_un_pago_se_aplica_a_varias_facturas(self):
        factura_1 = _factura_confirmada(self, Decimal("40"))
        factura_2 = services.create_supplier_invoice(
            self.tenant, supplier=self.supplier, supplier_invoice_number="F-0003", user=self.owner,
        )
        services.add_supplier_invoice_item(factura_2, description="Otra", quantity=Decimal("1"), unit_cost=Decimal("60"), user=self.owner)
        # `confirm_supplier_invoice` opera sobre una copia bloqueada y
        # devuelve esa instancia ya actualizada (total incluido) — se
        # reasigna aquí para no seguir usando la referencia desactualizada
        # en memoria (mismo patrón ya documentado en apps.sales.services).
        factura_2 = services.confirm_supplier_invoice(factura_2, self.owner)

        pago = services.create_supplier_payment(self.tenant, supplier=self.supplier, method=PaymentMethod.TRANSFER, amount=Decimal("100"), user=self.owner)
        services.apply_supplier_payment_to_invoices(
            pago, [{"invoice": factura_1, "amount": Decimal("40")}, {"invoice": factura_2, "amount": Decimal("60")}], self.owner,
        )
        self.assertEqual(services.get_invoice_balance_due(factura_1), Decimal("0"))
        self.assertEqual(services.get_invoice_balance_due(factura_2), Decimal("0"))

    def test_no_se_puede_sobre_aplicar_un_pago(self):
        factura = _factura_confirmada(self, Decimal("100"))
        pago = services.create_supplier_payment(self.tenant, supplier=self.supplier, method=PaymentMethod.TRANSFER, amount=Decimal("50"), user=self.owner)
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.allocate_supplier_payment(pago, factura, Decimal("60"), self.owner)

    def test_no_se_puede_exceder_el_saldo_pendiente_de_la_factura(self):
        factura = _factura_confirmada(self, Decimal("50"))
        pago = services.create_supplier_payment(self.tenant, supplier=self.supplier, method=PaymentMethod.TRANSFER, amount=Decimal("100"), user=self.owner)
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.allocate_supplier_payment(pago, factura, Decimal("80"), self.owner)

    def test_reversar_asignacion_libera_saldo(self):
        factura = _factura_confirmada(self, Decimal("100"))
        pago = services.record_supplier_payment_for_invoice(factura, method=PaymentMethod.TRANSFER, amount=Decimal("100"), user=self.owner)
        asignacion = services.get_payment_allocations(pago).first()
        services.reverse_supplier_allocation(asignacion, self.owner)
        self.assertEqual(services.get_invoice_balance_due(factura), Decimal("100"))
        self.assertEqual(services.get_unallocated_supplier_payment_amount(pago), Decimal("100"))

    def test_anular_pago_reversa_todas_sus_asignaciones(self):
        factura = _factura_confirmada(self, Decimal("100"))
        pago = services.record_supplier_payment_for_invoice(factura, method=PaymentMethod.TRANSFER, amount=Decimal("100"), user=self.owner)
        services.void_supplier_payment(pago, self.owner)
        pago.refresh_from_db()
        self.assertEqual(pago.status, SupplierPayment.Status.VOIDED)
        self.assertEqual(services.get_invoice_balance_due(factura), Decimal("100"))


class SupplierAdvanceTests(PurchasesTestCase):
    def test_registrar_anticipo_sin_factura(self):
        anticipo = services.register_supplier_advance(
            self.tenant, supplier=self.supplier, method=PaymentMethod.TRANSFER, amount=Decimal("200"), user=self.owner,
        )
        self.assertEqual(services.get_supplier_advance_balance(self.supplier), Decimal("200"))
        self.assertIsNotNone(anticipo.pk)

    def test_aplicar_anticipo_a_factura_pendiente(self):
        services.register_supplier_advance(self.tenant, supplier=self.supplier, method=PaymentMethod.TRANSFER, amount=Decimal("200"), user=self.owner)
        factura = _factura_confirmada(self, Decimal("150"))
        services.apply_supplier_advance_to_invoice(self.supplier, factura, Decimal("150"), self.owner)
        self.assertEqual(services.get_invoice_balance_due(factura), Decimal("0"))
        self.assertEqual(services.get_supplier_advance_balance(self.supplier), Decimal("50"))

    def test_sin_anticipos_disponibles_lanza_error(self):
        factura = _factura_confirmada(self, Decimal("50"))
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.apply_supplier_advance_to_invoice(self.supplier, factura, Decimal("10"), self.owner)


class SupplierCashPaymentTests(PurchasesTestCase):
    def test_pago_en_efectivo_exige_sesion_de_caja_abierta(self):
        factura = _factura_confirmada(self, Decimal("50"))
        with self.assertRaises(Exception):
            services.record_supplier_payment_for_invoice(factura, method=PaymentMethod.CASH, amount=Decimal("50"), user=self.owner)

    def test_pago_en_efectivo_registra_movimiento_de_caja_de_salida(self):
        sesion = self.abrir_caja(self.owner)
        efectivo_antes = get_expected_cash(sesion)
        factura = _factura_confirmada(self, Decimal("50"))
        services.record_supplier_payment_for_invoice(
            factura, method=PaymentMethod.CASH, amount=Decimal("50"), user=self.owner, cash_session=sesion,
        )
        self.assertEqual(get_expected_cash(sesion), efectivo_antes - Decimal("50"))
        self.assertTrue(
            CashMovement.all_objects.filter(
                tenant=self.tenant, cash_session=sesion, movement_type=CashMovement.MovementType.SUPPLIER_PAYMENT_CASH,
            ).exists()
        )

    def test_anticipo_en_efectivo_usa_su_propio_tipo_de_movimiento(self):
        sesion = self.abrir_caja(self.owner)
        services.register_supplier_advance(
            self.tenant, supplier=self.supplier, method=PaymentMethod.CASH, amount=Decimal("30"), user=self.owner, cash_session=sesion,
        )
        self.assertTrue(
            CashMovement.all_objects.filter(
                tenant=self.tenant, cash_session=sesion, movement_type=CashMovement.MovementType.SUPPLIER_ADVANCE_CASH,
            ).exists()
        )

    def test_pago_por_transferencia_no_afecta_la_caja(self):
        sesion = self.abrir_caja(self.owner)
        efectivo_antes = get_expected_cash(sesion)
        factura = _factura_confirmada(self, Decimal("50"))
        services.record_supplier_payment_for_invoice(factura, method=PaymentMethod.TRANSFER, amount=Decimal("50"), user=self.owner)
        self.assertEqual(get_expected_cash(sesion), efectivo_antes)
