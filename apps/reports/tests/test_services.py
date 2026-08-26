from decimal import Decimal

from apps.reports import services
from apps.sales.models import Sale

from ._helpers import ReportsTestCase


class SalesReportServiceTests(ReportsTestCase):
    def test_resumen_y_detalle(self):
        reporte = services.get_sales_report(self.tenant, status=Sale.Status.CONFIRMED)
        self.assertEqual(reporte["summary"]["count"], 1)
        self.assertEqual(reporte["summary"]["total"], self.venta.total)
        self.assertEqual(list(reporte["rows"])[0].pk, self.venta.pk)

    def test_filtro_por_cliente(self):
        from apps.customers.models import Customer

        otro_cliente = Customer.objects.create(tenant=self.tenant, first_name="Otro", last_name="Cliente")
        reporte = services.get_sales_report(self.tenant, customer=otro_cliente)
        self.assertEqual(reporte["summary"]["count"], 0)


class InventoryReportServiceTests(ReportsTestCase):
    def test_detecta_stock_bajo(self):
        reporte = services.get_inventory_report(self.tenant)
        self.assertEqual(reporte["summary"]["total_products"], 1)
        self.assertEqual(reporte["summary"]["low_stock_count"], 1)


class CashReportServiceTests(ReportsTestCase):
    def test_sesion_incluida_en_reporte(self):
        reporte = services.get_cash_report(self.tenant)
        self.assertEqual(reporte["summary"]["count"], 1)
        self.assertEqual(reporte["rows"][0]["session"].pk, self.sesion.pk)


class AccountsReceivableReportServiceTests(ReportsTestCase):
    def test_venta_sin_pago_aparece_como_pendiente(self):
        reporte = services.get_accounts_receivable_report(self.tenant)
        self.assertEqual(reporte["summary"]["total_pending"], self.venta.total)
        self.assertEqual(len(reporte["rows"]), 1)

    def test_venta_pagada_no_aparece(self):
        from apps.sales import services as sales_services

        sales_services.record_payment_for_sale(self.venta, method="cash", amount=self.venta.total, user=self.owner)
        reporte = services.get_accounts_receivable_report(self.tenant)
        self.assertEqual(reporte["summary"]["total_pending"], Decimal("0"))


class ExpensesReportServiceTests(ReportsTestCase):
    def test_resumen_incluye_el_gasto_pagado(self):
        reporte = services.get_expenses_report(self.tenant)
        self.assertEqual(reporte["summary"]["count"], 1)
        self.assertEqual(reporte["summary"]["total"], self.gasto.total)


class HRReportServiceTests(ReportsTestCase):
    def test_resumen_cuenta_empleados(self):
        reporte = services.get_hr_report(self.tenant)
        self.assertEqual(reporte["summary"]["total_employees"], 1)


class PayrollReportServiceTests(ReportsTestCase):
    def test_resumen_incluye_la_nomina_calculada(self):
        reporte = services.get_payroll_report(self.tenant)
        self.assertEqual(reporte["summary"]["count"], 1)
        self.assertEqual(reporte["summary"]["gross_total"], Decimal("1000"))


class MultiTenantReportServiceTests(ReportsTestCase):
    def test_reportes_aislados_por_tenant(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa", slug="otra-empresa-reportes")
        self.assertEqual(services.get_sales_report(otro_tenant)["summary"]["count"], 0)
        self.assertEqual(services.get_expenses_report(otro_tenant)["summary"]["count"], 0)
        self.assertEqual(services.get_hr_report(otro_tenant)["summary"]["total_employees"], 0)
        self.assertEqual(services.get_payroll_report(otro_tenant)["summary"]["count"], 0)


class ExecutiveSummaryServiceTests(ReportsTestCase):
    def test_resumen_ejecutivo_agrega_dominios(self):
        resumen = services.get_executive_summary(self.tenant)
        self.assertEqual(resumen["sales_total"], self.venta.total)
        self.assertEqual(resumen["expenses_total"], self.gasto.total)
        self.assertEqual(resumen["low_stock_count"], 1)
