from django.contrib import admin

from .models import IsolationSample, Membership, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "is_active", "created_at")
    list_filter = ("tenant", "role", "is_active")


@admin.register(IsolationSample)
class IsolationSampleAdmin(admin.ModelAdmin):
    """Solo para depuración interna (ver models.py): no forma parte de
    ninguna funcionalidad de negocio."""

    list_display = ("label", "tenant")

    def get_queryset(self, request):
        # El admin debe poder ver todos los tenants (herramienta interna
        # de staff), no solo el tenant activo del contexto.
        return IsolationSample.all_objects.all()
