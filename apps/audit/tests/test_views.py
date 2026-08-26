from django.urls import reverse

from apps.audit import services
from apps.audit.models import AuditLog

from ._helpers import AuditTestCase


class AuditSearchViewTests(AuditTestCase):
    def test_owner_puede_buscar(self):
        respuesta = self.owner_client.get(reverse("audit:search"))
        self.assertEqual(respuesta.status_code, 200)

    def test_empleado_sin_audit_view_recibe_403(self):
        respuesta = self.employee_client.get(reverse("audit:search"))
        self.assertEqual(respuesta.status_code, 403)

    def test_busqueda_muestra_eventos_del_tenant(self):
        services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas", reason="evento visible")
        respuesta = self.owner_client.get(reverse("audit:search"))
        self.assertContains(respuesta, "evento visible")


class AuditDetailViewTests(AuditTestCase):
    def test_owner_puede_ver_detalle(self):
        evento = services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas", reason="detalle")
        respuesta = self.owner_client.get(reverse("audit:detail", args=["audit", evento.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "detalle")

    def test_detalle_de_id_inexistente_da_404(self):
        respuesta = self.owner_client.get(reverse("audit:detail", args=["audit", 999999]))
        self.assertEqual(respuesta.status_code, 404)

    def test_empleado_sin_permiso_recibe_403(self):
        evento = services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas")
        respuesta = self.employee_client.get(reverse("audit:detail", args=["audit", evento.pk]))
        self.assertEqual(respuesta.status_code, 403)


class AuditExportViewTests(AuditTestCase):
    def test_owner_puede_exportar_csv(self):
        services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas")
        respuesta = self.owner_client.get(reverse("audit:export"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv")

    def test_exportar_audita_a_si_mismo(self):
        self.owner_client.get(reverse("audit:export"))
        self.assertTrue(
            AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.EXPORT_PERFORMED, domain="audit").exists()
        )

    def test_empleado_sin_audit_export_recibe_403(self):
        respuesta = self.employee_client.get(reverse("audit:export"))
        self.assertEqual(respuesta.status_code, 403)


class AuditMultiTenantTests(AuditTestCase):
    def test_tenant_b_no_ve_eventos_de_tenant_a(self):
        from django.contrib.auth import get_user_model

        from apps.tenants.models import Membership, Tenant

        User = get_user_model()
        tenant_b = Tenant.objects.create(name="Empresa Auditoría B", slug="empresa-auditoria-b")
        owner_b = User.objects.create_user(email="owner.b.auditoria@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=owner_b, tenant=tenant_b, role=Membership.Role.OWNER)
        cliente_b = self.client_class()
        cliente_b.login(username="owner.b.auditoria@example.com", password="clave-de-prueba-987")

        services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas", reason="solo_tenant_a")
        respuesta = cliente_b.get(reverse("audit:search"))
        self.assertNotContains(respuesta, "solo_tenant_a")

    def test_tenant_b_no_puede_ver_detalle_de_evento_de_tenant_a(self):
        from django.contrib.auth import get_user_model

        from apps.tenants.models import Membership, Tenant

        User = get_user_model()
        tenant_b = Tenant.objects.create(name="Empresa Auditoría B2", slug="empresa-auditoria-b2")
        owner_b = User.objects.create_user(email="owner.b2.auditoria@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=owner_b, tenant=tenant_b, role=Membership.Role.OWNER)
        cliente_b = self.client_class()
        cliente_b.login(username="owner.b2.auditoria@example.com", password="clave-de-prueba-987")

        evento = services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas")
        respuesta = cliente_b.get(reverse("audit:detail", args=["audit", evento.pk]))
        self.assertEqual(respuesta.status_code, 404)
