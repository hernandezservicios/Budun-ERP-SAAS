from django.contrib import admin

from .models import Category, InventoryUnit, Product, StockMovement


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
    list_display = (
        "name",
        "sku",
        "tenant",
        "category",
        "inventory_tracking_type",
        "sale_price",
        "is_active",
    )
    list_filter = ("tenant", "is_active", "category", "inventory_tracking_type")
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


@admin.register(InventoryUnit)
class InventoryUnitAdmin(admin.ModelAdmin):
    """Herramienta interna de staff, solo lectura (igual que
    `StockMovementAdmin`): las unidades se crean/transicionan
    exclusivamente vía `services.py`. Los identificadores se muestran
    parcialmente enmascarados en el listado (defensa adicional: un
    vistazo a la lista de administración no debería bastar para copiar
    un IMEI/serie completo; la búsqueda exacta sigue funcionando)."""

    list_display = ("product", "tenant", "identificador_enmascarado", "status", "unit_cost", "entry_date")
    list_filter = ("tenant", "status")
    search_fields = ("product__name", "product__sku", "serial", "imei_1", "imei_2")

    def get_queryset(self, request):
        return InventoryUnit.all_objects.select_related("tenant", "product")

    @admin.display(description="Identificador")
    def identificador_enmascarado(self, obj):
        valor = obj.serial or obj.imei_1 or obj.imei_2 or ""
        if len(valor) <= 4:
            return valor
        return f"···{valor[-4:]}"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
