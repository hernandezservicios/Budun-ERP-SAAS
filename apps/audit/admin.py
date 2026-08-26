from django.contrib import admin

from .models import AuditLog


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(_ReadOnlyAdmin):
    list_display = ("created_at", "tenant", "action", "domain", "object_type", "object_id", "user", "ip_address")
    list_filter = ("domain", "action")
    search_fields = ("object_type", "object_id", "reason")

    def get_queryset(self, request):
        return AuditLog.objects.select_related("tenant", "user")
