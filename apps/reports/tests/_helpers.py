"""Utilidades compartidas por los tests de FASE 14 (Reportes) — mismo
patrón que `apps/accounting/tests/_helpers.py`. Construye datos
mínimos reales en Ventas/Inventario/Caja/Gastos/RRHH/Nómina, siempre
vía los servicios de cada dominio (nunca creando filas a mano salvo
que el propio dominio no ofrezca un atajo más simple)."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.models import Customer, Supplier
from apps.expenses import services as expenses_services
from apps.expenses.models import ExpenseCategory
from apps.hr.models import Employee
from apps.inventory import services as inv_services
from apps.inventory.models import Product
from apps.payroll import services as payroll_services
from apps.pos.models import CashRegister, CashSession
from apps.sales import services as sales_services
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class ReportsTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Reportes", slug="empresa-reportes")
        self.owner = User.objects.create_user(email="owner.reportes@example.com", password="clave-de-prueba-987")
        self.staff = User.objects.create_user(email="staff.reportes@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.staff, tenant=self.tenant, role=Membership.Role.MEMBER)

        self.customer = Customer.objects.create(tenant=self.tenant, first_name="Cliente", last_name="Reportes")
        self.supplier = Supplier.objects.create(tenant=self.tenant, legal_name="Proveedor Reportes SRL")

        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto Reportes", sku="TST-REP-1", sale_price=Decimal("100"), tax_rate=Decimal("0"),
            min_stock=Decimal("5"),
        )
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("2"), user=self.owner)  # bajo min_stock

        venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.customer)
        sales_services.add_sale_item(venta, product=self.producto, quantity=Decimal("1"), user=self.owner)
        self.venta = sales_services.confirm_sale(venta, self.owner)

        self.categoria_gasto = ExpenseCategory.all_objects.create(tenant=self.tenant, name="Servicios")
        gasto = expenses_services.create_expense(
            self.tenant, category=self.categoria_gasto, user=self.owner, description="Internet",
            expense_date=date.today(), amount=Decimal("50"),
        )
        gasto = expenses_services.submit_expense_for_approval(gasto, self.owner)
        self.gasto = expenses_services.approve_expense(gasto, self.owner)
        expenses_services.record_expense_payment(self.tenant, self.gasto, method="transfer", amount=Decimal("50"), user=self.owner)

        self.empleado = Employee.all_objects.create(
            tenant=self.tenant, first_name="Ana", last_name="Pérez", hire_date=date(2024, 1, 15), base_salary=Decimal("1000"),
        )
        periodo_nomina = payroll_services.create_payroll_period(
            self.tenant, start_date=date.today() - timedelta(days=15), end_date=date.today(),
            pay_date=date.today(), user=self.owner,
        )
        self.nomina = payroll_services.calculate_payroll_for_employee(self.tenant, periodo_nomina, self.empleado, user=self.owner)

        self.caja = CashRegister.all_objects.create(tenant=self.tenant, name="Caja Reportes", code="CAJA-REP")
        self.caja.authorized_users.add(self.owner)
        self.sesion = CashSession.all_objects.create(tenant=self.tenant, cash_register=self.caja, user=self.owner, opening_amount=Decimal("100"))

        self.client.login(username="staff.reportes@example.com", password="clave-de-prueba-987")
        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.reportes@example.com", password="clave-de-prueba-987")
