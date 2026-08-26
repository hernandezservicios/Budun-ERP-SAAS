"""Ampliación final de FASE 15 — campos comerciales de `Product`,
`ProductImage` y agrupación de variantes (ver `docs/api-catalog.md`)."""

import tempfile
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.inventory import services
from apps.inventory.models import Product, ProductImage

from ._helpers import InventoryTestCase

_CATALOG_MEDIA_TEMPORAL = tempfile.mkdtemp(prefix="erp-saas-test-catalog-media-")


def _png_real():
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="red").save(buffer, format="PNG")
    return SimpleUploadedFile("foto.png", buffer.getvalue(), content_type="image/png")


@override_settings(CATALOG_MEDIA_ROOT=_CATALOG_MEDIA_TEMPORAL)
class ProductVariantTests(InventoryTestCase):
    def setUp(self):
        super().setUp()
        self.negro = Product.objects.create(
            tenant=self.tenant, name="Samsung S25 256GB Negro", sku="S25-256-NEG", sale_price=Decimal("800"),
            brand="Samsung", model_name="S25 256GB", variant_attributes={"color": "Negro", "capacity": "256GB"},
        )
        self.azul = Product.objects.create(
            tenant=self.tenant, name="Samsung S25 256GB Azul", sku="S25-256-AZU", sale_price=Decimal("800"),
            brand="Samsung", model_name="S25 256GB", variant_attributes={"color": "Azul", "capacity": "256GB"},
        )
        self.suelto = Product.objects.create(
            tenant=self.tenant, name="Producto sin marca", sku="SUELTO-1", sale_price=Decimal("10"),
        )
        services.register_stock_in(product=self.negro, quantity=Decimal("4"), user=self.user)
        services.register_stock_in(product=self.azul, quantity=Decimal("3"), user=self.user)

    def test_get_variant_group_agrupa_por_marca_y_modelo(self):
        grupo = list(services.get_variant_group(self.negro))
        self.assertEqual({p.pk for p in grupo}, {self.negro.pk, self.azul.pk})

    def test_get_variant_group_de_producto_sin_marca_devuelve_solo_si_mismo(self):
        grupo = list(services.get_variant_group(self.suelto))
        self.assertEqual([p.pk for p in grupo], [self.suelto.pk])

    def test_get_variant_availability_incluye_stock_de_cada_variante(self):
        disponibilidad = {p.pk: p.current_stock for p in services.get_variant_availability(self.negro)}
        self.assertEqual(disponibilidad[self.negro.pk], Decimal("4"))
        self.assertEqual(disponibilidad[self.azul.pk], Decimal("3"))


@override_settings(CATALOG_MEDIA_ROOT=_CATALOG_MEDIA_TEMPORAL)
class ProductImageServiceTests(InventoryTestCase):
    def setUp(self):
        super().setUp()
        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto con imagen", sku="IMG-1", sale_price=Decimal("50"),
        )

    def test_register_product_image_la_primera_es_principal_por_defecto(self):
        imagen = services.register_product_image(product=self.producto, archivo=_png_real(), user=self.user)
        self.assertTrue(imagen.is_primary)
        self.assertEqual(imagen.tenant, self.tenant)

    def test_register_product_image_rechaza_extension_no_permitida(self):
        pdf_falso = SimpleUploadedFile("doc.pdf", b"%PDF-1.4\nresto", content_type="application/pdf")
        with self.assertRaises(services.InvalidInventoryOperation):
            services.register_product_image(product=self.producto, archivo=pdf_falso, user=self.user)

    def test_marcar_una_segunda_imagen_como_principal_desmarca_la_anterior(self):
        primera = services.register_product_image(product=self.producto, archivo=_png_real(), user=self.user)
        segunda = services.register_product_image(
            product=self.producto, archivo=_png_real(), user=self.user, is_primary=True,
        )
        primera.refresh_from_db()
        self.assertFalse(primera.is_primary)
        self.assertTrue(segunda.is_primary)

    def test_set_primary_product_image(self):
        primera = services.register_product_image(product=self.producto, archivo=_png_real(), user=self.user)
        segunda = services.register_product_image(product=self.producto, archivo=_png_real(), user=self.user)
        services.set_primary_product_image(segunda)
        primera.refresh_from_db()
        segunda.refresh_from_db()
        self.assertFalse(primera.is_primary)
        self.assertTrue(segunda.is_primary)

    def test_delete_product_image_borra_la_fila(self):
        imagen = services.register_product_image(product=self.producto, archivo=_png_real(), user=self.user)
        pk = imagen.pk
        services.delete_product_image(imagen)
        self.assertFalse(ProductImage.all_objects.filter(pk=pk).exists())

    def test_get_product_images_ordena_principal_primero(self):
        services.register_product_image(product=self.producto, archivo=_png_real(), user=self.user)
        principal = services.register_product_image(
            product=self.producto, archivo=_png_real(), user=self.user, is_primary=True,
        )
        primera = services.get_product_images(self.producto).first()
        self.assertEqual(primera.pk, principal.pk)

    def test_cada_imagen_tiene_un_public_id_unico(self):
        i1 = services.register_product_image(product=self.producto, archivo=_png_real(), user=self.user)
        i2 = services.register_product_image(product=self.producto, archivo=_png_real(), user=self.user)
        self.assertNotEqual(i1.public_id, i2.public_id)
