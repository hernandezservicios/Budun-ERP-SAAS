from django.contrib import admin

from .models import ApprovalPolicy, ApprovalRequest


@admin.register(ApprovalPolicy)
class ApprovalPolicyAdmin(admin.ModelAdmin):
    list_display = ("tenant", "scope", "role", "user", "max_discount_percent", "max_discount_amount", "can_approve")
    list_filter = ("tenant", "scope", "can_approve")

    def get_queryset(self, request):
        return ApprovalPolicy.all_objects.select_related("tenant", "user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("action_type", "tenant", "status", "requested_by", "requested_value", "requested_at")
    list_filter = ("tenant", "action_type", "status")

    def get_queryset(self, request):
        return ApprovalRequest.all_objects.select_related("tenant", "requested_by", "approved_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
