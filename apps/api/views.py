"""
Endpoints de `/api/v1/` (FASE 15, ver `docs/api-inventory.md`).
TODOS de solo lectura (GET únicamente — ningún POST/PUT/DELETE en
ningún endpoint de esta fase). Reutilizan literalmente
`apps.inventory.services` — nunca reimplementan esas consultas aquí.
El tenant SIEMPRE viene de `request.tenant` (resuelto por
`ApiKeyAuthentication` desde la clave, nunca de un parámetro de la
URL/query string)."""

from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.views import APIView

from apps.inventory import services as inv_services
from apps.inventory.models import Category, InventoryUnit, Product, StockMovement

from .authentication import ApiKeyAuthentication
from .pagination import ApiV1Pagination
from .permissions import HasScope
from .responses import build_success_response
from .serializers import (
    ApiKeyStatusSerializer,
    CategorySerializer,
    InventoryUnitSerializer,
    ProductSerializer,
    StockMovementSerializer,
)


class _ApiV1View(APIView):
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasScope]
    required_scope = None


class _ApiV1ListView(_ApiV1View, generics.ListAPIView):
    pagination_class = ApiV1Pagination

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        pagina = self.paginate_queryset(queryset)
        serializer = self.get_serializer(pagina if pagina is not None else queryset, many=True)
        meta = self.paginator.get_pagination_meta() if pagina is not None else {}
        return build_success_response(serializer.data, meta=meta)

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class HealthView(_ApiV1View):
    required_scope = "health:read"

    def get(self, request):
        serializer = ApiKeyStatusSerializer({
            "tenant": request.tenant.name, "scopes": request.api_key.scopes, "status": request.api_key.status,
        })
        return build_success_response(serializer.data)


class ProductListView(_ApiV1ListView):
    required_scope = "products:read"
    serializer_class = ProductSerializer

    def get_queryset(self):
        parametros = self.request.query_params
        queryset = inv_services.list_products_with_stock(
            self.request.tenant, search=parametros.get("search", ""), category_id=parametros.get("category") or None,
            only_active=parametros.get("only_active", "1") != "0", only_low_stock=parametros.get("low_stock") == "1",
        )
        if parametros.get("sku"):
            queryset = queryset.filter(sku=parametros["sku"])
        if parametros.get("barcode"):
            queryset = queryset.filter(barcode=parametros["barcode"])
        if parametros.get("tracking_type"):
            queryset = queryset.filter(inventory_tracking_type=parametros["tracking_type"])
        actualizado_desde = parse_datetime(parametros.get("updated_since", "") or "")
        if actualizado_desde:
            queryset = queryset.filter(updated_at__gte=actualizado_desde)
        return queryset


class ProductDetailView(_ApiV1View):
    required_scope = "products:read"

    def get(self, request, pk):
        try:
            producto = inv_services.list_products_with_stock(request.tenant, only_active=False).get(pk=pk)
        except Product.DoesNotExist:
            raise NotFound("Producto no encontrado.")
        return build_success_response(ProductSerializer(producto).data)


class CategoryListView(_ApiV1ListView):
    required_scope = "categories:read"
    serializer_class = CategorySerializer

    def get_queryset(self):
        return Category.all_objects.filter(tenant=self.request.tenant).order_by("order", "name")


class InventoryListView(_ApiV1ListView):
    """Igual que `products/`, pero es el endpoint documentado para
    "estado del inventario" (mismo dato — `current_stock` anotado —,
    nombre distinto porque el CRM/agente IA lo consume con otra
    intención: disponibilidad, no catálogo)."""

    required_scope = "inventory:read"
    serializer_class = ProductSerializer

    def get_queryset(self):
        return inv_services.list_products_with_stock(self.request.tenant, only_active=True)


class InventoryLowStockView(_ApiV1ListView):
    required_scope = "inventory:read"
    serializer_class = ProductSerializer

    def get_queryset(self):
        return inv_services.get_low_stock_products(self.request.tenant)


class InventoryMovementsView(_ApiV1ListView):
    required_scope = "inventory_movements:read"
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        queryset = StockMovement.all_objects.filter(tenant=self.request.tenant).order_by("-created_at", "-id")
        parametros = self.request.query_params
        if parametros.get("product"):
            queryset = queryset.filter(product_id=parametros["product"])
        actualizado_desde = parse_datetime(parametros.get("updated_since", "") or "")
        if actualizado_desde:
            queryset = queryset.filter(created_at__gte=actualizado_desde)
        return queryset


class InventorySerializedView(_ApiV1ListView):
    required_scope = "serialized_inventory:read"
    serializer_class = InventoryUnitSerializer

    def get_queryset(self):
        queryset = InventoryUnit.all_objects.filter(tenant=self.request.tenant).order_by("-created_at", "-id")
        parametros = self.request.query_params
        if parametros.get("product"):
            queryset = queryset.filter(product_id=parametros["product"])
        if parametros.get("state"):
            queryset = queryset.filter(status=parametros["state"])
        if parametros.get("serial"):
            queryset = queryset.filter(serial=parametros["serial"])
        if parametros.get("imei"):
            queryset = queryset.filter(Q(imei_1=parametros["imei"]) | Q(imei_2=parametros["imei"]))
        return queryset
