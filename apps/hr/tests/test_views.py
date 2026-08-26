from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse

from apps.hr import services
from apps.hr.models import Attendance, Department, Employee, EmploymentContract, Incident, Leave, LeaveType, Position
from apps.tenants.models import Membership, Tenant

from ._helpers import HRTestCase


class EmployeeHttpFlowTests(HRTestCase):
    def test_crear_editar_y_ver_empleado_via_http(self):
        respuesta = self.owner_client.post(reverse("hr:employee_create"), {
            "first_name": "Ana", "last_name": "Pérez", "identification_type": "", "identification_number": "",
            "birth_date": "", "phone": "", "email": "", "address": "", "city": "", "state_province": "", "country": "",
            "hire_date": date(2024, 1, 15).isoformat(), "department": self.departamento.pk, "position": self.cargo.pk,
            "supervisor": "", "base_salary": "50000", "currency": "USD", "bank_name": "", "bank_account_number": "", "notes": "",
        })
        empleado = Employee.all_objects.get(tenant=self.tenant, first_name="Ana")
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[empleado.pk]))

        respuesta = self.owner_client.get(reverse("hr:employee_detail", args=[empleado.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "50000")  # el propietario ve el salario

        respuesta = self.client.get(reverse("hr:employee_detail", args=[empleado.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "50000")  # el staff (MEMBER) no ve el salario

    def test_cambiar_estado_via_http(self):
        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        respuesta = self.owner_client.post(reverse("hr:employee_status_change", args=[empleado.pk]), {
            "new_status": "on_leave", "reason": "",
        })
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[empleado.pk]))
        empleado.refresh_from_db()
        self.assertEqual(empleado.status, Employee.Status.ON_LEAVE)

    def test_staff_no_puede_editar_empleado(self):
        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        respuesta = self.client.post(reverse("hr:employee_edit", args=[empleado.pk]), {
            "first_name": "Ana", "last_name": "Modificada", "hire_date": self.fecha_ingreso().isoformat(),
            "base_salary": "999999",
        })
        self.assertEqual(respuesta.status_code, 403)
        empleado.refresh_from_db()
        self.assertEqual(empleado.last_name, "Pérez")
        self.assertEqual(empleado.base_salary, Decimal("0"))

    def test_edit_form_no_se_renderiza_para_staff(self):
        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        respuesta = self.client.get(reverse("hr:employee_detail", args=[empleado.pk]))
        self.assertNotContains(respuesta, "Editar empleado")

    def test_sensible_se_audita_en_hractivitylog(self):
        from apps.hr.models import HRActivityLog

        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        self.owner_client.get(reverse("hr:employee_detail", args=[empleado.pk]))
        self.assertTrue(
            HRActivityLog.all_objects.filter(
                tenant=self.tenant, entity_type="employee", entity_id=empleado.pk,
                action=HRActivityLog.Action.SENSITIVE_DATA_VIEWED,
            ).exists()
        )


class EmploymentContractHttpTests(HRTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )

    def test_crear_y_terminar_contrato_via_http(self):
        respuesta = self.owner_client.post(reverse("hr:contract_create", args=[self.empleado.pk]), {
            "contract_type": "indefinite", "start_date": self.fecha_ingreso().isoformat(), "end_date": "",
            "salary": "50000", "currency": "USD", "work_schedule": "", "conditions": "", "notes": "",
        })
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[self.empleado.pk]))
        contrato = EmploymentContract.all_objects.get(tenant=self.tenant, employee=self.empleado)
        self.assertEqual(contrato.status, EmploymentContract.Status.ACTIVE)

        respuesta = self.owner_client.post(reverse("hr:contract_terminate", args=[self.empleado.pk, contrato.pk]))
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[self.empleado.pk]))
        contrato.refresh_from_db()
        self.assertEqual(contrato.status, EmploymentContract.Status.TERMINATED)


class AttendanceHttpTests(HRTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )

    def test_entrada_y_salida_via_http(self):
        respuesta = self.owner_client.post(reverse("hr:attendance_check_in", args=[self.empleado.pk]), {
            "date": date.today().isoformat(), "check_in_time": "08:00", "work_schedule": "",
        })
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[self.empleado.pk]))
        asistencia = Attendance.all_objects.get(tenant=self.tenant, employee=self.empleado, date=date.today())

        respuesta = self.owner_client.post(reverse("hr:attendance_check_out", args=[self.empleado.pk, asistencia.pk]), {
            "check_out_time": "17:00",
        })
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[self.empleado.pk]))
        asistencia.refresh_from_db()
        self.assertIsNotNone(asistencia.check_out)


class LeaveHttpTests(HRTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        services.create_default_leave_types(self.tenant)
        self.vacaciones = LeaveType.all_objects.get(tenant=self.tenant, name="Vacaciones")

    def test_solicitar_aprobar_via_http(self):
        respuesta = self.client.post(reverse("hr:leave_request", args=[self.empleado.pk]), {
            "leave_type": self.vacaciones.pk, "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=2)).isoformat(), "reason": "descanso",
        })
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[self.empleado.pk]))
        ausencia = Leave.all_objects.get(tenant=self.tenant, employee=self.empleado)
        self.assertEqual(ausencia.status, Leave.Status.REQUESTED)

        respuesta = self.owner_client.post(reverse("hr:leave_approve", args=[self.empleado.pk, ausencia.pk]), {"decision_reason": ""})
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[self.empleado.pk]))
        ausencia.refresh_from_db()
        self.assertEqual(ausencia.status, Leave.Status.APPROVED)

    def test_staff_no_puede_aprobar_via_http(self):
        ausencia = services.request_leave(
            self.tenant, employee=self.empleado, leave_type=self.vacaciones, start_date=date.today(),
            end_date=date.today(), user=self.staff,
        )
        respuesta = self.client.post(reverse("hr:leave_approve", args=[self.empleado.pk, ausencia.pk]), {"decision_reason": ""})
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[self.empleado.pk]))
        ausencia.refresh_from_db()
        self.assertEqual(ausencia.status, Leave.Status.REQUESTED)  # sigue pendiente, no se aprobó


class IncidentHttpTests(HRTestCase):
    def test_reportar_incidente_via_http(self):
        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        respuesta = self.owner_client.post(reverse("hr:incident_report", args=[empleado.pk]), {
            "incident_type": "safety", "date": date.today().isoformat(), "description": "Resbalón", "severity": "low",
        })
        self.assertRedirects(respuesta, reverse("hr:employee_detail", args=[empleado.pk]))
        self.assertTrue(Incident.all_objects.filter(tenant=self.tenant, employee=empleado).exists())


class DepartmentPositionHttpTests(HRTestCase):
    def test_crear_departamento_via_http(self):
        respuesta = self.owner_client.post(reverse("hr:department_list"), {"name": "Finanzas", "description": ""})
        self.assertRedirects(respuesta, reverse("hr:department_list"))
        self.assertTrue(Department.all_objects.filter(tenant=self.tenant, name="Finanzas").exists())

    def test_crear_cargo_via_http(self):
        respuesta = self.owner_client.post(reverse("hr:position_list"), {
            "name": "Gerente", "department": self.departamento.pk, "description": "", "level": "", "suggested_base_salary": "",
        })
        self.assertRedirects(respuesta, reverse("hr:position_list"))
        self.assertTrue(Position.all_objects.filter(tenant=self.tenant, name="Gerente").exists())


class HRMultiTenantHttpTests(HRTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        self.tenant_b = Tenant.objects.create(name="Empresa RRHH B", slug="empresa-rrhh-b")
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.owner_b = User.objects.create_user(email="owner.rrhh.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

    def test_tenant_b_no_puede_ver_empleado_de_tenant_a(self):
        client_b = self.client_class()
        client_b.login(username="owner.rrhh.b@example.com", password="clave-de-prueba-987")
        respuesta = client_b.get(reverse("hr:employee_detail", args=[self.empleado.pk]))
        self.assertEqual(respuesta.status_code, 404)
