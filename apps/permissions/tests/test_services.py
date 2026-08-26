from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.permissions import services
from apps.permissions.catalog import is_valid_permission_code
from apps.permissions.models import RolePermission, UserPermissionOverride
from apps.permissions.services import InvalidPermissionOperation

from ._helpers import PermissionsTestCase


class HasPermissionResolutionTests(PermissionsTestCase):
    def test_owner_siempre_autorizado_incluso_sin_fila_de_rol(self):
        # OWNER no tiene entrada en DEFAULT_ROLE_PERMISSIONS: la
        # autorización viene de la regla especial, no del catálogo.
        self.assertTrue(services.has_permission(self.tenant, self.owner, "accounting.close_period"))
        self.assertTrue(services.has_permission(self.tenant, self.owner, "api.inventory.manage"))

    def test_superusuario_siempre_autorizado_aunque_no_tenga_membresia(self):
        self.assertTrue(services.has_permission(self.tenant, self.superuser, "accounting.close_period"))

    def test_admin_tiene_permiso_de_fabrica_pero_no_los_excluidos(self):
        self.assertTrue(services.has_permission(self.tenant, self.admin, "customers.view"))
        self.assertFalse(services.has_permission(self.tenant, self.admin, "accounting.close_period"))
        self.assertFalse(services.has_permission(self.tenant, self.admin, "settings.manage"))

    def test_employee_es_de_solo_lectura_en_la_mayoria_de_dominios(self):
        self.assertTrue(services.has_permission(self.tenant, self.employee, "sales.view"))
        self.assertFalse(services.has_permission(self.tenant, self.employee, "sales.create"))
        self.assertFalse(services.has_permission(self.tenant, self.employee, "hr.sensitive.view"))

    def test_rolepermission_del_tenant_amplia_el_default_de_fabrica(self):
        self.assertFalse(services.has_permission(self.tenant, self.employee, "sales.create"))
        RolePermission.all_objects.create(tenant=self.tenant, role="employee", permission_code="sales.create", is_granted=True)
        self.assertTrue(services.has_permission(self.tenant, self.employee, "sales.create"))

    def test_rolepermission_del_tenant_puede_revocar_un_default_de_fabrica(self):
        self.assertTrue(services.has_permission(self.tenant, self.manager, "sales.create"))
        RolePermission.all_objects.create(tenant=self.tenant, role="manager", permission_code="sales.create", is_granted=False)
        self.assertFalse(services.has_permission(self.tenant, self.manager, "sales.create"))

    def test_override_de_usuario_gana_sobre_rolepermission_y_default(self):
        RolePermission.all_objects.create(tenant=self.tenant, role="employee", permission_code="sales.create", is_granted=True)
        UserPermissionOverride.all_objects.create(
            tenant=self.tenant, user=self.employee, permission_code="sales.create", is_granted=False, reason="prueba",
        )
        self.assertFalse(services.has_permission(self.tenant, self.employee, "sales.create"))

    def test_override_de_usuario_puede_conceder_algo_que_su_rol_no_da(self):
        UserPermissionOverride.all_objects.create(
            tenant=self.tenant, user=self.employee, permission_code="accounting.post", is_granted=True, reason="caso especial",
        )
        self.assertTrue(services.has_permission(self.tenant, self.employee, "accounting.post"))

    def test_usuario_sin_membresia_en_el_tenant_no_tiene_ningun_permiso(self):
        self.assertFalse(services.has_permission(self.tenant, self.owner_b, "customers.view"))

    def test_codigo_de_permiso_invalido_lanza_excepcion(self):
        self.assertFalse(is_valid_permission_code("no.existe"))
        with self.assertRaises(InvalidPermissionOperation):
            services.has_permission(self.tenant, self.owner, "no.existe")


class RequirePermissionTests(PermissionsTestCase):
    def _request(self, user, tenant):
        request = RequestFactory().get("/")
        request.user = user
        request.tenant = tenant
        return request

    def test_require_permission_pasa_silenciosamente_si_autorizado(self):
        request = self._request(self.owner, self.tenant)
        self.assertTrue(services.require_permission(request, "settings.manage"))

    def test_require_permission_lanza_permission_denied_si_no_autorizado(self):
        request = self._request(self.employee, self.tenant)
        with self.assertRaises(PermissionDenied):
            services.require_permission(request, "settings.manage")

    def test_require_permission_lanza_si_no_hay_tenant_activo(self):
        request = self._request(self.owner, None)
        with self.assertRaises(PermissionDenied):
            services.require_permission(request, "settings.manage")


class RolePermissionManagementTests(PermissionsTestCase):
    def test_set_role_permission_es_idempotente_por_rol_y_codigo(self):
        services.set_role_permission(self.tenant, role="employee", code="sales.create", is_granted=True, user=self.owner)
        services.set_role_permission(self.tenant, role="employee", code="sales.create", is_granted=True, user=self.owner)
        self.assertEqual(
            RolePermission.all_objects.filter(tenant=self.tenant, role="employee", permission_code="sales.create").count(), 1,
        )

    def test_get_effective_role_permissions_combina_default_y_override_de_tenant(self):
        efectivos = services.get_effective_role_permissions(self.tenant, "employee")
        self.assertIn("sales.view", efectivos)
        self.assertNotIn("sales.create", efectivos)
        services.set_role_permission(self.tenant, role="employee", code="sales.create", is_granted=True, user=self.owner)
        efectivos = services.get_effective_role_permissions(self.tenant, "employee")
        self.assertIn("sales.create", efectivos)

    def test_set_user_permission_override_y_remove_user_permission_override(self):
        services.set_user_permission_override(
            self.tenant, target_user=self.employee, code="accounting.post", is_granted=True, user=self.owner,
        )
        self.assertTrue(services.has_permission(self.tenant, self.employee, "accounting.post"))
        services.remove_user_permission_override(self.tenant, target_user=self.employee, code="accounting.post")
        self.assertFalse(services.has_permission(self.tenant, self.employee, "accounting.post"))

    def test_overrides_aislados_por_tenant(self):
        services.set_role_permission(self.tenant, role="employee", code="sales.create", is_granted=True, user=self.owner)
        self.assertEqual(RolePermission.all_objects.filter(tenant=self.otro_tenant).count(), 0)
