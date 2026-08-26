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


class PayrollReportSensitiveDataHttpTests(ReportsTestCase):
    def test_propietario_ve_desglose_por_empleado(self):
        respuesta = self.owner_client.get(reverse("reports:payroll"))
        self.assertContains(respuesta, self.empleado.display_name)

    def test_staff_no_ve_desglose_por_empleado(self):
        respuesta = self.client.get(reverse("reports:payroll"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, self.empleado.display_name)
