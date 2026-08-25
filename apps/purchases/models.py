"""
Compras (FASE 12, ver `docs/purchases.md`): dominio central de compras
del ERP — Orden de Compra, Recepción (parcial/completa, cantidad y
serializado), Factura de Proveedor, Cuentas por Pagar (`SupplierPayment`/
`SupplierPaymentAllocation`, mismo patrón que `apps.sales.Payment`/
`PaymentAllocation`), Devolución a Proveedor y documentos adjuntos.

Reutiliza literalmente, nunca duplica:
- `apps.customers.models.Supplier` (FASE 9) — el proveedor.
- `apps.inventory.services` (FASE 8) — toda entrada/salida de stock y
  toda alta/transición de `InventoryUnit`.
- `apps.approvals.services` (FASE 11) — compra sobre el límite y
  sobre-recepción, mismas primitivas que ya usa `apps.pos`.
- `apps.pos.services` (FASE 11) — sesión de caja y movimiento de
  efectivo para pagos a proveedor en efectivo.
- `apps.sales.models.DocumentSequence`/`generate_document_number` — la
  numeración de "OC-000001"/"REC-000001"/"DEVP-000001" es la MISMA
  tabla de secuencias que usan Cotizaciones/Proformas/Ventas, solo con
  tipos de documento nuevos — nunca un segundo sistema de numeración.
- `apps.customers.models.DocumentoBaseMixin`/`EXTENSIONES_DOCUMENTO_PERMITIDAS`
  (FASE 9) — el mismo sistema de archivos seguro que ya usa
  `apps.sales.SalesDocumentAttachment`.
- `apps.sales.models.PaymentMethod` — mismo vocabulario de métodos de
  pago que Cuentas por Cobrar.

`PurchaseOrderItem` deliberadamente NO tiene `received_quantity`/
`pending_quantity` como campos guardados: serían una segunda fuente de
verdad que podría desincronizarse de `PurchaseReceiptItem` (el mismo
principio que ya evitó un `current_stock` en `Product` desde FASE 8).
Se calculan siempre en `services.get_purchase_order_item_received_quantity`
agregando sobre `PurchaseReceiptItem`, nunca desde un campo aparte.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

import logging
import os
import uuid

from apps.customers.models import (
    DocumentoBaseMixin,
    EXTENSIONES_DOCUMENTO_PERMITIDAS,
    PaymentTerms,
    Supplier,
)
from apps.inventory.models import InventoryUnit, Product
from apps.pos.models import CashSession
from apps.sales.models import PaymentMethod
from apps.tenants.models import TenantScopedModel

logger = logging.getLogger("apps.purchases.documents")


# ---------------------------------------------------------------------
# Orden de Compra
# ---------------------------------------------------------------------


class PurchaseOrder(TenantScopedModel):
    """Documento comercial que solicita mercancía a un proveedor.
    Numerada vía `apps.sales.services.generate_document_number` (tipo
    `DocumentSequence.DocumentType.PURCHASE_ORDER`, prefijo "OC") — la
    misma infraestructura de numeración que Cotizaciones/Ventas."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        SENT = "sent", "Enviada"
        PARTIALLY_RECEIVED = "partially_received", "Parcialmente recibida"
        RECEIVED = "received", "Recibida por completo"
        CANCELED = "canceled", "Cancelada"
        CLOSED = "closed", "Cerrada"

    supplier = models.ForeignKey(
        Supplier, verbose_name="proveedor", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    number = models.CharField("número", max_length=30)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    issue_date = models.DateField("fecha de emisión", default=timezone.localdate)
    expected_date = models.DateField("fecha esperada de entrega", null=True, blank=True)
    currency = models.CharField("moneda", max_length=3, default="USD")
    payment_terms = models.CharField(
        "condiciones de pago", max_length=20, choices=PaymentTerms.choices, default=PaymentTerms.CONTADO
    )
    notes = models.TextField("notas", blank=True)
    terms = models.TextField("términos y condiciones", blank=True)

    global_discount_percent = models.DecimalField(
        "descuento global (%)", max_digits=5, decimal_places=2, default=Decimal("0")
    )
    global_discount_amount = models.DecimalField(
        "descuento global (monto)", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    # Costos atribuibles a la orden completa (preparación de landed
    # cost): se registran a nivel de cabecera porque su prorrateo por
    # línea/unidad es un cálculo de distribución que esta fase deja
    # preparado, no construido — ver docstring del módulo y
    # docs/purchase-orders.md sección "Landed cost".
    freight_cost = models.DecimalField("costo de flete", max_digits=12, decimal_places=2, default=Decimal("0"))
    insurance_cost = models.DecimalField("costo de seguro", max_digits=12, decimal_places=2, default=Decimal("0"))
    other_costs = models.DecimalField("otros costos atribuibles", max_digits=12, decimal_places=2, default=Decimal("0"))

    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_total = models.DecimalField("descuento total", max_digits=12, decimal_places=2, default=Decimal("0"))
    tax_total = models.DecimalField("impuesto total", max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("total", max_digits=12, decimal_places=2, default=Decimal("0"))

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    sent_at = models.DateTimeField("enviada el", null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="enviada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    canceled_at = models.DateTimeField("cancelada el", null=True, blank=True)
    canceled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="cancelada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    cancel_reason = models.CharField("motivo de cancelación", max_length=255, blank=True)
    closed_at = models.DateTimeField("cerrada el", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="cerrada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    created_at = models.DateTimeField("creada", auto_now_add=True)
    updated_at = models.DateTimeField("actualizada", auto_now=True)

    class Meta:
        verbose_name = "orden de compra"
        verbose_name_plural = "órdenes de compra"
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_purchaseorder_tenant_numero"),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "issue_date"], name="idx_po_tenant_estado"),
            models.Index(fields=["tenant", "supplier"], name="idx_po_tenant_proveedor"),
        ]

    def __str__(self):
        return self.number


class PurchaseOrderItem(TenantScopedModel):
    """Línea de orden de compra. `description`/`sku_snapshot`/`unit_cost`
    son SNAPSHOT tomados al agregar la línea — nunca se vuelve a leer
    `Product` para recalcular una línea ya guardada, mismo principio que
    `apps.sales.CommercialDocumentItemMixin`."""

    purchase_order = models.ForeignKey(
        PurchaseOrder, verbose_name="orden de compra", on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(Product, verbose_name="producto", on_delete=models.PROTECT, related_name="+")
    description = models.CharField("descripción", max_length=255)
    sku_snapshot = models.CharField("SKU (al momento)", max_length=64, blank=True)
    quantity = models.DecimalField("cantidad ordenada", max_digits=12, decimal_places=3, default=Decimal("1"))
    unit_cost = models.DecimalField("costo unitario", max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_percent = models.DecimalField("descuento (%)", max_digits=5, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField("descuento (monto)", max_digits=12, decimal_places=2, default=Decimal("0"))
    tax_rate = models.DecimalField("tasa de impuesto (%)", max_digits=5, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField("impuesto", max_digits=12, decimal_places=2, default=Decimal("0"))
    subtotal = models.DecimalField("subtotal de línea", max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("total de línea", max_digits=12, decimal_places=2, default=Decimal("0"))
    line_order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "línea de orden de compra"
        verbose_name_plural = "líneas de orden de compra"
        ordering = ["line_order", "id"]
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gt=0), name="poitem_cantidad_positiva"),
        ]

    def __str__(self):
        return f"{self.description} x{self.quantity}"


# ---------------------------------------------------------------------
# Recepción (inmutable, mismo principio que apps.sales.Return: una
# corrección es una operación nueva, nunca una edición del historial)
# ---------------------------------------------------------------------


class PurchaseReceipt(TenantScopedModel):
    """Recepción física de mercancía contra una orden de compra —
    parcial o completa. Inmutable una vez creada: sin estados ni
    edición, igual que `apps.sales.Return`. Numerada vía la misma
    `DocumentSequence` (tipo `PURCHASE_RECEIPT`, prefijo "REC")."""

    purchase_order = models.ForeignKey(
        PurchaseOrder, verbose_name="orden de compra", on_delete=models.PROTECT, related_name="receipts"
    )
    number = models.CharField("número", max_length=30)
    receipt_date = models.DateField("fecha de recepción", default=timezone.localdate)
    notes = models.CharField("notas", max_length=255, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="recibida por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "recepción de compra"
        verbose_name_plural = "recepciones de compra"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_purchasereceipt_tenant_numero"),
        ]
        indexes = [
            models.Index(fields=["tenant", "purchase_order"], name="idx_receipt_tenant_oc"),
        ]

    def __str__(self):
        return self.number


class PurchaseReceiptItem(TenantScopedModel):
    """Una línea de recepción es, o bien una cantidad recibida de un
    producto QUANTITY, o bien exactamente UNA unidad física de un
    producto SERIALIZED (nunca "recibí 5" sin 5 filas individuales) —
    mismo patrón XOR que `apps.sales.ReturnItem`. `unit_cost` es el
    costo REAL registrado al recibir (puede diferir del estimado en la
    orden — base de landed cost), congelado aquí, nunca recalculado."""

    receipt = models.ForeignKey(PurchaseReceipt, verbose_name="recepción", on_delete=models.CASCADE, related_name="items")
    purchase_order_item = models.ForeignKey(
        PurchaseOrderItem, verbose_name="línea de orden de compra", on_delete=models.PROTECT, related_name="+"
    )
    quantity_received = models.DecimalField(
        "cantidad recibida", max_digits=12, decimal_places=3, null=True, blank=True
    )
    inventory_unit = models.ForeignKey(
        InventoryUnit, verbose_name="unidad de inventario", on_delete=models.PROTECT,
        null=True, blank=True, related_name="+",
    )
    unit_cost = models.DecimalField("costo unitario recibido", max_digits=12, decimal_places=2, default=Decimal("0"))
    condition_notes = models.CharField("condición / notas", max_length=255, blank=True)

    class Meta:
        verbose_name = "línea de recepción"
        verbose_name_plural = "líneas de recepción"
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(quantity_received__isnull=False) & models.Q(inventory_unit__isnull=True))
                    | (models.Q(quantity_received__isnull=True) & models.Q(inventory_unit__isnull=False))
                ),
                name="receiptitem_cantidad_xor_unidad",
            ),
            models.CheckConstraint(
                check=models.Q(quantity_received__isnull=True) | models.Q(quantity_received__gt=0),
                name="receiptitem_cantidad_positiva",
            ),
        ]

    def __str__(self):
        objetivo = self.inventory_unit_id or self.quantity_received
        return f"Recepción {objetivo} ({self.receipt.number})"


# ---------------------------------------------------------------------
# Factura de proveedor (documento distinto de la orden/recepción)
# ---------------------------------------------------------------------


class SupplierInvoice(TenantScopedModel):
    """Factura del proveedor — documento conceptualmente separado de
    `PurchaseOrder`/`PurchaseReceipt`: puede emitirse después de una
    recepción, parcialmente, o incluso sin una orden de compra formal
    asociada (compra directa). `supplier_invoice_number` es el número
    del PROVEEDOR (texto libre, su propio documento) — nunca se genera
    con `DocumentSequence`, que solo numera NUESTROS documentos."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        CONFIRMED = "confirmed", "Confirmada"
        CANCELED = "canceled", "Cancelada"

    supplier = models.ForeignKey(Supplier, verbose_name="proveedor", on_delete=models.PROTECT, related_name="invoices")
    purchase_order = models.ForeignKey(
        PurchaseOrder, verbose_name="orden de compra", on_delete=models.PROTECT,
        null=True, blank=True, related_name="invoices",
    )
    supplier_invoice_number = models.CharField("número de factura del proveedor", max_length=50)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    issue_date = models.DateField("fecha de emisión", default=timezone.localdate)
    due_date = models.DateField("fecha de vencimiento", null=True, blank=True)
    currency = models.CharField("moneda", max_length=3, default="USD")

    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_total = models.DecimalField("descuento total", max_digits=12, decimal_places=2, default=Decimal("0"))
    tax_total = models.DecimalField("impuesto total", max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("total", max_digits=12, decimal_places=2, default=Decimal("0"))

    notes = models.CharField("notas", max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="registrada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    confirmed_at = models.DateTimeField("confirmada el", null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="confirmada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    canceled_at = models.DateTimeField("cancelada el", null=True, blank=True)
    canceled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="cancelada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "factura de proveedor"
        verbose_name_plural = "facturas de proveedor"
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "supplier", "supplier_invoice_number"],
                name="unique_supplierinvoice_tenant_proveedor_numero",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "supplier", "status"], name="idx_sinv_tenant_proveedor"),
        ]

    def __str__(self):
        return f"{self.supplier_invoice_number} ({self.supplier})"


class SupplierInvoiceItem(TenantScopedModel):
    invoice = models.ForeignKey(SupplierInvoice, verbose_name="factura", on_delete=models.CASCADE, related_name="items")
    purchase_order_item = models.ForeignKey(
        PurchaseOrderItem, verbose_name="línea de orden de compra", on_delete=models.PROTECT,
        null=True, blank=True, related_name="+",
    )
    description = models.CharField("descripción", max_length=255)
    quantity = models.DecimalField("cantidad", max_digits=12, decimal_places=3, default=Decimal("1"))
    unit_cost = models.DecimalField("costo unitario", max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_percent = models.DecimalField("descuento (%)", max_digits=5, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField("descuento (monto)", max_digits=12, decimal_places=2, default=Decimal("0"))
    tax_rate = models.DecimalField("tasa de impuesto (%)", max_digits=5, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField("impuesto", max_digits=12, decimal_places=2, default=Decimal("0"))
    subtotal = models.DecimalField("subtotal de línea", max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("total de línea", max_digits=12, decimal_places=2, default=Decimal("0"))
    line_order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "línea de factura de proveedor"
        verbose_name_plural = "líneas de factura de proveedor"
        ordering = ["line_order", "id"]


# ---------------------------------------------------------------------
# Cuentas por Pagar: SupplierPayment + SupplierPaymentAllocation —
# mismo patrón append-only que apps.sales.Payment/PaymentAllocation.
# Un anticipo a proveedor es simplemente un SupplierPayment sin ninguna
# asignación todavía (mismo principio que "anticipo de cliente" en
# Cuentas por Cobrar) — nunca un modelo separado.
# ---------------------------------------------------------------------


class SupplierPayment(TenantScopedModel):
    """Dinero entregado a un proveedor. Puede aplicarse a una o varias
    `SupplierInvoice` mediante `SupplierPaymentAllocation`; sin ninguna
    asignación todavía, representa un anticipo (saldo a favor NUESTRO
    frente al proveedor) sin aplicar — ver
    `services.get_supplier_advance_balance`."""

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmado"
        VOIDED = "voided", "Anulado"

    supplier = models.ForeignKey(Supplier, verbose_name="proveedor", on_delete=models.PROTECT, related_name="+")
    method = models.CharField("método", max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    reference = models.CharField("referencia", max_length=255, blank=True)
    idempotency_key = models.CharField("clave de idempotencia", max_length=100, blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    cash_session = models.ForeignKey(
        CashSession, verbose_name="sesión de caja", on_delete=models.PROTECT,
        null=True, blank=True, related_name="+",
        help_text="Solo cuando method=CASH — la sesión de caja abierta que registró la salida de efectivo.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="registrado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "pago a proveedor"
        verbose_name_plural = "pagos a proveedor"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="supplierpayment_monto_positivo"),
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="unique_supplierpayment_tenant_idempotency_no_vacio",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "supplier"], name="idx_suppay_tenant_prov"),
        ]

    def __str__(self):
        return f"{self.get_method_display()} {self.amount}"


class SupplierPaymentAllocation(TenantScopedModel):
    """Cuánto de un `SupplierPayment` se aplicó a qué `SupplierInvoice`
    — el ledger de cuentas por pagar. Nunca se borra: `status=REVERSED`
    (con auditoría) deshace una asignación equivocada, mismo principio
    que `apps.sales.PaymentAllocation`."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        REVERSED = "reversed", "Reversada"

    payment = models.ForeignKey(
        SupplierPayment, verbose_name="pago", on_delete=models.PROTECT, related_name="allocations"
    )
    supplier_invoice = models.ForeignKey(
        SupplierInvoice, verbose_name="factura de proveedor", on_delete=models.PROTECT, related_name="payment_allocations"
    )
    amount = models.DecimalField("monto aplicado", max_digits=12, decimal_places=2)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="aplicada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("fecha", auto_now_add=True)
    reversed_at = models.DateTimeField("reversada el", null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="reversada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "asignación de pago a proveedor"
        verbose_name_plural = "asignaciones de pago a proveedor"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="supplierpaymentallocation_monto_positivo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "payment", "status"], name="idx_spa_tenant_pago"),
            models.Index(fields=["tenant", "supplier_invoice", "status"], name="idx_spa_tenant_factura"),
        ]

    def __str__(self):
        return f"{self.amount} — pago #{self.payment_id} → {self.supplier_invoice.supplier_invoice_number}"


# ---------------------------------------------------------------------
# Devolución a proveedor (inmutable, mismo principio que apps.sales.Return)
# ---------------------------------------------------------------------


class SupplierReturn(TenantScopedModel):
    """Devolución de mercancía a un proveedor. Inmutable una vez creada
    — sin estados ni edición, igual que `apps.sales.Return`. Numerada
    vía la misma `DocumentSequence` (tipo `SUPPLIER_RETURN`, prefijo
    "DEVP")."""

    purchase_order = models.ForeignKey(
        PurchaseOrder, verbose_name="orden de compra", on_delete=models.PROTECT, related_name="supplier_returns"
    )
    number = models.CharField("número", max_length=30)
    reason = models.CharField("motivo", max_length=255, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="registrada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "devolución a proveedor"
        verbose_name_plural = "devoluciones a proveedor"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_supplierreturn_tenant_numero"),
        ]

    def __str__(self):
        return self.number


class SupplierReturnItem(TenantScopedModel):
    return_document = models.ForeignKey(
        SupplierReturn, verbose_name="devolución", on_delete=models.CASCADE, related_name="items"
    )
    receipt_item = models.ForeignKey(
        PurchaseReceiptItem, verbose_name="línea de recepción", on_delete=models.PROTECT, related_name="+"
    )
    quantity_returned = models.DecimalField(
        "cantidad devuelta", max_digits=12, decimal_places=3, null=True, blank=True
    )
    inventory_unit = models.ForeignKey(
        InventoryUnit, verbose_name="unidad de inventario", on_delete=models.PROTECT,
        null=True, blank=True, related_name="+",
    )
    condition_notes = models.CharField("condición / notas", max_length=255, blank=True)

    class Meta:
        verbose_name = "línea de devolución a proveedor"
        verbose_name_plural = "líneas de devolución a proveedor"
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(quantity_returned__isnull=False) & models.Q(inventory_unit__isnull=True))
                    | (models.Q(quantity_returned__isnull=True) & models.Q(inventory_unit__isnull=False))
                ),
                name="supplierreturnitem_cantidad_xor_unidad",
            ),
        ]

    def __str__(self):
        objetivo = self.inventory_unit_id or self.quantity_returned
        return f"Devolución {objetivo} ({self.return_document.number})"


# ---------------------------------------------------------------------
# Documentos adjuntos (reutiliza FASE 9 — no se crea un segundo sistema
# de archivos)
# ---------------------------------------------------------------------


def _ruta_documento_compra(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"compras/{instance.tenant_id}/{instance.document_type}/{instance.document_id}/{uuid.uuid4().hex}{extension}"


class PurchaseDocumentAttachment(TenantScopedModel, DocumentoBaseMixin):
    """Adjunto de Orden de Compra/Recepción/Factura de Proveedor/
    Devolución a proveedor. Reutiliza literalmente la validación de
    archivos y las categorías de FASE 9 — nunca se reimplementa esa
    lógica aquí (mismo patrón que `apps.sales.SalesDocumentAttachment`)."""

    class DocumentType(models.TextChoices):
        PURCHASE_ORDER = "purchase_order", "Orden de compra"
        PURCHASE_RECEIPT = "purchase_receipt", "Recepción de compra"
        SUPPLIER_INVOICE = "supplier_invoice", "Factura de proveedor"
        SUPPLIER_RETURN = "supplier_return", "Devolución a proveedor"

    document_type = models.CharField("tipo de documento", max_length=20, choices=DocumentType.choices)
    document_id = models.PositiveBigIntegerField("ID del documento")
    file = models.FileField(
        "archivo",
        upload_to=_ruta_documento_compra,
        validators=[FileExtensionValidator(allowed_extensions=EXTENSIONES_DOCUMENTO_PERMITIDAS)],
    )

    class Meta:
        verbose_name = "documento adjunto de compra"
        verbose_name_plural = "documentos adjuntos de compra"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["tenant", "document_type", "document_id"], name="idx_purchdoc_tenant_documento"),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.document_type} #{self.document_id})"


@receiver(post_delete, sender=PurchaseDocumentAttachment)
def _eliminar_archivo_adjunto_compra(sender, instance, **kwargs):
    """Mismo patrón que FASE 9/FASE 10 (`apps.customers.models`/
    `apps.sales.models`): limpia el archivo físico ante cualquier camino
    de borrado, capturando `OSError` sin propagarlo."""
    if instance.file:
        try:
            instance.file.delete(save=False)
        except OSError:
            logger.exception(
                "No se pudo borrar el archivo físico del adjunto eliminado: %s", instance.file.name
            )


# ---------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo — mismo principio que
# apps.customers.ActivityLog/apps.sales.SalesActivityLog)
# ---------------------------------------------------------------------


class PurchasesActivityLog(TenantScopedModel):
    class Action(models.TextChoices):
        CREATED = "created", "Creación"
        UPDATED = "updated", "Edición"
        SENT = "sent", "Enviada"
        CANCELED = "canceled", "Cancelada"
        CLOSED = "closed", "Cerrada"
        RECEIVED_PARTIAL = "received_partial", "Recepción parcial"
        RECEIVED_FULL = "received_full", "Recepción completa"
        INVOICE_REGISTERED = "invoice_registered", "Factura de proveedor registrada"
        INVOICE_CONFIRMED = "invoice_confirmed", "Factura de proveedor confirmada"
        INVOICE_CANCELED = "invoice_canceled", "Factura de proveedor cancelada"
        PAYMENT_RECORDED = "payment_recorded", "Pago registrado"
        PAYMENT_VOIDED = "payment_voided", "Pago anulado"
        PAYMENT_ALLOCATED = "payment_allocated", "Pago aplicado a factura"
        PAYMENT_ALLOCATION_REVERSED = "payment_allocation_reversed", "Aplicación de pago reversada"
        SUPPLIER_RETURN_CREATED = "supplier_return_created", "Devolución a proveedor registrada"
        ATTACHMENT_UPLOADED = "attachment_uploaded", "Adjunto subido"
        ATTACHMENT_DELETED = "attachment_deleted", "Adjunto eliminado"

    entity_type = models.CharField("tipo de entidad", max_length=25)
    # "purchase_order" | "purchase_receipt" | "supplier_invoice" | "supplier_return"
    entity_id = models.PositiveBigIntegerField("id de la entidad")
    entity_label = models.CharField("identificador de la entidad (al momento del evento)", max_length=255, blank=True)
    action = models.CharField("acción", max_length=30, choices=Action.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    details = models.CharField("detalles", max_length=255, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "registro de actividad (compras)"
        verbose_name_plural = "registros de actividad (compras)"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["tenant", "entity_type", "entity_id", "created_at"], name="idx_purchact_tenant_entidad"
            ),
        ]

    def __str__(self):
        return f"{self.get_action_display()} · {self.entity_type} #{self.entity_id}"
