"""
Modelos de Productos e Inventario (FASE 8).

`Category` y `Product` heredan de `TenantScopedModel` (FASE 3): aislamiento
automático por tenant a través de `objects` (tenant-aware) y `all_objects`
(vía de escape consciente, solo para admin/auditoría — nunca para vistas
de negocio).

`StockMovement` es el LIBRO MAYOR de inventario para productos por
CANTIDAD (append-only, nunca se edita ni se borra una fila ya creada).
`InventoryUnit` es el equivalente para productos SERIALIZADOS (IMEI/serie):
cada unidad física individual es su propia fila, y su disponibilidad es
simplemente su `status` — nunca un conteo desnormalizado que se pudiera
desincronizar. Deliberadamente NO existe ningún campo `current_stock` en
`Product`: el stock/disponibilidad se calcula siempre a partir de
`StockMovement` (CANTIDAD) o de `InventoryUnit` (SERIALIZADO), según
`Product.inventory_tracking_type` (ver `services.get_current_stock`).
Esto hace imposible, por diseño, que el stock mostrado contradiga el
historial real, para ambos tipos de producto.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

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
    """Producto del catálogo. El stock NO vive aquí (ver `StockMovement`,
    `InventoryUnit` y `services.get_current_stock`)."""

    class TrackingType(models.TextChoices):
        QUANTITY = "quantity", "Por cantidad"
        SERIALIZED = "serialized", "Serializado (IMEI / número de serie)"

    inventory_tracking_type = models.CharField(
        "tipo de seguimiento de inventario",
        max_length=20,
        choices=TrackingType.choices,
        default=TrackingType.QUANTITY,
        blank=True,  # tiene un default sensato: omitirlo en un formulario/API no debe ser un error
    )
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


class InventoryUnit(TenantScopedModel):
    """Unidad individual de un producto SERIALIZADO (p. ej. un teléfono
    concreto identificado por IMEI, o un equipo identificado por número
    de serie). Es el equivalente de `StockMovement` para este tipo de
    producto: cada fila es una unidad física real, y su disponibilidad
    es simplemente su `status` — nunca un conteo desnormalizado aparte
    (ver `services.get_current_stock`).

    Los campos `purchase_origin`, `sale_reference` y `customer_reference`
    son texto libre PROVISIONAL: todavía no existen los modelos Purchase
    (FASE 12), Sale/SaleItem (FASE 10) ni Customer (FASE 9). Cuando esas
    fases los construyan, lo natural es que esos modelos referencien a
    `InventoryUnit` mediante su propia FK (p. ej. `SaleItem.inventory_unit`),
    no al revés — estos campos de texto quedan como referencia legible
    mientras tanto y se documentan como provisionales en
    `docs/inventory.md`.
    """

    class Status(models.TextChoices):
        EN_STOCK = "en_stock", "En stock"
        RESERVADO = "reservado", "Reservado"
        VENDIDO = "vendido", "Vendido"
        DEVUELTO = "devuelto", "Devuelto"
        REPARACION = "reparacion", "En reparación"
        GARANTIA = "garantia", "En garantía"
        DANADO = "danado", "Dañado"
        PERDIDO = "perdido", "Perdido"

    product = models.ForeignKey(
        Product,
        verbose_name="producto",
        related_name="inventory_units",
        on_delete=models.PROTECT,
    )
    serial = models.CharField("número de serie", max_length=100, blank=True)
    imei_1 = models.CharField("IMEI 1", max_length=20, blank=True)
    imei_2 = models.CharField("IMEI 2", max_length=20, blank=True)
    status = models.CharField(
        "estado", max_length=20, choices=Status.choices, default=Status.EN_STOCK
    )
    unit_cost = models.DecimalField("costo unitario", max_digits=12, decimal_places=2, default=Decimal("0"))
    entry_date = models.DateField("fecha de ingreso", default=timezone.localdate)
    purchase_origin = models.CharField(
        "origen de compra", max_length=255, blank=True,
        help_text="Texto libre provisional hasta que exista el modelo de Compras (FASE 12).",
    )
    sale_reference = models.CharField(
        "referencia de venta", max_length=255, blank=True,
        help_text="Texto libre provisional hasta que exista el modelo de Ventas (FASE 10).",
    )
    customer_reference = models.CharField(
        "referencia de cliente", max_length=255, blank=True,
        help_text="Texto libre provisional hasta que exista el modelo de Clientes (FASE 9).",
    )
    warranty_until = models.DateField("garantía hasta", null=True, blank=True)
    notes = models.CharField("notas", max_length=255, blank=True)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="último cambio de estado por",
        related_name="inventory_unit_status_changes",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("creada", auto_now_add=True)
    updated_at = models.DateTimeField("actualizada", auto_now=True)

    class Meta:
        verbose_name = "unidad de inventario"
        verbose_name_plural = "unidades de inventario"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "serial"], condition=Q(serial__gt=""),
                name="unique_unit_tenant_serial_no_vacio",
            ),
            models.UniqueConstraint(
                fields=["tenant", "imei_1"], condition=Q(imei_1__gt=""),
                name="unique_unit_tenant_imei1_no_vacio",
            ),
            models.UniqueConstraint(
                fields=["tenant", "imei_2"], condition=Q(imei_2__gt=""),
                name="unique_unit_tenant_imei2_no_vacio",
            ),
            models.CheckConstraint(
                check=Q(imei_1="") | Q(imei_2="") | ~Q(imei_1=F("imei_2")),
                name="unit_imei1_distinto_de_imei2",
            ),
            models.CheckConstraint(
                check=~Q(serial="") | ~Q(imei_1="") | ~Q(imei_2=""),
                name="unit_al_menos_un_identificador",
            ),
            models.CheckConstraint(check=Q(unit_cost__gte=0), name="unit_cost_no_negativo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "product", "status"], name="idx_unit_tenant_prod_estado"),
            models.Index(fields=["tenant", "status"], name="idx_unit_tenant_estado"),
        ]

    def __str__(self):
        identificador = self.serial or self.imei_1 or self.imei_2 or f"#{self.pk}"
        return f"{self.product.sku} · {identificador} ({self.get_status_display()})"
