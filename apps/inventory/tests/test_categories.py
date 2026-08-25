from django.urls import reverse

from apps.inventory.models import Category, Product

from ._helpers import InventoryTestCase


class CategoryCrudTests(InventoryTestCase):
    def test_crear_categoria(self):
        respuesta = self.client.post(
            reverse("inventory:category_create"), {"name": "Bebidas", "order": 1, "is_active": "on"}
        )
        self.assertRedirects(respuesta, reverse("inventory:category_list"))
        # all_objects: fuera de una request real, el ContextVar de
        # TenantMiddleware ya no está fijado (ver nota de diseño en
        # apps/inventory/services.py) — se filtra tenant explícitamente.
        categoria = Category.all_objects.get(tenant=self.tenant, name="Bebidas")
        self.assertTrue(categoria.is_active)

    def test_listar_categorias(self):
        Category.objects.create(tenant=self.tenant, name="Snacks", order=1)
        respuesta = self.client.get(reverse("inventory:category_list"))
        self.assertContains(respuesta, "Snacks")

    def test_editar_categoria(self):
        categoria = Category.objects.create(tenant=self.tenant, name="Original", order=1)
        respuesta = self.client.post(
            reverse("inventory:category_update", args=[categoria.pk]),
            {"name": "Renombrada", "order": 2, "is_active": "on"},
        )
        self.assertRedirects(respuesta, reverse("inventory:category_list"))
        categoria.refresh_from_db()
        self.assertEqual(categoria.name, "Renombrada")
        self.assertEqual(categoria.order, 2)

    def test_eliminar_categoria_sin_productos(self):
        categoria = Category.objects.create(tenant=self.tenant, name="Sin productos", order=1)
        respuesta = self.client.post(reverse("inventory:category_delete", args=[categoria.pk]))
        self.assertRedirects(respuesta, reverse("inventory:category_list"))
        self.assertFalse(Category.all_objects.filter(pk=categoria.pk).exists())

    def test_eliminar_categoria_con_productos_falla_con_mensaje_claro(self):
        """on_delete=PROTECT en Product.category: el borrado debe
        rechazarse con un mensaje, no con un 500."""
        categoria = Category.objects.create(tenant=self.tenant, name="Con productos", order=1)
        Product.objects.create(
            tenant=self.tenant, name="Producto X", sku="SKU-X", category=categoria
        )

        respuesta = self.client.post(
            reverse("inventory:category_delete", args=[categoria.pk]), follow=True
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "tiene productos asociados")
        self.assertTrue(Category.all_objects.filter(pk=categoria.pk).exists())

    def test_nombre_duplicado_rechazado_en_el_mismo_tenant(self):
        Category.objects.create(tenant=self.tenant, name="Repetida", order=1)
        respuesta = self.client.post(
            reverse("inventory:category_create"), {"name": "Repetida", "order": 2, "is_active": "on"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["form"].is_valid())
        self.assertEqual(Category.all_objects.filter(tenant=self.tenant, name="Repetida").count(), 1)
