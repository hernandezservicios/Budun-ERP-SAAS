"""
Única vía sancionada para operar sobre Recursos Humanos (ver
`docs/hr.md`). Ninguna vista debe escribir estos modelos directamente.

Mismos principios que `apps.expenses.services`/`apps.purchases.services`:
- `all_objects` (nunca `objects`/TenantManager) en toda consulta,
  filtrando siempre `tenant` explícitamente.
- `transaction.atomic()` + `select_for_update()` en toda operación que
  lea-y-luego-escriba.
- Errores de negocio como `InvalidHROperation` (nunca una excepción
  genérica ni un `IntegrityError` de PostgreSQL sin traducir).
- Información sensible (salario, datos bancarios): `can_view_sensitive_employee_data`
  es la única fuente de verdad sobre quién puede verla — hoy, con solo
  dos roles (OWNER/MEMBER), solo el propietario del tenant; cada
  lectura por el propietario se audita explícitamente.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.approvals import services as approvals_services
from apps.approvals.models import ApprovalRequest
from apps.customers.file_validation import nombre_original_seguro, validar_archivo_adjunto

from .models import (
    Attendance,
    Department,
    Employee,
    EmployeeDocument,
    EmploymentContract,
    HRActivityLog,
    Incident,
    Leave,
    LeaveType,
    Position,
    WorkSchedule,
)


class InvalidHROperation(ValidationError):
    """Operación de RRHH inválida: transición de estado no permitida,
    contrato activo duplicado, autorización insuficiente, etc."""


# ------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo)
# ------------------------------------------------------------------


def log_activity(tenant, *, entity_type, entity_id, action, user, entity_label="", details=""):
    return HRActivityLog.all_objects.create(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id, entity_label=entity_label,
        action=action, user=user, details=details,
    )


def get_activity_log(tenant, *, entity_type, entity_id, limit=20):
    return HRActivityLog.all_objects.filter(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id
    ).select_related("user")[:limit]


# ------------------------------------------------------------------
# Privacidad de información sensible (ver docs/hr.md sección
# "Auditoría/Privacidad") — nunca solo ocultar elementos de la UI.
# ------------------------------------------------------------------


def can_view_sensitive_employee_data(tenant, user):
    """Hoy, con solo dos roles (OWNER/MEMBER, ver `apps.tenants.models.Membership`),
    la única forma real de distinguir acceso a salario/datos bancarios
    es "es el propietario del tenant" — un cajero (MEMBER) nunca ve esto
    solo por pertenecer al tenant. FASE 15 (Roles granulares) podrá
    introducir un permiso dedicado sin romper este diseño."""
    return approvals_services.is_owner(tenant, user)


def log_sensitive_access(employee, user):
    log_activity(
        employee.tenant, entity_type="employee", entity_id=employee.pk, entity_label=employee.display_name,
        action=HRActivityLog.Action.SENSITIVE_DATA_VIEWED, user=user,
    )


# ------------------------------------------------------------------
# Departamentos y Cargos
# ------------------------------------------------------------------


def list_departments(tenant, *, only_active=True):
    queryset = Department.all_objects.filter(tenant=tenant)
    if only_active:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


def create_department(tenant, *, name, description="", manager=None):
    nombre = (name or "").strip()
    if not nombre:
        raise InvalidHROperation("El nombre del departamento es obligatorio.")
    if Department.all_objects.filter(tenant=tenant, name__iexact=nombre).exists():
        raise InvalidHROperation(f"Ya existe un departamento llamado «{nombre}».")
    return Department.all_objects.create(tenant=tenant, name=nombre, description=description, manager=manager)


def set_department_active(department, *, is_active):
    department.is_active = is_active
    department.save(update_fields=["is_active"])
    return department


def list_positions(tenant, *, only_active=True):
    queryset = Position.all_objects.filter(tenant=tenant).select_related("department")
    if only_active:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


def create_position(tenant, *, name, department=None, description="", level="", suggested_base_salary=None):
    nombre = (name or "").strip()
    if not nombre:
        raise InvalidHROperation("El nombre del cargo es obligatorio.")
    if Position.all_objects.filter(tenant=tenant, name__iexact=nombre).exists():
        raise InvalidHROperation(f"Ya existe un cargo llamado «{nombre}».")
    return Position.all_objects.create(
        tenant=tenant, name=nombre, department=department, description=description,
        level=level, suggested_base_salary=suggested_base_salary,
    )


def set_position_active(position, *, is_active):
    position.is_active = is_active
    position.save(update_fields=["is_active"])
    return position


# ------------------------------------------------------------------
# Empleados
# ------------------------------------------------------------------

_TRANSICIONES_EMPLEADO = {
    Employee.Status.ACTIVE: {Employee.Status.ON_LEAVE, Employee.Status.SUSPENDED, Employee.Status.TERMINATED, Employee.Status.INACTIVE},
    Employee.Status.ON_LEAVE: {Employee.Status.ACTIVE, Employee.Status.TERMINATED},
    Employee.Status.SUSPENDED: {Employee.Status.ACTIVE, Employee.Status.TERMINATED},
    Employee.Status.INACTIVE: {Employee.Status.ACTIVE, Employee.Status.TERMINATED},
    Employee.Status.TERMINATED: set(),
}


def list_employees(tenant, *, status=None, department=None, search=""):
    queryset = Employee.all_objects.filter(tenant=tenant).select_related("department", "position", "supervisor")
    if status:
        queryset = queryset.filter(status=status)
    if department:
        queryset = queryset.filter(department=department)
    if search:
        from django.db.models import Q

        queryset = queryset.filter(
            Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(identification_number__icontains=search)
        )
    return queryset.order_by("first_name", "last_name")


@transaction.atomic
def create_employee(
    tenant, *, first_name, last_name, hire_date, user=None, identification_type="", identification_number="",
    birth_date=None, phone="", email="", address="", city="", state_province="", country="",
    department=None, position=None, supervisor=None, base_salary=Decimal("0"), currency=None,
    bank_name="", bank_account_number="", notes="",
):
    if not (first_name or "").strip() and not (last_name or "").strip():
        raise InvalidHROperation("El empleado debe tener al menos nombre o apellido.")
    if department is not None and department.tenant_id != tenant.id:
        raise InvalidHROperation("El departamento no pertenece a este tenant.")
    if position is not None and position.tenant_id != tenant.id:
        raise InvalidHROperation("El cargo no pertenece a este tenant.")
    if supervisor is not None and supervisor.tenant_id != tenant.id:
        raise InvalidHROperation("El supervisor no pertenece a este tenant.")

    empleado = Employee.all_objects.create(
        tenant=tenant, first_name=first_name, last_name=last_name, hire_date=hire_date,
        identification_type=identification_type, identification_number=identification_number,
        birth_date=birth_date, phone=phone, email=email, address=address, city=city,
        state_province=state_province, country=country, department=department, position=position,
        supervisor=supervisor, base_salary=base_salary, currency=currency or "USD",
        bank_name=bank_name, bank_account_number=bank_account_number, notes=notes,
    )
    log_activity(
        tenant, entity_type="employee", entity_id=empleado.pk, entity_label=empleado.display_name,
        action=HRActivityLog.Action.CREATED, user=user,
    )
    return empleado


@transaction.atomic
def update_employee(employee, user, **campos):
    locked = Employee.all_objects.select_for_update().get(pk=employee.pk, tenant=employee.tenant)
    for campo in (
        "first_name", "last_name", "identification_type", "identification_number", "birth_date", "phone",
        "email", "address", "city", "state_province", "country", "department", "position", "supervisor",
        "base_salary", "currency", "bank_name", "bank_account_number", "notes", "termination_date",
    ):
        if campo in campos:
            setattr(locked, campo, campos[campo])
    locked.save()
    log_activity(
        locked.tenant, entity_type="employee", entity_id=locked.pk, entity_label=locked.display_name,
        action=HRActivityLog.Action.UPDATED, user=user,
    )
    return locked


@transaction.atomic
def change_employee_status(employee, new_status, user, *, reason=""):
    locked = Employee.all_objects.select_for_update().get(pk=employee.pk, tenant=employee.tenant)
    permitidas = _TRANSICIONES_EMPLEADO.get(locked.status, set())
    if new_status not in permitidas:
        raise InvalidHROperation(
            f"No se puede pasar de «{locked.get_status_display()}» a «{Employee.Status(new_status).label}»."
        )
    locked.status = new_status
    if new_status == Employee.Status.TERMINATED and not locked.termination_date:
        locked.termination_date = timezone.localdate()
    locked.save(update_fields=["status", "termination_date", "updated_at"])
    log_activity(
        locked.tenant, entity_type="employee", entity_id=locked.pk, entity_label=locked.display_name,
        action=HRActivityLog.Action.STATUS_CHANGED, user=user, details=reason,
    )
    return locked


# ------------------------------------------------------------------
# Contratos laborales
# ------------------------------------------------------------------


@transaction.atomic
def create_employment_contract(
    tenant, employee, *, contract_type, start_date, salary, user, currency=None, end_date=None,
    work_schedule=None, conditions="", notes="", activate=True,
):
    if employee.tenant_id != tenant.id:
        raise InvalidHROperation("El empleado no pertenece a este tenant.")
    if salary is None or salary < 0:
        raise InvalidHROperation("El salario del contrato no puede ser negativo.")
    try:
        with transaction.atomic():
            contrato = EmploymentContract.all_objects.create(
                tenant=tenant, employee=employee, contract_type=contract_type, start_date=start_date,
                end_date=end_date, salary=salary, currency=currency or employee.currency,
                work_schedule=work_schedule, conditions=conditions,
                status=EmploymentContract.Status.ACTIVE if activate else EmploymentContract.Status.DRAFT,
                created_by=user, notes=notes,
            )
    except IntegrityError as error:
        raise InvalidHROperation(
            "Este empleado ya tiene un contrato activo — termínalo antes de activar uno nuevo."
        ) from error
    log_activity(
        tenant, entity_type="employee", entity_id=employee.pk, entity_label=employee.display_name,
        action=HRActivityLog.Action.CONTRACT_CREATED, user=user, details=contrato.get_contract_type_display(),
    )
    return contrato


@transaction.atomic
def terminate_contract(contract, user, *, end_date=None):
    locked = EmploymentContract.all_objects.select_for_update().get(pk=contract.pk, tenant=contract.tenant)
    if locked.status != EmploymentContract.Status.ACTIVE:
        raise InvalidHROperation(f"Un contrato en estado «{locked.get_status_display()}» no puede terminarse.")
    locked.status = EmploymentContract.Status.TERMINATED
    locked.end_date = end_date or timezone.localdate()
    locked.save(update_fields=["status", "end_date"])
    log_activity(
        locked.tenant, entity_type="employee", entity_id=locked.employee_id, entity_label=locked.employee.display_name,
        action=HRActivityLog.Action.CONTRACT_TERMINATED, user=user,
    )
    return locked


def get_active_contract(employee):
    return EmploymentContract.all_objects.filter(
        tenant=employee.tenant, employee=employee, status=EmploymentContract.Status.ACTIVE
    ).first()


def get_employee_contracts(employee):
    return EmploymentContract.all_objects.filter(tenant=employee.tenant, employee=employee).order_by("-start_date")


# ------------------------------------------------------------------
# Documentos de empleado (reutiliza literalmente FASE 9)
# ------------------------------------------------------------------


def register_employee_document(employee, *, archivo, category, user, notes=""):
    _extension, content_type = validar_archivo_adjunto(archivo)
    adjunto = EmployeeDocument.all_objects.create(
        tenant=employee.tenant, employee=employee, category=category, file=archivo,
        original_filename=nombre_original_seguro(archivo.name), content_type=content_type, size_bytes=archivo.size,
        uploaded_by=user, notes=notes,
    )
    log_activity(
        employee.tenant, entity_type="employee", entity_id=employee.pk, entity_label=employee.display_name,
        action=HRActivityLog.Action.ATTACHMENT_UPLOADED, user=user, details=adjunto.original_filename,
    )
    return adjunto


def get_employee_documents(employee):
    return EmployeeDocument.all_objects.filter(tenant=employee.tenant, employee=employee).select_related("uploaded_by")


def delete_employee_document(document, user):
    tenant, employee_id, employee_label, nombre = (
        document.tenant, document.employee_id, document.employee.display_name, document.original_filename
    )
    document.delete()
    log_activity(
        tenant, entity_type="employee", entity_id=employee_id, entity_label=employee_label,
        action=HRActivityLog.Action.ATTACHMENT_DELETED, user=user, details=nombre,
    )


# ------------------------------------------------------------------
# Horarios de trabajo
# ------------------------------------------------------------------


def list_work_schedules(tenant, *, only_active=True):
    queryset = WorkSchedule.all_objects.filter(tenant=tenant)
    if only_active:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


def create_work_schedule(tenant, *, name, start_time, end_time, days_of_week=None, break_minutes=0):
    return WorkSchedule.all_objects.create(
        tenant=tenant, name=name, start_time=start_time, end_time=end_time,
        days_of_week=days_of_week or [], break_minutes=break_minutes,
    )


# ------------------------------------------------------------------
# Asistencia
# ------------------------------------------------------------------


@transaction.atomic
def record_check_in(tenant, employee, *, date, check_in_time, user, work_schedule=None, source=Attendance.Source.MANUAL):
    if employee.tenant_id != tenant.id:
        raise InvalidHROperation("El empleado no pertenece a este tenant.")
    late_minutes = 0
    if work_schedule is not None:
        entrada_programada = work_schedule.start_time
        if check_in_time > entrada_programada:
            delta = timedelta(hours=check_in_time.hour, minutes=check_in_time.minute) - timedelta(
                hours=entrada_programada.hour, minutes=entrada_programada.minute
            )
            late_minutes = max(0, int(delta.total_seconds() // 60))
    try:
        with transaction.atomic():
            asistencia = Attendance.all_objects.create(
                tenant=tenant, employee=employee, date=date, check_in=check_in_time, work_schedule=work_schedule,
                late_minutes=late_minutes, source=source, recorded_by=user,
            )
    except IntegrityError as error:
        raise InvalidHROperation(
            f"Ya existe un registro de asistencia para {employee.display_name} en {date} — registra la salida en vez de una nueva entrada."
        ) from error
    log_activity(
        tenant, entity_type="employee", entity_id=employee.pk, entity_label=employee.display_name,
        action=HRActivityLog.Action.ATTENDANCE_RECORDED, user=user, details=f"Entrada {date}",
    )
    return asistencia


@transaction.atomic
def record_check_out(tenant, attendance, *, check_out_time, user):
    locked = Attendance.all_objects.select_for_update().get(pk=attendance.pk, tenant=tenant)
    if locked.check_in is None:
        raise InvalidHROperation("No se puede registrar salida sin una entrada previa.")
    if locked.check_out is not None:
        raise InvalidHROperation("Ya se registró la salida de este día.")
    entrada = timedelta(hours=locked.check_in.hour, minutes=locked.check_in.minute)
    salida = timedelta(hours=check_out_time.hour, minutes=check_out_time.minute)
    if salida < entrada:
        raise InvalidHROperation("La hora de salida no puede ser anterior a la hora de entrada.")
    horas = Decimal(str(round((salida - entrada).total_seconds() / 3600, 2)))
    if locked.work_schedule is not None and locked.work_schedule.break_minutes:
        horas -= (Decimal(locked.work_schedule.break_minutes) / Decimal("60")).quantize(Decimal("0.01"))
        horas = max(horas, Decimal("0"))
    locked.check_out = check_out_time
    locked.worked_hours = horas
    locked.save(update_fields=["check_out", "worked_hours"])
    log_activity(
        tenant, entity_type="employee", entity_id=locked.employee_id, entity_label=locked.employee.display_name,
        action=HRActivityLog.Action.ATTENDANCE_RECORDED, user=user, details=f"Salida {locked.date}",
    )
    return locked


def get_employee_attendance(employee, *, date_from=None, date_to=None):
    queryset = Attendance.all_objects.filter(tenant=employee.tenant, employee=employee)
    if date_from:
        queryset = queryset.filter(date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date__lte=date_to)
    return queryset.order_by("-date")


# ------------------------------------------------------------------
# Ausencias / Vacaciones / Permisos
# ------------------------------------------------------------------

DEFAULT_LEAVE_TYPES = [
    ("Vacaciones", True, True),
    ("Permiso", False, True),
    ("Enfermedad", True, True),
    ("Otro", False, True),
]


def list_leave_types(tenant, *, only_active=True):
    queryset = LeaveType.all_objects.filter(tenant=tenant)
    if only_active:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name")


@transaction.atomic
def create_default_leave_types(tenant):
    existentes = {nombre.lower() for nombre in LeaveType.all_objects.filter(tenant=tenant).values_list("name", flat=True)}
    creados = []
    for nombre, es_pagada, requiere_aprobacion in DEFAULT_LEAVE_TYPES:
        if nombre.lower() in existentes:
            continue
        creados.append(LeaveType.all_objects.create(
            tenant=tenant, name=nombre, is_paid=es_pagada, requires_approval=requiere_aprobacion,
        ))
    return creados


@transaction.atomic
def request_leave(tenant, *, employee, leave_type, start_date, end_date, user, reason=""):
    if employee.tenant_id != tenant.id or leave_type.tenant_id != tenant.id:
        raise InvalidHROperation("El empleado o el tipo de ausencia no pertenece a este tenant.")
    if end_date < start_date:
        raise InvalidHROperation("La fecha de fin no puede ser anterior a la fecha de inicio.")
    duracion = (end_date - start_date).days + 1

    solicitud = Leave.all_objects.create(
        tenant=tenant, employee=employee, leave_type=leave_type, start_date=start_date, end_date=end_date,
        duration_days=duracion, reason=reason, requested_by=user,
    )
    log_activity(
        tenant, entity_type="employee", entity_id=employee.pk, entity_label=employee.display_name,
        action=HRActivityLog.Action.LEAVE_REQUESTED, user=user, details=leave_type.name,
    )
    if not leave_type.requires_approval:
        solicitud.status = Leave.Status.APPROVED
        solicitud.decided_at = timezone.now()
        solicitud.save(update_fields=["status", "decided_at"])
    else:
        approvals_services.request_approval(
            tenant, action_type=ApprovalRequest.ActionType.LEAVE_REQUEST, requested_by=user,
            document_type="leave", document_id=solicitud.pk,
            reason=f"Ausencia de {employee.display_name}: {leave_type.name} ({start_date} a {end_date})",
        )
    return solicitud


@transaction.atomic
def approve_leave(leave, user, *, decision_reason=""):
    """A diferencia de `apps.expenses.approve_expense` (que gatea por
    MONTO, sin permiso especial), una ausencia no tiene una dimensión de
    monto que auto-decida — aprobar/rechazar es puramente una cuestión
    de AUTORIDAD, exactamente como resolver una `ApprovalRequest`
    (`can_user_approve`, ver `apps.approvals.services`)."""
    locked = Leave.all_objects.select_for_update().get(pk=leave.pk, tenant=leave.tenant)
    if locked.status != Leave.Status.REQUESTED:
        raise InvalidHROperation(f"Una ausencia en estado «{locked.get_status_display()}» no puede aprobarse.")
    if not approvals_services.can_user_approve(locked.tenant, user):
        raise InvalidHROperation("No tienes permiso para aprobar ausencias.")
    locked.status = Leave.Status.APPROVED
    locked.approved_by = user
    locked.decision_reason = decision_reason
    locked.decided_at = timezone.now()
    locked.save(update_fields=["status", "approved_by", "decision_reason", "decided_at"])

    solicitud = approvals_services.get_usable_approved_request(
        locked.tenant, action_type=ApprovalRequest.ActionType.LEAVE_REQUEST, document_type="leave", document_id=locked.pk,
    )
    pendiente = ApprovalRequest.all_objects.filter(
        tenant=locked.tenant, action_type=ApprovalRequest.ActionType.LEAVE_REQUEST,
        document_type="leave", document_id=locked.pk, status=ApprovalRequest.Status.PENDING,
    ).first()
    if pendiente is not None:
        approvals_services.resolve_approval(pendiente, approved=True, user=user, approved_value=Decimal("1"))
    log_activity(
        locked.tenant, entity_type="employee", entity_id=locked.employee_id, entity_label=locked.employee.display_name,
        action=HRActivityLog.Action.LEAVE_APPROVED, user=user,
    )
    return locked


@transaction.atomic
def reject_leave(leave, user, *, decision_reason=""):
    locked = Leave.all_objects.select_for_update().get(pk=leave.pk, tenant=leave.tenant)
    if locked.status != Leave.Status.REQUESTED:
        raise InvalidHROperation(f"Una ausencia en estado «{locked.get_status_display()}» no puede rechazarse.")
    if not approvals_services.can_user_approve(locked.tenant, user):
        raise InvalidHROperation("No tienes permiso para rechazar ausencias.")
    locked.status = Leave.Status.REJECTED
    locked.approved_by = user
    locked.decision_reason = decision_reason
    locked.decided_at = timezone.now()
    locked.save(update_fields=["status", "approved_by", "decision_reason", "decided_at"])

    pendiente = ApprovalRequest.all_objects.filter(
        tenant=locked.tenant, action_type=ApprovalRequest.ActionType.LEAVE_REQUEST,
        document_type="leave", document_id=locked.pk, status=ApprovalRequest.Status.PENDING,
    ).first()
    if pendiente is not None:
        approvals_services.resolve_approval(pendiente, approved=False, user=user, decision_reason=decision_reason)
    log_activity(
        locked.tenant, entity_type="employee", entity_id=locked.employee_id, entity_label=locked.employee.display_name,
        action=HRActivityLog.Action.LEAVE_REJECTED, user=user, details=decision_reason,
    )
    return locked


@transaction.atomic
def cancel_leave(leave, user):
    locked = Leave.all_objects.select_for_update().get(pk=leave.pk, tenant=leave.tenant)
    if locked.status not in (Leave.Status.REQUESTED, Leave.Status.APPROVED):
        raise InvalidHROperation(f"Una ausencia en estado «{locked.get_status_display()}» no puede cancelarse.")
    locked.status = Leave.Status.CANCELED
    locked.decided_at = timezone.now()
    locked.save(update_fields=["status", "decided_at"])
    log_activity(
        locked.tenant, entity_type="employee", entity_id=locked.employee_id, entity_label=locked.employee.display_name,
        action=HRActivityLog.Action.LEAVE_CANCELED, user=user,
    )
    return locked


def get_employee_leaves(employee):
    return Leave.all_objects.filter(tenant=employee.tenant, employee=employee).select_related("leave_type").order_by("-start_date")


# ------------------------------------------------------------------
# Incidentes
# ------------------------------------------------------------------


@transaction.atomic
def report_incident(tenant, *, employee, incident_type, date, description, user, severity=Incident.Severity.LOW):
    if employee.tenant_id != tenant.id:
        raise InvalidHROperation("El empleado no pertenece a este tenant.")
    incidente = Incident.all_objects.create(
        tenant=tenant, employee=employee, incident_type=incident_type, date=date, description=description,
        severity=severity, reported_by=user,
    )
    log_activity(
        tenant, entity_type="employee", entity_id=employee.pk, entity_label=employee.display_name,
        action=HRActivityLog.Action.INCIDENT_REPORTED, user=user, details=incidente.get_incident_type_display(),
    )
    return incidente


@transaction.atomic
def update_incident_status(incident, new_status, user, *, resolution=""):
    locked = Incident.all_objects.select_for_update().get(pk=incident.pk, tenant=incident.tenant)
    locked.status = new_status
    if resolution:
        locked.resolution = resolution
    locked.save(update_fields=["status", "resolution"])
    if new_status in (Incident.Status.RESOLVED, Incident.Status.CLOSED):
        log_activity(
            locked.tenant, entity_type="employee", entity_id=locked.employee_id, entity_label=locked.employee.display_name,
            action=HRActivityLog.Action.INCIDENT_RESOLVED, user=user, details=resolution,
        )
    return locked


def get_employee_incidents(employee):
    return Incident.all_objects.filter(tenant=employee.tenant, employee=employee).order_by("-date")
