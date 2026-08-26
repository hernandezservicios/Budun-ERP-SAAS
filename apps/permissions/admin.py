from django.contrib import admin

from .models import RolePermission, UserPermissionOverride


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("tenant", "role", "permission_code", "is_granted", "updated_at")
    list_filter = ("role", "is_granted")
    search_fields = ("permission_code",)


@admin.register(UserPermissionOverride)
class UserPermissionOverrideAdmin(admin.ModelAdmin):
    list_display = ("tenant", "user", "permission_code", "is_granted", "created_at")
    list_filter = ("is_granted",)
    search_fields = ("permission_code", "user__email")
