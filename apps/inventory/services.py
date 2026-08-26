"""
Capa de servicios de Inventario (FASE 8).

Esta es la ÚNICA vía sancionada para tocar el stock/disponibilidad de un
producto. Ninguna vista debe crear un `StockMovement`/`InventoryUnit`
directamente ni calcular el stock a mano: siempre a través de estas
funciones, que:

1. Bloquean la fila del producto (`select_for_update`) dentro de una
   transacción, para que dos operaciones concurrentes del mismo producto
   nunca se pisen entre sí (condición de carrera).
2. Calculan el stock/disponibilidad anterior a partir del historial real
   (nunca de un campo desnormalizado que se pudiera desincronizar).
3. Rechazan cualquier operación que dejaría el stock en negativo, que no
   tiene sentido, o que no corresponde al tipo de seguimiento del
   producto (`inventory_tracking_type`).

Regla de Multi-Tenancy: todas las funciones reciben `tenant` explícito (a
través del propio `product.tenant`) y solo operan sobre productos de ese
tenant — nunca se confía en un `product_id`/identificador sin verificar
antes que pertenece al tenant activo (eso lo hace la vista, ver
`views.py`).

Nota de diseño importante: aquí se usa deliberadamente `all_objects` (no
`objects`/`TenantManager`) en todas las consultas, filtrando SIEMPRE por
`tenant` de forma explícita. `TenantManager` depende de un `ContextVar`
que solo `TenantMiddleware` fija durante una request HTTP real; un
servicio debe funcionar igual de correcto si se llama desde un test
unitario, un comando de administración o una tarea en segundo plano,
donde ese ContextVar no está fijado. Esto NO es la misma situación que
"usar `all_objects` en una vista": aquí el filtro por tenant sigue siendo
explícito y obligatorio en cada consulta, solo que no depende del estado
ambiental de la request.

Seguridad: ningún mensaje de error ni log de este módulo incluye el
IMEI/serie completo de una unidad — solo el SKU del producto y el estado,
para no filtrar identificadores sensibles en logs o páginas de error
(ver `docs/inventory.md`).
"""

import dataclasses
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce

from .models import Category, InventoryUnit, Product, ProductImage, StockMovement


class InvalidInventoryOperation(ValidationError):
    """Se lanza cuando una operación de inventario no es válida (cantidad
    inválida, resultaría en stock negativo, ajuste sin cambios, tipo de
    seguimiento incorrecto, transición de estado no permitida, etc.)."""


# ------------------------------------------------------------------
# Stock / disponibilidad (unificado para ambos tipos de seguimiento)
# ------------------------------------------------------------------


def get_current_stock(product):
    """Stock/disponibilidad actual de un producto, sea cual sea su tipo
    de seguimiento:

    - QUANTITY: `stock_after` del `StockMovement` más reciente (o 0).
    - SERIALIZED: cantidad de `InventoryUnit` en estado EN_STOCK.

    Una sola función, un único punto de verdad para "cuánto hay" — nunca
    dos funciones que pudieran divergir entre sí.
    """
    if product.inventory_tracking_type == Product.TrackingType.SERIALIZED:
        return get_available_units_count(product)

    ultimo = (
        StockMovement.all_objects.filter(product=product)
        .order_by("-created_at", "-id")
        .values_list("stock_after", flat=True)
        .first()
    )
    return ultimo if ultimo is not None else Decimal("0")


def _current_stock_subquery():
    """Subquery reutilizable para anotar el stock/disponibilidad actual
    de cada producto en un queryset, en una sola consulta (evita N+1 al
    listar), cubriendo ambos tipos de seguimiento con un `Case/When`."""
    ultimo_movimiento = StockMovement.all_objects.filter(product=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )
    unidades_en_stock = (
        InventoryUnit.all_objects.filter(product=OuterRef("pk"), status=InventoryUnit.Status.EN_STOCK)
        .values("product")
        .annotate(total=Count("id"))
        .values("total")
    )

    return Case(
        When(
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
            then=Coalesce(
                Subquery(unidades_en_stock[:1], output_field=DecimalField(max_digits=12, decimal_places=3)),
                Value(Decimal("0")),
            ),
        ),
        default=Coalesce(
            Subquery(ultimo_movimiento.values("stock_after")[:1]),
            Value(Decimal("0")),
        ),
        output_field=DecimalField(max_digits=12, decimal_places=3),
    )


def list_products_with_stock(
    tenant, *, search="", category_id=None, only_active=True, only_low_stock=False
):
    """Queryset de productos del tenant, con el stock/disponibilidad
    actual anotado en una sola consulta (`select_related` para la
    categoría, subquery para el stock — sin N+1). Funciona igual para
    productos por cantidad y serializados."""
    queryset = (
        Product.all_objects.filter(tenant=tenant)
        .select_related("category")
        .annotate(current_stock=_current_stock_subquery())
    )

    if only_active:
        queryset = queryset.filter(is_active=True)
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(sku__icontains=search) | Q(barcode__icontains=search)
        )
    if category_id:
        queryset = queryset.filter(category_id=category_id)
    if only_low_stock:
        queryset = queryset.filter(current_stock__lte=F("min_stock"))

    return queryset


def get_low_stock_products(tenant):
    """Productos activos cuyo stock/disponibilidad actual está en o por
    debajo de su stock mínimo configurado (ambos tipos de seguimiento)."""
    return list_products_with_stock(tenant, only_active=True, only_low_stock=True)


def get_active_categories(tenant):
    return Category.all_objects.filter(tenant=tenant, is_active=True).order_by("order", "name")


# ------------------------------------------------------------------
# Productos por CANTIDAD — StockMovement
# ------------------------------------------------------------------


def get_product_movements(product, limit=None):
    """Historial de movimientos de un producto por cantidad, más
    reciente primero."""
    queryset = (
        StockMovement.all_objects.filter(product=product)
        .select_related("user")
        .order_by("-created_at", "-id")
    )
    return queryset[:limit] if limit else queryset


def _require_quantity_tracking(product):
    if product.inventory_tracking_type != Product.TrackingType.QUANTITY:
        raise InvalidInventoryOperation(
            f"«{product.sku}» es un producto serializado: usa unidades individuales "
            "(IMEI/serie), no movimientos de cantidad."
        )


@transaction.atomic
def register_stock_in(*, product, quantity, user, notes="", unit_cost=None):
    _require_quantity_tracking(product)
    return _register_movement(
        product=product,
        quantity=quantity,
        movement_type=StockMovement.MovementType.IN,
        user=user,
        notes=notes,
        sign=1,
        unit_cost=unit_cost,
    )


@transaction.atomic
def register_stock_out(*, product, quantity, user, notes=""):
    _require_quantity_tracking(product)
    return _register_movement(
        product=product,
        quantity=quantity,
        movement_type=StockMovement.MovementType.OUT,
        user=user,
        notes=notes,
        sign=-1,
    )


@transaction.atomic
def register_stock_adjustment(*, product, new_stock, user, notes=""):
    """Ajuste: fija el stock a un valor exacto (p. ej. tras un conteo
    físico), en vez de sumar/restar una cantidad. El costo promedio
    ponderado se arrastra sin cambio — un conteo físico no trae consigo
    un costo confiable, nunca se fabrica uno (ver docs/accounting.md)."""
    _require_quantity_tracking(product)
    if new_stock < 0:
        raise InvalidInventoryOperation("El stock ajustado no puede ser negativo.")

    locked_product = Product.all_objects.select_for_update().get(pk=product.pk, tenant=product.tenant)
    stock_before = get_current_stock(locked_product)

    if new_stock == stock_before:
        raise InvalidInventoryOperation(
            "El stock ajustado es igual al actual; no hay ningún cambio que registrar."
        )

    promedio_actual = get_current_average_cost(locked_product)
    return StockMovement.all_objects.create(
        tenant=locked_product.tenant,
        product=locked_product,
        movement_type=StockMovement.MovementType.ADJUSTMENT,
        quantity=abs(new_stock - stock_before),
        stock_before=stock_before,
        stock_after=new_stock,
        unit_cost=None,
        average_cost_after=promedio_actual,
        user=user,
        notes=notes,
    )


def _register_movement(*, product, quantity, movement_type, user, notes, sign, unit_cost=None):
    if quantity is None or quantity <= 0:
        raise InvalidInventoryOperation("La cantidad debe ser mayor que cero.")

    # SELECT ... FOR UPDATE: bloquea la fila mientras dura la transacción,
    # para que dos movimientos concurrentes del mismo producto no lean el
    # mismo "stock anterior" y produzcan un resultado incorrecto.
    locked_product = Product.all_objects.select_for_update().get(pk=product.pk, tenant=product.tenant)
    stock_before = get_current_stock(locked_product)
    stock_after = stock_before + (sign * quantity)

    if stock_after < 0:
        raise InvalidInventoryOperation(
            f"La salida dejaría el stock en negativo (actual: {stock_before}, solicitado: {quantity})."
        )

    # Costeo por promedio ponderado (ampliación de cierre de FASE 14).
    # Ver docs/accounting.md para la política completa.
    promedio_anterior = get_current_average_cost(locked_product)
    if movement_type == StockMovement.MovementType.IN:
        if unit_cost is not None:
            # Se recalcula sumando el costo total de lo que ya había más
            # el costo del lote entrante, dividido entre el stock
            # resultante -- la definición estándar de promedio ponderado.
            costo_movimiento = unit_cost
            promedio_nuevo = (stock_before * promedio_anterior + quantity * unit_cost) / stock_after
        else:
            # Entrada sin costo conocido (p. ej. un alta manual sin
            # información de compra): el promedio no cambia, nunca se
            # fabrica un costo que nadie proporcionó.
            costo_movimiento = None
            promedio_nuevo = promedio_anterior
    else:
        # Salida: el costo consumido es el promedio vigente en este
        # instante (base real del COGS, ver apps.sales.services.confirm_sale)
        # -- retirar unidades a su propio costo promedio nunca cambia el
        # promedio de las unidades que quedan.
        costo_movimiento = promedio_anterior
        promedio_nuevo = promedio_anterior

    return StockMovement.all_objects.create(
        tenant=locked_product.tenant,
        product=locked_product,
        movement_type=movement_type,
        quantity=quantity,
        stock_before=stock_before,
        stock_after=stock_after,
        unit_cost=costo_movimiento,
        average_cost_after=promedio_nuevo,
        user=user,
        notes=notes,
    )


def get_current_average_cost(product):
    """Costo promedio ponderado ACTUAL de un producto por CANTIDAD —
    mismo patrón que `get_current_stock`: se lee del `average_cost_after`
    del `StockMovement` más reciente, nunca un campo desnormalizado en
    `Product`. Para SERIALIZED, o un producto sin ningún movimiento
    (o solo movimientos históricos sin costo), devuelve 0 — SERIALIZED
    tiene su propio costo específico por unidad
    (`InventoryUnit.unit_cost`)."""
    if product.inventory_tracking_type == Product.TrackingType.SERIALIZED:
        return Decimal("0")
    ultimo = (
        StockMovement.all_objects.filter(product=product)
        .order_by("-created_at", "-id")
        .values_list("average_cost_after", flat=True)
        .first()
    )
    return ultimo if ultimo is not None else Decimal("0")


def get_inventory_valuation(tenant):
    """Valor total de inventario del tenant — nunca una tercera fuente de
    verdad: se apoya exactamente en `get_current_stock`/
    `get_current_average_cost` (QUANTITY) e `InventoryUnit.unit_cost`
    (SERIALIZED), ya establecidos. Usado por el reporte de Inventario
    (FASE 14) y por la reconciliación contable
    (`apps.accounting.services.get_inventory_gl_reconciliation`)."""
    productos = list_products_with_stock(tenant, only_active=False)
    filas = []
    total = Decimal("0")
    for producto in productos:
        if not producto.current_stock:
            continue
        if producto.inventory_tracking_type == Product.TrackingType.SERIALIZED:
            costo_promedio = None
            valor = InventoryUnit.all_objects.filter(
                tenant=tenant, product=producto, status=InventoryUnit.Status.EN_STOCK,
            ).aggregate(total=Sum("unit_cost"))["total"] or Decimal("0")
        else:
            costo_promedio = get_current_average_cost(producto)
            valor = producto.current_stock * costo_promedio
        filas.append({
            "product": producto, "stock": producto.current_stock,
            "average_cost": costo_promedio, "value": valor,
        })
        total += valor
    return {"rows": filas, "total_value": total}


# ------------------------------------------------------------------
# Productos SERIALIZADOS — InventoryUnit
# ------------------------------------------------------------------

#: Máquina de estados de una unidad individual. Cada clave es un estado
#: de origen; el valor, el conjunto de estados a los que puede pasar.
#: Cualquier transición fuera de este mapa se rechaza explícitamente.
ALLOWED_UNIT_TRANSITIONS = {
    InventoryUnit.Status.EN_STOCK: {
        InventoryUnit.Status.RESERVADO,
        InventoryUnit.Status.VENDIDO,
        InventoryUnit.Status.REPARACION,
        InventoryUnit.Status.DANADO,
        InventoryUnit.Status.PERDIDO,
        # FASE 12 (Compras): devolver una unidad EN_STOCK al proveedor.
        InventoryUnit.Status.DEVUELTO_PROVEEDOR,
    },
    InventoryUnit.Status.RESERVADO: {
        InventoryUnit.Status.EN_STOCK,  # se cancela la reserva
        InventoryUnit.Status.VENDIDO,
    },
    InventoryUnit.Status.VENDIDO: {
        InventoryUnit.Status.DEVUELTO,
    },
    InventoryUnit.Status.DEVUELTO: {
        InventoryUnit.Status.EN_STOCK,
        InventoryUnit.Status.REPARACION,
        InventoryUnit.Status.DANADO,
    },
    InventoryUnit.Status.REPARACION: {
        InventoryUnit.Status.EN_STOCK,
        InventoryUnit.Status.GARANTIA,
        InventoryUnit.Status.DANADO,
    },
    InventoryUnit.Status.GARANTIA: {
        InventoryUnit.Status.EN_STOCK,
        InventoryUnit.Status.REPARACION,
        InventoryUnit.Status.DANADO,
    },
    InventoryUnit.Status.DANADO: {
        InventoryUnit.Status.REPARACION,
        InventoryUnit.Status.PERDIDO,
    },
    InventoryUnit.Status.PERDIDO: set(),  # estado terminal: sin salida
    InventoryUnit.Status.DEVUELTO_PROVEEDOR: set(),  # estado terminal: sin salida
}


def get_available_units_count(product):
    return InventoryUnit.all_objects.filter(
        product=product, status=InventoryUnit.Status.EN_STOCK
    ).count()


def list_units_for_product(product, status=None):
    """Unidades individuales de un producto, opcionalmente filtradas por
    estado. Más reciente primero."""
    queryset = InventoryUnit.all_objects.filter(product=product).select_related("status_changed_by")
    if status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("-created_at", "-id")


def _require_serialized_tracking(product):
    if product.inventory_tracking_type != Product.TrackingType.SERIALIZED:
        raise InvalidInventoryOperation(
            f"«{product.sku}» es un producto por cantidad: usa movimientos de stock "
            "(entrada/salida/ajuste), no unidades individuales."
        )


@transaction.atomic
def register_serialized_unit(
    *,
    product,
    user,
    serial="",
    imei_1="",
    imei_2="",
    unit_cost=Decimal("0"),
    entry_date=None,
    purchase_origin="",
    notes="",
):
    """Da de alta una unidad individual nueva (equivalente a una "entrada
    de stock" para un producto serializado). Sin `StockMovement`: la
    unidad misma, en estado EN_STOCK, es el registro."""
    _require_serialized_tracking(product)

    serial = (serial or "").strip()
    imei_1 = (imei_1 or "").strip()
    imei_2 = (imei_2 or "").strip()

    if not (serial or imei_1 or imei_2):
        raise InvalidInventoryOperation(
            "Debes indicar al menos un identificador: número de serie, IMEI 1 o IMEI 2."
        )
    if imei_1 and imei_2 and imei_1 == imei_2:
        raise InvalidInventoryOperation("IMEI 1 e IMEI 2 no pueden ser iguales.")

    kwargs = dict(
        tenant=product.tenant,
        product=product,
        serial=serial,
        imei_1=imei_1,
        imei_2=imei_2,
        unit_cost=unit_cost,
        purchase_origin=purchase_origin,
        notes=notes,
        status=InventoryUnit.Status.EN_STOCK,
        status_changed_by=user,
    )
    if entry_date is not None:
        kwargs["entry_date"] = entry_date

    return InventoryUnit.all_objects.create(**kwargs)


@transaction.atomic
def transition_unit_status(*, unit, new_status, user, notes=""):
    """Cambia el estado de una unidad, validando la máquina de estados
    (ver `ALLOWED_UNIT_TRANSITIONS`). Nunca expone el IMEI/serie completo
    en el mensaje de error — solo el SKU del producto y los estados."""
    locked_unit = InventoryUnit.all_objects.select_for_update().get(
        pk=unit.pk, tenant=unit.tenant
    )
    permitidos = ALLOWED_UNIT_TRANSITIONS.get(locked_unit.status, set())
    if new_status not in permitidos:
        raise InvalidInventoryOperation(
            f"No se puede pasar la unidad de «{locked_unit.product.sku}» de "
            f"{locked_unit.get_status_display()} a {InventoryUnit.Status(new_status).label}."
        )

    locked_unit.status = new_status
    locked_unit.status_changed_by = user
    if notes:
        locked_unit.notes = notes
    locked_unit.save(update_fields=["status", "status_changed_by", "notes", "updated_at"])
    return locked_unit


def ensure_unit_available_for_sale(unit):
    """Regla de negocio reutilizable para FASE 10 (Ventas) y FASE 11
    (POS): una unidad solo puede venderse si está EN_STOCK. Rechaza
    explícitamente vender una unidad inexistente (el llamador debe
    resolverla primero, ver `search_catalog`), ya vendida, reservada por
    otra operación, en reparación, dañada o perdida."""
    if unit.status != InventoryUnit.Status.EN_STOCK:
        raise InvalidInventoryOperation(
            f"La unidad de «{unit.product.sku}» no está disponible para venta "
            f"(estado actual: {unit.get_status_display()})."
        )


# ------------------------------------------------------------------
# Búsqueda unificada (nombre, SKU, código de barras/QR, IMEI, serie)
# ------------------------------------------------------------------


@dataclasses.dataclass
class SearchResult:
    """Resultado de `search_catalog`. `unit` solo se establece cuando la
    coincidencia fue por identificador de una unidad individual exacta
    (IMEI/serie): en ese caso el resultado ya representa la unidad
    concreta a vender, no solo la familia de producto."""

    product: object
    unit: object = None

    @property
    def requires_unit_selection(self):
        """True si el resultado es un producto SERIALIZADO encontrado
        por nombre/SKU/código de barras (no por IMEI/serie exacto): el
        llamador (POS, FASE 11) debe pedir a continuación el IMEI/serie
        concreto antes de poder agregarlo al carrito."""
        return (
            self.unit is None
            and self.product.inventory_tracking_type == self.product.TrackingType.SERIALIZED
        )


def search_catalog(tenant, query):
    """Búsqueda única reutilizable por FASE 10/11/15: nombre, SKU, código
    de barras (un QR escaneado normalmente solo codifica uno de estos
    valores como texto, así que no hace falta un campo "QR" aparte),
    número de serie o IMEI.

    Prioridad: una coincidencia EXACTA de serie/IMEI identifica una única
    unidad física real y se devuelve sola (no tiene sentido mezclarla con
    resultados de texto libre). Si no hay coincidencia de unidad, se
    buscan productos por nombre/SKU/código de barras.

    Nunca se filtra por un tenant que no sea el explícitamente indicado
    — ver regla de Multi-Tenancy al inicio de este archivo.
    """
    query = (query or "").strip()
    if not query:
        return []

    unidad = (
        InventoryUnit.all_objects.filter(tenant=tenant)
        .filter(Q(serial=query) | Q(imei_1=query) | Q(imei_2=query))
        .select_related("product")
        .first()
    )
    if unidad:
        return [SearchResult(product=unidad.product, unit=unidad)]

    productos = (
        Product.all_objects.filter(tenant=tenant, is_active=True)
        .filter(Q(name__icontains=query) | Q(sku__iexact=query) | Q(barcode=query))
        .order_by("name")
    )
    return [SearchResult(product=producto) for producto in productos]


# ------------------------------------------------------------------
# Imágenes de producto y agrupación de variantes (ampliación final de
# FASE 15, Catalog API — ver docs/api-catalog.md). Nunca una segunda
# fuente de verdad de disponibilidad: la agrupación de variantes solo
# junta productos ya existentes por `brand`+`model_name`, la
# disponibilidad de cada uno sigue viniendo de `get_current_stock`.
# ------------------------------------------------------------------

_EXTENSIONES_IMAGEN_PERMITIDAS = {".png", ".jpg", ".jpeg"}


def register_product_image(*, product, archivo, user, is_primary=False):
    """Valida (extensión + firma binaria + tamaño) y guarda una imagen
    comercial de un producto. Reutiliza la MISMA validación de archivos
    ya usada para documentos de Clientes/Proveedores (import diferido:
    `apps.inventory`, FASE 8, es anterior a `apps.customers`, FASE 9, en
    la cadena de dependencias del proyecto — nunca un import a nivel de
    módulo en sentido contrario)."""
    from apps.customers.file_validation import nombre_original_seguro, validar_archivo_adjunto

    extension, content_type = validar_archivo_adjunto(archivo)
    if extension not in _EXTENSIONES_IMAGEN_PERMITIDAS:
        raise InvalidInventoryOperation("Solo se permiten imágenes PNG o JPG para el catálogo.")

    if is_primary:
        ProductImage.all_objects.filter(tenant=product.tenant, product=product).update(is_primary=False)
    elif not ProductImage.all_objects.filter(tenant=product.tenant, product=product).exists():
        is_primary = True  # la primera imagen de un producto es principal por defecto.

    return ProductImage.all_objects.create(
        tenant=product.tenant, product=product, image=archivo, is_primary=is_primary,
        original_filename=nombre_original_seguro(archivo.name), content_type=content_type,
        size_bytes=archivo.size, uploaded_by=user,
    )


def set_primary_product_image(imagen):
    ProductImage.all_objects.filter(tenant=imagen.tenant, product_id=imagen.product_id).update(is_primary=False)
    imagen.is_primary = True
    imagen.save(update_fields=["is_primary"])
    return imagen


def delete_product_image(imagen):
    # El archivo físico se borra vía la señal `post_delete` (ver
    # models.py) — mismo patrón que `CustomerDocument`.
    imagen.delete()


def get_product_images(product):
    return ProductImage.all_objects.filter(tenant=product.tenant, product=product).order_by("-is_primary", "order", "id")


def get_variant_group(product):
    """Productos "variantes entre sí" de `product`: mismo tenant,
    `brand`+`model_name` no vacíos e iguales — incluye al propio
    `product`. Un producto sin marca/modelo no tiene grupo (devuelve
    solo sí mismo)."""
    if not product.brand or not product.model_name:
        return Product.all_objects.filter(pk=product.pk)
    return Product.all_objects.filter(
        tenant=product.tenant, brand=product.brand, model_name=product.model_name, is_active=True,
    ).order_by("name")


def get_variant_availability(product):
    """El grupo de variantes de `product`, con `current_stock` anotado
    en una sola consulta (reutiliza `list_products_with_stock` — nunca
    una segunda fuente de disponibilidad)."""
    grupo_pks = list(get_variant_group(product).values_list("pk", flat=True))
    return list_products_with_stock(product.tenant, only_active=True).filter(pk__in=grupo_pks)
