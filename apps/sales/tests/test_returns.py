from decimal import Decimal

from django.urls import reverse

from apps.inventory import services as inv_services
from apps.inventory.models import InventoryUnit
from apps.sales import services
from apps.sales.models import Return, Sale

from ._helpers import SalesTestCase


class ReturnServiceTests(SalesTestCase):
    def setUp(self):
        super().setUp()
        self.sale = services.create_sale(self.tenant, user=self.user)
        self.item_cantidad = services.add_sale_item(self.sale, product=self.producto_cantidad, quantity=Decimal("5"), user=self.user)
        self.item_unidad = services.add_sale_item(self.sale, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
        self.sale = services.confirm_sale(self.sale, self.user)

    def test_no_se_puede_devolver_venta_no_confirmada(self):
        sale_borrador = services.create_sale(self.tenant, user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.create_return(sale_borrador, items=[{"sale_item": self.item_cantidad, "quantity_returned": Decimal("1")}], user=self.user)

    def test_devolucion_sin_lineas_es_rechazada(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.create_return(self.sale, items=[], user=self.user)

    def test_devolucion_parcial_de_cantidad_incrementa_stock(self):
        stock_antes = inv_services.get_current_stock(self.producto_cantidad)
        devolucion = services.create_return(self.sale, items=[{"sale_item": self.item_cantidad, "quantity_returned": Decimal("2")}], user=self.user)
        self.assertTrue(devolucion.number.startswith("DEV-"))
        self.assertEqual(inv_services.get_current_stock(self.producto_cantidad), stock_antes + Decimal("2"))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.PARTIALLY_RETURNED)

    def test_devolucion_de_unidad_serializada_queda_devuelto_no_en_stock(self):
        services.create_return(self.sale, items=[{"sale_item": self.item_unidad}], user=self.user)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.status, InventoryUnit.Status.DEVUELTO)

    def test_devolucion_total_deja_venta_returned(self):
        services.create_return(
            self.sale,
            items=[{"sale_item": self.item_cantidad, "quantity_returned": Decimal("5")}, {"sale_item": self.item_unidad}],
            user=self.user,
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.RETURNED)

    def test_devolucion_cantidad_cero_es_rechazada(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.create_return(self.sale, items=[{"sale_item": self.item_cantidad, "quantity_returned": Decimal("0")}], user=self.user)

    def test_se_puede_devolver_sobre_venta_parcialmente_devuelta(self):
        services.create_return(self.sale, items=[{"sale_item": self.item_cantidad, "quantity_returned": Decimal("1")}], user=self.user)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.PARTIALLY_RETURNED)
        # segunda devolución sobre lo restante
        services.create_return(
            self.sale,
            items=[{"sale_item": self.item_cantidad, "quantity_returned": Decimal("4")}, {"sale_item": self.item_unidad}],
            user=self.user,
        )
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.RETURNED)


class ReturnHttpViewTests(SalesTestCase):
    def setUp(self):
        super().setUp()
        self.sale = services.create_sale(self.tenant, user=self.user)
        self.item_cantidad = services.add_sale_item(self.sale, product=self.producto_cantidad, quantity=Decimal("5"), user=self.user)
        self.sale = services.confirm_sale(self.sale, self.user)

    def test_formulario_de_devolucion_responde_200(self):
        respuesta = self.client.get(reverse("sales:sale_return_create", args=[self.sale.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_registrar_devolucion_via_http(self):
        respuesta = self.client.post(
            reverse("sales:sale_return_create", args=[self.sale.pk]),
            {
                "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1", "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
                "form-0-sale_item_id": str(self.item_cantidad.pk), "form-0-include": "on", "form-0-quantity_returned": "2",
                "reason": "Cliente cambió de opinión",
            },
        )
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[self.sale.pk]))
        self.assertTrue(Return.all_objects.filter(tenant=self.tenant, sale=self.sale).exists())
