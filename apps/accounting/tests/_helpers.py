"""Utilidades compartidas por los tests de FASE 14 (Contabilidad) —
mismo patrón que `apps/payroll/tests/_helpers.py`."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounting import services
from apps.accounting.models import Account, AccountMapping
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class AccountingTestCase(TestCase):
    """Tenant con un propietario, un plan de cuentas mínimo real
    (Activos/Pasivos/Patrimonio/Ingresos/Costos/Gastos con al menos una
    cuenta de posting bajo cada tipo) y un período contable abierto que
    cubre la fecha de hoy — listo para probar cualquier flujo contable."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Contable", slug="empresa-contable")
        self.owner = User.objects.create_user(email="owner.contable@example.com", password="clave-de-prueba-987")
        self.staff = User.objects.create_user(email="staff.contable@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.staff, tenant=self.tenant, role=Membership.Role.MEMBER)

        self.cuenta_activos = Account.all_objects.create(
            tenant=self.tenant, code="1000", name="Activos", account_type=Account.AccountType.ASSET,
            normal_balance=Account.NormalBalance.DEBIT, allows_posting=False,
        )
        self.cuenta_caja = Account.all_objects.create(
            tenant=self.tenant, code="1100", name="Efectivo y equivalentes", account_type=Account.AccountType.ASSET,
            normal_balance=Account.NormalBalance.DEBIT, parent=self.cuenta_activos, level=2,
        )
        self.cuenta_ar = Account.all_objects.create(
            tenant=self.tenant, code="1200", name="Cuentas por cobrar", account_type=Account.AccountType.ASSET,
            normal_balance=Account.NormalBalance.DEBIT, parent=self.cuenta_activos, level=2,
        )
        self.cuenta_pasivos = Account.all_objects.create(
            tenant=self.tenant, code="2000", name="Pasivos", account_type=Account.AccountType.LIABILITY,
            normal_balance=Account.NormalBalance.CREDIT, allows_posting=False,
        )
        self.cuenta_impuestos = Account.all_objects.create(
            tenant=self.tenant, code="2100", name="Impuestos por pagar", account_type=Account.AccountType.LIABILITY,
            normal_balance=Account.NormalBalance.CREDIT, parent=self.cuenta_pasivos, level=2,
        )
        self.cuenta_patrimonio = Account.all_objects.create(
            tenant=self.tenant, code="3000", name="Capital", account_type=Account.AccountType.EQUITY,
            normal_balance=Account.NormalBalance.CREDIT,
        )
        self.cuenta_ingresos = Account.all_objects.create(
            tenant=self.tenant, code="4000", name="Ingresos por ventas", account_type=Account.AccountType.REVENUE,
            normal_balance=Account.NormalBalance.CREDIT,
        )
        self.cuenta_costos = Account.all_objects.create(
            tenant=self.tenant, code="5000", name="Costo de ventas", account_type=Account.AccountType.COST,
            normal_balance=Account.NormalBalance.DEBIT,
        )
        self.cuenta_gastos = Account.all_objects.create(
            tenant=self.tenant, code="6000", name="Gastos operativos", account_type=Account.AccountType.EXPENSE,
            normal_balance=Account.NormalBalance.DEBIT,
        )
        self.cuenta_nomina = Account.all_objects.create(
            tenant=self.tenant, code="6100", name="Gasto de nómina", account_type=Account.AccountType.EXPENSE,
            normal_balance=Account.NormalBalance.DEBIT,
        )

        self.periodo = services.open_period(
            self.tenant, name="2025-01", start_date=date(2025, 1, 1), end_date=date(2025, 1, 31), user=self.owner,
        )
        # Un segundo período (sin solaparse con el anterior) que cubre
        # la fecha REAL de hoy — necesario porque varios eventos reales
        # (pagos, reversos, ventas/gastos/nómina confirmados en otros
        # tests) se fechan con `timezone.localdate()`, nunca con la
        # fecha fija de enero 2025 usada en los asientos manuales.
        hoy = timezone.localdate()
        self.periodo_actual = services.open_period(
            self.tenant, name="periodo-actual", start_date=hoy - timedelta(days=1), end_date=hoy + timedelta(days=1),
            user=self.owner,
        )

        self.client.login(username="staff.contable@example.com", password="clave-de-prueba-987")
        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.contable@example.com", password="clave-de-prueba-987")

    def configurar_mapeos_completos(self):
        services.set_account_mapping(self.tenant, key=AccountMapping.Key.ACCOUNTS_RECEIVABLE, account=self.cuenta_ar)
        services.set_account_mapping(self.tenant, key=AccountMapping.Key.SALES_REVENUE, account=self.cuenta_ingresos)
        services.set_account_mapping(self.tenant, key=AccountMapping.Key.SALES_TAX_PAYABLE, account=self.cuenta_impuestos)
        services.set_account_mapping(self.tenant, key=AccountMapping.Key.CASH_AND_EQUIVALENTS, account=self.cuenta_caja)
        services.set_account_mapping(self.tenant, key=AccountMapping.Key.OPERATING_EXPENSE, account=self.cuenta_gastos)
        services.set_account_mapping(self.tenant, key=AccountMapping.Key.PAYROLL_EXPENSE, account=self.cuenta_nomina)
