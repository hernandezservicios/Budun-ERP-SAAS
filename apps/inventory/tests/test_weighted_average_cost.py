"""Tests del costeo por promedio ponderado para productos QUANTITY —
ampliación de cierre de FASE 14 (ver docs/accounting.md). El costeo
específico por unidad de productos SERIALIZED (`InventoryUnit.unit_cost`)
ya estaba cubierto desde FASE 8/12, sin cambios."""

from decimal import Decimal

from apps.inventory import services
from apps.inventory.models import Product

from ._helpers import InventoryTestCase


class WeightedAverageCostTests(InventoryTestCase):
    def setUp(self):
        super().setUp()
        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto Promedio", sku="AVG-1", sale_price=Decimal("100"),
        )

    def test_producto_sin_movimientos_tiene_costo_promedio_cero(self):
        self.assertEqual(services.get_current_average_cost(self.producto), Decimal("0"))

    def test_una_sola_entrada_establece_el_promedio(self):
        services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.user, unit_cost=Decimal("5"))
        self.assertEqual(services.get_current_average_cost(self.producto), Decimal("5"))

    def test_entradas_mixtas_recalculan_el_promedio_ponderado(self):
        services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.user, unit_cost=Decimal("30"))
        services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.user, unit_cost=Decimal("40"))
        # (10*30 + 10*40) / 20 = 35
        self.assertEqual(services.get_current_average_cost(self.producto), Decimal("35"))

    def test_salida_consume_el_promedio_vigente_sin_cambiarlo(self):
        services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.user, unit_cost=Decimal("30"))
        movimiento = services.register_stock_out(product=self.producto, quantity=Decimal("4"), user=self.user)
        self.assertEqual(movimiento.unit_cost, Decimal("30"))
        self.assertEqual(services.get_current_average_cost(self.producto), Decimal("30"))

    def test_ajuste_no_cambia_el_promedio_ponderado(self):
        services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.user, unit_cost=Decimal("30"))
        movimiento = services.register_stock_adjustment(product=self.producto, new_stock=Decimal("8"), user=self.user)
        self.assertIsNone(movimiento.unit_cost)
        self.assertEqual(movimiento.average_cost_after, Decimal("30"))
        self.assertEqual(services.get_current_average_cost(self.producto), Decimal("30"))

    def test_entrada_sin_costo_conocido_no_cambia_el_promedio(self):
        services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.user, unit_cost=Decimal("30"))
        services.register_stock_in(product=self.producto, quantity=Decimal("5"), user=self.user)  # sin unit_cost
        self.assertEqual(services.get_current_average_cost(self.producto), Decimal("30"))

    def test_get_inventory_valuation_quantity(self):
        services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.user, unit_cost=Decimal("7"))
        valorizacion = services.get_inventory_valuation(self.tenant)
        self.assertEqual(valorizacion["total_value"], Decimal("70"))

    def test_get_inventory_valuation_serialized(self):
        producto_serial = Product.objects.create(
            tenant=self.tenant, name="Serial Valorizado", sku="AVG-SER-1", sale_price=Decimal("900"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        services.register_serialized_unit(product=producto_serial, user=self.user, imei_1="999888777666555", unit_cost=Decimal("500"))
        valorizacion = services.get_inventory_valuation(self.tenant)
        self.assertEqual(valorizacion["total_value"], Decimal("500"))

    def test_serialized_get_current_average_cost_siempre_cero(self):
        producto_serial = Product.objects.create(
            tenant=self.tenant, name="Serial Promedio", sku="AVG-SER-2", sale_price=Decimal("900"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.assertEqual(services.get_current_average_cost(producto_serial), Decimal("0"))
