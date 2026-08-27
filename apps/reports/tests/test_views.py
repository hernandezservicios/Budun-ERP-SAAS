from io import BytesIO

from django.urls import reverse

from ._helpers import ReportsTestCase


class ReportsHttpTests(ReportsTestCase):
    def test_todas_las_vistas_responden_200(self):
        urls = [
            "reports:index", "reports:sales", "reports:inventory", "reports:cash",
            "reports:accounts_receivable", "reports:accounts_payable", "reports:purchases",
            "reports:expenses", "reports:hr", "reports:payroll", "reports:customers", "reports:suppliers",
        ]
        for nombre in urls:
            respuesta = self.owner_client.get(reverse(nombre))
            self.assertEqual(respuesta.status_code, 200, f"{nombre} devolvió {respuesta.status_code}")

    def test_export_csv_ventas(self):
        respuesta = self.owner_client.get(reverse("reports:sales"), {"export": "csv"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv")
        self.assertIn(self.venta.number, respuesta.content.decode("utf-8"))

    def test_export_csv_gastos(self):
        respuesta = self.owner_client.get(reverse("reports:expenses"), {"export": "csv"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(self.gasto.number, respuesta.content.decode("utf-8"))

    def test_export_pdf_ventas(self):
        respuesta = self.owner_client.get(reverse("reports:sales"), {"export": "pdf"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertTrue(respuesta.content.startswith(b"%PDF"))

    def test_export_xlsx_ventas(self):
        respuesta = self.owner_client.get(reverse("reports:sales"), {"export": "xlsx"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def test_export_csv_neutraliza_formula_injection_en_nombre_de_cliente(self):
        """FASE 18 — Security Hardening. Un cliente con un nombre que
        empieza con `=` (fórmula de Excel/Sheets, ej. para ejecutar un
        comando en la máquina de quien abre el reporte) nunca debe
        llegar crudo a la celda exportada."""
        self.customer.first_name = "=cmd|'/c calc'!A1"
        self.customer.save()

        respuesta = self.owner_client.get(reverse("reports:sales"), {"export": "csv"})
        contenido = respuesta.content.decode("utf-8")
        self.assertNotIn(",=cmd|", contenido)
        self.assertIn("'=cmd|", contenido)

    def test_export_xlsx_neutraliza_formula_injection_en_nombre_de_cliente(self):
        from openpyxl import load_workbook

        self.customer.first_name = "=cmd|'/c calc'!A1"
        self.customer.save()

        respuesta = self.owner_client.get(reverse("reports:sales"), {"export": "xlsx"})
        libro = load_workbook(BytesIO(respuesta.content))
        valores = [celda.value for fila in libro.active.iter_rows() for celda in fila if celda.value]
        self.assertTrue(any(str(v).startswith("'=cmd|") for v in valores))
        self.assertFalse(any(str(v) == "=cmd|'/c calc'!A1" for v in valores))

    def test_estado_de_cuenta_de_cliente_responde_200(self):
        respuesta = self.owner_client.get(reverse("reports:customer_statement", args=[self.customer.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.venta.number)

    def test_estado_de_cuenta_de_proveedor_responde_200(self):
        respuesta = self.owner_client.get(reverse("reports:supplier_statement", args=[self.supplier.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_estado_de_cuenta_de_cliente_de_otro_tenant_404(self):
        from apps.tenants.models import Tenant
        from apps.customers.models import Customer

        otro_tenant = Tenant.objects.create(name="Otra Empresa Statements", slug="otra-empresa-statements")
        otro_cliente = Customer.objects.create(tenant=otro_tenant, first_name="Ajeno", last_name="Cliente")
        respuesta = self.owner_client.get(reverse("reports:customer_statement", args=[otro_cliente.pk]))
        self.assertEqual(respuesta.status_code, 404)


class PayrollReportSensitiveDataHttpTests(ReportsTestCase):
    def test_propietario_ve_desglose_por_empleado(self):
        respuesta = self.owner_client.get(reverse("reports:payroll"))
        self.assertContains(respuesta, self.empleado.display_name)

    def test_staff_no_ve_desglose_por_empleado(self):
        respuesta = self.client.get(reverse("reports:payroll"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, self.empleado.display_name)
