from django.urls import reverse

from apps.permissions.models import RolePermission, UserPermissionOverride

from ._helpers import PermissionsTestCase


class RolesIndexViewTests(PermissionsTestCase):
    def test_owner_puede_ver_el_indice(self):
        respuesta = self.owner_client.get(reverse("permissions:index"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Roles y Permisos")

    def test_empleado_sin_settings_manage_recibe_403(self):
        respuesta = self.employee_client.get(reverse("permissions:index"))
        self.assertEqual(respuesta.status_code, 403)


class RolePermissionsViewTests(PermissionsTestCase):
    def test_owner_puede_ver_permisos_de_un_rol(self):
        respuesta = self.owner_client.get(reverse("permissions:role_permissions", args=["employee"]))
        self.assertEqual(respuesta.status_code, 200)

    def test_empleado_no_puede_ver_permisos_de_un_rol(self):
        respuesta = self.employee_client.get(reverse("permissions:role_permissions", args=["employee"]))
        self.assertEqual(respuesta.status_code, 403)

    def test_owner_puede_conceder_un_permiso_nuevo_al_rol_employee(self):
        url = reverse("permissions:role_permissions", args=["employee"])
        datos = {codigo: "on" for codigo in self._codigos_actuales("employee")}
        datos["sales.create"] = "on"
        respuesta = self.owner_client.post(url, datos)
        self.assertEqual(respuesta.status_code, 302)
        fila = RolePermission.all_objects.get(tenant=self.tenant, role="employee", permission_code="sales.create")
        self.assertTrue(fila.is_granted)

    def _codigos_actuales(self, role):
        from apps.permissions.services import get_effective_role_permissions

        return get_effective_role_permissions(self.tenant, role)


class UserOverridesViewTests(PermissionsTestCase):
    def test_owner_puede_ver_overrides_de_un_usuario(self):
        respuesta = self.owner_client.get(reverse("permissions:user_overrides", args=[self.employee.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_empleado_no_puede_ver_overrides_ajenos(self):
        respuesta = self.employee_client.get(reverse("permissions:user_overrides", args=[self.employee.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_owner_puede_conceder_override_a_un_empleado(self):
        url = reverse("permissions:user_overrides", args=[self.employee.pk])
        respuesta = self.owner_client.post(url, {"permission_code": "accounting.post", "decision": "grant", "reason": "cobertura temporal"})
        self.assertEqual(respuesta.status_code, 302)
        fila = UserPermissionOverride.all_objects.get(tenant=self.tenant, user=self.employee, permission_code="accounting.post")
        self.assertTrue(fila.is_granted)

    def test_owner_puede_limpiar_override_existente(self):
        UserPermissionOverride.all_objects.create(
            tenant=self.tenant, user=self.employee, permission_code="accounting.post", is_granted=True,
        )
        url = reverse("permissions:user_overrides", args=[self.employee.pk])
        self.owner_client.post(url, {"permission_code": "accounting.post", "decision": "clear", "reason": ""})
        self.assertFalse(
            UserPermissionOverride.all_objects.filter(tenant=self.tenant, user=self.employee, permission_code="accounting.post").exists(),
        )

    def test_tenant_b_no_puede_administrar_overrides_de_usuario_de_tenant_a(self):
        url = reverse("permissions:user_overrides", args=[self.employee.pk])
        respuesta = self.owner_b_client.get(url)
        self.assertEqual(respuesta.status_code, 404)


class SettingsHubViewTests(PermissionsTestCase):
    def test_manager_con_settings_view_puede_entrar(self):
        respuesta = self.manager_client.get(reverse("core:settings"))
        self.assertEqual(respuesta.status_code, 200)

    def test_empleado_sin_settings_view_recibe_403(self):
        respuesta = self.employee_client.get(reverse("core:settings"))
        self.assertEqual(respuesta.status_code, 403)

    def test_hub_enlaza_a_roles_y_permisos(self):
        respuesta = self.owner_client.get(reverse("core:settings"))
        self.assertContains(respuesta, reverse("permissions:index"))
