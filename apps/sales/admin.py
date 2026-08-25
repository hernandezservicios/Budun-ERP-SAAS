from django.contrib import admin

from .models import (
    CreditNote,
    CreditNoteApplication,
    DocumentSequence,
    Payment,
    PaymentAllocation,
    ProformaInvoice,
    ProformaInvoiceItem,
    Quotation,
    QuotationItem,
    Refund,
    Reservation,
    Return,
    ReturnItem,
    Sale,
    SaleItem,
    SalesActivityLog,
    SalesDocumentAttachment,
)


class _ItemInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class QuotationItemInline(_ItemInline):
    model = QuotationItem
    fields = ("description", "sku_snapshot", "quantity", "unit_price", "discount_amount", "tax_amount", "total")


class ProformaInvoiceItemInline(_ItemInline):
    model = ProformaInvoiceItem
    fields = ("description", "sku_snapshot", "quantity", "unit_price", "discount_amount", "tax_amount", "total")


class SaleItemInline(_ItemInline):
    model = SaleItem
    fields = ("description", "sku_snapshot", "quantity", "unit_price", "discount_amount", "tax_amount", "total")


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    """Herramienta interna de staff, SOLO LECTURA: los documentos
    comerciales se crean/transicionan únicamente vía `services.py`
    (numeración, snapshot histórico, auditoría) — nunca a mano desde el
    admin."""

    list_display = ("number", "tenant", "customer", "status", "total", "issue_date")
    list_filter = ("tenant", "status")
    search_fields = ("number",)
    inlines = [QuotationItemInline]

    def get_queryset(self, request):
        return Quotation.all_objects.select_related("tenant", "customer")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProformaInvoice)
class ProformaInvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "tenant", "customer", "status", "total", "issue_date")
    list_filter = ("tenant", "status")
    search_fields = ("number",)
    inlines = [ProformaInvoiceItemInline]

    def get_queryset(self, request):
        return ProformaInvoice.all_objects.select_related("tenant", "customer")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("number", "tenant", "customer", "status", "payment_status", "total", "issue_date")
    list_filter = ("tenant", "status", "payment_status")
    search_fields = ("number",)
    inlines = [SaleItemInline]

    def get_queryset(self, request):
        return Sale.all_objects.select_related("tenant", "customer")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("customer", "tenant", "method", "amount", "status", "created_at")
    list_filter = ("tenant", "method", "status")

    def get_queryset(self, request):
        return Payment.all_objects.select_related("tenant", "customer")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ("payment", "sale", "tenant", "amount", "status", "created_at")
    list_filter = ("tenant", "status")

    def get_queryset(self, request):
        return PaymentAllocation.all_objects.select_related("tenant", "payment", "sale")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ("number", "tenant", "customer", "status", "source_type", "amount", "issue_date")
    list_filter = ("tenant", "status", "source_type")
    search_fields = ("number",)

    def get_queryset(self, request):
        return CreditNote.all_objects.select_related("tenant", "customer")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CreditNoteApplication)
class CreditNoteApplicationAdmin(admin.ModelAdmin):
    list_display = ("credit_note", "sale", "tenant", "amount", "status", "created_at")
    list_filter = ("tenant", "status")

    def get_queryset(self, request):
        return CreditNoteApplication.all_objects.select_related("tenant", "credit_note", "sale")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("payment", "tenant", "amount", "status", "created_at")
    list_filter = ("tenant", "status")

    def get_queryset(self, request):
        return Refund.all_objects.select_related("tenant", "payment")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("product", "tenant", "status", "quantity", "inventory_unit", "created_at")
    list_filter = ("tenant", "status", "source_type")

    def get_queryset(self, request):
        return Reservation.all_objects.select_related("tenant", "product", "customer", "inventory_unit")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ReturnItemInline(_ItemInline):
    model = ReturnItem
    fields = ("sale_item", "quantity_returned", "inventory_unit", "condition_notes")


@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ("number", "tenant", "sale", "created_at")
    list_filter = ("tenant",)
    search_fields = ("number",)
    inlines = [ReturnItemInline]

    def get_queryset(self, request):
        return Return.all_objects.select_related("tenant", "sale")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SalesDocumentAttachment)
class SalesDocumentAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "document_type", "document_id", "tenant", "category", "uploaded_at")
    list_filter = ("tenant", "document_type", "category")

    def get_queryset(self, request):
        return SalesDocumentAttachment.all_objects.select_related("tenant", "uploaded_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SalesActivityLog)
class SalesActivityLogAdmin(admin.ModelAdmin):
    list_display = ("action", "entity_type", "entity_label", "tenant", "user", "created_at")
    list_filter = ("tenant", "entity_type", "action")

    def get_queryset(self, request):
        return SalesActivityLog.all_objects.select_related("tenant", "user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ("tenant", "document_type", "prefix", "next_number")
    list_filter = ("document_type",)

    def get_queryset(self, request):
        return DocumentSequence.all_objects.select_related("tenant")
