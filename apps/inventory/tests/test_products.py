from decimal import Decimal

from django.urls import reverse

from apps.inventory.models import Category, Product

from ._helpers import InventoryTestCase


class ProductCrudTests(InventoryTestCase):
    def test_crear_producto(self):
        respuesta = self.client.post(
            reverse("inventory:product_create"),
            {
                "name": "Refresco 600ml",
                "sku": "REF-600",
                "barcode": "",
                "category": "",
                "description": "",
                "purchase_price": "8.50",
                "sale_price": "15.00",
                "tax_rate": "16",
                "min_stock": "10",
                "is_active": "on",
            },
        )
        producto = Product.all_objects.get(tenant=self.tenant, sku="REF-600")
        self.assertRedirects(respuesta, reverse("inventory:product_detail", args=[producto.pk]))
        self.assertEqual(producto.sale_price, Decimal("15.00"))

    def test_editar_producto(self):
        producto = Product.objects.create(
            tenant=self.tenant, name="Original", sku="ORIG-1", sale_price=Decimal("10")
        )
        respuesta = self.client.post(
            reverse("inventory:product_update", args=[producto.pk]),
            {
                "name": "Actualizado",
                "sku": "ORIG-1",
                "barcode": "",
                "category": "",
                "description": "",
                "purchase_price": "5",
                "sale_price": "12",
                "tax_rate": "0",
                "min_stock": "0",
                "is_active": "on",
            },
        )
        self.assertRedirects(respuesta, reverse("inventory:product_detail", args=[producto.pk]))
        producto.refresh_from_db()
        self.assertEqual(producto.name, "Actualizado")
        self.assertEqual(producto.sale_price, Decimal("12"))

    def test_desactivar_producto_es_borrado_suave(self):
        producto = Product.objects.create(tenant=self.tenant, name="A desactivar", sku="DESACT-1")
        respuesta = self.client.post(reverse("inventory:product_deactivate", args=[producto.pk]))
        self.assertRedirects(respuesta, reverse("inventory:product_list"))
        producto.refresh_from_db()
        self.assertFalse(producto.is_active)
        # Sigue existiendo (borrado suave, no físico).
        self.assertTrue(Product.all_objects.filter(pk=producto.pk).exists())

    def test_sku_duplicado_rechazado_en_el_mismo_tenant(self):
        Product.objects.create(tenant=self.tenant, name="Primero", sku="DUP-1")
        respuesta = self.client.post(
            reverse("inventory:product_create"),
            {
                "name": "Segundo",
                "sku": "DUP-1",
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
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["form"].is_valid())
        self.assertEqual(Product.all_objects.filter(tenant=self.tenant, sku="DUP-1").count(), 1)

    def test_codigo_de_barras_duplicado_rechazado(self):
        Product.objects.create(tenant=self.tenant, name="Primero", sku="BC-1", barcode="7501234567890")
        respuesta = self.client.post(
            reverse("inventory:product_create"),
            {
                "name": "Segundo",
                "sku": "BC-2",
                "barcode": "7501234567890",
                "category": "",
                "description": "",
                "purchase_price": "0",
                "sale_price": "0",
                "tax_rate": "0",
                "min_stock": "0",
                "is_active": "on",
            },
        )
        self.assertFalse(respuesta.context["form"].is_valid())

    def test_multiples_productos_con_codigo_de_barras_vacio_son_validos(self):
        """El UniqueConstraint de barcode es parcial (condition=~vacío):
        varios productos sin código de barras no deben chocar entre sí."""
        Product.objects.create(tenant=self.tenant, name="Sin barcode 1", sku="NB-1", barcode="")
        Product.objects.create(tenant=self.tenant, name="Sin barcode 2", sku="NB-2", barcode="")
        self.assertEqual(Product.all_objects.filter(tenant=self.tenant, barcode="").count(), 2)

    def test_precio_negativo_rechazado_por_el_formulario(self):
        respuesta = self.client.post(
            reverse("inventory:product_create"),
            {
                "name": "Precio inválido",
                "sku": "NEG-1",
                "barcode": "",
                "category": "",
                "description": "",
                "purchase_price": "-5",
                "sale_price": "10",
                "tax_rate": "0",
                "min_stock": "0",
                "is_active": "on",
            },
        )
        self.assertFalse(respuesta.context["form"].is_valid())
        self.assertFalse(Product.all_objects.filter(tenant=self.tenant, sku="NEG-1").exists())

    def test_precio_negativo_rechazado_por_check_constraint_de_postgres(self):
        """Defensa en profundidad: incluso saltándose el formulario, la
        base de datos rechaza un precio negativo."""
        from django.db import IntegrityError, transaction

        producto = Product(
            tenant=self.tenant, name="Directo a BD", sku="DB-NEG-1", sale_price=Decimal("-1")
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                producto.save()

    def test_busqueda_por_nombre(self):
        Product.objects.create(tenant=self.tenant, name="Manzana Roja", sku="MZ-1")
        Product.objects.create(tenant=self.tenant, name="Plátano", sku="PL-1")
        respuesta = self.client.get(reverse("inventory:product_list"), {"q": "Manzana"})
        self.assertContains(respuesta, "Manzana Roja")
        self.assertNotContains(respuesta, "Plátano")

    def test_busqueda_por_sku(self):
        Product.objects.create(tenant=self.tenant, name="Producto A", sku="ABC-123")
        respuesta = self.client.get(reverse("inventory:product_list"), {"q": "ABC-123"})
        self.assertContains(respuesta, "Producto A")

    def test_filtro_por_categoria(self):
        categoria_a = Category.objects.create(tenant=self.tenant, name="Categoría A")
        categoria_b = Category.objects.create(tenant=self.tenant, name="Categoría B")
        Product.objects.create(tenant=self.tenant, name="En A", sku="EN-A", category=categoria_a)
        Product.objects.create(tenant=self.tenant, name="En B", sku="EN-B", category=categoria_b)

        respuesta = self.client.get(reverse("inventory:product_list"), {"categoria": categoria_a.pk})
        self.assertContains(respuesta, "En A")
        self.assertNotContains(respuesta, "En B")

    def test_productos_inactivos_ocultos_por_defecto(self):
        Product.objects.create(tenant=self.tenant, name="Inactivo", sku="INACT-1", is_active=False)
        respuesta = self.client.get(reverse("inventory:product_list"))
        self.assertNotContains(respuesta, "Inactivo")

        respuesta_con_inactivos = self.client.get(
            reverse("inventory:product_list"), {"mostrar_inactivos": "1"}
        )
        self.assertContains(respuesta_con_inactivos, "Inactivo")

    def test_paginacion(self):
        for i in range(25):
            Product.objects.create(tenant=self.tenant, name=f"Producto {i}", sku=f"PAG-{i}")
        respuesta = self.client.get(reverse("inventory:product_list"))
        self.assertTrue(respuesta.context["is_paginated"])
        self.assertEqual(len(respuesta.context["products"]), 20)
