import tempfile
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.api import integration_services
from apps.inventory import services as inv_services
from apps.inventory.models import Product

from ._helpers import IntegrationTestCase

_CATALOG_MEDIA_TEMPORAL = tempfile.mkdtemp(prefix="erp-saas-test-catalog-api-media-")

_CAMPOS_PROHIBIDOS = {
    "imei", "imei_1", "imei_2", "serial", "serial_number", "unit_cost", "purchase_cost",
    "cost", "margin", "supplier", "supplier_id", "stock_movements", "customer",
    "customer_private_data", "payments", "cash", "accounting", "payroll", "hr_sensitive_data",
}


def _png_real():
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="blue").save(buffer, format="PNG")
    return SimpleUploadedFile("foto.png", buffer.getvalue(), content_type="image/png")


class CatalogWhitelistTests(IntegrationTestCase):
    """Sección 6 de la ampliación: verificar la AUSENCIA de campos
    prohibidos, no solo la presencia de los permitidos."""

    def test_product_list_nunca_incluye_campos_prohibidos(self):
        respuesta = self.owner_client.get(reverse("catalog:product_list"), **self.auth_headers())
        fila = respuesta.json()["data"][0]
        self.assertFalse(_CAMPOS_PROHIBIDOS & set(fila.keys()))

    def test_product_detail_nunca_incluye_campos_prohibidos(self):
        respuesta = self.owner_client.get(reverse("catalog:product_detail", args=[self.producto.pk]), **self.auth_headers())
        cuerpo = respuesta.json()["data"]
        self.assertFalse(_CAMPOS_PROHIBIDOS & set(cuerpo.keys()))

    def test_product_response_nunca_incluye_purchase_price(self):
        respuesta = self.owner_client.get(reverse("catalog:product_list"), **self.auth_headers())
        self.assertNotIn("purchase_price", respuesta.json()["data"][0])


class CatalogSearchAndListTests(IntegrationTestCase):
    def test_search_por_nombre(self):
        respuesta = self.owner_client.get(reverse("catalog:search") + "?q=Catalog", **self.auth_headers())
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.json()["data"]), 1)

    def test_search_por_sku(self):
        respuesta = self.owner_client.get(reverse("catalog:search") + "?q=CAT-1", **self.auth_headers())
        self.assertEqual(len(respuesta.json()["data"]), 1)

    def test_search_por_marca(self):
        respuesta = self.owner_client.get(reverse("catalog:search") + "?brand=Marca", **self.auth_headers())
        self.assertEqual(len(respuesta.json()["data"]), 1)

    def test_search_por_color_variante(self):
        respuesta = self.owner_client.get(reverse("catalog:search") + "?color=Negro", **self.auth_headers())
        self.assertEqual(len(respuesta.json()["data"]), 1)
        respuesta_vacia = self.owner_client.get(reverse("catalog:search") + "?color=Verde", **self.auth_headers())
        self.assertEqual(len(respuesta_vacia.json()["data"]), 0)

    def test_search_nunca_busca_por_imei_o_serial(self):
        """Producto serializado con un IMEI real: buscar por ese IMEI
        vía Catalog API nunca debe devolver resultados (sección 4)."""
        producto_serial = Product.objects.create(
            tenant=self.tenant, name="Producto serializado", sku="SER-1", sale_price=Decimal("100"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        inv_services.register_serialized_unit(product=producto_serial, user=self.owner, imei_1="999888777666555")
        respuesta = self.owner_client.get(reverse("catalog:search") + "?q=999888777666555", **self.auth_headers())
        self.assertEqual(len(respuesta.json()["data"]), 0)

    def test_product_list_incluye_disponibilidad_de_la_misma_fuente_de_verdad(self):
        respuesta = self.owner_client.get(reverse("catalog:product_list"), **self.auth_headers())
        fila = respuesta.json()["data"][0]
        self.assertEqual(fila["available_quantity"], "7.000")
        self.assertTrue(fila["available"])

    def test_product_detail_404_para_producto_de_otro_tenant(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Empresa Catalog 2", slug="empresa-catalog-2")
        producto_ajeno = Product.objects.create(tenant=otro_tenant, name="Ajeno", sku="AJENO-CAT", sale_price=Decimal("1"))
        respuesta = self.owner_client.get(reverse("catalog:product_detail", args=[producto_ajeno.pk]), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 404)


class CatalogVariantsAndAvailabilityTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.variante_azul = Product.objects.create(
            tenant=self.tenant, name="Teléfono Catalog Azul", sku="CAT-2", sale_price=Decimal("500"),
            brand=self.producto.brand, model_name=self.producto.model_name, variant_attributes={"color": "Azul"},
        )
        inv_services.register_stock_in(product=self.variante_azul, quantity=Decimal("3"), user=self.owner)

    def test_variants_devuelve_el_grupo_completo_con_disponibilidad(self):
        respuesta = self.owner_client.get(
            reverse("catalog:variants") + f"?product={self.producto.pk}", **self.auth_headers(),
        )
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()["data"]
        self.assertEqual(len(datos), 2)
        colores = {fila["variant_attributes"].get("color"): fila["available_quantity"] for fila in datos}
        self.assertEqual(colores["Negro"], "7.000")
        self.assertEqual(colores["Azul"], "3.000")

    def test_variants_requiere_parametro_product(self):
        respuesta = self.owner_client.get(reverse("catalog:variants"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 400)

    def test_product_detail_incluye_variantes_hermanas(self):
        respuesta = self.owner_client.get(reverse("catalog:product_detail", args=[self.producto.pk]), **self.auth_headers())
        variantes = respuesta.json()["data"]["variants"]
        self.assertEqual(len(variantes), 1)
        self.assertEqual(variantes[0]["id"], self.variante_azul.pk)

    def test_availability_filtra_por_producto(self):
        respuesta = self.owner_client.get(
            reverse("catalog:availability") + f"?product={self.producto.pk}", **self.auth_headers(),
        )
        self.assertEqual(len(respuesta.json()["data"]), 1)

    def test_availability_requiere_scope_propio(self):
        integration_services.set_integration_scopes(self.integration, scopes=["catalog:read"], user=self.owner)
        respuesta = self.owner_client.get(reverse("catalog:availability"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 403)


@override_settings(CATALOG_MEDIA_ROOT=_CATALOG_MEDIA_TEMPORAL)
class CatalogMediaTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.imagen = inv_services.register_product_image(product=self.producto, archivo=_png_real(), user=self.owner)

    def test_media_list_devuelve_metadatos_con_url_absoluta(self):
        respuesta = self.owner_client.get(reverse("catalog:media_list") + f"?product={self.producto.pk}", **self.auth_headers())
        self.assertEqual(respuesta.status_code, 200)
        fila = respuesta.json()["data"][0]
        self.assertTrue(fila["url"].startswith("http"))
        self.assertTrue(fila["is_primary"])

    def test_media_list_requiere_scope_propio(self):
        integration_services.set_integration_scopes(self.integration, scopes=["catalog:read"], user=self.owner)
        respuesta = self.owner_client.get(reverse("catalog:media_list") + f"?product={self.producto.pk}", **self.auth_headers())
        self.assertEqual(respuesta.status_code, 403)

    def test_media_file_sirve_la_imagen_sin_autenticacion(self):
        respuesta = self.owner_client.get(reverse("catalog:media_file", args=[self.imagen.public_id]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "image/png")

    def test_media_file_de_uuid_inexistente_da_404(self):
        import uuid

        respuesta = self.owner_client.get(reverse("catalog:media_file", args=[uuid.uuid4()]))
        self.assertEqual(respuesta.status_code, 404)

    def test_product_response_incluye_primary_image_y_images(self):
        respuesta = self.owner_client.get(reverse("catalog:product_detail", args=[self.producto.pk]), **self.auth_headers())
        cuerpo = respuesta.json()["data"]
        self.assertIsNotNone(cuerpo["primary_image"])
        self.assertEqual(len(cuerpo["images"]), 1)


class CatalogSecurityTests(IntegrationTestCase):
    def test_sin_encabezado_authorization_devuelve_401(self):
        respuesta = self.owner_client.get(reverse("catalog:product_list"))
        self.assertEqual(respuesta.status_code, 401)

    def test_credencial_invalida_devuelve_401(self):
        respuesta = self.owner_client.get(reverse("catalog:product_list"), **self.auth_headers("no-es-una-credencial-real"))
        self.assertEqual(respuesta.status_code, 401)

    def test_credencial_revocada_devuelve_401(self):
        integration_services.revoke_integration(self.integration, user=self.owner)
        respuesta = self.owner_client.get(reverse("catalog:product_list"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 401)

    def test_credencial_deshabilitada_devuelve_401(self):
        integration_services.set_integration_enabled(self.integration, is_enabled=False, user=self.owner)
        respuesta = self.owner_client.get(reverse("catalog:product_list"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 401)

    def test_scope_insuficiente_devuelve_403(self):
        integration_services.set_integration_scopes(self.integration, scopes=["catalog:media:read"], user=self.owner)
        respuesta = self.owner_client.get(reverse("catalog:product_list"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 403)

    def test_page_size_maximo_no_permite_paginas_ilimitadas(self):
        respuesta = self.owner_client.get(reverse("catalog:product_list") + "?page_size=99999", **self.auth_headers())
        self.assertLessEqual(respuesta.json()["meta"]["page_size"], 100)


class CatalogMultiTenantIsolationTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        from apps.tenants.models import Membership, Tenant

        User = get_user_model()
        self.tenant_b = Tenant.objects.create(name="Empresa Catalog B", slug="empresa-catalog-b")
        self.owner_b = User.objects.create_user(email="owner.b.catalog@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner_b, tenant=self.tenant_b, role=Membership.Role.OWNER)
        self.producto_b = Product.objects.create(tenant=self.tenant_b, name="Producto B", sku="CAT-B-1", sale_price=Decimal("1"))
        self.integration_b, self.secreto_b = integration_services.create_integration(
            self.tenant_b, user=self.owner_b, name="Integración B", provider="budun", scopes=["catalog:read"],
        )

    def test_credencial_de_tenant_a_nunca_ve_productos_de_tenant_b(self):
        respuesta = self.owner_client.get(reverse("catalog:product_list"), **self.auth_headers())
        skus = {fila["sku"] for fila in respuesta.json()["data"]}
        self.assertNotIn("CAT-B-1", skus)

    def test_credencial_de_tenant_b_resuelve_su_propio_tenant(self):
        respuesta = self.owner_client.get(reverse("catalog:product_list"), **self.auth_headers(self.secreto_b))
        cuerpo = respuesta.json()["data"]
        self.assertEqual(len(cuerpo), 1)
        self.assertEqual(cuerpo[0]["sku"], "CAT-B-1")
