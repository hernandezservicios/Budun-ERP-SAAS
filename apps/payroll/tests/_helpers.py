"""Utilidades compartidas por los tests de FASE 13 (Nómina) — mismo
patrón que `apps/hr/tests/_helpers.py`/`apps/expenses/tests/_helpers.py`."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.hr.models import Employee
from apps.pos.models import CashRegister
from apps.pos.services import open_cash_session
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class PayrollTestCase(TestCase):
    """Tenant con un propietario, un empleado de nómina (usuario del
    sistema, MEMBER sin política de autorización especial), un
    `Employee` (persona a la que se le calcula nómina) y una caja
    activa — listo para probar cualquier flujo de Nómina."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Nómina", slug="empresa-nomina")
        self.owner = User.objects.create_user(email="owner.nomina@example.com", password="clave-de-prueba-987")
        self.staff = User.objects.create_user(email="staff.nomina@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.staff, tenant=self.tenant, role=Membership.Role.MEMBER)

        self.empleado = Employee.all_objects.create(
            tenant=self.tenant, first_name="Ana", last_name="Pérez", hire_date=date(2024, 1, 15),
            base_salary=Decimal("50000"), currency="USD",
        )
        self.empleado_2 = Employee.all_objects.create(
            tenant=self.tenant, first_name="Luis", last_name="Gómez", hire_date=date(2024, 2, 1),
            base_salary=Decimal("40000"), currency="USD",
        )

        self.caja = CashRegister.all_objects.create(tenant=self.tenant, name="Caja Principal", code="CAJA-01")
        self.caja.authorized_users.add(self.owner, self.staff)

        self.client.login(username="staff.nomina@example.com", password="clave-de-prueba-987")
        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.nomina@example.com", password="clave-de-prueba-987")

    def abrir_caja(self, user):
        return open_cash_session(self.tenant, cash_register=self.caja, user=user, opening_amount=Decimal("100"))
