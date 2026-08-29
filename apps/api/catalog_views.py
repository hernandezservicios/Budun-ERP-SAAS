"""
Catalog API (`/api/v1/catalog/`, ampliación final de FASE 15 — ver
`docs/api-catalog.md`). Capa COMERCIAL, conceptualmente independiente
de la Inventory API administrativa (`/api/v1/`, `apps.api.views`):
autenticada por `Integration` (nunca `ApiKey`), scopes propios
(`catalog:*`, nunca `inventory:*`/`products:*` de la otra capa).
TODOS los endpoints de solo lectura, reutilizando literalmente
`apps.inventory.services` — nunca una segunda fuente de disponibilidad.
`CatalogMediaFileView` es la única excepción sin autenticación: sirve
el archivo público de una imagen ya marcada como publicable por el
tenant, identificada por un UUID no adivinable."""

from django.http import FileResponse, Http404
from django.views import View
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.views import APIView

from apps.inventory import services as inv_services
from apps.inventory.models import Product, ProductImage

from .catalog_serializers import CatalogMediaSerializer, CatalogProductSerializer, CatalogVariantSerializer
from .integration_authentication import IntegrationCredentialAuthentication
from .pagination import ApiV1Pagination
from .permissions import HasCatalogScope
from .responses import build_success_response
from .throttling import CatalogRateThrottle


class _CatalogView(APIView):
    authentication_classes = [IntegrationCredentialAuthentication]
    permission_classes = [HasCatalogScope]
    throttle_classes = [CatalogRateThrottle]
    required_scope = "catalog:read"


class _CatalogListView(_CatalogView, generics.ListAPIView):
    pagination_class = ApiV1Pagination

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        pagina = self.paginate_queryset(queryset)
        serializer = self.get_serializer(
            pagina if pagina is not None else queryset, many=True, context=self._contexto_serializer(request),
        )
        meta = self.paginator.get_pagination_meta() if pagina is not None else {}
        return build_success_response(serializer.data, meta=meta)

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def _contexto_serializer(self, request):
        return {"request": request}


def _adjuntar_imagenes(productos):
    """Precarga las imágenes de cada producto en `_catalog_images` (una
    sola consulta, sin N+1) — usado por los serializers de catálogo."""
    productos = list(productos)
    if not productos:
        return productos
    ids = [p.pk for p in productos]
    imagenes_por_producto = {}
    for imagen in ProductImage.all_objects.filter(product_id__in=ids).order_by("-is_primary", "order", "id"):
        imagenes_por_producto.setdefault(imagen.product_id, []).append(imagen)
    for producto in productos:
        producto._catalog_images = imagenes_por_producto.get(producto.pk, [])
    return productos


class CatalogSearchView(_CatalogListView):
    """Búsqueda por nombre/SKU/barcode/marca/modelo (sección 4) —
    NUNCA por IMEI/serial. Un filtro `color`/`capacity`/`size`
    estructurado (`variant_attributes` es JSON, no texto libre)
    complementa la búsqueda de variante/color pedida en la
    especificación sin depender de un `icontains` no soportado de
    forma fiable sobre JSONField."""

    required_scope = "catalog:read"
    serializer_class = CatalogProductSerializer

    def get_queryset(self):
        parametros = self.request.query_params
        query = (parametros.get("q") or "").strip()
        queryset = inv_services.list_products_with_stock(self.request.tenant, search=query, only_active=True)
        if parametros.get("brand"):
            queryset = queryset.filter(brand__iexact=parametros["brand"])
        if parametros.get("model"):
            queryset = queryset.filter(model_name__iexact=parametros["model"])
        if parametros.get("color"):
            queryset = queryset.filter(variant_attributes__color__iexact=parametros["color"])
        if parametros.get("capacity"):
            queryset = queryset.filter(variant_attributes__capacity__iexact=parametros["capacity"])
        return queryset

    def list(self, request, *args, **kwargs):
        # FASE 19 (Performance): antes se llamaba `_adjuntar_imagenes`
        # sobre el queryset COMPLETO, antes de paginar — con miles de
        # productos coincidentes, esto cargaba y consultaba imágenes de
        # TODOS ellos aunque `page_size` solo devuelva 20 (medido: 2000
        # productos → ~540ms/~5MB pico, contra ~80ms/~140KB con 20 — el
        # costo escalaba con el total de coincidencias, nunca con lo
        # realmente devuelto — ver `docs/performance.md`). Corregido
        # paginando PRIMERO y adjuntando imágenes solo a la página.
        queryset = self.get_queryset()
        pagina = self.paginate_queryset(queryset)
        productos = _adjuntar_imagenes(pagina if pagina is not None else queryset)
        serializer = self.get_serializer(productos, many=True, context={"request": request})
        meta = self.paginator.get_pagination_meta() if pagina is not None else {}
        return build_success_response(serializer.data, meta=meta)


class CatalogProductListView(_CatalogListView):
    required_scope = "catalog:read"
    serializer_class = CatalogProductSerializer

    def get_queryset(self):
        return inv_services.list_products_with_stock(self.request.tenant, only_active=True)

    def list(self, request, *args, **kwargs):
        # FASE 19 (Performance): antes se llamaba `_adjuntar_imagenes`
        # sobre el queryset COMPLETO, antes de paginar — con miles de
        # productos coincidentes, esto cargaba y consultaba imágenes de
        # TODOS ellos aunque `page_size` solo devuelva 20 (medido: 2000
        # productos → ~540ms/~5MB pico, contra ~80ms/~140KB con 20 — el
        # costo escalaba con el total de coincidencias, nunca con lo
        # realmente devuelto — ver `docs/performance.md`). Corregido
        # paginando PRIMERO y adjuntando imágenes solo a la página.
        queryset = self.get_queryset()
        pagina = self.paginate_queryset(queryset)
        productos = _adjuntar_imagenes(pagina if pagina is not None else queryset)
        serializer = self.get_serializer(productos, many=True, context={"request": request})
        meta = self.paginator.get_pagination_meta() if pagina is not None else {}
        return build_success_response(serializer.data, meta=meta)


class CatalogProductDetailView(_CatalogView):
    required_scope = "catalog:read"

    def get(self, request, pk):
        try:
            producto = inv_services.list_products_with_stock(request.tenant, only_active=True).get(pk=pk)
        except Product.DoesNotExist:
            raise NotFound("Producto no encontrado.")
        grupo = list(inv_services.get_variant_availability(producto))
        # `get_variant_availability` vuelve a consultar la BD, así que la
        # fila del propio `producto` en `grupo` es una instancia DISTINTA
        # (mismo pk, objeto Python diferente) — se reemplaza por la
        # instancia real que se va a serializar para que
        # `_adjuntar_imagenes` le anote `_catalog_images` a ELLA, no a un
        # duplicado que nunca se serializa.
        grupo = [producto if p.pk == producto.pk else p for p in grupo]
        _adjuntar_imagenes(grupo)
        serializer = CatalogProductSerializer(producto, context={"request": request, "variant_group": grupo})
        return build_success_response(serializer.data)


class CatalogAvailabilityView(_CatalogListView):
    """Disponibilidad comercial agregada — mismo dato que `products/`
    (`current_stock` anotado), expuesto como endpoint dedicado y más
    liviano para integraciones que solo necesitan verificar stock."""

    required_scope = "catalog:availability:read"
    serializer_class = CatalogProductSerializer

    def get_queryset(self):
        parametros = self.request.query_params
        queryset = inv_services.list_products_with_stock(self.request.tenant, only_active=True)
        if parametros.get("product"):
            queryset = queryset.filter(pk=parametros["product"])
        return queryset


class CatalogVariantsView(_CatalogView):
    """Grupo de variantes de un producto (sección 8: "Samsung S25 256GB
    — Negro → 4 disponibles"). Requiere `?product=<id>`."""

    required_scope = "catalog:read"

    def get(self, request):
        product_id = request.query_params.get("product")
        if not product_id:
            raise ValidationError({"product": "Parámetro requerido."})
        try:
            producto = inv_services.list_products_with_stock(request.tenant, only_active=True).get(pk=product_id)
        except Product.DoesNotExist:
            raise NotFound("Producto no encontrado.")
        grupo = inv_services.get_variant_availability(producto)
        serializer = CatalogVariantSerializer(grupo, many=True, context={"request": request})
        return build_success_response(serializer.data)


class CatalogMediaListView(_CatalogView):
    """Metadatos de las imágenes de un producto (URL absoluta ya
    resuelta). Requiere `?product=<id>`. No confundir con
    `CatalogMediaFileView` (sirve los bytes reales, público, sin
    autenticación)."""

    required_scope = "catalog:media:read"

    def get(self, request):
        product_id = request.query_params.get("product")
        if not product_id:
            raise ValidationError({"product": "Parámetro requerido."})
        producto = Product.all_objects.filter(tenant=request.tenant, pk=product_id).first()
        if producto is None:
            raise NotFound("Producto no encontrado.")
        imagenes = inv_services.get_product_images(producto)
        serializer = CatalogMediaSerializer(imagenes, many=True, context={"request": request})
        return build_success_response(serializer.data)


class CatalogMediaFileView(View):
    """Sirve el archivo real de una imagen de catálogo — PÚBLICA, sin
    autenticación (un `<img src>` de un CRM externo no puede enviar un
    Bearer token). Identificada por `public_id` (UUID), nunca por el
    `id` secuencial del producto/imagen — no hay forma de enumerar
    imágenes de otro tenant adivinando la URL. Solo lectura: esta
    vista nunca acepta más que GET."""

    def get(self, request, public_id):
        imagen = ProductImage.all_objects.filter(public_id=public_id).first()
        if imagen is None or not imagen.image:
            raise Http404("Imagen no encontrada.")
        return FileResponse(imagen.image.open("rb"), content_type=imagen.content_type or "application/octet-stream")
