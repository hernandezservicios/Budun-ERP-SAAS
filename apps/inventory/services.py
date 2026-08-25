"""
Capa de servicios de Inventario (FASE 8).

Esta es la ÚNICA vía sancionada para crear movimientos de stock. Ninguna
vista debe crear un `StockMovement` directamente ni calcular el stock a
mano: siempre a través de estas funciones, que:

1. Bloquean la fila del producto (`select_for_update`) dentro de una
   transacción, para que dos movimientos concurrentes del mismo producto
   nunca se pisen entre sí (condición de carrera).
2. Calculan el stock anterior a partir del último movimiento real (nunca
   de un campo desnormalizado que se pudiera desincronizar).
3. Rechazan cualquier operación que dejaría el stock en negativo o que
   no tiene sentido (cantidad <= 0, ajuste igual al valor actual).

Regla de Multi-Tenancy: todas las funciones reciben `tenant` explícito (a
través del propio `product.tenant`) y solo operan sobre productos de ese
tenant — nunca se confía en un `product_id` sin verificar antes que
pertenece al tenant activo (eso lo hace la vista, ver `views.py`).

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
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce

from .models import Category, Product, StockMovement


class InvalidInventoryOperation(ValidationError):
    """Se lanza cuando una operación de inventario no es válida (cantidad
    inválida, resultaría en stock negativo, ajuste sin cambios, etc.)."""


def get_current_stock(product):
    """Stock actual de un producto: el `stock_after` de su movimiento más
    reciente, o 0 si nunca tuvo ninguno. Nunca un campo desnormalizado."""
    ultimo = (
        StockMovement.all_objects.filter(product=product)
        .order_by("-created_at", "-id")
        .values_list("stock_after", flat=True)
        .first()
    )
    return ultimo if ultimo is not None else Decimal("0")


def _current_stock_subquery():
    """Subquery reutilizable para anotar el stock actual de cada producto
    en un queryset, en una sola consulta (evita N+1 al listar)."""
    ultimo_movimiento = StockMovement.all_objects.filter(product=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )
    return Coalesce(
        Subquery(ultimo_movimiento.values("stock_after")[:1]),
        Value(Decimal("0")),
        output_field=DecimalField(max_digits=12, decimal_places=3),
    )


def list_products_with_stock(
    tenant, *, search="", category_id=None, only_active=True, only_low_stock=False
):
    """Queryset de productos del tenant, con el stock actual anotado en
    una sola consulta (`select_related` para la categoría, subquery para
    el stock — sin N+1)."""
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
    """Productos activos cuyo stock actual está en o por debajo de su
    stock mínimo configurado."""
    return list_products_with_stock(tenant, only_active=True, only_low_stock=True)


def get_active_categories(tenant):
    return Category.all_objects.filter(tenant=tenant, is_active=True).order_by("order", "name")


def get_product_movements(product, limit=None):
    """Historial de movimientos de un producto, más reciente primero."""
    queryset = (
        StockMovement.all_objects.filter(product=product)
        .select_related("user")
        .order_by("-created_at", "-id")
    )
    return queryset[:limit] if limit else queryset


@transaction.atomic
def register_stock_in(*, product, quantity, user, notes=""):
    return _register_movement(
        product=product,
        quantity=quantity,
        movement_type=StockMovement.MovementType.IN,
        user=user,
        notes=notes,
        sign=1,
    )


@transaction.atomic
def register_stock_out(*, product, quantity, user, notes=""):
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
    físico), en vez de sumar/restar una cantidad."""
    if new_stock < 0:
        raise InvalidInventoryOperation("El stock ajustado no puede ser negativo.")

    locked_product = Product.all_objects.select_for_update().get(pk=product.pk, tenant=product.tenant)
    stock_before = get_current_stock(locked_product)

    if new_stock == stock_before:
        raise InvalidInventoryOperation(
            "El stock ajustado es igual al actual; no hay ningún cambio que registrar."
        )

    return StockMovement.all_objects.create(
        tenant=locked_product.tenant,
        product=locked_product,
        movement_type=StockMovement.MovementType.ADJUSTMENT,
        quantity=abs(new_stock - stock_before),
        stock_before=stock_before,
        stock_after=new_stock,
        user=user,
        notes=notes,
    )


def _register_movement(*, product, quantity, movement_type, user, notes, sign):
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

    return StockMovement.all_objects.create(
        tenant=locked_product.tenant,
        product=locked_product,
        movement_type=movement_type,
        quantity=quantity,
        stock_before=stock_before,
        stock_after=stock_after,
        user=user,
        notes=notes,
    )
