from django.contrib import admin

from .models import ApiKey


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ApiKey)
class ApiKeyAdmin(_ReadOnlyAdmin):
    """Solo visibilidad — generar/rotar/revocar se hace desde
    Configuración → API de Inventario (`apps.api.services`), nunca
    editando esta fila directamente (eso saltaría la auditoría)."""

    list_display = ("key_prefix", "tenant", "status", "created_at", "last_used_at")
    list_filter = ("status",)
    search_fields = ("key_prefix",)

    def get_queryset(self, request):
        return ApiKey.all_objects.select_related("tenant")
