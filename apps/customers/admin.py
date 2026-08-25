from django.contrib import admin

from .models import ActivityLog, Customer, CustomerDocument, Supplier, SupplierDocument


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("display_name", "tenant", "party_type", "email", "phone", "is_active")
    list_filter = ("tenant", "is_active", "party_type")
    search_fields = ("first_name", "last_name", "company_name", "trade_name", "identification_number", "email")

    def get_queryset(self, request):
        # Herramienta interna de staff: debe poder ver todos los tenants.
        return Customer.all_objects.select_related("tenant")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("display_name", "tenant", "party_type", "email", "phone", "is_active")
    list_filter = ("tenant", "is_active", "party_type")
    search_fields = ("legal_name", "trade_name", "identification_number", "email")

    def get_queryset(self, request):
        return Supplier.all_objects.select_related("tenant")


@admin.register(CustomerDocument)
class CustomerDocumentAdmin(admin.ModelAdmin):
    """Solo lectura: los documentos se crean/eliminan únicamente vía
    `services.py` (validación de archivo + auditoría), nunca a mano
    desde el admin."""

    list_display = ("original_filename", "customer", "tenant", "category", "uploaded_by", "uploaded_at")
    list_filter = ("tenant", "category")
    search_fields = ("original_filename", "customer__first_name", "customer__last_name", "customer__company_name")

    def get_queryset(self, request):
        return CustomerDocument.all_objects.select_related("tenant", "customer", "uploaded_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SupplierDocument)
class SupplierDocumentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "supplier", "tenant", "category", "uploaded_by", "uploaded_at")
    list_filter = ("tenant", "category")
    search_fields = ("original_filename", "supplier__legal_name", "supplier__trade_name")

    def get_queryset(self, request):
        return SupplierDocument.all_objects.select_related("tenant", "supplier", "uploaded_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Solo lectura: la bitácora se crea únicamente vía
    `services.log_activity`."""

    list_display = ("action", "entity_type", "entity_label", "tenant", "user", "created_at")
    list_filter = ("tenant", "entity_type", "action")
    search_fields = ("entity_label", "details")

    def get_queryset(self, request):
        return ActivityLog.all_objects.select_related("tenant", "user")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
