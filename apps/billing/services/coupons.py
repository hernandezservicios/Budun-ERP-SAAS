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


def calculate_discount(coupon, amount):
    amount = Decimal(amount)
    if coupon.discount_type == Coupon.DiscountType.PERCENT:
        descuento = (amount * coupon.discount_value / Decimal("100")).quantize(Decimal("0.01"))
    else:
        descuento = coupon.discount_value
    return min(descuento, amount)
