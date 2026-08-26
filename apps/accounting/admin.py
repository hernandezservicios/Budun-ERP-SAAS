"""Admin de solo lectura (oversight/depuración) — el Admin de Django
NUNCA es la UI principal de Contabilidad (regla del proyecto, ver
CLAUDE.md). Mismo patrón que `apps.payroll.admin`/`apps.hr.admin`."""

from django.contrib import admin

from .models import (
    Account,
    AccountingActivityLog,
    AccountingPeriod,
    AccountMapping,
    JournalEntry,
    JournalEntryLine,
)


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class JournalEntryLineInline(admin.TabularInline):
    model = JournalEntryLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in JournalEntryLine._meta.fields]


@admin.register(Account)
class AccountAdmin(_ReadOnlyAdmin):
    list_display = ("code", "name", "tenant", "account_type", "allows_posting", "is_active")
    list_filter = ("tenant", "account_type", "is_active")
    search_fields = ("code", "name")

    def get_queryset(self, request):
        return Account.all_objects.select_related("tenant", "parent")


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(_ReadOnlyAdmin):
    list_display = ("name", "tenant", "status", "start_date", "end_date")
    list_filter = ("tenant", "status")

    def get_queryset(self, request):
        return AccountingPeriod.all_objects.select_related("tenant")


@admin.register(JournalEntry)
class JournalEntryAdmin(_ReadOnlyAdmin):
    list_display = ("number", "tenant", "entry_date", "status", "source_type")
    list_filter = ("tenant", "status", "source_type")
    search_fields = ("number",)
    inlines = [JournalEntryLineInline]

    def get_queryset(self, request):
        return JournalEntry.all_objects.select_related("tenant", "period")


@admin.register(AccountMapping)
class AccountMappingAdmin(_ReadOnlyAdmin):
    list_display = ("key", "account", "tenant")
    list_filter = ("tenant", "key")

    def get_queryset(self, request):
        return AccountMapping.all_objects.select_related("tenant", "account")


@admin.register(AccountingActivityLog)
class AccountingActivityLogAdmin(_ReadOnlyAdmin):
    list_display = ("entity_type", "entity_id", "tenant", "action", "user", "created_at")
    list_filter = ("tenant", "action")

    def get_queryset(self, request):
        return AccountingActivityLog.all_objects.select_related("tenant", "user")
