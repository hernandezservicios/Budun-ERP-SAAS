from datetime import date

from django.urls import reverse

from apps.payroll import services
from apps.payroll.models import Payroll, PayrollPeriod
from apps.tenants.models import Membership, Tenant

from ._helpers import PayrollTestCase


class PayrollHttpFlowTests(PayrollTestCase):
    def test_flujo_completo_via_http(self):
        respuesta = self.owner_client.post(reverse("payroll:period_list"), {
            "start_date": date(2025, 1, 1).isoformat(), "end_date": date(2025, 1, 15).isoformat(),
            "pay_date": date(2025, 1, 16).isoformat(), "currency": "USD", "notes": "",
        })
        periodo = PayrollPeriod.all_objects.get(tenant=self.tenant)
        self.assertRedirects(respuesta, reverse("payroll:period_detail", args=[periodo.pk]))

        respuesta = self.owner_client.post(reverse("payroll:payroll_calculate", args=[periodo.pk]), {
            "employee": self.empleado.pk,
        })
        self.assertRedirects(respuesta, reverse("payroll:period_detail", args=[periodo.pk]))
        nomina = Payroll.all_objects.get(tenant=self.tenant, period=periodo, employee=self.empleado)
        self.assertEqual(nomina.gross_total, self.empleado.base_salary)

        respuesta = self.owner_client.get(reverse("payroll:payroll_detail", args=[nomina.pk]))
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.owner_client.post(reverse("payroll:period_approve", args=[periodo.pk]))
        self.assertRedirects(respuesta, reverse("payroll:period_detail", args=[periodo.pk]))
        periodo.refresh_from_db()
        self.assertEqual(periodo.status, PayrollPeriod.Status.APPROVED)

        respuesta = self.owner_client.post(reverse("payroll:payroll_payment_add", args=[nomina.pk]), {
            "method": "transfer", "amount": str(nomina.net_total), "reference": "", "notes": "",
        })
        self.assertRedirects(respuesta, reverse("payroll:payroll_detail", args=[nomina.pk]))
        nomina.refresh_from_db()
        self.assertEqual(nomina.status, Payroll.Status.PAID)

        respuesta = self.owner_client.post(reverse("payroll:period_close", args=[periodo.pk]))
        self.assertRedirects(respuesta, reverse("payroll:period_detail", args=[periodo.pk]))
        periodo.refresh_from_db()
        self.assertEqual(periodo.status, PayrollPeriod.Status.CLOSED)

    def test_staff_sin_permiso_no_puede_aprobar_via_http(self):
        periodo = services.create_payroll_period(
            self.tenant, start_date=date(2025, 1, 1), end_date=date(2025, 1, 15),
            pay_date=date(2025, 1, 16), user=self.owner,
        )
        services.calculate_payroll_for_employee(self.tenant, periodo, self.empleado, user=self.owner)
        respuesta = self.client.post(reverse("payroll:period_approve", args=[periodo.pk]))
        self.assertRedirects(respuesta, reverse("payroll:period_detail", args=[periodo.pk]))
        periodo.refresh_from_db()
        self.assertEqual(periodo.status, PayrollPeriod.Status.PROCESSING)  # sigue sin aprobar


class PayrollLineHttpTests(PayrollTestCase):
    def test_agregar_linea_via_http(self):
        periodo = services.create_payroll_period(
            self.tenant, start_date=date(2025, 1, 1), end_date=date(2025, 1, 15),
            pay_date=date(2025, 1, 16), user=self.owner,
        )
        nomina = services.calculate_payroll_for_employee(self.tenant, periodo, self.empleado, user=self.owner)
        respuesta = self.owner_client.post(reverse("payroll:payroll_line_add", args=[nomina.pk]), {
            "category": "earning", "concept": "bonus", "description": "Bono de desempeño", "amount": "1000",
        })
        self.assertRedirects(respuesta, reverse("payroll:payroll_detail", args=[nomina.pk]))
        nomina.refresh_from_db()
        self.assertEqual(nomina.gross_total, self.empleado.base_salary + 1000)


class PayrollMultiTenantHttpTests(PayrollTestCase):
    def setUp(self):
        super().setUp()
        self.periodo = services.create_payroll_period(
            self.tenant, start_date=date(2025, 1, 1), end_date=date(2025, 1, 15),
            pay_date=date(2025, 1, 16), user=self.owner,
        )
        self.tenant_b = Tenant.objects.create(name="Empresa Nómina B", slug="empresa-nomina-b")
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.owner_b = User.objects.create_user(email="owner.nomina.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

    def test_tenant_b_no_puede_ver_periodo_de_tenant_a(self):
        client_b = self.client_class()
        client_b.login(username="owner.nomina.b@example.com", password="clave-de-prueba-987")
        respuesta = client_b.get(reverse("payroll:period_detail", args=[self.periodo.pk]))
        self.assertEqual(respuesta.status_code, 404)
