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


class SalesReportCogsMarginTests(ReportsTestCase):
    """Ampliación de cierre de FASE 14: margen bruto en el reporte de
    Ventas. `self.venta` (fixture) confirma con costo 0 (register_stock_in
    sin unit_cost) — el margen debe caer exactamente al subtotal menos
    descuentos, sin ningún costo fabricado."""

    def test_margen_sin_costo_conocido_iguala_subtotal_menos_descuentos(self):
        reporte = services.get_sales_report(self.tenant, status=Sale.Status.CONFIRMED)
        self.assertEqual(reporte["summary"]["cost_total"], Decimal("0"))
        self.assertEqual(reporte["summary"]["margin"], self.venta.subtotal - self.venta.discount_total)

    def test_margen_con_costo_conocido_lo_descuenta(self):
        from apps.inventory import services as inv_services
        from apps.inventory.models import Product
        from apps.sales import services as sales_services

        # Producto NUEVO y stock limpio -- evita mezclar el promedio
        # ponderado con `self.producto`, que el fixture de la clase ya
        # vendió (a costo 0) en su propio setUp.
        producto_nuevo = Product.objects.create(
            tenant=self.tenant, name="Producto Margen", sku="TST-MARGEN-1", sale_price=Decimal("50"),
        )
        inv_services.register_stock_in(product=producto_nuevo, quantity=Decimal("5"), user=self.owner, unit_cost=Decimal("10"))
        venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.customer)
        sales_services.add_sale_item(venta, product=producto_nuevo, quantity=Decimal("2"), user=self.owner)
        sales_services.confirm_sale(venta, self.owner)

        reporte = services.get_sales_report(self.tenant, status=Sale.Status.CONFIRMED)
        # Costo total ahora incluye la venta original del fixture (0) + esta nueva (2*10=20).
        self.assertEqual(reporte["summary"]["cost_total"], Decimal("20"))


class InventoryValuationReportServiceTests(ReportsTestCase):
    def test_valorizacion_incluida_en_resumen(self):
        reporte = services.get_inventory_report(self.tenant)
        self.assertIn("inventory_value", reporte["summary"])
        self.assertIn("valuation_rows", reporte)


class CustomerStatementServiceTests(ReportsTestCase):
    def test_estado_de_cuenta_incluye_la_venta_confirmada(self):
        estado = services.get_customer_statement(self.tenant, self.customer)
        self.assertEqual(estado["summary"]["total_invoiced"], self.venta.total)
        self.assertEqual(len(estado["rows"]), 1)
        self.assertEqual(estado["rows"][0]["type"], "Venta")

    def test_estado_de_cuenta_incluye_pago_como_movimiento_negativo(self):
        from apps.sales import services as sales_services

        sales_services.record_payment_for_sale(self.venta, method="cash", amount=self.venta.total, user=self.owner)
        estado = services.get_customer_statement(self.tenant, self.customer)
        tipos = {m["type"] for m in estado["rows"]}
        self.assertIn("Pago", tipos)
        self.assertEqual(estado["summary"]["total_pending"], Decimal("0"))


class SupplierStatementServiceTests(ReportsTestCase):
    def test_estado_de_cuenta_proveedor_sin_facturas_confirmadas(self):
        estado = services.get_supplier_statement(self.tenant, self.supplier)
        self.assertEqual(estado["summary"]["total_purchased"], Decimal("0"))
        self.assertEqual(estado["rows"], [])
