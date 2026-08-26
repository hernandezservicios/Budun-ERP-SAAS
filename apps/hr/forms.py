"""Formularios de RRHH (FASE 13). Formularios planos (no `ModelForm`):
el guardado real siempre lo hace `services.py`, nunca `form.save()` —
mismo criterio que `apps.expenses.forms`/`apps.purchases.forms`."""

from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.customers.file_validation import FORMATOS_PERMITIDOS_LEGIBLE, validar_archivo_adjunto
from apps.customers.models import DocumentCategory, IdentificationType

from .models import Department, Employee, EmploymentContract, Incident, LeaveType, Position, WorkSchedule

_DIAS_SEMANA = [(0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"), (4, "Viernes"), (5, "Sábado"), (6, "Domingo")]


class DepartmentForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=100)
    description = forms.CharField(label="Descripción", max_length=255, required=False)


class PositionForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=100)
    department = forms.ModelChoiceField(label="Departamento", queryset=Department.objects.none(), required=False)
    description = forms.CharField(label="Descripción", max_length=255, required=False)
    level = forms.CharField(label="Nivel", max_length=50, required=False)
    suggested_base_salary = forms.DecimalField(label="Salario base sugerido", max_digits=12, decimal_places=2, required=False, min_value=Decimal("0"))

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["department"].queryset = Department.objects.filter(tenant=tenant, is_active=True)


class EmployeeForm(forms.Form):
    first_name = forms.CharField(label="Nombre", max_length=150, required=False)
    last_name = forms.CharField(label="Apellido", max_length=150, required=False)
    identification_type = forms.ChoiceField(label="Tipo de identificación", choices=[("", "—")] + list(IdentificationType.choices), required=False)
    identification_number = forms.CharField(label="Número de identificación", max_length=50, required=False)
    birth_date = forms.DateField(label="Fecha de nacimiento", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    phone = forms.CharField(label="Teléfono", max_length=30, required=False)
    email = forms.EmailField(label="Correo electrónico", required=False)
    address = forms.CharField(label="Dirección", max_length=255, required=False)
    city = forms.CharField(label="Ciudad", max_length=100, required=False)
    state_province = forms.CharField(label="Provincia / Estado", max_length=100, required=False)
    country = forms.CharField(label="País", max_length=100, required=False)
    hire_date = forms.DateField(label="Fecha de ingreso", widget=forms.DateInput(attrs={"type": "date"}))
    department = forms.ModelChoiceField(label="Departamento", queryset=Department.objects.none(), required=False)
    position = forms.ModelChoiceField(label="Cargo", queryset=Position.objects.none(), required=False)
    supervisor = forms.ModelChoiceField(label="Supervisor", queryset=Employee.objects.none(), required=False)
    base_salary = forms.DecimalField(label="Salario base", max_digits=12, decimal_places=2, required=False, min_value=Decimal("0"), initial=Decimal("0"))
    currency = forms.CharField(label="Moneda", max_length=3, initial="USD", required=False)
    bank_name = forms.CharField(label="Banco", max_length=100, required=False)
    bank_account_number = forms.CharField(label="Número de cuenta", max_length=50, required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, tenant=None, exclude_employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["department"].queryset = Department.objects.filter(tenant=tenant, is_active=True)
            self.fields["position"].queryset = Position.objects.filter(tenant=tenant, is_active=True)
            supervisores = Employee.objects.filter(tenant=tenant, status=Employee.Status.ACTIVE)
            if exclude_employee is not None:
                supervisores = supervisores.exclude(pk=exclude_employee.pk)
            self.fields["supervisor"].queryset = supervisores

    def clean_base_salary(self):
        return self.cleaned_data.get("base_salary") or Decimal("0")

    def clean(self):
        datos = super().clean()
        if not (datos.get("first_name") or datos.get("last_name")):
            raise forms.ValidationError("El empleado debe tener al menos nombre o apellido.")
        return datos


class EmployeeStatusForm(forms.Form):
    new_status = forms.ChoiceField(label="Nuevo estado", choices=Employee.Status.choices)
    reason = forms.CharField(label="Motivo", max_length=255, required=False)


class EmploymentContractForm(forms.Form):
    contract_type = forms.ChoiceField(label="Tipo de contrato", choices=EmploymentContract.ContractType.choices)
    start_date = forms.DateField(label="Fecha de inicio", widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(label="Fecha de fin", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    salary = forms.DecimalField(label="Salario", max_digits=12, decimal_places=2, min_value=Decimal("0"))
    currency = forms.CharField(label="Moneda", max_length=3, initial="USD", required=False)
    work_schedule = forms.ModelChoiceField(label="Horario", queryset=WorkSchedule.objects.none(), required=False)
    conditions = forms.CharField(label="Condiciones", widget=forms.Textarea(attrs={"rows": 3}), required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["work_schedule"].queryset = WorkSchedule.objects.filter(tenant=tenant, is_active=True)


class EmployeeDocumentForm(forms.Form):
    file = forms.FileField(label="Archivo")
    category = forms.ChoiceField(label="Categoría", choices=DocumentCategory.choices, initial=DocumentCategory.OTRO)
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].help_text = f"Formatos permitidos: {FORMATOS_PERMITIDOS_LEGIBLE}. Máximo 10 MB."

    def clean_file(self):
        archivo = self.cleaned_data["file"]
        try:
            validar_archivo_adjunto(archivo)
        except forms.ValidationError:
            raise
        except Exception as error:  # noqa: BLE001 — nunca dejar pasar un archivo sin validar
            raise forms.ValidationError(str(error))
        return archivo


class WorkScheduleForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=100)
    days_of_week = forms.MultipleChoiceField(label="Días", choices=_DIAS_SEMANA, required=False, widget=forms.CheckboxSelectMultiple)
    start_time = forms.TimeField(label="Hora de entrada", widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(label="Hora de salida", widget=forms.TimeInput(attrs={"type": "time"}))
    break_minutes = forms.IntegerField(label="Minutos de descanso", required=False, min_value=0, initial=0)

    def clean_days_of_week(self):
        return [int(dia) for dia in self.cleaned_data.get("days_of_week", [])]

    def clean_break_minutes(self):
        return self.cleaned_data.get("break_minutes") or 0


class AttendanceCheckInForm(forms.Form):
    date = forms.DateField(label="Fecha", initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}))
    check_in_time = forms.TimeField(label="Hora de entrada", widget=forms.TimeInput(attrs={"type": "time"}))
    work_schedule = forms.ModelChoiceField(label="Horario", queryset=WorkSchedule.objects.none(), required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["work_schedule"].queryset = WorkSchedule.objects.filter(tenant=tenant, is_active=True)


class AttendanceCheckOutForm(forms.Form):
    check_out_time = forms.TimeField(label="Hora de salida", widget=forms.TimeInput(attrs={"type": "time"}))


class LeaveTypeForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=100)
    description = forms.CharField(label="Descripción", max_length=255, required=False)
    is_paid = forms.BooleanField(label="Remunerada", required=False, initial=True)
    requires_approval = forms.BooleanField(label="Requiere autorización", required=False, initial=True)


class LeaveRequestForm(forms.Form):
    leave_type = forms.ModelChoiceField(label="Tipo de ausencia", queryset=LeaveType.objects.none())
    start_date = forms.DateField(label="Fecha de inicio", widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(label="Fecha de fin", widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(label="Motivo", max_length=255, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["leave_type"].queryset = LeaveType.objects.filter(tenant=tenant, is_active=True)

    def clean(self):
        datos = super().clean()
        if datos.get("start_date") and datos.get("end_date") and datos["end_date"] < datos["start_date"]:
            self.add_error("end_date", "La fecha de fin no puede ser anterior a la fecha de inicio.")
        return datos


class LeaveDecisionForm(forms.Form):
    decision_reason = forms.CharField(label="Motivo de la decisión", max_length=255, required=False)


class IncidentForm(forms.Form):
    incident_type = forms.ChoiceField(label="Tipo", choices=Incident.IncidentType.choices)
    date = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(label="Descripción", widget=forms.Textarea(attrs={"rows": 3}))
    severity = forms.ChoiceField(label="Severidad", choices=Incident.Severity.choices)


class IncidentResolutionForm(forms.Form):
    status = forms.ChoiceField(label="Estado", choices=Incident.Status.choices)
    resolution = forms.CharField(label="Resolución", widget=forms.Textarea(attrs={"rows": 3}), required=False)
