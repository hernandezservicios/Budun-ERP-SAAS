"""
Cupones / promociones (FASE 17 sección 34). Estructura deliberadamente
simple — "no crear un motor innecesariamente complejo si el proyecto no
lo necesita": un `Coupon` global (no tenant-scoped, código único),
aplicado a una `Subscription`/`SaaSInvoice` por referencia directa
(snapshot del código en `SaaSInvoice.coupon_code_snapshot`) — sin una
tabla de "redención" separada; `times_redeemed` se incrementa
atómicamente (`select_for_update`) en `apps.billing.services.coupons`."""

from django.conf import settings
from django.db import models


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Porcentaje"
        FIXED = "fixed", "Monto fijo"

    code = models.CharField("código", max_length=50, unique=True)
    discount_type = models.CharField("tipo de descuento", max_length=10, choices=DiscountType.choices)
    discount_value = models.DecimalField("valor del descuento", max_digits=10, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, blank=True, help_text="Solo aplica si el tipo es 'monto fijo'.")
    valid_from = models.DateField("válido desde", null=True, blank=True)
    valid_until = models.DateField("válido hasta", null=True, blank=True)
    max_redemptions = models.PositiveIntegerField("máximo de usos", null=True, blank=True, help_text="Vacío = ilimitado.")
    times_redeemed = models.PositiveIntegerField("veces usado", default=0)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "cupón"
        verbose_name_plural = "cupones"
        ordering = ["-created_at"]

    def __str__(self):
        return self.code
