from decimal import Decimal

from django.urls import reverse

from apps.inventory import services
from apps.inventory.models import Product, StockMovement
from apps.inventory.services import InvalidInventoryOperation

from ._helpers import InventoryTestCase


class StockServiceUnitTests(InventoryTestCase):
    """Unit tests directos contra `services.py` (sin pasar por HTTP),
    exactamente el escenario que motivó usar `all_objects` en vez de
    `objects`/TenantManager dentro de los servicios (ver services.py)."""

    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(
            tenant=self.tenant, name="Producto Base", sku="BASE-1", min_stock=Decimal("5")
        )

    def test_stock_inicial_es_cero_sin_movimientos(self):
        self.assertEqual(services.get_current_stock(self.product), Decimal("0"))

    def test_entrada_incrementa_stock(self):
        movimiento = services.register_stock_in(
            product=self.product, quantity=Decimal("10"), user=self.user, notes="Compra inicial"
        )
        self.assertEqual(movimiento.stock_before, Decimal("0"))
        self.assertEqual(movimiento.stock_after, Decimal("10"))
        self.assertEqual(services.get_current_stock(self.product), Decimal("10"))

    def test_salida_disminuye_stock(self):
        services.register_stock_in(product=self.product, quantity=Decimal("10"), user=self.user)
        movimiento = services.register_stock_out(
            product=self.product, quantity=Decimal("4"), user=self.user, notes="Venta"
        )
        self.assertEqual(movimiento.stock_before, Decimal("10"))
        self.assertEqual(movimiento.stock_after, Decimal("6"))
        self.assertEqual(services.get_current_stock(self.product), Decimal("6"))

    def test_salida_que_deja_stock_exactamente_en_cero_es_valida(self):
        services.register_stock_in(product=self.product, quantity=Decimal("5"), user=self.user)
        movimiento = services.register_stock_out(
            product=self.product, quantity=Decimal("5"), user=self.user
        )
        self.assertEqual(movimiento.stock_after, Decimal("0"))
        self.assertEqual(services.get_current_stock(self.product), Decimal("0"))

    def test_salida_que_dejaria_stock_negativo_es_rechazada(self):
        services.register_stock_in(product=self.product, quantity=Decimal("3"), user=self.user)
        with self.assertRaises(InvalidInventoryOperation):
            services.register_stock_out(product=self.product, quantity=Decimal("5"), user=self.user)
        # El stock no debe haber cambiado: la operación inválida no dejó rastro.
        self.assertEqual(services.get_current_stock(self.product), Decimal("3"))
        self.assertEqual(StockMovement.all_objects.filter(product=self.product).count(), 1)

    def test_cantidad_cero_es_rechazada_en_entrada(self):
        with self.assertRaises(InvalidInventoryOperation):
            services.register_stock_in(product=self.product, quantity=Decimal("0"), user=self.user)

    def test_cantidad_negativa_es_rechazada_en_salida(self):
        with self.assertRaises(InvalidInventoryOperation):
            services.register_stock_out(product=self.product, quantity=Decimal("-1"), user=self.user)

    def test_ajuste_fija_el_stock_exacto(self):
        services.register_stock_in(product=self.product, quantity=Decimal("10"), user=self.user)
        movimiento = services.register_stock_adjustment(
            product=self.product, new_stock=Decimal("7"), user=self.user, notes="Conteo físico"
        )
        self.assertEqual(movimiento.movement_type, StockMovement.MovementType.ADJUSTMENT)
        self.assertEqual(movimiento.stock_before, Decimal("10"))
        self.assertEqual(movimiento.stock_after, Decimal("7"))
        self.assertEqual(services.get_current_stock(self.product), Decimal("7"))

    def test_ajuste_negativo_es_rechazado(self):
        with self.assertRaises(InvalidInventoryOperation):
            services.register_stock_adjustment(
                product=self.product, new_stock=Decimal("-1"), user=self.user
            )

    def test_ajuste_igual_al_stock_actual_es_rechazado(self):
        services.register_stock_in(product=self.product, quantity=Decimal("10"), user=self.user)
        with self.assertRaises(InvalidInventoryOperation):
            services.register_stock_adjustment(
                product=self.product, new_stock=Decimal("10"), user=self.user
            )

    def test_stock_bajo_se_detecta_correctamente(self):
        # min_stock=5. Con 4 unidades, debe aparecer en "stock bajo".
        services.register_stock_in(product=self.product, quantity=Decimal("4"), user=self.user)
        bajos = services.get_low_stock_products(self.tenant)
        self.assertIn(self.product.pk, [p.pk for p in bajos])

    def test_stock_por_encima_del_minimo_no_aparece_en_stock_bajo(self):
        services.register_stock_in(product=self.product, quantity=Decimal("100"), user=self.user)
        bajos = services.get_low_stock_products(self.tenant)
        self.assertNotIn(self.product.pk, [p.pk for p in bajos])

    def test_movimiento_registra_todos_los_campos_de_auditoria(self):
        movimiento = services.register_stock_in(
            product=self.product, quantity=Decimal("2"), user=self.user, notes="Nota de prueba"
        )
        self.assertEqual(movimiento.tenant, self.tenant)
        self.assertEqual(movimiento.product, self.product)
        self.assertEqual(movimiento.movement_type, StockMovement.MovementType.IN)
        self.assertEqual(movimiento.quantity, Decimal("2"))
        self.assertEqual(movimiento.stock_before, Decimal("0"))
        self.assertEqual(movimiento.stock_after, Decimal("2"))
        self.assertEqual(movimiento.user, self.user)
        self.assertEqual(movimiento.notes, "Nota de prueba")
        self.assertIsNotNone(movimiento.created_at)

    def test_secuencia_de_movimientos_mantiene_consistencia(self):
        services.register_stock_in(product=self.product, quantity=Decimal("20"), user=self.user)
        services.register_stock_out(product=self.product, quantity=Decimal("5"), user=self.user)
        services.register_stock_adjustment(
            product=self.product, new_stock=Decimal("30"), user=self.user
        )
        services.register_stock_out(product=self.product, quantity=Decimal("30"), user=self.user)

        self.assertEqual(services.get_current_stock(self.product), Decimal("0"))
        historial = list(services.get_product_movements(self.product))
        self.assertEqual(len(historial), 4)
        # Cada "stock_before" debe encadenar exactamente con el
        # "stock_after" del movimiento inmediatamente anterior.
        historial_cronologico = list(reversed(historial))
        for anterior, siguiente in zip(historial_cronologico, historial_cronologico[1:]):
            self.assertEqual(anterior.stock_after, siguiente.stock_before)


class StockMovementViewTests(InventoryTestCase):
    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(tenant=self.tenant, name="Vista Producto", sku="VP-1")

    def test_registrar_entrada_via_http(self):
        respuesta = self.client.post(
            reverse("inventory:stock_in", args=[self.product.pk]),
            {"quantity": "15", "notes": "Entrada de prueba"},
        )
        self.assertRedirects(respuesta, reverse("inventory:product_detail", args=[self.product.pk]))
        self.assertEqual(services.get_current_stock(self.product), Decimal("15"))

    def test_registrar_salida_invalida_muestra_error_sin_romper(self):
        respuesta = self.client.post(
            reverse("inventory:stock_out", args=[self.product.pk]), {"quantity": "5", "notes": ""}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "dejaría el stock en negativo")
        self.assertEqual(services.get_current_stock(self.product), Decimal("0"))

    def test_ajuste_via_http(self):
        respuesta = self.client.post(
            reverse("inventory:stock_adjustment", args=[self.product.pk]),
            {"new_stock": "50", "notes": "Conteo inicial"},
        )
        self.assertRedirects(respuesta, reverse("inventory:product_detail", args=[self.product.pk]))
        self.assertEqual(services.get_current_stock(self.product), Decimal("50"))

    def test_detalle_de_producto_muestra_stock_y_alerta_de_bajo_stock(self):
        product_bajo = Product.objects.create(
            tenant=self.tenant, name="Bajo Stock", sku="BAJO-1", min_stock=Decimal("10")
        )
        services.register_stock_in(product=product_bajo, quantity=Decimal("3"), user=self.user)

        respuesta = self.client.get(reverse("inventory:product_detail", args=[product_bajo.pk]))
        self.assertContains(respuesta, "por debajo de su stock mínimo")
