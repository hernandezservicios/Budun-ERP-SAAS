from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse

from apps.api import services
from apps.api.throttling import ApiKeyRateThrottle
from apps.inventory import services as inv_services
from apps.inventory.models import Product

from ._helpers import ApiTestCase


class HealthEndpointTests(ApiTestCase):
    def test_health_con_clave_valida_devuelve_200_y_el_sobre_estandar(self):
        respuesta = self.client.get(reverse("api_v1:health"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertTrue(cuerpo["success"])
        self.assertIsNone(cuerpo["errors"])
        self.assertEqual(cuerpo["data"]["tenant"], self.tenant.name)

    def test_sin_encabezado_authorization_devuelve_401(self):
        respuesta = self.client.get(reverse("api_v1:health"))
        self.assertEqual(respuesta.status_code, 401)
        self.assertFalse(respuesta.json()["success"])

    def test_clave_invalida_devuelve_401(self):
        respuesta = self.client.get(reverse("api_v1:health"), **self.auth_headers("no-es-una-clave-real"))
        self.assertEqual(respuesta.status_code, 401)

    def test_clave_revocada_devuelve_401(self):
        services.revoke_api_key(self.api_key, user=self.owner)
        respuesta = self.client.get(reverse("api_v1:health"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 401)

    def test_scope_insuficiente_devuelve_403(self):
        services.set_api_key_scopes(self.api_key, scopes=["health:read"], user=self.owner)
        respuesta = self.client.get(reverse("api_v1:product_list"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 403)


class ProductEndpointTests(ApiTestCase):
    def test_products_list_devuelve_el_producto_con_stock_y_paginacion(self):
        respuesta = self.client.get(reverse("api_v1:product_list"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertEqual(len(cuerpo["data"]), 1)
        self.assertEqual(cuerpo["data"][0]["sku"], "API-1")
        self.assertEqual(cuerpo["data"][0]["current_stock"], "10.000")
        self.assertIn("page", cuerpo["meta"])
        self.assertIn("total", cuerpo["meta"])

    def test_products_detail_devuelve_404_para_id_de_otro_tenant(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Empresa API 3", slug="empresa-api-3")
        producto_ajeno = Product.objects.create(tenant=otro_tenant, name="Ajeno", sku="AJENO-1", sale_price=Decimal("1"))
        respuesta = self.client.get(reverse("api_v1:product_detail", args=[producto_ajeno.pk]), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 404)

    def test_products_filtra_por_sku(self):
        Product.objects.create(tenant=self.tenant, name="Otro", sku="OTRO-1", sale_price=Decimal("5"))
        respuesta = self.client.get(reverse("api_v1:product_list") + "?sku=API-1", **self.auth_headers())
        cuerpo = respuesta.json()
        self.assertEqual(len(cuerpo["data"]), 1)
        self.assertEqual(cuerpo["data"][0]["sku"], "API-1")

    def test_page_size_maximo_no_permite_paginas_ilimitadas(self):
        respuesta = self.client.get(reverse("api_v1:product_list") + "?page_size=99999", **self.auth_headers())
        self.assertEqual(respuesta.status_code, 200)
        self.assertLessEqual(respuesta.json()["meta"]["page_size"], 100)


class InventoryEndpointTests(ApiTestCase):
    def test_low_stock_incluye_producto_por_debajo_del_minimo(self):
        respuesta = self.client.get(reverse("api_v1:inventory_low_stock"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 200)
        # min_stock=5, stock actual=10 -> no debería aparecer todavía.
        self.assertEqual(len(respuesta.json()["data"]), 0)
        inv_services.register_stock_out(product=self.producto, quantity=Decimal("8"), user=self.owner)
        respuesta = self.client.get(reverse("api_v1:inventory_low_stock"), **self.auth_headers())
        self.assertEqual(len(respuesta.json()["data"]), 1)

    def test_movements_devuelve_los_movimientos_del_producto(self):
        respuesta = self.client.get(reverse("api_v1:inventory_movements") + f"?product={self.producto.pk}", **self.auth_headers())
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.json()["data"]), 1)
        self.assertEqual(respuesta.json()["data"][0]["movement_type"], "in")


class SerializedInventoryEndpointTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.producto_serial = Product.objects.create(
            tenant=self.tenant, name="Teléfono API", sku="API-TEL", sale_price=Decimal("500"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.unidad = inv_services.register_serialized_unit(
            product=self.producto_serial, user=self.owner, imei_1="123456789012345",
        )

    def test_serialized_enmascara_el_imei_por_defecto(self):
        respuesta = self.client.get(reverse("api_v1:inventory_serialized"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 200)
        fila = next(f for f in respuesta.json()["data"] if f["id"] == self.unidad.pk)
        self.assertNotEqual(fila["imei_1_masked"], "123456789012345")
        self.assertTrue(fila["imei_1_masked"].startswith("···"))
        self.assertTrue(fila["imei_1_masked"].endswith("2345"))

    def test_serialized_sin_scope_devuelve_403(self):
        services.set_api_key_scopes(self.api_key, scopes=["products:read"], user=self.owner)
        respuesta = self.client.get(reverse("api_v1:inventory_serialized"), **self.auth_headers())
        self.assertEqual(respuesta.status_code, 403)


class ApiMultiTenantIsolationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        from apps.tenants.models import Membership, Tenant

        User = get_user_model()
        self.tenant_b = Tenant.objects.create(name="Empresa API B", slug="empresa-api-b")
        self.owner_b = User.objects.create_user(email="owner.b.api@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner_b, tenant=self.tenant_b, role=Membership.Role.OWNER)
        self.producto_b = Product.objects.create(tenant=self.tenant_b, name="Producto B", sku="API-B-1", sale_price=Decimal("1"))
        self.api_key_b, self.secreto_b = services.generate_api_key(
            self.tenant_b, user=self.owner_b, scopes=["products:read"],
        )

    def test_clave_de_tenant_a_nunca_ve_productos_de_tenant_b(self):
        respuesta = self.client.get(reverse("api_v1:product_list"), **self.auth_headers())
        skus = {fila["sku"] for fila in respuesta.json()["data"]}
        self.assertNotIn("API-B-1", skus)

    def test_clave_de_tenant_b_resuelve_su_propio_tenant_nunca_el_enviado_por_parametro(self):
        respuesta = self.client.get(reverse("api_v1:product_list"), **self.auth_headers(self.secreto_b))
        cuerpo = respuesta.json()
        self.assertEqual(len(cuerpo["data"]), 1)
        self.assertEqual(cuerpo["data"][0]["sku"], "API-B-1")


class ApiRateLimitTests(ApiTestCase):
    def test_supera_el_limite_configurado_devuelve_429(self):
        # `SimpleRateThrottle.THROTTLE_RATES` (DRF) se calcula UNA VEZ
        # como atributo de CLASE al importar `rest_framework.throttling`
        # — `override_settings(REST_FRAMEWORK=...)` dispara
        # `reload_api_settings`, pero eso nunca vuelve a tocar ese
        # atributo de clase ya fijado. La forma correcta de probar un
        # límite distinto es parchear la clase directamente.
        with patch.object(ApiKeyRateThrottle, "THROTTLE_RATES", {"api_key": "2/min"}):
            for _ in range(2):
                respuesta = self.client.get(reverse("api_v1:health"), **self.auth_headers())
                self.assertEqual(respuesta.status_code, 200)
            respuesta = self.client.get(reverse("api_v1:health"), **self.auth_headers())
            self.assertEqual(respuesta.status_code, 429)
