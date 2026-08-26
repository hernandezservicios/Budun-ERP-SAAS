from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tenants.models import Membership, Tenant

User = get_user_model()


class PermissionsTestCase(TestCase):
    """Fixture compartida: un tenant con un usuario por cada rol no-OWNER
    más un OWNER, y un segundo tenant (con su propio OWNER) para probar
    aislamiento Multi-Tenant."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Permisos", slug="empresa-permisos")
        self.otro_tenant = Tenant.objects.create(name="Empresa Permisos B", slug="empresa-permisos-b")

        self.owner = User.objects.create_user(email="owner.permisos@example.com", password="clave-de-prueba-987")
        self.admin = User.objects.create_user(email="admin.permisos@example.com", password="clave-de-prueba-987")
        self.manager = User.objects.create_user(email="manager.permisos@example.com", password="clave-de-prueba-987")
        self.cashier = User.objects.create_user(email="cashier.permisos@example.com", password="clave-de-prueba-987")
        self.employee = User.objects.create_user(email="employee.permisos@example.com", password="clave-de-prueba-987")
        self.superuser = User.objects.create_user(
            email="super.permisos@example.com", password="clave-de-prueba-987", is_superuser=True, is_staff=True,
        )

        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.admin, tenant=self.tenant, role=Membership.Role.ADMIN)
        Membership.objects.create(user=self.manager, tenant=self.tenant, role=Membership.Role.MANAGER)
        Membership.objects.create(user=self.cashier, tenant=self.tenant, role=Membership.Role.CASHIER)
        Membership.objects.create(user=self.employee, tenant=self.tenant, role=Membership.Role.EMPLOYEE)

        self.owner_b = User.objects.create_user(email="owner.b.permisos@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner_b, tenant=self.otro_tenant, role=Membership.Role.OWNER)

        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.permisos@example.com", password="clave-de-prueba-987")
        self.admin_client = self.client_class()
        self.admin_client.login(username="admin.permisos@example.com", password="clave-de-prueba-987")
        self.manager_client = self.client_class()
        self.manager_client.login(username="manager.permisos@example.com", password="clave-de-prueba-987")
        self.employee_client = self.client_class()
        self.employee_client.login(username="employee.permisos@example.com", password="clave-de-prueba-987")
        self.owner_b_client = self.client_class()
        self.owner_b_client.login(username="owner.b.permisos@example.com", password="clave-de-prueba-987")
