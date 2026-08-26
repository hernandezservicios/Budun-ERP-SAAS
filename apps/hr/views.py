"""
Vistas de RRHH (FASE 13). Deliberadamente delgadas: toda la lógica vive
en `apps.hr.services`, que a su vez consume literalmente
`apps.approvals`/`apps.customers.file_validation` — esta capa solo arma
el request/response. Información sensible (salario/datos bancarios)
nunca se oculta solo en la plantilla: la vista decide explícitamente
qué contexto pasar según `services.can_view_sensitive_employee_data`, y
cada lectura por el propietario se audita.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.customers.file_validation import nombre_original_seguro
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import (
    AttendanceCheckInForm,
    AttendanceCheckOutForm,
    DepartmentForm,
    EmployeeDocumentForm,
    EmployeeForm,
    EmployeeStatusForm,
    EmploymentContractForm,
    IncidentForm,
    IncidentResolutionForm,
    LeaveDecisionForm,
    LeaveRequestForm,
    LeaveTypeForm,
    PositionForm,
    WorkScheduleForm,
)
from .models import Attendance, Department, Employee, EmployeeDocument, EmploymentContract, Incident, Leave, LeaveType, Position, WorkSchedule


def _mensaje_error(error):
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


# ------------------------------------------------------------------
# Departamentos y Cargos
# ------------------------------------------------------------------


class DepartmentListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {"departamentos": services.list_departments(request.tenant, only_active=False), "form": DepartmentForm()}
        return render(request, "hr/department_list.html", context)

    def post(self, request):
        form = DepartmentForm(request.POST)
        if form.is_valid():
            try:
                services.create_department(request.tenant, **form.cleaned_data)
                messages.success(request, "Departamento creado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa el nombre del departamento.")
        return redirect("hr:department_list")


class DepartmentToggleView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        departamento = get_object_or_404(Department, pk=pk, tenant=request.tenant)
        services.set_department_active(departamento, is_active=not departamento.is_active)
        messages.success(request, "Departamento actualizado.")
        return redirect("hr:department_list")


class PositionListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {"cargos": services.list_positions(request.tenant, only_active=False), "form": PositionForm(tenant=request.tenant)}
        return render(request, "hr/position_list.html", context)

    def post(self, request):
        form = PositionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                services.create_position(request.tenant, **form.cleaned_data)
                messages.success(request, "Cargo creado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del cargo.")
        return redirect("hr:position_list")


class PositionToggleView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        cargo = get_object_or_404(Position, pk=pk, tenant=request.tenant)
        services.set_position_active(cargo, is_active=not cargo.is_active)
        messages.success(request, "Cargo actualizado.")
        return redirect("hr:position_list")


# ------------------------------------------------------------------
# Empleados
# ------------------------------------------------------------------


class EmployeeListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "hr/employee_list.html"
    context_object_name = "empleados"
    paginate_by = 20

    def get_queryset(self):
        return services.list_employees(
            self.request.tenant, status=self.request.GET.get("estado", ""), search=self.request.GET.get("q", "").strip(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["estados"] = Employee.Status.choices
        context["q"] = self.request.GET.get("q", "")
        context["estado"] = self.request.GET.get("estado", "")
        return context


class EmployeeCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        return render(request, "hr/employee_form.html", {"form": EmployeeForm(tenant=request.tenant)})

    def post(self, request):
        form = EmployeeForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                empleado = services.create_employee(request.tenant, user=request.user, **form.cleaned_data)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
                return render(request, "hr/employee_form.html", {"form": form})
            messages.success(request, f"Empleado «{empleado.display_name}» creado correctamente.")
            return redirect("hr:employee_detail", pk=empleado.pk)
        return render(request, "hr/employee_form.html", {"form": form})


class EmployeeDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        puede_ver_sensible = services.can_view_sensitive_employee_data(request.tenant, request.user)
        if puede_ver_sensible:
            services.log_sensitive_access(empleado, request.user)
        # El formulario de edición incluye salario/datos bancarios — se
        # arma (y se renderiza) SOLO si este usuario puede verlos; nunca
        # se oculta solo en la plantilla (ver docs/hr.md). Un MEMBER sin
        # ese permiso simplemente no ve ningún formulario de edición
        # hoy (simplificación explícita de FASE 13 con solo dos roles
        # — FASE 15 podrá separar "editar datos básicos" de "editar
        # datos sensibles" sin romper este diseño).
        edit_form = None
        if puede_ver_sensible:
            edit_form = EmployeeForm(tenant=request.tenant, exclude_employee=empleado, initial={
                "first_name": empleado.first_name, "last_name": empleado.last_name,
                "identification_type": empleado.identification_type, "identification_number": empleado.identification_number,
                "birth_date": empleado.birth_date, "phone": empleado.phone, "email": empleado.email,
                "address": empleado.address, "city": empleado.city, "state_province": empleado.state_province,
                "country": empleado.country, "hire_date": empleado.hire_date, "department": empleado.department_id,
                "position": empleado.position_id, "supervisor": empleado.supervisor_id, "base_salary": empleado.base_salary,
                "currency": empleado.currency, "bank_name": empleado.bank_name,
                "bank_account_number": empleado.bank_account_number, "notes": empleado.notes,
            })
        context = {
            "empleado": empleado,
            "puede_ver_sensible": puede_ver_sensible,
            "edit_form": edit_form,
            "status_form": EmployeeStatusForm(),
            "contract_form": EmploymentContractForm(tenant=request.tenant),
            "document_form": EmployeeDocumentForm(),
            "checkin_form": AttendanceCheckInForm(tenant=request.tenant),
            "checkout_form": AttendanceCheckOutForm(),
            "leave_form": LeaveRequestForm(tenant=request.tenant),
            "leave_decision_form": LeaveDecisionForm(),
            "incident_form": IncidentForm(),
            "incident_resolution_form": IncidentResolutionForm(),
            "contracts": services.get_employee_contracts(empleado),
            "documentos": services.get_employee_documents(empleado),
            "asistencias": services.get_employee_attendance(empleado)[:30],
            "ausencias": services.get_employee_leaves(empleado),
            "incidentes": services.get_employee_incidents(empleado),
            "activity_log": services.get_activity_log(request.tenant, entity_type="employee", entity_id=empleado.pk),
        }
        return render(request, "hr/employee_detail.html", context)


class EmployeeEditView(LoginRequiredMixin, TenantRequiredMixin, View):
    """El formulario incluye salario/datos bancarios — nunca basta con
    no mostrar el botón en la plantilla: se rechaza aquí también,
    en el servidor, para cualquier usuario que no pueda ver esa
    información (ver `services.can_view_sensitive_employee_data`)."""

    def post(self, request, pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        if not services.can_view_sensitive_employee_data(request.tenant, request.user):
            raise PermissionDenied("No tienes permiso para editar este empleado.")
        form = EmployeeForm(request.POST, tenant=request.tenant, exclude_employee=empleado)
        if form.is_valid():
            try:
                services.update_employee(empleado, request.user, **form.cleaned_data)
                messages.success(request, "Empleado actualizado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del empleado.")
        return redirect("hr:employee_detail", pk=empleado.pk)


class EmployeeStatusChangeView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        form = EmployeeStatusForm(request.POST)
        if form.is_valid():
            try:
                services.change_employee_status(
                    empleado, form.cleaned_data["new_status"], request.user, reason=form.cleaned_data["reason"],
                )
                messages.success(request, "Estado del empleado actualizado.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa el estado seleccionado.")
        return redirect("hr:employee_detail", pk=empleado.pk)


# ------------------------------------------------------------------
# Contratos
# ------------------------------------------------------------------


class EmploymentContractCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        form = EmploymentContractForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                services.create_employment_contract(request.tenant, empleado, user=request.user, **form.cleaned_data)
                messages.success(request, "Contrato creado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del contrato.")
        return redirect("hr:employee_detail", pk=empleado.pk)


class EmploymentContractTerminateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, contract_pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        contrato = get_object_or_404(EmploymentContract, pk=contract_pk, tenant=request.tenant, employee=empleado)
        try:
            services.terminate_contract(contrato, request.user)
            messages.success(request, "Contrato terminado.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("hr:employee_detail", pk=empleado.pk)


# ------------------------------------------------------------------
# Documentos
# ------------------------------------------------------------------


class EmployeeDocumentUploadView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        form = EmployeeDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                services.register_employee_document(
                    empleado, archivo=form.cleaned_data["file"], category=form.cleaned_data["category"],
                    user=request.user, notes=form.cleaned_data["notes"],
                )
                messages.success(request, "Documento subido correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
        return redirect("hr:employee_detail", pk=empleado.pk)


class EmployeeDocumentDeleteView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, document_pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        documento = get_object_or_404(EmployeeDocument, pk=document_pk, tenant=request.tenant, employee=empleado)
        services.delete_employee_document(documento, request.user)
        messages.success(request, "Documento eliminado correctamente.")
        return redirect("hr:employee_detail", pk=empleado.pk)


class EmployeeDocumentDownloadView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk, document_pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        documento = get_object_or_404(EmployeeDocument, pk=document_pk, tenant=request.tenant, employee=empleado)
        return FileResponse(documento.file.open("rb"), as_attachment=True, filename=nombre_original_seguro(documento.original_filename))


# ------------------------------------------------------------------
# Horarios
# ------------------------------------------------------------------


class WorkScheduleListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {"horarios": services.list_work_schedules(request.tenant, only_active=False), "form": WorkScheduleForm()}
        return render(request, "hr/work_schedule_list.html", context)

    def post(self, request):
        form = WorkScheduleForm(request.POST)
        if form.is_valid():
            services.create_work_schedule(request.tenant, **form.cleaned_data)
            messages.success(request, "Horario creado correctamente.")
        else:
            messages.error(request, "Revisa los datos del horario.")
        return redirect("hr:work_schedule_list")


# ------------------------------------------------------------------
# Asistencia
# ------------------------------------------------------------------


class AttendanceCheckInView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        form = AttendanceCheckInForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                services.record_check_in(
                    request.tenant, empleado, date=form.cleaned_data["date"],
                    check_in_time=form.cleaned_data["check_in_time"], user=request.user,
                    work_schedule=form.cleaned_data["work_schedule"],
                )
                messages.success(request, "Entrada registrada correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos de la entrada.")
        return redirect("hr:employee_detail", pk=empleado.pk)


class AttendanceCheckOutView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, attendance_pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        asistencia = get_object_or_404(Attendance, pk=attendance_pk, tenant=request.tenant, employee=empleado)
        form = AttendanceCheckOutForm(request.POST)
        if form.is_valid():
            try:
                services.record_check_out(request.tenant, asistencia, check_out_time=form.cleaned_data["check_out_time"], user=request.user)
                messages.success(request, "Salida registrada correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa la hora de salida.")
        return redirect("hr:employee_detail", pk=empleado.pk)


# ------------------------------------------------------------------
# Ausencias / Vacaciones
# ------------------------------------------------------------------


class LeaveTypeListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {"tipos": services.list_leave_types(request.tenant, only_active=False), "form": LeaveTypeForm()}
        return render(request, "hr/leave_type_list.html", context)

    def post(self, request):
        form = LeaveTypeForm(request.POST)
        if form.is_valid():
            LeaveType.all_objects.get_or_create(
                tenant=request.tenant, name=form.cleaned_data["name"],
                defaults={
                    "description": form.cleaned_data["description"], "is_paid": form.cleaned_data["is_paid"],
                    "requires_approval": form.cleaned_data["requires_approval"],
                },
            )
            messages.success(request, "Tipo de ausencia creado correctamente.")
        else:
            messages.error(request, "Revisa los datos del tipo de ausencia.")
        return redirect("hr:leave_type_list")


class LeaveTypeSeedDefaultsView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        creados = services.create_default_leave_types(request.tenant)
        if creados:
            messages.success(request, f"Se crearon {len(creados)} tipos de ausencia sugeridos.")
        else:
            messages.info(request, "Ya existían todos los tipos sugeridos.")
        return redirect("hr:leave_type_list")


class LeaveRequestView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        form = LeaveRequestForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                services.request_leave(request.tenant, employee=empleado, user=request.user, **form.cleaned_data)
                messages.success(request, "Ausencia solicitada correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos de la solicitud.")
        return redirect("hr:employee_detail", pk=empleado.pk)


class LeaveApproveView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, leave_pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        ausencia = get_object_or_404(Leave, pk=leave_pk, tenant=request.tenant, employee=empleado)
        form = LeaveDecisionForm(request.POST)
        reason = form.cleaned_data["decision_reason"] if form.is_valid() else ""
        try:
            services.approve_leave(ausencia, request.user, decision_reason=reason)
            messages.success(request, "Ausencia aprobada.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("hr:employee_detail", pk=empleado.pk)


class LeaveRejectView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, leave_pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        ausencia = get_object_or_404(Leave, pk=leave_pk, tenant=request.tenant, employee=empleado)
        form = LeaveDecisionForm(request.POST)
        reason = form.cleaned_data["decision_reason"] if form.is_valid() else ""
        try:
            services.reject_leave(ausencia, request.user, decision_reason=reason)
            messages.success(request, "Ausencia rechazada.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("hr:employee_detail", pk=empleado.pk)


class LeaveCancelView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, leave_pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        ausencia = get_object_or_404(Leave, pk=leave_pk, tenant=request.tenant, employee=empleado)
        try:
            services.cancel_leave(ausencia, request.user)
            messages.success(request, "Ausencia cancelada.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("hr:employee_detail", pk=empleado.pk)


# ------------------------------------------------------------------
# Incidentes
# ------------------------------------------------------------------


class IncidentReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        form = IncidentForm(request.POST)
        if form.is_valid():
            try:
                services.report_incident(request.tenant, employee=empleado, user=request.user, **form.cleaned_data)
                messages.success(request, "Incidente reportado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del incidente.")
        return redirect("hr:employee_detail", pk=empleado.pk)


class IncidentUpdateStatusView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, incident_pk):
        empleado = get_object_or_404(Employee, pk=pk, tenant=request.tenant)
        incidente = get_object_or_404(Incident, pk=incident_pk, tenant=request.tenant, employee=empleado)
        form = IncidentResolutionForm(request.POST)
        if form.is_valid():
            services.update_incident_status(
                incidente, form.cleaned_data["status"], request.user, resolution=form.cleaned_data["resolution"],
            )
            messages.success(request, "Incidente actualizado.")
        else:
            messages.error(request, "Revisa los datos de la resolución.")
        return redirect("hr:employee_detail", pk=empleado.pk)
