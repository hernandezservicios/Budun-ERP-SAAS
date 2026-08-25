"""
Aislamiento Multi-Tenant de Productos e Inventario (FASE 8, objetivo
explícito del usuario): Tenant A nunca debe poder leer, modificar,
eliminar, buscar, filtrar ni acceder por URL/ID manipulado a datos de
Tenant B.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.inventory import services
from apps.inventory.models import Category, Product, StockMovement
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class InventoryIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Inventario Tenant A", slug="inv-tenant-a")
        self.tenant_b = Tenant.objects.create(name="Inventario Tenant B", slug="inv-tenant-b")

        self.user_a = User.objects.create_user(email="inv.a@example.com", password="clave-de-prueba-987")
        self.user_b = User.objects.create_user(email="inv.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user_a, tenant=self.tenant_a, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.user_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

        self.category_a = Category.objects.create(tenant=self.tenant_a, name="Categoría A")
        self.category_b = Category.objects.create(tenant=self.tenant_b, name="Categoría B")

        self.product_a = Product.objects.create(
            tenant=self.tenant_a,
            name="Producto Secreto A",
            sku="SEC-A",
            category=self.category_a,
            min_stock=Decimal("5"),
        )
        self.product_b = Product.objects.create(
            tenant=self.tenant_b,
            name="Producto Secreto B",
            sku="SEC-B",
            category=self.category_b,
            min_stock=Decimal("5"),
        )

        services.register_stock_in(product=self.product_a, quantity=Decimal("50"), user=self.user_a)
        services.register_stock_in(product=self.product_b, quantity=Decimal("99"), user=self.user_b)

        self.client_a = self.client_class()
        self.client_a.login(username="inv.a@example.com", password="clave-de-prueba-987")
        self.client_b = self.client_class()
        self.client_b.login(username="inv.b@example.com", password="clave-de-prueba-987")

    # --- Lectura -------------------------------------------------------

    def test_tenant_a_no_puede_leer_producto_de_tenant_b_por_url(self):
        respuesta = self.client_a.get(reverse("inventory:product_detail", args=[self.product_b.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_listado_de_productos_no_mezcla_tenants(self):
        respuesta_a = self.client_a.get(reverse("inventory:product_list"))
        self.assertContains(respuesta_a, "Producto Secreto A")
        self.assertNotContains(respuesta_a, "Producto Secreto B")

    def test_listado_de_categorias_no_mezcla_tenants(self):
        respuesta_a = self.client_a.get(reverse("inventory:category_list"))
        self.assertContains(respuesta_a, "Categoría A")
        self.assertNotContains(respuesta_a, "Categoría B")

    # --- Modificación ---------------------------------------------------

    def test_tenant_a_no_puede_editar_producto_de_tenant_b(self):
        respuesta = self.client_a.post(
            reverse("inventory:product_update", args=[self.product_b.pk]),
            {
                "name": "Hackeado",
                "sku": "SEC-B",
                "barcode": "",
                "category": "",
                "description": "",
                "purchase_price": "0",
                "sale_price": "0",
                "tax_rate": "0",
                "min_stock": "0",
                "is_active": "on",
            },
        )
        self.assertEqual(respuesta.status_code, 404)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.name, "Producto Secreto B")

    def test_tenant_a_no_puede_editar_categoria_de_tenant_b(self):
        respuesta = self.client_a.post(
            reverse("inventory:category_update", args=[self.category_b.pk]),
            {"name": "Hackeada", "order": 0, "is_active": "on"},
        )
        self.assertEqual(respuesta.status_code, 404)
        self.category_b.refresh_from_db()
        self.assertEqual(self.category_b.name, "Categoría B")

    def test_tenant_a_no_puede_registrar_movimiento_de_stock_sobre_producto_de_tenant_b(self):
        respuesta = self.client_a.post(
            reverse("inventory:stock_in", args=[self.product_b.pk]),
            {"quantity": "999", "notes": "intento de manipulación"},
        )
        self.assertEqual(respuesta.status_code, 404)
        # El stock de B no debe haber cambiado ni un solo movimiento.
        self.assertEqual(services.get_current_stock(self.product_b), Decimal("99"))
        self.assertEqual(StockMovement.all_objects.filter(product=self.product_b).count(), 1)

    def test_tenant_a_no_puede_desactivar_producto_de_tenant_b(self):
        respuesta = self.client_a.post(
            reverse("inventory:product_deactivate", args=[self.product_b.pk])
        )
        self.assertEqual(respuesta.status_code, 404)
        self.product_b.refresh_from_db()
        self.assertTrue(self.product_b.is_active)

    # --- Eliminación ------------------------------------------------------

    def test_tenant_a_no_puede_eliminar_categoria_de_tenant_b(self):
        respuesta = self.client_a.post(reverse("inventory:category_delete", args=[self.category_b.pk]))
        self.assertEqual(respuesta.status_code, 404)
        self.assertTrue(Category.all_objects.filter(pk=self.category_b.pk).exists())

    # --- Búsquedas y filtros ------------------------------------------------

    def test_busqueda_de_tenant_a_no_encuentra_producto_de_tenant_b(self):
        respuesta = self.client_a.get(reverse("inventory:product_list"), {"q": "Secreto B"})
        self.assertNotContains(respuesta, "Producto Secreto B")

    def test_filtrar_por_id_de_categoria_de_otro_tenant_no_devuelve_nada(self):
        """Manipular ?categoria=<id de la categoría de otro tenant> no
        debe filtrar por esa categoría real de otro tenant ni devolver
        productos del propio tenant que no correspondan."""
        respuesta = self.client_a.get(
            reverse("inventory:product_list"), {"categoria": self.category_b.pk}
        )
        self.assertNotContains(respuesta, "Producto Secreto A")
        self.assertNotContains(respuesta, "Producto Secreto B")

    # --- IDs manipulados en cada URL de inventario ------------------------

    def test_ids_manipulados_en_todas_las_urls_de_producto_devuelven_404(self):
        urls_con_id_ajeno = [
            reverse("inventory:product_detail", args=[self.product_b.pk]),
            reverse("inventory:product_update", args=[self.product_b.pk]),
            reverse("inventory:stock_in", args=[self.product_b.pk]),
            reverse("inventory:stock_out", args=[self.product_b.pk]),
            reverse("inventory:stock_adjustment", args=[self.product_b.pk]),
        ]
        for url in urls_con_id_ajeno:
            with self.subTest(url=url):
                self.assertEqual(self.client_a.get(url).status_code, 404)

    def test_manipular_sesion_hacia_otro_tenant_no_filtra_datos_de_inventario(self):
        """Regresión directa de FASE 3: ni siquiera manipulando
        active_tenant_id en la sesión se puede ver el inventario de otro
        tenant."""
        session = self.client_a.session
        session["active_tenant_id"] = self.tenant_b.id
        session.save()

        respuesta = self.client_a.get(reverse("inventory:product_list"))
        self.assertNotContains(respuesta, "Producto Secreto B")

    def test_stock_de_tenant_b_nunca_cambia_por_operaciones_de_tenant_a(self):
        """Verificación final de extremo a extremo: pase lo que pase en
        el tenant A, el stock de B permanece intacto."""
        self.client_a.post(
            reverse("inventory:stock_out", args=[self.product_a.pk]),
            {"quantity": "10", "notes": ""},
        )
        self.assertEqual(services.get_current_stock(self.product_b), Decimal("99"))
