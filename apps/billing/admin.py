from django.contrib import admin

from .models import PayPalGatewayStatus, PayPalTransaction, PayPalWebhookEvent


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Mismo patrón que `apps.api.admin` — solo visibilidad para staff
    interno; toda mutación real pasa por `apps.billing.services` (para
    no saltarse la auditoría ni la lógica de idempotencia/concurrencia)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PayPalGatewayStatus)
class PayPalGatewayStatusAdmin(_ReadOnlyAdmin):
    list_display = ("is_enabled", "last_tested_at", "last_test_ok", "last_tested_environment", "updated_at")


@admin.register(PayPalTransaction)
class PayPalTransactionAdmin(_ReadOnlyAdmin):
    list_display = ("id", "tenant", "plan_id", "purpose", "environment", "status", "amount", "currency", "created_at")
    list_filter = ("status", "purpose", "environment")
    search_fields = ("external_order_id", "external_capture_id", "external_refund_id")

    def get_queryset(self, request):
        return PayPalTransaction.objects.select_related("tenant")


@admin.register(PayPalWebhookEvent)
class PayPalWebhookEventAdmin(_ReadOnlyAdmin):
    list_display = ("event_id", "event_type", "status", "transaction", "received_at", "processed_at")
    list_filter = ("status", "event_type")
    search_fields = ("event_id",)
