from django.contrib import admin

from .models import ApiKey, Integration


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


@admin.register(Integration)
class IntegrationAdmin(_ReadOnlyAdmin):
    """Solo visibilidad — crear/rotar/revocar se hace desde
    Configuración → Integraciones (`apps.api.integration_services`),
    nunca editando esta fila directamente (eso saltaría la auditoría)."""

    list_display = ("name", "provider", "tenant", "status", "is_enabled", "created_at", "last_used_at")
    list_filter = ("provider", "status", "is_enabled")
    search_fields = ("name", "app_key")

    def get_queryset(self, request):
        return Integration.all_objects.select_related("tenant")
