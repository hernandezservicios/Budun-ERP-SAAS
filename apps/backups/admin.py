from django.contrib import admin

from .models import BackupRun


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Mismo patrón que `apps.audit.admin._ReadOnlyAdmin` — un registro
    de ejecución de backup nunca se edita ni se crea a mano desde el
    admin, solo se observa. Visibilidad de plataforma exclusivamente
    (`is_superuser`, ver `docs/backup-recovery.md` sección "Platform /
    Tenant") — ningún tenant tiene acceso al admin de Django en primer
    lugar (no es la UI principal del proyecto, ver CLAUDE.md)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BackupRun)
class BackupRunAdmin(_ReadOnlyAdmin):
    list_display = ("started_at", "kind", "status", "size_bytes", "duration_seconds", "encrypted")
    list_filter = ("kind", "status", "encrypted")
    search_fields = ("relative_path", "checksum_sha256")
