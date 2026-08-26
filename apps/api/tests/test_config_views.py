from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.api.models import ApiKey
from apps.tenants.models import Membership

from ._helpers import ApiTestCase

User = get_user_model()


class ApiKeyConfigViewTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        # Empieza sin clave (la de `ApiTestCase` se revoca/borra no —
        # se usa un tenant nuevo, sin clave, para probar el flujo de
        # generación desde cero).
        from apps.tenants.models import Tenant

        self.tenant_nuevo = Tenant.objects.create(name="Empresa API Config", slug="empresa-api-config")
        Membership.objects.create(user=self.owner, tenant=self.tenant_nuevo, role=Membership.Role.OWNER)
        self.admin = User.objects.create_user(email="admin.api@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.admin, tenant=self.tenant_nuevo, role=Membership.Role.ADMIN)
        self.admin_client = self.client_class()
        self.admin_client.login(username="admin.api@example.com", password="clave-de-prueba-987")

        self.owner_client_nuevo = self.client_class()
        self.owner_client_nuevo.login(username="owner.api@example.com", password="clave-de-prueba-987")
        self._activar_tenant(self.owner_client_nuevo, self.tenant_nuevo)
        self._activar_tenant(self.admin_client, self.tenant_nuevo)

    def _activar_tenant(self, client, tenant):
        session = client.session
        from apps.tenants.middleware import ACTIVE_TENANT_SESSION_KEY

        session[ACTIVE_TENANT_SESSION_KEY] = tenant.pk
        session.save()

    def test_ver_configuracion_sin_clave_muestra_formulario_de_generar(self):
        respuesta = self.owner_client_nuevo.get(reverse("api_config:config"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Generar clave")

    def test_generar_clave_crea_fila_y_muestra_secreto_una_vez(self):
        respuesta = self.owner_client_nuevo.post(reverse("api_config:generate"), {"scopes": ["health:read", "products:read"]})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Copia esta clave ahora")
        self.assertTrue(ApiKey.all_objects.filter(tenant=self.tenant_nuevo).exists())

    def test_admin_no_puede_generar_clave_por_defecto(self):
        respuesta = self.admin_client.post(reverse("api_config:generate"), {"scopes": ["health:read"]})
        self.assertEqual(respuesta.status_code, 403)

    def test_admin_puede_ver_la_configuracion(self):
        respuesta = self.admin_client.get(reverse("api_config:config"))
        self.assertEqual(respuesta.status_code, 200)


class ApiKeyConfigActionsTests(ApiTestCase):
    """Usa `self.api_key` ya generada por `ApiTestCase`."""

    def test_rotar_invalida_el_secreto_anterior_y_muestra_uno_nuevo(self):
        respuesta = self.owner_client.post(reverse("api_config:rotate"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Copia esta clave ahora")

    def test_revocar_marca_la_clave_como_revocada(self):
        respuesta = self.owner_client.post(reverse("api_config:revoke"))
        self.assertRedirects(respuesta, reverse("api_config:config"))
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.status, ApiKey.Status.REVOKED)

    def test_probar_conexion_actualiza_el_estado(self):
        self.owner_client.post(reverse("api_config:test_connection"))
        self.api_key.refresh_from_db()
        self.assertTrue(self.api_key.last_test_ok)

    def test_actualizar_scopes(self):
        respuesta = self.owner_client.post(reverse("api_config:update_scopes"), {"scopes": ["health:read"]})
        self.assertRedirects(respuesta, reverse("api_config:config"))
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.scopes, ["health:read"])
