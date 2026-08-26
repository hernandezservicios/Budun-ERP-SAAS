"""
Recursos Humanos (FASE 13, ver `docs/hr.md`): Empleados, Departamentos,
Cargos, Contratos, Horarios, Asistencia, Ausencias/Vacaciones e
Incidentes. Dominio separado de Gastos y Nómina (`apps.expenses`,
`apps.payroll`) aunque relacionado — la Nómina consume `Employee` como
referencia (salario base, moneda), nunca lo duplica.

Reutiliza literalmente, nunca duplica:
- `apps.customers.models.IdentificationType` — mismo catálogo de tipos
  de identificación que Clientes/Proveedores (cédula/pasaporte/etc.).
- `apps.customers.models.DocumentoBaseMixin`/`DocumentCategory`/
  `EXTENSIONES_DOCUMENTO_PERMITIDAS` (FASE 9) — mismo sistema de
  archivos seguro que el resto del proyecto; `DocumentCategory` ya
  incluye exactamente las categorías pedidas para documentos de
  empleado (identificación/documento_fiscal/contrato/certificado/
  comprobante/documento_bancario/otro), sin necesidad de un catálogo
  nuevo.
- `apps.approvals.services` — aprobación de solicitudes de
  ausencia/vacaciones, misma primitiva reutilizable que Gastos/POS/
  Compras.

Información sensible (salario, datos bancarios): nunca se restringe
ocultando elementos de la UI únicamente — `services.py` expone
`can_view_sensitive_employee_data` (hoy: solo el propietario del
tenant, ver `docs/hr.md` sección "Auditoría/Privacidad") y toda lectura
de esos campos por el propietario se audita explícitamente
(`HRActivityLog.Action.SENSITIVE_DATA_VIEWED`).
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

import logging
import os
import uuid

from apps.customers.models import (
    DocumentoBaseMixin,
    EXTENSIONES_DOCUMENTO_PERMITIDAS,
    IdentificationType,
)
from apps.tenants.models import TenantScopedModel

logger = logging.getLogger("apps.hr.documents")


# ---------------------------------------------------------------------
# Departamentos y Cargos
# ---------------------------------------------------------------------


class Department(TenantScopedModel):
    name = models.CharField("nombre", max_length=100)
    description = models.CharField("descripción", max_length=255, blank=True)
    manager = models.ForeignKey(
        "Employee", verbose_name="responsable", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="managed_departments",
    )
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "departamento"
        verbose_name_plural = "departamentos"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_department_tenant_nombre"),
        ]

    def __str__(self):
        return self.name


class Position(TenantScopedModel):
    name = models.CharField("nombre", max_length=100)
    department = models.ForeignKey(
        Department, verbose_name="departamento", on_delete=models.PROTECT, related_name="positions",
        null=True, blank=True,
    )
    description = models.CharField("descripción", max_length=255, blank=True)
    level = models.CharField("nivel", max_length=50, blank=True, help_text="Texto libre — ej. «Junior», «Senior», «Gerencial».")
    suggested_base_salary = models.DecimalField(
        "salario base sugerido", max_digits=12, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "cargo"
        verbose_name_plural = "cargos"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_position_tenant_nombre"),
        ]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------
# Empleado
# ---------------------------------------------------------------------


class Employee(TenantScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"
        ON_LEAVE = "on_leave", "De licencia"
        SUSPENDED = "suspended", "Suspendido"
        TERMINATED = "terminated", "Desvinculado"

    first_name = models.CharField("nombre", max_length=150)
    last_name = models.CharField("apellido", max_length=150)
    identification_type = models.CharField(
        "tipo de identificación", max_length=20, choices=IdentificationType.choices, blank=True
    )
    identification_number = models.CharField("número de identificación", max_length=50, blank=True)
    birth_date = models.DateField("fecha de nacimiento", null=True, blank=True)
    phone = models.CharField("teléfono", max_length=30, blank=True)
    email = models.EmailField("correo electrónico", blank=True)
    address = models.CharField("dirección", max_length=255, blank=True)
    city = models.CharField("ciudad", max_length=100, blank=True)
    state_province = models.CharField("provincia / estado", max_length=100, blank=True)
    country = models.CharField("país", max_length=100, blank=True)
    hire_date = models.DateField("fecha de ingreso")
    termination_date = models.DateField("fecha de salida", null=True, blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    department = models.ForeignKey(
        Department, verbose_name="departamento", on_delete=models.PROTECT, related_name="employees",
        null=True, blank=True,
    )
    position = models.ForeignKey(
        Position, verbose_name="cargo", on_delete=models.PROTECT, related_name="employees", null=True, blank=True,
    )
    supervisor = models.ForeignKey(
        "self", verbose_name="supervisor", on_delete=models.SET_NULL, null=True, blank=True, related_name="subordinates",
    )
    # --- Información sensible: salario y datos bancarios (ver docs/hr.md) ---
    base_salary = models.DecimalField("salario base", max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField("moneda", max_length=3, default="USD")
    bank_name = models.CharField("banco", max_length=100, blank=True)
    bank_account_number = models.CharField("número de cuenta", max_length=50, blank=True)

    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "empleado"
        verbose_name_plural = "empleados"
        ordering = ["first_name", "last_name"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_employee_tenant_estado"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "identification_number"],
                condition=models.Q(identification_number__gt=""),
                name="unique_employee_tenant_identificacion_no_vacia",
            ),
            models.CheckConstraint(
                check=models.Q(identification_number="") | ~models.Q(identification_type=""),
                name="employee_tipo_identificacion_si_hay_numero",
            ),
            models.CheckConstraint(check=models.Q(base_salary__gte=0), name="employee_salario_no_negativo"),
        ]

    @property
    def display_name(self):
        return f"{self.first_name} {self.last_name}".strip() or f"#{self.pk}"

    def __str__(self):
        return self.display_name


# ---------------------------------------------------------------------
# Contrato laboral
# ---------------------------------------------------------------------


class EmploymentContract(TenantScopedModel):
    class ContractType(models.TextChoices):
        INDEFINITE = "indefinite", "Indefinido"
        FIXED_TERM = "fixed_term", "Plazo fijo"
        PROBATIONARY = "probationary", "Período de prueba"
        OTHER = "other", "Otro"

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        ACTIVE = "active", "Activo"
        TERMINATED = "terminated", "Terminado"
        EXPIRED = "expired", "Vencido"

    employee = models.ForeignKey(Employee, verbose_name="empleado", on_delete=models.PROTECT, related_name="contracts")
    contract_type = models.CharField("tipo", max_length=20, choices=ContractType.choices)
    start_date = models.DateField("fecha de inicio")
    end_date = models.DateField("fecha de fin", null=True, blank=True)
    salary = models.DecimalField("salario", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    work_schedule = models.ForeignKey(
        "WorkSchedule", verbose_name="horario", on_delete=models.SET_NULL, null=True, blank=True, related_name="contracts",
    )
    conditions = models.TextField("condiciones", blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "contrato laboral"
        verbose_name_plural = "contratos laborales"
        ordering = ["-start_date", "-id"]
        constraints = [
            # Nunca dos contratos ACTIVOS a la vez para el mismo empleado —
            # mismo principio de "una sola fila vigente" que
            # ApprovalPolicy (unique_policy_tenant_default).
            models.UniqueConstraint(
                fields=["tenant", "employee"], condition=models.Q(status="active"),
                name="unique_active_contract_per_employee",
            ),
            models.CheckConstraint(check=models.Q(salary__gte=0), name="contract_salario_no_negativo"),
        ]

    def __str__(self):
        return f"Contrato {self.get_contract_type_display()} — {self.employee}"


# ---------------------------------------------------------------------
# Documentos de empleado (reutiliza FASE 9 — no se crea un segundo
# sistema de archivos)
# ---------------------------------------------------------------------


def _ruta_documento_empleado(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"empleados/{instance.tenant_id}/{instance.employee_id}/{uuid.uuid4().hex}{extension}"


class EmployeeDocument(TenantScopedModel, DocumentoBaseMixin):
    employee = models.ForeignKey(Employee, verbose_name="empleado", on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(
        "archivo",
        upload_to=_ruta_documento_empleado,
        validators=[FileExtensionValidator(allowed_extensions=EXTENSIONES_DOCUMENTO_PERMITIDAS)],
    )

    class Meta:
        verbose_name = "documento de empleado"
        verbose_name_plural = "documentos de empleado"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["tenant", "employee"], name="idx_empdoc_tenant_empleado"),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.employee})"


@receiver(post_delete, sender=EmployeeDocument)
def _eliminar_archivo_adjunto_empleado(sender, instance, **kwargs):
    if instance.file:
        try:
            instance.file.delete(save=False)
        except OSError:
            logger.exception("No se pudo borrar el archivo físico del adjunto de empleado eliminado: %s", instance.file.name)


# ---------------------------------------------------------------------
# Horario de trabajo
# ---------------------------------------------------------------------


class WorkSchedule(TenantScopedModel):
    name = models.CharField("nombre", max_length=100)
    days_of_week = models.JSONField(
        "días de la semana", default=list,
        help_text="Lista de enteros 0=lunes .. 6=domingo.",
    )
    start_time = models.TimeField("hora de entrada")
    end_time = models.TimeField("hora de salida")
    break_minutes = models.PositiveSmallIntegerField("minutos de descanso", default=0)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "horario de trabajo"
        verbose_name_plural = "horarios de trabajo"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_workschedule_tenant_nombre"),
        ]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------
# Asistencia
# ---------------------------------------------------------------------


class Attendance(TenantScopedModel):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        SYSTEM = "system", "Sistema"

    employee = models.ForeignKey(Employee, verbose_name="empleado", on_delete=models.PROTECT, related_name="attendances")
    date = models.DateField("fecha")
    check_in = models.TimeField("entrada", null=True, blank=True)
    check_out = models.TimeField("salida", null=True, blank=True)
    work_schedule = models.ForeignKey(
        WorkSchedule, verbose_name="horario", on_delete=models.SET_NULL, null=True, blank=True, related_name="attendances",
    )
    late_minutes = models.PositiveIntegerField("minutos de retraso", default=0)
    worked_hours = models.DecimalField("horas trabajadas", max_digits=5, decimal_places=2, null=True, blank=True)
    observation = models.CharField("observación", max_length=255, blank=True)
    source = models.CharField("origen del registro", max_length=10, choices=Source.choices, default=Source.MANUAL)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="registrado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "asistencia"
        verbose_name_plural = "asistencias"
        ordering = ["-date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "employee", "date"], name="unique_attendance_tenant_empleado_fecha"),
        ]
        indexes = [
            models.Index(fields=["tenant", "employee", "date"], name="idx_attend_tenant_emp_fecha"),
        ]

    def __str__(self):
        return f"{self.employee} — {self.date}"


# ---------------------------------------------------------------------
# Ausencias / Vacaciones / Permisos
# ---------------------------------------------------------------------


class LeaveType(TenantScopedModel):
    name = models.CharField("nombre", max_length=100)
    description = models.CharField("descripción", max_length=255, blank=True)
    is_paid = models.BooleanField("remunerada", default=True)
    requires_approval = models.BooleanField("requiere autorización", default=True)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "tipo de ausencia"
        verbose_name_plural = "tipos de ausencia"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_leavetype_tenant_nombre"),
        ]

    def __str__(self):
        return self.name


class Leave(TenantScopedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Solicitada"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        CANCELED = "canceled", "Cancelada"

    employee = models.ForeignKey(Employee, verbose_name="empleado", on_delete=models.PROTECT, related_name="leaves")
    leave_type = models.ForeignKey(LeaveType, verbose_name="tipo", on_delete=models.PROTECT, related_name="leaves")
    start_date = models.DateField("fecha de inicio")
    end_date = models.DateField("fecha de fin")
    duration_days = models.PositiveIntegerField("duración (días)")
    reason = models.CharField("motivo", max_length=255, blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.REQUESTED)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="solicitado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="resuelto por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    decision_reason = models.CharField("motivo de la decisión", max_length=255, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    decided_at = models.DateTimeField("decidida", null=True, blank=True)

    class Meta:
        verbose_name = "ausencia"
        verbose_name_plural = "ausencias"
        ordering = ["-start_date", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(duration_days__gt=0), name="leave_duracion_positiva"),
        ]
        indexes = [
            models.Index(fields=["tenant", "employee", "status"], name="idx_leave_tenant_emp_estado"),
        ]

    def __str__(self):
        return f"{self.employee} — {self.leave_type} ({self.start_date} a {self.end_date})"


# ---------------------------------------------------------------------
# Incidentes
# ---------------------------------------------------------------------


class Incident(TenantScopedModel):
    class IncidentType(models.TextChoices):
        DISCIPLINARY = "disciplinary", "Disciplinario"
        SAFETY = "safety", "Seguridad"
        PERFORMANCE = "performance", "Desempeño"
        OTHER = "other", "Otro"

    class Severity(models.TextChoices):
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        HIGH = "high", "Alta"
        CRITICAL = "critical", "Crítica"

    class Status(models.TextChoices):
        OPEN = "open", "Abierto"
        IN_REVIEW = "in_review", "En revisión"
        RESOLVED = "resolved", "Resuelto"
        CLOSED = "closed", "Cerrado"

    employee = models.ForeignKey(Employee, verbose_name="empleado", on_delete=models.PROTECT, related_name="incidents")
    incident_type = models.CharField("tipo", max_length=20, choices=IncidentType.choices)
    date = models.DateField("fecha")
    description = models.TextField("descripción")
    severity = models.CharField("severidad", max_length=10, choices=Severity.choices, default=Severity.LOW)
    resolution = models.TextField("resolución", blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.OPEN)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="reportado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "incidente"
        verbose_name_plural = "incidentes"
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["tenant", "employee", "status"], name="idx_incident_tenant_emp_estado"),
        ]

    def __str__(self):
        return f"{self.get_incident_type_display()} — {self.employee} ({self.date})"


# ---------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo)
# ---------------------------------------------------------------------


class HRActivityLog(TenantScopedModel):
    class Action(models.TextChoices):
        CREATED = "created", "Creación"
        UPDATED = "updated", "Edición"
        STATUS_CHANGED = "status_changed", "Cambio de estado"
        CONTRACT_CREATED = "contract_created", "Contrato creado"
        CONTRACT_TERMINATED = "contract_terminated", "Contrato terminado"
        ATTENDANCE_RECORDED = "attendance_recorded", "Asistencia registrada"
        LEAVE_REQUESTED = "leave_requested", "Ausencia solicitada"
        LEAVE_APPROVED = "leave_approved", "Ausencia aprobada"
        LEAVE_REJECTED = "leave_rejected", "Ausencia rechazada"
        LEAVE_CANCELED = "leave_canceled", "Ausencia cancelada"
        INCIDENT_REPORTED = "incident_reported", "Incidente reportado"
        INCIDENT_RESOLVED = "incident_resolved", "Incidente resuelto"
        ATTACHMENT_UPLOADED = "attachment_uploaded", "Adjunto subido"
        ATTACHMENT_DELETED = "attachment_deleted", "Adjunto eliminado"
        SENSITIVE_DATA_VIEWED = "sensitive_data_viewed", "Datos sensibles consultados"

    entity_type = models.CharField("tipo de entidad", max_length=25)
    entity_id = models.PositiveBigIntegerField("id de la entidad")
    entity_label = models.CharField("identificador de la entidad (al momento del evento)", max_length=255, blank=True)
    action = models.CharField("acción", max_length=30, choices=Action.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    details = models.CharField("detalles", max_length=255, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "registro de actividad (RRHH)"
        verbose_name_plural = "registros de actividad (RRHH)"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "entity_type", "entity_id"], name="idx_hrlog_tenant_entidad"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.entity_type} #{self.entity_id}"
