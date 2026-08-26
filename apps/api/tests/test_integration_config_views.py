from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.api.models import Integration
from apps.tenants.models import Membership

from ._helpers import IntegrationTestCase

User = get_user_model()


class IntegrationConfigViewsTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(email="admin.catalog@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.admin, tenant=self.tenant, role=Membership.Role.ADMIN)
        self.admin_client = self.client_class()
        self.admin_client.login(username="admin.catalog@example.com", password="clave-de-prueba-987")

    def test_owner_puede_ver_la_lista(self):
        respuesta = self.owner_client.get(reverse("api_integrations:list"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Integración de prueba")

    def test_crear_integracion_muestra_el_secreto_una_vez(self):
        respuesta = self.owner_client.post(reverse("api_integrations:create"), {
            "name": "Nueva integración", "provider": Integration.Provider.BUDUN, "scopes": ["catalog:read"],
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Copia esta credencial ahora")
        self.assertTrue(Integration.all_objects.filter(tenant=self.tenant, name="Nueva integración").exists())

    def test_admin_no_puede_crear_integracion_por_defecto(self):
        respuesta = self.admin_client.post(reverse("api_integrations:create"), {
            "name": "Bloqueada", "provider": Integration.Provider.BUDUN, "scopes": ["catalog:read"],
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_admin_puede_ver_pero_no_rotar(self):
        respuesta = self.admin_client.get(reverse("api_integrations:detail", args=[self.integration.pk]))
        self.assertEqual(respuesta.status_code, 200)
        respuesta_rotar = self.admin_client.post(reverse("api_integrations:rotate", args=[self.integration.pk]))
        self.assertEqual(respuesta_rotar.status_code, 403)

    def test_rotar_muestra_nuevo_secreto(self):
        respuesta = self.owner_client.post(reverse("api_integrations:rotate", args=[self.integration.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Copia esta credencial ahora")

    def test_revocar_marca_como_revocada(self):
        respuesta = self.owner_client.post(reverse("api_integrations:revoke", args=[self.integration.pk]))
        self.assertRedirects(respuesta, reverse("api_integrations:detail", args=[self.integration.pk]))
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.status, Integration.Status.REVOKED)

    def test_alternar_deshabilita_y_habilita(self):
        self.owner_client.post(reverse("api_integrations:toggle", args=[self.integration.pk]))
        self.integration.refresh_from_db()
        self.assertFalse(self.integration.is_enabled)
        self.owner_client.post(reverse("api_integrations:toggle", args=[self.integration.pk]))
        self.integration.refresh_from_db()
        self.assertTrue(self.integration.is_enabled)

    def test_probar_conexion_actualiza_estado(self):
        self.owner_client.post(reverse("api_integrations:test_connection", args=[self.integration.pk]))
        self.integration.refresh_from_db()
        self.assertTrue(self.integration.last_test_ok)

    def test_actualizar_scopes(self):
        respuesta = self.owner_client.post(
            reverse("api_integrations:update_scopes", args=[self.integration.pk]), {"scopes": ["catalog:read"]},
        )
        self.assertRedirects(respuesta, reverse("api_integrations:detail", args=[self.integration.pk]))
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.scopes, ["catalog:read"])

    def test_tenant_b_no_puede_ver_integracion_de_tenant_a(self):
        from apps.tenants.models import Tenant

        tenant_b = Tenant.objects.create(name="Empresa Catalog Config B", slug="empresa-catalog-config-b")
        owner_b = User.objects.create_user(email="owner.b.catalog.config@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=owner_b, tenant=tenant_b, role=Membership.Role.OWNER)
        cliente_b = self.client_class()
        cliente_b.login(username="owner.b.catalog.config@example.com", password="clave-de-prueba-987")
        respuesta = cliente_b.get(reverse("api_integrations:detail", args=[self.integration.pk]))
        self.assertEqual(respuesta.status_code, 404)
