from datetime import timedelta

from django.utils import timezone

from apps.api import integration_services
from apps.api.models import Integration

from ._helpers import TODOS_LOS_SCOPES_CATALOG, IntegrationTestCase


class IntegrationLifecycleTests(IntegrationTestCase):
    def test_create_integration_crea_una_fila_activa_habilitada(self):
        self.assertEqual(self.integration.status, Integration.Status.ACTIVE)
        self.assertTrue(self.integration.is_enabled)
        self.assertTrue(self.integration.is_active)
        self.assertTrue(self.integration.app_key.startswith("app_"))
        self.assertEqual(self.integration.scopes, TODOS_LOS_SCOPES_CATALOG)

    def test_create_integration_rechaza_scope_de_inventario_no_de_catalogo(self):
        with self.assertRaises(integration_services.InvalidIntegrationOperation):
            integration_services.create_integration(
                self.tenant, user=self.owner, name="Otra", provider=Integration.Provider.BUDUN,
                scopes=["inventory:read"],
            )

    def test_create_integration_rechaza_nombre_duplicado_en_el_mismo_tenant(self):
        with self.assertRaises(integration_services.InvalidIntegrationOperation):
            integration_services.create_integration(
                self.tenant, user=self.owner, name="Integración de prueba",
                provider=Integration.Provider.BUDUN, scopes=["catalog:read"],
            )

    def test_un_tenant_puede_tener_varias_integraciones(self):
        segunda, _secreto = integration_services.create_integration(
            self.tenant, user=self.owner, name="Segunda integración",
            provider=Integration.Provider.OTHER_ERP, scopes=["catalog:read"],
        )
        self.assertEqual(Integration.all_objects.filter(tenant=self.tenant).count(), 2)
        self.assertNotEqual(segunda.app_key, self.integration.app_key)

    def test_el_secreto_completo_nunca_se_guarda(self):
        self.assertNotEqual(self.integration.secret_hash, self.secreto)

    def test_authenticate_integration_resuelve_la_credencial_correcta(self):
        resuelta = integration_services.authenticate_integration(self.secreto)
        self.assertEqual(resuelta.pk, self.integration.pk)

    def test_authenticate_integration_rechaza_secreto_invalido(self):
        self.assertIsNone(integration_services.authenticate_integration("no-es-un-secreto-real"))

    def test_rotate_integration_credential_invalida_el_secreto_anterior(self):
        app_key_antes = self.integration.app_key
        _integration, nuevo_secreto = integration_services.rotate_integration_credential(self.integration, user=self.owner)
        self.assertIsNone(integration_services.authenticate_integration(self.secreto))
        self.assertIsNotNone(integration_services.authenticate_integration(nuevo_secreto))
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.app_key, app_key_antes)  # el app_key no cambia al rotar.

    def test_revoke_integration_invalida_la_credencial(self):
        integration_services.revoke_integration(self.integration, user=self.owner)
        self.assertIsNone(integration_services.authenticate_integration(self.secreto))
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.status, Integration.Status.REVOKED)
        self.assertFalse(self.integration.is_active)

    def test_set_integration_enabled_false_invalida_la_credencial_reversiblemente(self):
        integration_services.set_integration_enabled(self.integration, is_enabled=False, user=self.owner)
        self.assertIsNone(integration_services.authenticate_integration(self.secreto))
        integration_services.set_integration_enabled(self.integration, is_enabled=True, user=self.owner)
        self.assertIsNotNone(integration_services.authenticate_integration(self.secreto))

    def test_authenticate_integration_rechaza_credencial_expirada(self):
        self.integration.expires_at = timezone.now() - timedelta(days=1)
        self.integration.save(update_fields=["expires_at"])
        self.assertIsNone(integration_services.authenticate_integration(self.secreto))

    def test_set_integration_scopes_valida_lista(self):
        with self.assertRaises(integration_services.InvalidIntegrationOperation):
            integration_services.set_integration_scopes(self.integration, scopes=["algo_invalido"], user=self.owner)
        integration_services.set_integration_scopes(self.integration, scopes=["catalog:read"], user=self.owner)
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.scopes, ["catalog:read"])

    def test_test_integration_connection_devuelve_ok_para_integracion_activa(self):
        ok, error = integration_services.test_integration_connection(self.integration, user=self.owner)
        self.assertTrue(ok)
        self.assertEqual(error, "")

    def test_test_integration_connection_devuelve_error_si_deshabilitada(self):
        integration_services.set_integration_enabled(self.integration, is_enabled=False, user=self.owner)
        ok, error = integration_services.test_integration_connection(self.integration, user=self.owner)
        self.assertFalse(ok)
        self.assertTrue(error)

    def test_operaciones_de_ciclo_de_vida_se_auditan(self):
        from apps.audit.models import AuditLog

        self.assertTrue(AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.INTEGRATION_CREATED).exists())
        integration_services.rotate_integration_credential(self.integration, user=self.owner)
        self.assertTrue(AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.INTEGRATION_ROTATED).exists())
        integration_services.revoke_integration(self.integration, user=self.owner)
        self.assertTrue(AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.INTEGRATION_REVOKED).exists())

    def test_credencial_de_apikey_nunca_autentica_una_integracion(self):
        """`ApiKey` (Inventory API) y `Integration` (Catalog API) son
        credenciales completamente separadas — la de una nunca sirve
        para la otra."""
        from apps.api import services as apikey_services

        api_key, secreto_apikey = apikey_services.generate_api_key(
            self.tenant, user=self.owner, scopes=["health:read"],
        )
        self.assertIsNone(integration_services.authenticate_integration(secreto_apikey))
