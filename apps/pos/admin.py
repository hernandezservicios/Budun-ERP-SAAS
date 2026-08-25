from django.contrib import admin

from .models import CashMovement, CashRegister, CashSession


@admin.register(CashRegister)
class CashRegisterAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "tenant", "status", "terminal")
    list_filter = ("tenant", "status")
    search_fields = ("code", "name")

    def get_queryset(self, request):
        return CashRegister.all_objects.select_related("tenant")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = ("cash_register", "user", "tenant", "status", "opening_amount", "expected_cash", "counted_cash", "difference", "opened_at")
    list_filter = ("tenant", "status")

    def get_queryset(self, request):
        return CashSession.all_objects.select_related("tenant", "cash_register", "user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CashMovement)
class CashMovementAdmin(admin.ModelAdmin):
    list_display = ("movement_type", "cash_session", "tenant", "amount", "user", "created_at")
    list_filter = ("tenant", "movement_type")

    def get_queryset(self, request):
        return CashMovement.all_objects.select_related("tenant", "cash_session", "user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
