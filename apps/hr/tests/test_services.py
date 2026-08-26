from datetime import date, time, timedelta
from decimal import Decimal

from apps.hr import services
from apps.hr.models import (
    Attendance,
    Department,
    Employee,
    EmployeeDocument,
    EmploymentContract,
    Incident,
    Leave,
    LeaveType,
    Position,
)

from ._helpers import HRTestCase


class DepartmentPositionServiceTests(HRTestCase):
    def test_crear_departamento_duplicado_es_rechazado(self):
        with self.assertRaises(services.InvalidHROperation):
            services.create_department(self.tenant, name="Operaciones")

    def test_crear_cargo_duplicado_es_rechazado(self):
        with self.assertRaises(services.InvalidHROperation):
            services.create_position(self.tenant, name="Analista")

    def test_desactivar_departamento(self):
        services.set_department_active(self.departamento, is_active=False)
        self.departamento.refresh_from_db()
        self.assertFalse(self.departamento.is_active)


class EmployeeServiceTests(HRTestCase):
    def test_crear_empleado(self):
        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(),
            department=self.departamento, position=self.cargo, base_salary=Decimal("50000"), user=self.owner,
        )
        self.assertEqual(empleado.status, Employee.Status.ACTIVE)
        self.assertEqual(empleado.display_name, "Ana Pérez")

    def test_empleado_sin_nombre_ni_apellido_es_rechazado(self):
        with self.assertRaises(services.InvalidHROperation):
            services.create_employee(self.tenant, first_name="", last_name="", hire_date=self.fecha_ingreso(), user=self.owner)

    def test_departamento_de_otro_tenant_es_rechazado(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa", slug="otra-empresa-rrhh")
        otro_departamento = Department.all_objects.create(tenant=otro_tenant, name="Otro")
        with self.assertRaises(services.InvalidHROperation):
            services.create_employee(
                self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(),
                department=otro_departamento, user=self.owner,
            )

    def test_cambio_de_estado_valido(self):
        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        empleado = services.change_employee_status(empleado, Employee.Status.ON_LEAVE, self.owner)
        self.assertEqual(empleado.status, Employee.Status.ON_LEAVE)
        empleado = services.change_employee_status(empleado, Employee.Status.ACTIVE, self.owner)
        self.assertEqual(empleado.status, Employee.Status.ACTIVE)

    def test_cambio_de_estado_invalido_es_rechazado(self):
        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        empleado = services.change_employee_status(empleado, Employee.Status.TERMINATED, self.owner)
        with self.assertRaises(services.InvalidHROperation):
            services.change_employee_status(empleado, Employee.Status.ACTIVE, self.owner)

    def test_terminar_registra_fecha_de_salida(self):
        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        empleado = services.change_employee_status(empleado, Employee.Status.TERMINATED, self.owner)
        self.assertIsNotNone(empleado.termination_date)

    def test_solo_propietario_ve_datos_sensibles(self):
        self.assertTrue(services.can_view_sensitive_employee_data(self.tenant, self.owner))
        self.assertFalse(services.can_view_sensitive_employee_data(self.tenant, self.staff))

    def test_list_employees_aislado_por_tenant(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa", slug="otra-empresa-rrhh-2")
        services.create_employee(otro_tenant, first_name="Ajeno", last_name="X", hire_date=self.fecha_ingreso(), user=self.owner)
        services.create_employee(self.tenant, first_name="Propio", last_name="Y", hire_date=self.fecha_ingreso(), user=self.owner)
        resultado = services.list_employees(self.tenant)
        self.assertEqual(resultado.count(), 1)
        self.assertEqual(resultado.first().first_name, "Propio")


class EmploymentContractServiceTests(HRTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )

    def test_crear_contrato_activo(self):
        contrato = services.create_employment_contract(
            self.tenant, self.empleado, contract_type=EmploymentContract.ContractType.INDEFINITE,
            start_date=self.fecha_ingreso(), salary=Decimal("50000"), user=self.owner,
        )
        self.assertEqual(contrato.status, EmploymentContract.Status.ACTIVE)

    def test_no_se_puede_tener_dos_contratos_activos(self):
        services.create_employment_contract(
            self.tenant, self.empleado, contract_type=EmploymentContract.ContractType.INDEFINITE,
            start_date=self.fecha_ingreso(), salary=Decimal("50000"), user=self.owner,
        )
        with self.assertRaises(services.InvalidHROperation):
            services.create_employment_contract(
                self.tenant, self.empleado, contract_type=EmploymentContract.ContractType.FIXED_TERM,
                start_date=self.fecha_ingreso(), salary=Decimal("60000"), user=self.owner,
            )

    def test_terminar_contrato_permite_crear_uno_nuevo(self):
        contrato = services.create_employment_contract(
            self.tenant, self.empleado, contract_type=EmploymentContract.ContractType.INDEFINITE,
            start_date=self.fecha_ingreso(), salary=Decimal("50000"), user=self.owner,
        )
        services.terminate_contract(contrato, self.owner)
        nuevo = services.create_employment_contract(
            self.tenant, self.empleado, contract_type=EmploymentContract.ContractType.FIXED_TERM,
            start_date=date.today(), salary=Decimal("60000"), user=self.owner,
        )
        self.assertEqual(nuevo.status, EmploymentContract.Status.ACTIVE)


class AttendanceServiceTests(HRTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        self.horario = services.create_work_schedule(
            self.tenant, name="Turno oficina", start_time=time(8, 0), end_time=time(17, 0), break_minutes=60,
        )

    def test_registrar_entrada_sin_retraso(self):
        asistencia = services.record_check_in(
            self.tenant, self.empleado, date=date.today(), check_in_time=time(8, 0),
            user=self.owner, work_schedule=self.horario,
        )
        self.assertEqual(asistencia.late_minutes, 0)

    def test_registrar_entrada_con_retraso(self):
        asistencia = services.record_check_in(
            self.tenant, self.empleado, date=date.today(), check_in_time=time(8, 15),
            user=self.owner, work_schedule=self.horario,
        )
        self.assertEqual(asistencia.late_minutes, 15)

    def test_no_se_puede_registrar_dos_entradas_el_mismo_dia(self):
        services.record_check_in(self.tenant, self.empleado, date=date.today(), check_in_time=time(8, 0), user=self.owner)
        with self.assertRaises(services.InvalidHROperation):
            services.record_check_in(self.tenant, self.empleado, date=date.today(), check_in_time=time(8, 5), user=self.owner)

    def test_registrar_salida_calcula_horas_trabajadas(self):
        asistencia = services.record_check_in(
            self.tenant, self.empleado, date=date.today(), check_in_time=time(8, 0),
            user=self.owner, work_schedule=self.horario,
        )
        asistencia = services.record_check_out(self.tenant, asistencia, check_out_time=time(17, 0), user=self.owner)
        # 9 horas - 1 hora de descanso = 8 horas.
        self.assertEqual(asistencia.worked_hours, Decimal("8.00"))

    def test_no_se_puede_registrar_salida_sin_entrada_previa(self):
        asistencia = Attendance.all_objects.create(tenant=self.tenant, employee=self.empleado, date=date.today())
        with self.assertRaises(services.InvalidHROperation):
            services.record_check_out(self.tenant, asistencia, check_out_time=time(17, 0), user=self.owner)

    def test_no_se_puede_registrar_salida_dos_veces(self):
        asistencia = services.record_check_in(self.tenant, self.empleado, date=date.today(), check_in_time=time(8, 0), user=self.owner)
        asistencia = services.record_check_out(self.tenant, asistencia, check_out_time=time(17, 0), user=self.owner)
        with self.assertRaises(services.InvalidHROperation):
            services.record_check_out(self.tenant, asistencia, check_out_time=time(18, 0), user=self.owner)


class LeaveServiceTests(HRTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        creados = services.create_default_leave_types(self.tenant)
        self.vacaciones = LeaveType.all_objects.get(tenant=self.tenant, name="Vacaciones")
        self.permiso = LeaveType.all_objects.get(tenant=self.tenant, name="Permiso")

    def test_solicitar_ausencia_que_requiere_aprobacion_queda_pendiente(self):
        ausencia = services.request_leave(
            self.tenant, employee=self.empleado, leave_type=self.vacaciones,
            start_date=date.today(), end_date=date.today() + timedelta(days=4), user=self.staff,
        )
        self.assertEqual(ausencia.status, Leave.Status.REQUESTED)
        self.assertEqual(ausencia.duration_days, 5)

    def test_tipo_sin_aprobacion_se_autoaprueba(self):
        self.permiso.requires_approval = False
        self.permiso.save(update_fields=["requires_approval"])
        ausencia = services.request_leave(
            self.tenant, employee=self.empleado, leave_type=self.permiso,
            start_date=date.today(), end_date=date.today(), user=self.staff,
        )
        self.assertEqual(ausencia.status, Leave.Status.APPROVED)

    def test_propietario_aprueba_ausencia(self):
        ausencia = services.request_leave(
            self.tenant, employee=self.empleado, leave_type=self.vacaciones,
            start_date=date.today(), end_date=date.today(), user=self.staff,
        )
        ausencia = services.approve_leave(ausencia, self.owner)
        self.assertEqual(ausencia.status, Leave.Status.APPROVED)

    def test_miembro_sin_permiso_no_puede_aprobar(self):
        ausencia = services.request_leave(
            self.tenant, employee=self.empleado, leave_type=self.vacaciones,
            start_date=date.today(), end_date=date.today(), user=self.staff,
        )
        with self.assertRaises(services.InvalidHROperation):
            services.approve_leave(ausencia, self.staff)

    def test_rechazar_ausencia(self):
        ausencia = services.request_leave(
            self.tenant, employee=self.empleado, leave_type=self.vacaciones,
            start_date=date.today(), end_date=date.today(), user=self.staff,
        )
        ausencia = services.reject_leave(ausencia, self.owner, decision_reason="sin cobertura")
        self.assertEqual(ausencia.status, Leave.Status.REJECTED)

    def test_cancelar_ausencia(self):
        ausencia = services.request_leave(
            self.tenant, employee=self.empleado, leave_type=self.vacaciones,
            start_date=date.today(), end_date=date.today(), user=self.staff,
        )
        ausencia = services.cancel_leave(ausencia, self.staff)
        self.assertEqual(ausencia.status, Leave.Status.CANCELED)


class IncidentServiceTests(HRTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )

    def test_reportar_incidente(self):
        incidente = services.report_incident(
            self.tenant, employee=self.empleado, incident_type=Incident.IncidentType.SAFETY,
            date=date.today(), description="Resbalón en bodega", user=self.owner, severity=Incident.Severity.MEDIUM,
        )
        self.assertEqual(incidente.status, Incident.Status.OPEN)

    def test_resolver_incidente(self):
        incidente = services.report_incident(
            self.tenant, employee=self.empleado, incident_type=Incident.IncidentType.SAFETY,
            date=date.today(), description="x", user=self.owner,
        )
        incidente = services.update_incident_status(incidente, Incident.Status.RESOLVED, self.owner, resolution="Se colocó señalización")
        self.assertEqual(incidente.status, Incident.Status.RESOLVED)
        self.assertEqual(incidente.resolution, "Se colocó señalización")


class EmployeeDocumentServiceTests(HRTestCase):
    def test_subir_y_eliminar_documento(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.customers.tests._helpers import PDF_VALIDO

        empleado = services.create_employee(
            self.tenant, first_name="Ana", last_name="Pérez", hire_date=self.fecha_ingreso(), user=self.owner,
        )
        archivo = SimpleUploadedFile("cedula.pdf", PDF_VALIDO, content_type="application/pdf")
        documento = services.register_employee_document(empleado, archivo=archivo, category="identificacion", user=self.owner)
        self.assertEqual(EmployeeDocument.all_objects.filter(tenant=self.tenant, employee=empleado).count(), 1)
        services.delete_employee_document(documento, self.owner)
        self.assertEqual(EmployeeDocument.all_objects.filter(tenant=self.tenant, employee=empleado).count(), 0)
