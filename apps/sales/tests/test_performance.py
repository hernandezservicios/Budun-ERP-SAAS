"""
Performance del motor comercial (FASE 10): número de queries y ausencia
de N+1, verificado comparando el conteo de queries con pocos registros
vs. muchos — no solo asumido.
"""

from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.sales import services

from ._helpers import SalesTestCase


class SalesPerformanceTests(SalesTestCase):
    def _contar_queries(self, url):
        with CaptureQueriesContext(connection) as contexto:
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 200)
        return len(contexto.captured_queries)

    def test_listado_de_cotizaciones_no_crece_con_mas_cotizaciones(self):
        for _ in range(3):
            services.create_quotation(self.tenant, user=self.user, customer=self.customer)
        queries_con_3 = self._contar_queries(reverse("sales:quotation_list"))

        for _ in range(12):
            services.create_quotation(self.tenant, user=self.user, customer=self.customer)
        queries_con_15 = self._contar_queries(reverse("sales:quotation_list"))

        self.assertEqual(queries_con_3, queries_con_15)

    def test_listado_de_ventas_no_crece_con_mas_ventas(self):
        for _ in range(3):
            services.create_sale(self.tenant, user=self.user, customer=self.customer)
        queries_con_3 = self._contar_queries(reverse("sales:sale_list"))

        for _ in range(12):
            services.create_sale(self.tenant, user=self.user, customer=self.customer)
        queries_con_15 = self._contar_queries(reverse("sales:sale_list"))

        self.assertEqual(queries_con_3, queries_con_15)

    def test_detalle_de_venta_con_muchos_pagos_no_incurre_en_n_mas_1(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("40"), user=self.user)
        sale = services.confirm_sale(sale, self.user)

        for _ in range(2):
            services.record_payment(sale, method="cash", amount=Decimal("1"), user=self.user)
        queries_con_2 = self._contar_queries(reverse("sales:sale_detail", args=[sale.pk]))

        for _ in range(8):
            services.record_payment(sale, method="cash", amount=Decimal("1"), user=self.user)
        queries_con_10 = self._contar_queries(reverse("sales:sale_detail", args=[sale.pk]))

        self.assertEqual(queries_con_2, queries_con_10)
