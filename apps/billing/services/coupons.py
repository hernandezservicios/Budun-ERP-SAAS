"""
Cupones (FASE 17, sección 34) — validación y redención atómica
(`select_for_update` sobre `Coupon.times_redeemed`, para que dos
redenciones simultáneas del mismo cupón cerca del límite nunca lo
excedan)."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Coupon


class InvalidCouponOperation(ValidationError):
    pass


def validate_coupon(code, *, at_date=None):
    hoy = at_date or date.today()
    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        raise InvalidCouponOperation("Cupón no encontrado.") from None
    if not coupon.is_active:
        raise InvalidCouponOperation("Este cupón está desactivado.")
    if coupon.valid_from and hoy < coupon.valid_from:
        raise InvalidCouponOperation("Este cupón todavía no es válido.")
    if coupon.valid_until and hoy > coupon.valid_until:
        raise InvalidCouponOperation("Este cupón ya expiró.")
    if coupon.max_redemptions is not None and coupon.times_redeemed >= coupon.max_redemptions:
        raise InvalidCouponOperation("Este cupón ya alcanzó su límite de usos.")
    return coupon


def redeem_coupon(coupon):
    with transaction.atomic():
        coupon = Coupon.objects.select_for_update().get(pk=coupon.pk)
        if coupon.max_redemptions is not None and coupon.times_redeemed >= coupon.max_redemptions:
            raise InvalidCouponOperation("Este cupón ya alcanzó su límite de usos.")
        coupon.times_redeemed += 1
        coupon.save(update_fields=["times_redeemed"])
        return coupon


def is_coupon_currently_valid(coupon, *, at_date=None):
    """Vigencia por FECHA + interruptor manual (`is_active`) — nunca el
    límite de usos, que es un concepto de REDENCIÓN inicial (cuántas
    veces se activó un cupón), no de renovación continua de una
    suscripción ya en curso. FASE DE CORRECCIÓN 5: reutilizado por
    `invoicing.generate_invoice_for_subscription` en CADA renovación —
    antes de esta corrección, esa función solo comprobaba `coupon.
    is_active` (un interruptor manual del Super Admin), nunca
    `valid_from`/`valid_until`, así que un cupón por tiempo limitado
    (p. ej. una promoción de 3 meses) seguía descontando indefinidamente
    en cada renovación posterior a su fecha de vencimiento, hasta que
    alguien lo desactivara a mano. `validate_coupon` (primera vez que un
    tenant lo aplica) mantiene sus propios chequeos con mensajes
    específicos por separado — esta función es la versión booleana
    reutilizable para el punto de renovación, donde no hace falta un
    mensaje de error distinto por cada motivo."""
    hoy = at_date or date.today()
    if not coupon.is_active:
        return False
    if coupon.valid_from and hoy < coupon.valid_from:
        return False
    if coupon.valid_until and hoy > coupon.valid_until:
        return False
    return True


def calculate_discount(coupon, amount):
    amount = Decimal(amount)
    if coupon.discount_type == Coupon.DiscountType.PERCENT:
        descuento = (amount * coupon.discount_value / Decimal("100")).quantize(Decimal("0.01"))
    else:
        descuento = coupon.discount_value
    return min(descuento, amount)
