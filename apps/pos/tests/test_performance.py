from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.pos import services
from apps.sales import services as sales_services

from ._helpers import PosTestCase


class PosPerformanceTests(PosTestCase):
    def setUp(self):
        super().setUp()
        services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))

    def _contar_queries(self, url, params=None):
        with CaptureQueriesContext(connection) as contexto:
            respuesta = self.client.get(url, params or {})
            self.assertEqual(respuesta.status_code, 200)
        return len(contexto.captured_queries)

    def test_carrito_con_muchas_lineas_no_incurre_en_n_mas_1(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        for _ in range(3):
            services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant)
        queries_con_3 = self._contar_queries(reverse("pos:terminal_detail", args=[sale.pk]))

        for _ in range(12):
            services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant)
        queries_con_15 = self._contar_queries(reverse("pos:terminal_detail", args=[sale.pk]))

        self.assertEqual(queries_con_3, queries_con_15)

    def test_cobros_con_muchas_facturas_pendientes_no_incurre_en_n_mas_1(self):
        from apps.inventory import services as inv_services

        def crear_pendiente():
            inv_services.register_stock_in(product=self.producto, quantity=Decimal("1"), user=self.owner)
            venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.customer)
            sales_services.add_sale_item(venta, product=self.producto, quantity=Decimal("1"), user=self.owner)
            return sales_services.confirm_sale(venta, self.owner)

        for _ in range(3):
            crear_pendiente()
        queries_con_3 = self._contar_queries(reverse("pos:customer_collections", args=[self.customer.pk]))

        for _ in range(10):
            crear_pendiente()
        queries_con_13 = self._contar_queries(reverse("pos:customer_collections", args=[self.customer.pk]))

        self.assertEqual(queries_con_3, queries_con_13)
