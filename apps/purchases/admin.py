"""Admin de solo lectura (oversight/depuración) — el Admin de Django
NUNCA es la UI principal de Compras (regla del proyecto, ver CLAUDE.md).
Mismo patrón que `apps.pos.admin`/`apps.sales.admin`."""

from django.contrib import admin

from .models import (
    PurchaseDocumentAttachment,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    PurchasesActivityLog,
    SupplierInvoice,
    SupplierInvoiceItem,
    SupplierPayment,
    SupplierPaymentAllocation,
    SupplierReturn,
    SupplierReturnItem,
)


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in PurchaseOrderItem._meta.fields]


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(_ReadOnlyAdmin):
    list_display = ("number", "supplier", "tenant", "status", "issue_date", "total")
    list_filter = ("tenant", "status")
    search_fields = ("number",)
    inlines = [PurchaseOrderItemInline]

    def get_queryset(self, request):
        return PurchaseOrder.all_objects.select_related("tenant", "supplier")


@admin.register(PurchaseReceipt)
class PurchaseReceiptAdmin(_ReadOnlyAdmin):
    list_display = ("number", "purchase_order", "tenant", "receipt_date", "user")
    list_filter = ("tenant",)
    search_fields = ("number",)

    def get_queryset(self, request):
        return PurchaseReceipt.all_objects.select_related("tenant", "purchase_order", "user")


@admin.register(PurchaseReceiptItem)
class PurchaseReceiptItemAdmin(_ReadOnlyAdmin):
    list_display = ("receipt", "purchase_order_item", "tenant", "quantity_received", "inventory_unit", "unit_cost")
    list_filter = ("tenant",)

    def get_queryset(self, request):
        return PurchaseReceiptItem.all_objects.select_related("tenant", "receipt", "purchase_order_item", "inventory_unit")


@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(_ReadOnlyAdmin):
    list_display = ("supplier_invoice_number", "supplier", "tenant", "status", "issue_date", "total")
    list_filter = ("tenant", "status")
    search_fields = ("supplier_invoice_number",)

    def get_queryset(self, request):
        return SupplierInvoice.all_objects.select_related("tenant", "supplier", "purchase_order")


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(_ReadOnlyAdmin):
    list_display = ("method", "supplier", "tenant", "amount", "status", "created_at")
    list_filter = ("tenant", "method", "status")

    def get_queryset(self, request):
        return SupplierPayment.all_objects.select_related("tenant", "supplier")


@admin.register(SupplierPaymentAllocation)
class SupplierPaymentAllocationAdmin(_ReadOnlyAdmin):
    list_display = ("payment", "supplier_invoice", "tenant", "amount", "status", "created_at")
    list_filter = ("tenant", "status")

    def get_queryset(self, request):
        return SupplierPaymentAllocation.all_objects.select_related("tenant", "payment", "supplier_invoice")


@admin.register(SupplierReturn)
class SupplierReturnAdmin(_ReadOnlyAdmin):
    list_display = ("number", "purchase_order", "tenant", "user", "created_at")
    list_filter = ("tenant",)
    search_fields = ("number",)

    def get_queryset(self, request):
        return SupplierReturn.all_objects.select_related("tenant", "purchase_order", "user")


@admin.register(PurchaseDocumentAttachment)
class PurchaseDocumentAttachmentAdmin(_ReadOnlyAdmin):
    list_display = ("original_filename", "document_type", "document_id", "tenant", "uploaded_at")
    list_filter = ("tenant", "document_type", "category")

    def get_queryset(self, request):
        return PurchaseDocumentAttachment.all_objects.select_related("tenant")


@admin.register(PurchasesActivityLog)
class PurchasesActivityLogAdmin(_ReadOnlyAdmin):
    list_display = ("action", "entity_type", "entity_id", "tenant", "user", "created_at")
    list_filter = ("tenant", "action", "entity_type")

    def get_queryset(self, request):
        return PurchasesActivityLog.all_objects.select_related("tenant", "user")
