from datetime import timedelta

from django.utils import timezone

from apps.api import services
from apps.api.models import ApiKey

from ._helpers import TODOS_LOS_SCOPES, ApiTestCase


class ApiKeyLifecycleTests(ApiTestCase):
    def test_generate_api_key_crea_una_fila_activa_con_scopes(self):
        self.assertEqual(self.api_key.status, ApiKey.Status.ACTIVE)
        self.assertEqual(self.api_key.scopes, TODOS_LOS_SCOPES)
        self.assertTrue(self.api_key.key_prefix.startswith("bk_"))

    def test_generate_api_key_rechaza_scope_invalido(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Empresa API 2", slug="empresa-api-2")
        with self.assertRaises(services.InvalidApiKeyOperation):
            services.generate_api_key(otro_tenant, user=self.owner, scopes=["no_existe:read"])

    def test_generate_api_key_rechaza_una_segunda_clave_para_el_mismo_tenant(self):
        with self.assertRaises(services.InvalidApiKeyOperation):
            services.generate_api_key(self.tenant, user=self.owner, scopes=["health:read"])

    def test_el_secreto_completo_nunca_se_guarda(self):
        self.assertNotEqual(self.api_key.key_hash, self.secreto)
        self.assertNotIn(self.secreto, self.api_key.key_prefix)

    def test_authenticate_api_key_resuelve_la_clave_correcta(self):
        resuelta = services.authenticate_api_key(self.secreto)
        self.assertEqual(resuelta.pk, self.api_key.pk)

    def test_authenticate_api_key_rechaza_secreto_invalido(self):
        self.assertIsNone(services.authenticate_api_key("secreto-que-no-existe"))

    def test_rotate_api_key_invalida_el_secreto_anterior(self):
        _api_key, nuevo_secreto = services.rotate_api_key(self.api_key, user=self.owner)
        self.assertIsNone(services.authenticate_api_key(self.secreto))
        self.assertIsNotNone(services.authenticate_api_key(nuevo_secreto))
        self.assertEqual(ApiKey.all_objects.filter(tenant=self.tenant).count(), 1)

    def test_revoke_api_key_invalida_la_clave(self):
        services.revoke_api_key(self.api_key, user=self.owner)
        self.assertIsNone(services.authenticate_api_key(self.secreto))
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.status, ApiKey.Status.REVOKED)

    def test_authenticate_api_key_rechaza_clave_expirada(self):
        self.api_key.expires_at = timezone.now() - timedelta(days=1)
        self.api_key.save(update_fields=["expires_at"])
        self.assertIsNone(services.authenticate_api_key(self.secreto))

    def test_test_connection_devuelve_ok_para_clave_activa(self):
        ok, error = services.test_connection(self.api_key, user=self.owner)
        self.assertTrue(ok)
        self.assertEqual(error, "")
        self.api_key.refresh_from_db()
        self.assertTrue(self.api_key.last_test_ok)
        self.assertIsNotNone(self.api_key.last_tested_at)

    def test_test_connection_devuelve_error_para_clave_revocada(self):
        services.revoke_api_key(self.api_key, user=self.owner)
        ok, error = services.test_connection(self.api_key, user=self.owner)
        self.assertFalse(ok)
        self.assertTrue(error)

    def test_set_api_key_scopes_valida_lista(self):
        with self.assertRaises(services.InvalidApiKeyOperation):
            services.set_api_key_scopes(self.api_key, scopes=["algo_invalido"], user=self.owner)
        services.set_api_key_scopes(self.api_key, scopes=["health:read"], user=self.owner)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.scopes, ["health:read"])

    def test_operaciones_de_ciclo_de_vida_se_auditan(self):
        from apps.audit.models import AuditLog

        self.assertTrue(AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.API_KEY_CREATED).exists())
        services.rotate_api_key(self.api_key, user=self.owner)
        self.assertTrue(AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.API_KEY_ROTATED).exists())
        services.revoke_api_key(self.api_key, user=self.owner)
        self.assertTrue(AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.API_KEY_REVOKED).exists())
