"""
Serializers de la Catalog API (`/api/v1/catalog/`, ampliación final de
FASE 15 — ver `docs/api-catalog.md`). Whitelist EXPLÍCITA server-side:
solo los campos declarados aquí pueden llegar a la respuesta — nunca
el modelo Django crudo. Deliberadamente EXCLUIDOS de cualquier
serializer de este archivo (ver `docs/api-catalog.md` sección de
campos prohibidos, verificado con tests dedicados):
IMEI/IMEI_1/IMEI_2/serial/serial_number, unit_cost/purchase_cost/cost/
margin, supplier/supplier_id, stock_movements, customer/
customer_private_data, payments, cash, accounting, payroll,
hr_sensitive_data."""

from rest_framework import serializers

from . import catalog_urls_helpers


class CatalogMediaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    url = serializers.SerializerMethodField()
    is_primary = serializers.BooleanField()
    order = serializers.IntegerField()

    def get_url(self, obj):
        return catalog_urls_helpers.build_media_url(self.context.get("request"), obj)


class CatalogVariantSerializer(serializers.Serializer):
    """Una fila del grupo de variantes (sección 8 de la especificación:
    "Samsung S25 256GB — Negro → 4 disponibles")."""

    id = serializers.IntegerField()
    sku = serializers.CharField()
    variant_attributes = serializers.DictField()
    price = serializers.DecimalField(source="sale_price", max_digits=12, decimal_places=2)
    available = serializers.SerializerMethodField()
    available_quantity = serializers.SerializerMethodField()

    def get_available(self, obj):
        return _disponible(obj)

    def get_available_quantity(self, obj):
        return _cantidad_disponible(obj)


def _cantidad_disponible(producto):
    valor = getattr(producto, "current_stock", None)
    return None if valor is None else str(valor)


def _disponible(producto):
    valor = getattr(producto, "current_stock", None)
    return bool(valor) and valor > 0


class CatalogProductSerializer(serializers.Serializer):
    """Salida comercial de un producto — whitelist explícita, nunca el
    modelo Django crudo. `available_quantity` viene de la MISMA
    fuente de verdad que la API administrativa (`current_stock`
    anotado por `apps.inventory.services.list_products_with_stock`),
    nunca un contador paralelo."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    brand = serializers.CharField()
    model = serializers.CharField(source="model_name")
    sku = serializers.CharField()
    description = serializers.CharField()
    variants = serializers.SerializerMethodField()
    colors = serializers.SerializerMethodField()
    capacity = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    price = serializers.DecimalField(source="sale_price", max_digits=12, decimal_places=2)
    currency = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()
    available_quantity = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    def get_currency(self, obj):
        # `CurrencyConfiguration` (moneda funcional por tenant) es
        # todavía especificación, no está construida (ver
        # docs/currency.md) — "USD" es el mismo default ya usado en
        # todo el proyecto donde no existe una moneda real configurada
        # (`Sale.currency`/`Customer.currency`), nunca inventado aquí.
        return "USD"

    def get_available(self, obj):
        return _disponible(obj)

    def get_available_quantity(self, obj):
        return _cantidad_disponible(obj)

    def get_variants(self, obj):
        grupo = self.context.get("variant_group")
        if grupo is None:
            return []
        return CatalogVariantSerializer(
            [p for p in grupo if p.pk != obj.pk], many=True, context=self.context,
        ).data

    def get_colors(self, obj):
        return (obj.variant_attributes or {}).get("color")

    def get_capacity(self, obj):
        return (obj.variant_attributes or {}).get("capacity")

    def get_size(self, obj):
        return (obj.variant_attributes or {}).get("size")

    def get_primary_image(self, obj):
        imagen = next((img for img in getattr(obj, "_catalog_images", []) if img.is_primary), None)
        if imagen is None and getattr(obj, "_catalog_images", None):
            imagen = obj._catalog_images[0]
        if imagen is None:
            return None
        return catalog_urls_helpers.build_media_url(self.context.get("request"), imagen)

    def get_images(self, obj):
        imagenes = getattr(obj, "_catalog_images", [])
        return [catalog_urls_helpers.build_media_url(self.context.get("request"), img) for img in imagenes]
