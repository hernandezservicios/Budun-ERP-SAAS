"""Utilidades compartidas por los tests de FASE 13 (RRHH) — mismo
patrón que `apps/expenses/tests/_helpers.py`/`apps/purchases/tests/_helpers.py`."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.hr.models import Department, Position
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class HRTestCase(TestCase):
    """Tenant con un propietario, un empleado del área administrativa
    (MEMBER sin política de autorización especial), un departamento y
    un cargo — listo para probar cualquier flujo de RRHH."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa RRHH", slug="empresa-rrhh")
        self.owner = User.objects.create_user(email="owner.rrhh@example.com", password="clave-de-prueba-987")
        self.staff = User.objects.create_user(email="staff.rrhh@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.staff, tenant=self.tenant, role=Membership.Role.MEMBER)

        self.departamento = Department.all_objects.create(tenant=self.tenant, name="Operaciones")
        self.cargo = Position.all_objects.create(tenant=self.tenant, name="Analista", department=self.departamento)

        self.client.login(username="staff.rrhh@example.com", password="clave-de-prueba-987")
        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.rrhh@example.com", password="clave-de-prueba-987")

    def fecha_ingreso(self):
        return date(2024, 1, 15)
