from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tenants.models import Membership, Tenant

User = get_user_model()


class AuditTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Auditoría", slug="empresa-auditoria")
        self.owner = User.objects.create_user(email="owner.auditoria@example.com", password="clave-de-prueba-987")
        self.employee = User.objects.create_user(email="employee.auditoria@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.employee, tenant=self.tenant, role=Membership.Role.EMPLOYEE)

        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.auditoria@example.com", password="clave-de-prueba-987")
        self.employee_client = self.client_class()
        self.employee_client.login(username="employee.auditoria@example.com", password="clave-de-prueba-987")
