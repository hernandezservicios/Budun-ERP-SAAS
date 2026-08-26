"""Admin de solo lectura (oversight/depuración) — el Admin de Django
NUNCA es la UI principal de RRHH (regla del proyecto, ver CLAUDE.md).
Mismo patrón que `apps.expenses.admin`/`apps.purchases.admin`."""

from django.contrib import admin

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


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Department)
class DepartmentAdmin(_ReadOnlyAdmin):
    list_display = ("name", "tenant", "is_active")
    list_filter = ("tenant", "is_active")

    def get_queryset(self, request):
        return Department.all_objects.select_related("tenant", "manager")


@admin.register(Position)
class PositionAdmin(_ReadOnlyAdmin):
    list_display = ("name", "department", "tenant", "is_active")
    list_filter = ("tenant", "is_active")

    def get_queryset(self, request):
        return Position.all_objects.select_related("tenant", "department")


@admin.register(Employee)
class EmployeeAdmin(_ReadOnlyAdmin):
    list_display = ("display_name", "tenant", "status", "department", "position", "hire_date")
    list_filter = ("tenant", "status", "department")
    search_fields = ("first_name", "last_name", "identification_number")

    def get_queryset(self, request):
        return Employee.all_objects.select_related("tenant", "department", "position", "supervisor")


@admin.register(EmploymentContract)
class EmploymentContractAdmin(_ReadOnlyAdmin):
    list_display = ("employee", "tenant", "contract_type", "status", "start_date")
    list_filter = ("tenant", "status", "contract_type")

    def get_queryset(self, request):
        return EmploymentContract.all_objects.select_related("tenant", "employee")


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(_ReadOnlyAdmin):
    list_display = ("original_filename", "employee", "tenant", "category", "uploaded_at")
    list_filter = ("tenant", "category")

    def get_queryset(self, request):
        return EmployeeDocument.all_objects.select_related("tenant", "employee")


@admin.register(WorkSchedule)
class WorkScheduleAdmin(_ReadOnlyAdmin):
    list_display = ("name", "tenant", "start_time", "end_time", "is_active")
    list_filter = ("tenant", "is_active")

    def get_queryset(self, request):
        return WorkSchedule.all_objects.select_related("tenant")


@admin.register(Attendance)
class AttendanceAdmin(_ReadOnlyAdmin):
    list_display = ("employee", "tenant", "date", "check_in", "check_out", "worked_hours")
    list_filter = ("tenant", "date")

    def get_queryset(self, request):
        return Attendance.all_objects.select_related("tenant", "employee")


@admin.register(LeaveType)
class LeaveTypeAdmin(_ReadOnlyAdmin):
    list_display = ("name", "tenant", "is_paid", "requires_approval", "is_active")
    list_filter = ("tenant", "is_active")

    def get_queryset(self, request):
        return LeaveType.all_objects.select_related("tenant")


@admin.register(Leave)
class LeaveAdmin(_ReadOnlyAdmin):
    list_display = ("employee", "tenant", "leave_type", "status", "start_date", "end_date")
    list_filter = ("tenant", "status", "leave_type")

    def get_queryset(self, request):
        return Leave.all_objects.select_related("tenant", "employee", "leave_type")


@admin.register(Incident)
class IncidentAdmin(_ReadOnlyAdmin):
    list_display = ("employee", "tenant", "incident_type", "severity", "status", "date")
    list_filter = ("tenant", "status", "severity")

    def get_queryset(self, request):
        return Incident.all_objects.select_related("tenant", "employee")


@admin.register(HRActivityLog)
class HRActivityLogAdmin(_ReadOnlyAdmin):
    list_display = ("entity_type", "entity_id", "tenant", "action", "user", "created_at")
    list_filter = ("tenant", "action")

    def get_queryset(self, request):
        return HRActivityLog.all_objects.select_related("tenant", "user")
