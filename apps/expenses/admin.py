"""Admin de solo lectura (oversight/depuración) — el Admin de Django
NUNCA es la UI principal de Gastos (regla del proyecto, ver CLAUDE.md).
Mismo patrón que `apps.purchases.admin`/`apps.pos.admin`."""

from django.contrib import admin

from .models import (
    Expense,
    ExpenseCategory,
    ExpenseDocument,
    ExpensePayment,
    ExpenseRecurrence,
    ExpensesActivityLog,
)


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(_ReadOnlyAdmin):
    list_display = ("name", "tenant", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)

    def get_queryset(self, request):
        return ExpenseCategory.all_objects.select_related("tenant")


@admin.register(Expense)
class ExpenseAdmin(_ReadOnlyAdmin):
    list_display = ("number", "tenant", "category", "status", "total", "expense_date")
    list_filter = ("tenant", "status", "category")
    search_fields = ("number", "description")

    def get_queryset(self, request):
        return Expense.all_objects.select_related("tenant", "category", "supplier")


@admin.register(ExpensePayment)
class ExpensePaymentAdmin(_ReadOnlyAdmin):
    list_display = ("expense", "tenant", "method", "amount", "status", "created_at")
    list_filter = ("tenant", "method", "status")

    def get_queryset(self, request):
        return ExpensePayment.all_objects.select_related("tenant", "expense")


@admin.register(ExpenseRecurrence)
class ExpenseRecurrenceAdmin(_ReadOnlyAdmin):
    list_display = ("description", "tenant", "frequency", "status", "next_run_date")
    list_filter = ("tenant", "status", "frequency")

    def get_queryset(self, request):
        return ExpenseRecurrence.all_objects.select_related("tenant", "category", "supplier")


@admin.register(ExpenseDocument)
class ExpenseDocumentAdmin(_ReadOnlyAdmin):
    list_display = ("original_filename", "expense", "tenant", "category", "uploaded_at")
    list_filter = ("tenant", "category")

    def get_queryset(self, request):
        return ExpenseDocument.all_objects.select_related("tenant", "expense")


@admin.register(ExpensesActivityLog)
class ExpensesActivityLogAdmin(_ReadOnlyAdmin):
    list_display = ("entity_type", "entity_id", "tenant", "action", "user", "created_at")
    list_filter = ("tenant", "action")

    def get_queryset(self, request):
        return ExpensesActivityLog.all_objects.select_related("tenant", "user")
