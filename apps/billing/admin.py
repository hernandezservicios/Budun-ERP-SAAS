from django.contrib import admin

from .models import (
    BankAccount,
    BillingPolicy,
    BillingRefund,
    Coupon,
    CreditNote,
    CreditNoteApplication,
    PaymentProof,
    PayPalGatewayStatus,
    PayPalTransaction,
    PayPalWebhookEvent,
    Plan,
    PlanVersion,
    SaaSCustomer,
    SaaSInvoice,
    SaaSInvoiceLine,
    SaaSPayment,
    SaaSPaymentAllocation,
    Subscription,
)


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


# ------------------------------------------------------------------
# FASE 17 — Billing SaaS completo. Todas las mutaciones reales pasan
# por apps.billing.services (Configuración → Super Admin Billing es la
# UI real); este admin es solo visibilidad de respaldo para staff.
# ------------------------------------------------------------------

@admin.register(BillingPolicy)
class BillingPolicyAdmin(_ReadOnlyAdmin):
    list_display = ("grace_period_days", "past_due_to_suspend_days", "invoice_advance_days", "updated_at")


@admin.register(SaaSCustomer)
class SaaSCustomerAdmin(_ReadOnlyAdmin):
    list_display = ("name", "email", "country", "currency", "created_at")
    search_fields = ("name", "email")


@admin.register(Plan)
class PlanAdmin(_ReadOnlyAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")


@admin.register(PlanVersion)
class PlanVersionAdmin(_ReadOnlyAdmin):
    list_display = ("plan", "frequency", "price_amount", "price_currency", "is_current", "created_at")
    list_filter = ("frequency", "is_current")


@admin.register(Subscription)
class SubscriptionAdmin(_ReadOnlyAdmin):
    list_display = ("tenant", "plan_version", "status", "current_period_end", "created_at")
    list_filter = ("status",)

    def get_queryset(self, request):
        return Subscription.all_objects.select_related("tenant", "plan_version__plan")


@admin.register(SaaSInvoice)
class SaaSInvoiceAdmin(_ReadOnlyAdmin):
    list_display = ("number", "tenant", "status", "total", "currency", "due_date")
    list_filter = ("status",)
    search_fields = ("number",)

    def get_queryset(self, request):
        return SaaSInvoice.all_objects.select_related("tenant", "subscription")


@admin.register(SaaSInvoiceLine)
class SaaSInvoiceLineAdmin(_ReadOnlyAdmin):
    list_display = ("invoice", "description", "quantity", "amount")

    def get_queryset(self, request):
        return SaaSInvoiceLine.all_objects.select_related("invoice")


@admin.register(SaaSPayment)
class SaaSPaymentAdmin(_ReadOnlyAdmin):
    list_display = ("tenant", "saas_customer", "method", "amount", "currency", "status", "created_at")
    list_filter = ("method", "status")

    def get_queryset(self, request):
        return SaaSPayment.all_objects.select_related("tenant", "saas_customer")


@admin.register(SaaSPaymentAllocation)
class SaaSPaymentAllocationAdmin(_ReadOnlyAdmin):
    list_display = ("payment", "invoice", "amount", "status", "created_at")

    def get_queryset(self, request):
        return SaaSPaymentAllocation.all_objects.select_related("payment", "invoice")


@admin.register(CreditNote)
class CreditNoteAdmin(_ReadOnlyAdmin):
    list_display = ("number", "tenant", "amount", "currency", "created_at")
    search_fields = ("number",)

    def get_queryset(self, request):
        return CreditNote.all_objects.select_related("tenant")


@admin.register(CreditNoteApplication)
class CreditNoteApplicationAdmin(_ReadOnlyAdmin):
    list_display = ("credit_note", "invoice", "amount", "status")

    def get_queryset(self, request):
        return CreditNoteApplication.all_objects.select_related("credit_note", "invoice")


@admin.register(BillingRefund)
class BillingRefundAdmin(_ReadOnlyAdmin):
    list_display = ("payment", "amount", "currency", "status", "created_at")

    def get_queryset(self, request):
        return BillingRefund.all_objects.select_related("payment")


@admin.register(BankAccount)
class BankAccountAdmin(_ReadOnlyAdmin):
    list_display = ("bank_name", "country", "currency", "account_holder", "is_active", "priority")


@admin.register(PaymentProof)
class PaymentProofAdmin(_ReadOnlyAdmin):
    list_display = ("reference", "tenant", "status", "declared_amount", "declared_currency", "uploaded_at")
    list_filter = ("status",)
    search_fields = ("reference",)

    def get_queryset(self, request):
        return PaymentProof.all_objects.select_related("tenant", "invoice")


@admin.register(Coupon)
class CouponAdmin(_ReadOnlyAdmin):
    list_display = ("code", "discount_type", "discount_value", "is_active", "times_redeemed", "max_redemptions")
