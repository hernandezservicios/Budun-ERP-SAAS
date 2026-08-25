from decimal import Decimal

from django.urls import reverse

from apps.inventory import services as inv_services
from apps.inventory.models import InventoryUnit
from apps.sales import services
from apps.sales.models import Sale

from ._helpers import SalesTestCase


class SaleServiceTests(SalesTestCase):
    def test_crear_venta_directa_en_borrador(self):
        sale = services.create_sale(self.tenant, user=self.user, customer=self.customer)
        self.assertTrue(sale.number.startswith("FAC-"))
        self.assertEqual(sale.status, Sale.Status.DRAFT)

    def test_confirmar_venta_producto_cantidad_reduce_stock(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("5"), user=self.user)
        stock_antes = inv_services.get_current_stock(self.producto_cantidad)
        sale = services.confirm_sale(sale, self.user)
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)
        self.assertEqual(inv_services.get_current_stock(self.producto_cantidad), stock_antes - Decimal("5"))

    def test_confirmar_venta_producto_serializado_vende_unidad(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
        services.confirm_sale(sale, self.user)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.status, InventoryUnit.Status.VENDIDO)

    def test_no_se_puede_confirmar_venta_sin_lineas(self):
        sale = services.create_sale(self.tenant, user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.confirm_sale(sale, self.user)

    def test_no_se_puede_confirmar_venta_serializada_con_unidad_ya_vendida(self):
        sale1 = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale1, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
        services.confirm_sale(sale1, self.user)

        sale2 = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale2, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
        with self.assertRaises(services.InvalidSalesOperation):
            services.confirm_sale(sale2, self.user)

    def test_confirmar_venta_sin_stock_suficiente_es_rechazado(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("9999"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.confirm_sale(sale, self.user)

    def test_confirmar_venta_es_idempotente(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("3"), user=self.user)
        services.confirm_sale(sale, self.user)
        stock_tras_primera_confirmacion = inv_services.get_current_stock(self.producto_cantidad)
        services.confirm_sale(sale, self.user)  # repetir
        self.assertEqual(inv_services.get_current_stock(self.producto_cantidad), stock_tras_primera_confirmacion)

    def test_cancelar_venta_en_borrador(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.cancel_sale(sale, self.user, reason="Error de captura")
        self.assertEqual(sale.status, Sale.Status.CANCELED)
        self.assertEqual(sale.cancel_reason, "Error de captura")

    def test_no_se_puede_cancelar_venta_confirmada(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        services.confirm_sale(sale, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.cancel_sale(sale, self.user)

    def test_cancelar_venta_en_borrador_no_afecta_stock(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("5"), user=self.user)
        stock_antes = inv_services.get_current_stock(self.producto_cantidad)
        services.cancel_sale(sale, self.user)
        self.assertEqual(inv_services.get_current_stock(self.producto_cantidad), stock_antes)

    def test_venta_serializada_sin_unidad_asignada_es_rechazada_al_confirmar(self):
        sale = services.create_sale(self.tenant, user=self.user)
        # Se agrega directamente sin pasar por el form (que exigiría IMEI) para simular datos corruptos.
        from apps.sales.models import SaleItem

        SaleItem.all_objects.create(
            tenant=self.tenant, sale=sale, product=self.producto_serial, description="x", sku_snapshot="x",
            quantity=Decimal("1"), unit_price=Decimal("1"), line_order=1,
        )
        with self.assertRaises(services.InvalidSalesOperation):
            services.confirm_sale(sale, self.user)


class SaleHttpViewTests(SalesTestCase):
    def test_crear_venta_via_http(self):
        respuesta = self.client.post(reverse("sales:sale_create"), {
            "customer": self.customer.pk, "currency": "USD", "payment_terms": "contado",
            "notes": "", "terms": "", "global_discount_percent": "0", "global_discount_amount": "0", "issue_date": "",
        })
        sale = Sale.all_objects.filter(tenant=self.tenant).first()
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))

    def test_confirmar_venta_via_http(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        respuesta = self.client.post(reverse("sales:sale_confirm", args=[sale.pk]))
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)

    def test_cancelar_venta_via_http(self):
        sale = services.create_sale(self.tenant, user=self.user)
        respuesta = self.client.post(reverse("sales:sale_cancel", args=[sale.pk]))
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CANCELED)

    def test_recibo_via_http(self):
        sale = services.create_sale(self.tenant, user=self.user)
        respuesta = self.client.get(reverse("sales:sale_receipt", args=[sale.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, sale.number)
