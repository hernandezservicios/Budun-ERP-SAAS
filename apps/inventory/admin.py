from django.contrib import admin

from .models import Category, Product, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "order", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)

    def get_queryset(self, request):
        # Herramienta interna de staff: debe poder ver todos los tenants.
        return Category.all_objects.select_related("tenant")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "tenant", "category", "sale_price", "is_active")
    list_filter = ("tenant", "is_active", "category")
    search_fields = ("name", "sku", "barcode")

    def get_queryset(self, request):
        return Product.all_objects.select_related("tenant", "category")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "tenant", "movement_type", "quantity", "stock_after", "user", "created_at")
    list_filter = ("tenant", "movement_type")
    search_fields = ("product__name", "product__sku")

    def get_queryset(self, request):
        return StockMovement.all_objects.select_related("tenant", "product", "user")

    def has_add_permission(self, request):
        # Los movimientos solo se crean via services.py (transacciones +
        # bloqueo de fila); nunca a mano desde el admin.
        return False

    def has_change_permission(self, request, obj=None):
        return False
