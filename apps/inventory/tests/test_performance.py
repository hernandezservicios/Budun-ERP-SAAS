"""
Performance de Productos e Inventario (FASE 8): número de queries y
ausencia de N+1, verificado comparando el conteo de queries con pocos
registros vs. muchos — no solo asumido.
"""

from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.inventory import services
from apps.inventory.models import Category, Product

from ._helpers import InventoryTestCase


class ProductListPerformanceTests(InventoryTestCase):
    def _crear_productos(self, cantidad, categoria=None):
        # Contador de instancia que no reinicia entre llamadas: dos
        # llamadas en el mismo test no deben colisionar en el SKU único
        # por tenant.
        inicio = getattr(self, "_contador_sku", 0)
        for i in range(inicio, inicio + cantidad):
            producto = Product.objects.create(
                tenant=self.tenant, name=f"Producto {i}", sku=f"PERF-{i}", category=categoria
            )
            services.register_stock_in(product=producto, quantity=Decimal("10"), user=self.user)
        self._contador_sku = inicio + cantidad

    def _contar_queries(self, url):
        with CaptureQueriesContext(connection) as contexto:
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 200)
        return len(contexto.captured_queries)

    def test_listado_de_productos_no_crece_con_mas_productos(self):
        """El stock actual se anota con una subquery (una sola consulta
        total), no con una consulta por producto: el número de queries
        de la página no debe crecer al pasar de 3 a 15 productos (ambos
        dentro de la misma página de paginación)."""
        self._crear_productos(3)
        queries_con_3 = self._contar_queries(reverse("inventory:product_list"))

        self._crear_productos(12)  # 15 en total, todavía en una sola página (paginate_by=20)
        queries_con_15 = self._contar_queries(reverse("inventory:product_list"))

        self.assertEqual(
            queries_con_3,
            queries_con_15,
            "El listado de productos no debería ejecutar más queries solo "
            "porque hay más productos en la misma página (indicaría N+1).",
        )

    def test_listado_de_categorias_no_crece_con_mas_categorias(self):
        """El conteo de productos por categoría se anota (Count), no se
        consulta por fila."""
        for i in range(3):
            Category.objects.create(tenant=self.tenant, name=f"Categoría {i}", order=i)
        queries_con_3 = self._contar_queries(reverse("inventory:category_list"))

        for i in range(3, 12):
            Category.objects.create(tenant=self.tenant, name=f"Categoría {i}", order=i)
        queries_con_12 = self._contar_queries(reverse("inventory:category_list"))

        self.assertEqual(queries_con_3, queries_con_12)

    def test_detalle_de_producto_con_historial_largo_no_incurre_en_n_mas_1(self):
        """El historial de movimientos usa select_related("user"): no
        debe crecer con más movimientos (hasta el límite mostrado)."""
        producto = Product.objects.create(tenant=self.tenant, name="Con historial", sku="HIST-1")
        services.register_stock_in(product=producto, quantity=Decimal("5"), user=self.user)

        queries_con_1_movimiento = self._contar_queries(
            reverse("inventory:product_detail", args=[producto.pk])
        )

        for _ in range(9):
            services.register_stock_in(product=producto, quantity=Decimal("1"), user=self.user)

        queries_con_10_movimientos = self._contar_queries(
            reverse("inventory:product_detail", args=[producto.pk])
        )

        self.assertEqual(queries_con_1_movimiento, queries_con_10_movimientos)
