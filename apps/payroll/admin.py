"""Admin de solo lectura (oversight/depuración) — el Admin de Django
NUNCA es la UI principal de Nómina (regla del proyecto, ver CLAUDE.md).
Mismo patrón que `apps.hr.admin`/`apps.expenses.admin`."""

from django.contrib import admin

from .models import Payroll, PayrollActivityLog, PayrollLine, PayrollPayment, PayrollPeriod


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class PayrollLineInline(admin.TabularInline):
    model = PayrollLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in PayrollLine._meta.fields]


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(_ReadOnlyAdmin):
    list_display = ("number", "tenant", "status", "start_date", "end_date", "pay_date")
    list_filter = ("tenant", "status")
    search_fields = ("number",)

    def get_queryset(self, request):
        return PayrollPeriod.all_objects.select_related("tenant")


@admin.register(Payroll)
class PayrollAdmin(_ReadOnlyAdmin):
    list_display = ("employee_name_snapshot", "period", "tenant", "status", "gross_total", "net_total")
    list_filter = ("tenant", "status")
    inlines = [PayrollLineInline]

    def get_queryset(self, request):
        return Payroll.all_objects.select_related("tenant", "period", "employee")


@admin.register(PayrollPayment)
class PayrollPaymentAdmin(_ReadOnlyAdmin):
    list_display = ("payroll", "tenant", "method", "amount", "status", "created_at")
    list_filter = ("tenant", "method", "status")

    def get_queryset(self, request):
        return PayrollPayment.all_objects.select_related("tenant", "payroll")


@admin.register(PayrollActivityLog)
class PayrollActivityLogAdmin(_ReadOnlyAdmin):
    list_display = ("entity_type", "entity_id", "tenant", "action", "user", "created_at")
    list_filter = ("tenant", "action")

    def get_queryset(self, request):
        return PayrollActivityLog.all_objects.select_related("tenant", "user")
