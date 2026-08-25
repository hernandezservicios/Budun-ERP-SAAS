"""
Modelos de Productos e Inventario (FASE 8).

`Category` y `Product` heredan de `TenantScopedModel` (FASE 3): aislamiento
automático por tenant a través de `objects` (tenant-aware) y `all_objects`
(vía de escape consciente, solo para admin/auditoría — nunca para vistas
de negocio).

`StockMovement` es el LIBRO MAYOR de inventario (append-only, nunca se
edita ni se borra una fila ya creada): es la única fuente de verdad del
stock. Deliberadamente NO existe un campo `current_stock` en `Product`
que se pudiera desincronizar del historial real — el stock actual se
calcula siempre a partir del último movimiento (ver `services.py`). Esto
hace imposible, por diseño, que el stock mostrado contradiga el historial
de movimientos.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.tenants.models import TenantScopedModel


class Category(TenantScopedModel):
    """Categoría de producto. CRUD completo, aislada por tenant."""

    name = models.CharField("nombre", max_length=120)
    order = models.PositiveIntegerField("orden", default=0)
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)
    updated_at = models.DateTimeField("actualizada", auto_now=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_category_tenant_name"),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active", "order"], name="idx_category_tenant_activa"),
        ]

    def __str__(self):
        return self.name


class Product(TenantScopedModel):
    """Producto del catálogo. El stock NO vive aquí (ver `StockMovement`
    y `services.get_current_stock`)."""

    name = models.CharField("nombre", max_length=200)
    sku = models.CharField("SKU", max_length=64)
    barcode = models.CharField("código de barras", max_length=64, blank=True)
    category = models.ForeignKey(
        Category,
        verbose_name="categoría",
        related_name="products",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    description = models.TextField("descripción", blank=True)
    purchase_price = models.DecimalField(
        "precio de compra", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    sale_price = models.DecimalField(
        "precio de venta", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    tax_rate = models.DecimalField(
        "impuesto (%)", max_digits=5, decimal_places=2, default=Decimal("0")
    )
    is_active = models.BooleanField("activo", default=True)
    min_stock = models.DecimalField(
        "stock mínimo", max_digits=12, decimal_places=3, default=Decimal("0")
    )
    created_at = models.DateTimeField("creado", auto_now_add=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "sku"], name="unique_product_tenant_sku"),
            models.UniqueConstraint(
                fields=["tenant", "barcode"],
                condition=Q(barcode__gt=""),
                name="unique_product_tenant_barcode_no_vacio",
            ),
            models.CheckConstraint(
                check=Q(purchase_price__gte=0), name="product_purchase_price_no_negativo"
            ),
            models.CheckConstraint(check=Q(sale_price__gte=0), name="product_sale_price_no_negativo"),
            models.CheckConstraint(check=Q(tax_rate__gte=0), name="product_tax_rate_no_negativo"),
            models.CheckConstraint(check=Q(min_stock__gte=0), name="product_min_stock_no_negativo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active", "name"], name="idx_product_tenant_activo"),
            models.Index(fields=["tenant", "sku"], name="idx_product_tenant_sku"),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"


class StockMovement(TenantScopedModel):
    """Movimiento de inventario: entrada, salida o ajuste. Es el libro
    mayor append-only — nunca se edita ni se borra un movimiento ya
    creado (ver `services.py`, que es la única vía sancionada para
    crearlos)."""

    class MovementType(models.TextChoices):
        IN = "in", "Entrada"
        OUT = "out", "Salida"
        ADJUSTMENT = "adjustment", "Ajuste"

    product = models.ForeignKey(
        Product,
        verbose_name="producto",
        related_name="stock_movements",
        on_delete=models.PROTECT,
    )
    movement_type = models.CharField("tipo de movimiento", max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField("cantidad", max_digits=12, decimal_places=3)
    stock_before = models.DecimalField("stock anterior", max_digits=12, decimal_places=3)
    stock_after = models.DecimalField("stock posterior", max_digits=12, decimal_places=3)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        related_name="stock_movements",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    notes = models.CharField("motivo / notas", max_length=255, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "movimiento de inventario"
        verbose_name_plural = "movimientos de inventario"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=Q(quantity__gt=0), name="stock_movement_cantidad_positiva"),
            models.CheckConstraint(
                check=Q(stock_after__gte=0), name="stock_movement_stock_posterior_no_negativo"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "product", "created_at"], name="idx_stockmov_tenant_producto"),
            models.Index(fields=["tenant", "created_at"], name="idx_stockmov_tenant_fecha"),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} de {self.quantity} — {self.product.sku}"
