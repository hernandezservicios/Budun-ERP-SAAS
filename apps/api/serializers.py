"""
Serializers de solo lectura de `/api/v1/` — nunca exponen
`purchase_price`/`unit_cost` (información de costo/margen, financiera,
fuera de los scopes de esta fase) ni el IMEI/serie completo salvo que
un scope futuro explícito lo permita (no existe ese scope hoy, ver
`docs/api-inventory.md`)."""

from rest_framework import serializers

from apps.core.utils import mask_secret


class CategorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()


class ProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    barcode = serializers.CharField()
    name = serializers.CharField()
    category = serializers.SerializerMethodField()
    inventory_tracking_type = serializers.CharField()
    sale_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    is_active = serializers.BooleanField()
    current_stock = serializers.SerializerMethodField()
    min_stock = serializers.DecimalField(max_digits=12, decimal_places=3)

    def get_category(self, obj):
        return {"id": obj.category_id, "name": obj.category.name} if obj.category_id else None

    def get_current_stock(self, obj):
        valor = getattr(obj, "current_stock", None)
        return None if valor is None else str(valor)


class StockMovementSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    movement_type = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    stock_after = serializers.DecimalField(max_digits=12, decimal_places=3)
    notes = serializers.CharField()
    created_at = serializers.DateTimeField()


class InventoryUnitSerializer(serializers.Serializer):
    """Identificadores SIEMPRE enmascarados por defecto — no existe
    (todavía) un scope que permita verlos completos (ver
    `docs/api-inventory.md`, sección Scopes)."""

    id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    status = serializers.CharField()
    serial_masked = serializers.SerializerMethodField()
    imei_1_masked = serializers.SerializerMethodField()
    imei_2_masked = serializers.SerializerMethodField()
    entry_date = serializers.DateField()

    def get_serial_masked(self, obj):
        return mask_secret(obj.serial)

    def get_imei_1_masked(self, obj):
        return mask_secret(obj.imei_1)

    def get_imei_2_masked(self, obj):
        return mask_secret(obj.imei_2)


class ApiKeyStatusSerializer(serializers.Serializer):
    """Usado por `health/` para confirmar la clave sin exponer nada
    sensible — nunca el prefijo ni ningún fragmento del secreto."""

    tenant = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    status = serializers.CharField()
