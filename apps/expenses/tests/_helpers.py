"""Utilidades compartidas por los tests de FASE 13 (Gastos) — mismo
patrón que `apps/purchases/tests/_helpers.py`/`apps/pos/tests/_helpers.py`."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.models import Supplier
from apps.expenses.models import ExpenseCategory
from apps.pos.models import CashRegister
from apps.pos.services import open_cash_session
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class ExpensesTestCase(TestCase):
    """Tenant con un propietario, un empleado (MEMBER sin política de
    autorización especial), una categoría de gasto, un proveedor y una
    caja activa — listo para probar cualquier flujo de Gastos."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Gastos", slug="empresa-gastos")
        self.owner = User.objects.create_user(email="owner.gastos@example.com", password="clave-de-prueba-987")
        self.empleado = User.objects.create_user(email="empleado.gastos@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.empleado, tenant=self.tenant, role=Membership.Role.MEMBER)

        self.categoria = ExpenseCategory.all_objects.create(tenant=self.tenant, name="Servicios")
        self.supplier = Supplier.objects.create(tenant=self.tenant, legal_name="Proveedor de Gastos SRL", currency="USD")

        self.caja = CashRegister.all_objects.create(tenant=self.tenant, name="Caja Principal", code="CAJA-01")
        self.caja.authorized_users.add(self.owner, self.empleado)

        self.client.login(username="empleado.gastos@example.com", password="clave-de-prueba-987")
        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.gastos@example.com", password="clave-de-prueba-987")

    def abrir_caja(self, user):
        return open_cash_session(self.tenant, cash_register=self.caja, user=user, opening_amount=Decimal("100"))
