from decimal import Decimal

from apps.inventory.models import InventoryUnit
from apps.inventory.services import get_current_stock
from apps.purchases import services

from ._helpers import PurchasesTestCase


class SupplierReturnQuantityTests(PurchasesTestCase):
    def setUp(self):
        super().setUp()
        self.orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        self.item = services.add_purchase_order_item(
            self.orden, product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=Decimal("10"),
        )
        services.send_purchase_order(self.orden, self.owner, tenant=self.tenant)
        self.recepcion = services.receive_purchase_order(
            self.orden, lines=[{"purchase_order_item": self.item, "quantity_received": Decimal("10")}],
            user=self.owner, tenant=self.tenant,
        )
        self.receipt_item = services.get_receipt_items(self.recepcion).first()

    def test_devolucion_parcial_reduce_stock(self):
        stock_antes = get_current_stock(self.producto)
        devolucion = services.create_supplier_return(
            self.orden, items=[{"receipt_item": self.receipt_item, "quantity_returned": Decimal("3")}],
            user=self.owner, reason="Mercancía defectuosa",
        )
        self.assertTrue(devolucion.number.startswith("DEVP-"))
        self.assertEqual(get_current_stock(self.producto), stock_antes - Decimal("3"))

    def test_no_se_puede_devolver_mas_de_lo_recibido(self):
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.create_supplier_return(
                self.orden, items=[{"receipt_item": self.receipt_item, "quantity_returned": Decimal("20")}],
                user=self.owner,
            )


class SupplierReturnSerializedTests(PurchasesTestCase):
    def setUp(self):
        super().setUp()
        self.orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        self.item = services.add_purchase_order_item(
            self.orden, product=self.producto_serial, quantity=Decimal("1"), user=self.owner, unit_cost=Decimal("500"),
        )
        services.send_purchase_order(self.orden, self.owner, tenant=self.tenant)
        self.recepcion = services.receive_purchase_order(
            self.orden, lines=[{"purchase_order_item": self.item, "units": [{"imei_1": "999888777666555"}]}],
            user=self.owner, tenant=self.tenant,
        )
        self.receipt_item = services.get_receipt_items(self.recepcion).first()

    def test_devolucion_transiciona_la_unidad_a_devuelto_proveedor(self):
        services.create_supplier_return(
            self.orden, items=[{"receipt_item": self.receipt_item}], user=self.owner, reason="No enciende",
        )
        unidad = InventoryUnit.all_objects.get(pk=self.receipt_item.inventory_unit_id)
        self.assertEqual(unidad.status, InventoryUnit.Status.DEVUELTO_PROVEEDOR)
        self.assertEqual(get_current_stock(self.producto_serial), 0)

    def test_no_se_puede_devolver_la_misma_unidad_dos_veces(self):
        services.create_supplier_return(
            self.orden, items=[{"receipt_item": self.receipt_item}], user=self.owner,
        )
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.create_supplier_return(
                self.orden, items=[{"receipt_item": self.receipt_item}], user=self.owner,
            )
