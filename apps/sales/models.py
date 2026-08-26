"""
Motor comercial central del ERP (FASE 10): Cotizaciones, Proformas,
Ventas/Facturas, Pagos, Reservas, Devoluciones y Reembolsos.

## Por qué documentos independientes, no una sola entidad con estados
`Quotation`, `ProformaInvoice` y `Sale` son modelos separados (no una
única entidad "Document" con un campo `type`), tal como pidió
explícitamente el usuario: son conceptualmente distintos (una cotización
es una propuesta sin compromiso; una proforma es un documento
intermedio que puede iniciar una reserva; una venta/factura es la
transacción comercial definitiva con efectos reales en inventario). Cada
uno tiene su propia máquina de estados y su propia tabla de líneas.
Comparten forma a través de dos mixins abstractos
(`CommercialDocumentMixin`/`CommercialDocumentItemMixin`), pero no hay
ninguna tabla ni FK compartida entre ellos a nivel de cabecera.

## Snapshot histórico (requisito explícito)
Cada línea (`QuotationItem`/`ProformaInvoiceItem`/`SaleItem`) copia
`description`, `sku_snapshot`, `unit_price`, `tax_rate` y calcula sus
propios `subtotal`/`tax_amount`/`total` EN EL MOMENTO de agregarse.
Modificar el producto o su precio después nunca cambia un documento ya
emitido — mismo principio que llevó a que `StockMovement`/`InventoryUnit`
(FASE 8) nunca dependan de un valor mutable de `Product` calculado a
posteriori.

## Cálculo de totales (documentado explícitamente, ver `services.py`)
Cada línea calcula su propio descuento (`discount_percent` tiene
prioridad sobre `discount_amount` si es mayor que cero) y su propio
impuesto sobre la base ya descontada. El descuento GLOBAL del documento
(`global_discount_percent`/`global_discount_amount`) se aplica como una
rebaja final sobre la suma de los totales de línea — una simplificación
deliberada y documentada (no se redistribuye proporcionalmente en la
base imponible de cada línea) para mantener el cálculo por línea simple
y auditable.

## Números de documento (requisito explícito, ver `DocumentSequence`)
Nunca se usa el ID de base de datos como número comercial. Cada tenant
tiene una secuencia propia por tipo de documento (`DocumentSequence`,
`select_for_update()` para evitar duplicados bajo concurrencia — ver
`services.generate_document_number`).

## Reservas: una capa "blanda" sobre el inventario real
`Reservation` NUNCA toca `StockMovement` directamente. Para productos
QUANTITY, la disponibilidad "para prometer" es
`get_current_stock(product) - cantidad_reservada_activa(product)` — un
cálculo, no un movimiento. Para SERIALIZED, reservar SÍ transiciona la
unidad a `InventoryUnit.Status.RESERVADO` (reutilizando la máquina de
estados ya construida en FASE 8, `services.transition_unit_status` —
nunca se duplica esa lógica aquí).

## Pagos y cuentas por cobrar: Payment + PaymentAllocation
EXTENSIÓN OBLIGATORIA pedida explícitamente por el usuario tras el
cierre inicial de FASE 10. `Payment` ya NO referencia una única `Sale`:
representa dinero recibido de un `Customer`. `PaymentAllocation` es el
ledger que registra cuánto de ese dinero se aplicó a cada factura —
un pago puede aplicarse a varias facturas del mismo cliente, y una
factura puede recibir asignaciones de varios pagos. El monto asignado
nunca puede exceder ni lo disponible del pago
(`services.get_unallocated_payment_amount`) ni el saldo pendiente de la
factura (`services.get_sale_balance_due`) — ambos verificados dentro de
la misma transacción con `select_for_update()`, igual que el resto del
módulo. `services.record_payment_for_sale` sigue existiendo como atajo
para el caso más común (un pago, una venta, aplicado de inmediato) —
internamente crea el `Payment` y su `PaymentAllocation` en un solo paso
atómico, así que las vistas que solo cobran una venta no necesitan
saber que el ledger de asignaciones existe debajo.

## Devoluciones y reembolsos: separados a propósito
`Return`/`ReturnItem` es la devolución de MERCANCÍA (afecta inventario).
`Refund` es la devolución de DINERO (afecta pagos) — están
deliberadamente separados, tal como pidió el usuario, porque no toda
devolución de mercancía implica reembolso inmediato (podría ser una nota
de crédito futura) ni todo reembolso parte de una devolución física
(podría ser un ajuste de precio). `Return` es inmutable una vez creado
(sin estados ni cancelación): es en sí misma una operación correctiva;
deshacerla requeriría una nueva operación compensatoria, no revertir un
estado — decisión de diseño documentada en `docs/returns.md`.

## Auditoría
`SalesActivityLog` es, igual que `apps.customers.models.ActivityLog` en
FASE 9, una bitácora MÍNIMA acotada a este módulo — no el audit log
transversal de FASE 15.

## Qué se documenta pero NO se implementa todavía
- Motor de facturación fiscal electrónica (tipo/serie/número fiscal):
  ningún campo se agregó — no hay ninguna integración real que los
  fuera a usar hoy (a diferencia de los campos comerciales de FASE 9,
  que sí son configuración real usable). Ver `docs/sales.md`.
- PDF real: se implementan vistas HTML imprimibles (`@media print`)
  reutilizando el Design System, no generación de archivos PDF
  binarios — instalar una librería de PDF (WeasyPrint, reportlab, etc.)
  no está aprobado como dependencia nueva sin decisión explícita del
  usuario. Ver `docs/invoice-documents.md`.
- Integración real de pagos con PayPal: `Payment.method` incluye
  `OTHER` como valor extensible; el acoplamiento a un proveedor real
  queda para FASE 16, a través de la misma `services.record_payment`
  (nunca desde las vistas).
"""

import os
import uuid
from decimal import Decimal

import logging

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.customers.models import Customer, DocumentoBaseMixin, EXTENSIONES_DOCUMENTO_PERMITIDAS
from apps.customers.models import PaymentTerms as CustomerPaymentTerms
from apps.inventory.models import InventoryUnit, Product
from apps.tenants.models import TenantScopedModel

logger = logging.getLogger("apps.sales.documents")


# ---------------------------------------------------------------------
# Choices compartidos
# ---------------------------------------------------------------------


class PaymentMethod(models.TextChoices):
    """Extensible sin rehacer el modelo (mismo patrón que
    `IdentificationType` en FASE 9): un método nuevo es una línea nueva
    aquí. PayPal se integrará en FASE 16 reutilizando `OTHER` o
    agregando su propio valor, sin acoplar `Sale` a ningún proveedor."""

    CASH = "cash", "Efectivo"
    CARD = "card", "Tarjeta"
    TRANSFER = "transfer", "Transferencia"
    OTHER = "other", "Otro"


class DocumentSequence(TenantScopedModel):
    """Numeración comercial por tenant y tipo de documento — nunca se
    usa el ID de base de datos como número comercial. `select_for_update`
    en `services.generate_document_number` evita duplicados bajo
    concurrencia (dos ventas creadas al mismo tiempo nunca reciben el
    mismo número)."""

    class DocumentType(models.TextChoices):
        QUOTATION = "quotation", "Cotización"
        PROFORMA = "proforma", "Proforma"
        SALE = "sale", "Venta / Factura"
        RETURN = "return", "Devolución"
        CREDIT_NOTE = "credit_note", "Nota de crédito"
        # FASE 12 (Compras): reutiliza literalmente esta misma tabla de
        # secuencias — nunca un segundo sistema de numeración — solo se
        # agregan tipos de documento nuevos, mismo patrón extensible que
        # el resto de estos enums (ver docs/purchases.md).
        PURCHASE_ORDER = "purchase_order", "Orden de compra"
        PURCHASE_RECEIPT = "purchase_receipt", "Recepción de compra"
        SUPPLIER_RETURN = "supplier_return", "Devolución a proveedor"
        # FASE 13 (Gastos + RRHH + Nómina): mismo patrón — nunca un
        # segundo sistema de numeración por tenant.
        EXPENSE = "expense", "Gasto"
        PAYROLL_PERIOD = "payroll_period", "Período de nómina"
        # FASE 14 (Contabilidad General): mismo patrón — nunca un
        # segundo sistema de numeración por tenant.
        JOURNAL_ENTRY = "journal_entry", "Asiento contable"

    document_type = models.CharField("tipo de documento", max_length=20, choices=DocumentType.choices)
    prefix = models.CharField("prefijo", max_length=10)
    next_number = models.PositiveIntegerField("próximo número", default=1)
    padding = models.PositiveSmallIntegerField("relleno de ceros", default=6)

    class Meta:
        verbose_name = "secuencia de numeración"
        verbose_name_plural = "secuencias de numeración"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "document_type"], name="unique_sequence_tenant_tipo"),
        ]

    def __str__(self):
        return f"{self.prefix} ({self.tenant_id})"


# ---------------------------------------------------------------------
# Mixins compartidos (Cotización / Proforma / Venta)
# ---------------------------------------------------------------------


class CommercialDocumentMixin(models.Model):
    """Campos de cabecera comunes a `Quotation`/`ProformaInvoice`/`Sale`.
    Abstracto: cada modelo concreto declara su propio `number` (único
    por tenant), su propia máquina de estados y sus propias
    constraints."""

    customer = models.ForeignKey(
        Customer,
        verbose_name="cliente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Vacío para consumidor final / venta de mostrador anónima.",
    )
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="vendedor / responsable",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    currency = models.CharField("moneda", max_length=3, default="USD")
    payment_terms = models.CharField(
        "condiciones de pago",
        max_length=20,
        choices=CustomerPaymentTerms.choices,
        default=CustomerPaymentTerms.CONTADO,
    )
    notes = models.TextField("notas", blank=True)
    terms = models.TextField("términos y condiciones", blank=True)

    global_discount_percent = models.DecimalField(
        "descuento global (%)", max_digits=5, decimal_places=2, default=Decimal("0")
    )
    global_discount_amount = models.DecimalField(
        "descuento global (monto)", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_total = models.DecimalField(
        "descuento total", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    tax_total = models.DecimalField("impuesto total", max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("total", max_digits=12, decimal_places=2, default=Decimal("0"))

    created_at = models.DateTimeField("creado", auto_now_add=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        abstract = True


class CommercialDocumentItemMixin(models.Model):
    """Línea común a `QuotationItem`/`ProformaInvoiceItem`/`SaleItem`.
    Cada campo relevante para el cálculo es un SNAPSHOT tomado al
    agregar la línea — nunca se relee `Product` para recalcular una
    línea ya guardada."""

    product = models.ForeignKey(Product, verbose_name="producto", on_delete=models.PROTECT, related_name="+")
    inventory_unit = models.ForeignKey(
        InventoryUnit,
        verbose_name="unidad de inventario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Solo para productos SERIALIZED — la unidad física concreta de esta línea.",
    )
    description = models.CharField("descripción", max_length=255)
    sku_snapshot = models.CharField("SKU (al momento)", max_length=64, blank=True)
    quantity = models.DecimalField("cantidad", max_digits=12, decimal_places=3, default=Decimal("1"))
    unit_price = models.DecimalField("precio unitario", max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_percent = models.DecimalField(
        "descuento (%)", max_digits=5, decimal_places=2, default=Decimal("0")
    )
    discount_amount = models.DecimalField(
        "descuento (monto)", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    tax_rate = models.DecimalField("tasa de impuesto (%)", max_digits=5, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField("impuesto", max_digits=12, decimal_places=2, default=Decimal("0"))
    subtotal = models.DecimalField("subtotal de línea", max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("total de línea", max_digits=12, decimal_places=2, default=Decimal("0"))
    line_order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.description} x{self.quantity}"


# ---------------------------------------------------------------------
# Cotizaciones
# ---------------------------------------------------------------------


class Quotation(TenantScopedModel, CommercialDocumentMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        SENT = "sent", "Enviada"
        ACCEPTED = "accepted", "Aceptada"
        REJECTED = "rejected", "Rechazada"
        EXPIRED = "expired", "Vencida"
        CANCELED = "canceled", "Cancelada"
        CONVERTED = "converted", "Convertida"

    number = models.CharField("número", max_length=30)
    issue_date = models.DateField("fecha de emisión", default=timezone.localdate)
    expiry_date = models.DateField("fecha de vencimiento", null=True, blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    converted_at = models.DateTimeField("convertida el", null=True, blank=True)
    converted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="convertida por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "cotización"
        verbose_name_plural = "cotizaciones"
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_quotation_tenant_numero"),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "issue_date"], name="idx_quotation_tenant_estado"),
            models.Index(fields=["tenant", "customer"], name="idx_quotation_tenant_cliente"),
        ]

    def __str__(self):
        return self.number


class QuotationItem(TenantScopedModel, CommercialDocumentItemMixin):
    quotation = models.ForeignKey(Quotation, verbose_name="cotización", on_delete=models.CASCADE, related_name="items")

    class Meta:
        verbose_name = "línea de cotización"
        verbose_name_plural = "líneas de cotización"
        ordering = ["line_order", "id"]


# ---------------------------------------------------------------------
# Proforma / Prefactura
# ---------------------------------------------------------------------


class ProformaInvoice(TenantScopedModel, CommercialDocumentMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        ISSUED = "issued", "Emitida"
        EXPIRED = "expired", "Vencida"
        CANCELED = "canceled", "Cancelada"
        CONVERTED = "converted", "Convertida"

    number = models.CharField("número", max_length=30)
    issue_date = models.DateField("fecha de emisión", default=timezone.localdate)
    expiry_date = models.DateField("fecha de vencimiento", null=True, blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    source_quotation = models.OneToOneField(
        Quotation,
        verbose_name="cotización de origen",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="converted_proforma",
    )
    converted_at = models.DateTimeField("convertida el", null=True, blank=True)
    converted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="convertida por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "proforma"
        verbose_name_plural = "proformas"
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_proforma_tenant_numero"),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "issue_date"], name="idx_proforma_tenant_estado"),
            models.Index(fields=["tenant", "customer"], name="idx_proforma_tenant_cliente"),
        ]

    def __str__(self):
        return self.number


class ProformaInvoiceItem(TenantScopedModel, CommercialDocumentItemMixin):
    proforma = models.ForeignKey(
        ProformaInvoice, verbose_name="proforma", on_delete=models.CASCADE, related_name="items"
    )

    class Meta:
        verbose_name = "línea de proforma"
        verbose_name_plural = "líneas de proforma"
        ordering = ["line_order", "id"]


# ---------------------------------------------------------------------
# Venta / Factura (transacción comercial definitiva)
# ---------------------------------------------------------------------


class Sale(TenantScopedModel, CommercialDocumentMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        CONFIRMED = "confirmed", "Confirmada"
        CANCELED = "canceled", "Cancelada"
        RETURNED = "returned", "Devuelta"
        PARTIALLY_RETURNED = "partially_returned", "Parcialmente devuelta"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Sin pagar"
        PARTIALLY_PAID = "partially_paid", "Pago parcial"
        PAID = "paid", "Pagada"
        REFUNDED = "refunded", "Reembolsada"
        PARTIALLY_REFUNDED = "partially_refunded", "Parcialmente reembolsada"

    number = models.CharField("número", max_length=30)
    issue_date = models.DateField("fecha", default=timezone.localdate)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    payment_status = models.CharField(
        "estado de pago", max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )

    source_quotation = models.OneToOneField(
        Quotation,
        verbose_name="cotización de origen",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="converted_sale_direct",
    )
    source_proforma = models.OneToOneField(
        ProformaInvoice,
        verbose_name="proforma de origen",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="converted_sale",
    )

    confirmed_at = models.DateTimeField("confirmada el", null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="confirmada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    canceled_at = models.DateTimeField("cancelada el", null=True, blank=True)
    canceled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="cancelada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    cancel_reason = models.CharField("motivo de cancelación", max_length=255, blank=True)

    class Meta:
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_sale_tenant_numero"),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "issue_date"], name="idx_sale_tenant_estado"),
            models.Index(fields=["tenant", "customer"], name="idx_sale_tenant_cliente"),
            models.Index(fields=["tenant", "payment_status"], name="idx_sale_tenant_pago"),
        ]

    def __str__(self):
        return self.number


class SaleItem(TenantScopedModel, CommercialDocumentItemMixin):
    sale = models.ForeignKey(Sale, verbose_name="venta", on_delete=models.CASCADE, related_name="items")
    # Costo (COGS) de esta línea — ampliación de cierre de FASE 14. Solo
    # `SaleItem` lo tiene (no el mixin compartido con Cotización/Proforma:
    # esas nunca mueven inventario real, no hay costo que snapshotear).
    # Se llena en `services.confirm_sale`, en el momento en que el
    # inventario REALMENTE se mueve — nunca al agregar la línea a un
    # borrador, porque el costo promedio ponderado puede cambiar entre
    # ambos momentos. Ver docs/accounting.md.
    cost_amount = models.DecimalField("costo (COGS)", max_digits=12, decimal_places=2, default=Decimal("0"))

    class Meta:
        verbose_name = "línea de venta"
        verbose_name_plural = "líneas de venta"
        ordering = ["line_order", "id"]


# ---------------------------------------------------------------------
# Pagos
# ---------------------------------------------------------------------


class Payment(TenantScopedModel):
    """Dinero recibido de un cliente — YA NO está atado a una única
    venta (ver `PaymentAllocation` más abajo, extensión obligatoria
    pedida explícitamente por el usuario tras el cierre inicial de
    FASE 10: "un Payment puede aplicarse a una o varias facturas del
    mismo Customer"). `Payment.customer` identifica de quién es el
    dinero; `PaymentAllocation` es el ledger que registra CONTRA QUÉ
    venta(s) se aplicó, cuánto de cada una. Un pago sin ninguna
    asignación todavía representa saldo a favor del cliente sin aplicar
    (ver `services.get_unallocated_payment_amount`/
    `get_customer_credit_balance`)."""

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmado"
        VOIDED = "voided", "Anulado"

    customer = models.ForeignKey(
        Customer,
        verbose_name="cliente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Vacío solo para el pago inmediato de una venta de mostrador sin cliente registrado.",
    )
    method = models.CharField("método", max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    reference = models.CharField("referencia", max_length=255, blank=True)
    idempotency_key = models.CharField(
        "clave de idempotencia",
        max_length=100,
        blank=True,
        help_text="Evita crear el mismo pago dos veces ante un reintento (p. ej. doble clic, reintento de red).",
    )
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "pago"
        verbose_name_plural = "pagos"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="payment_monto_positivo"),
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="unique_payment_tenant_idempotency_no_vacio",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "customer"], name="idx_payment_tenant_cliente"),
        ]

    def __str__(self):
        return f"{self.get_method_display()} {self.amount}"


class PaymentAllocation(TenantScopedModel):
    """Cuánto de un `Payment` se aplicó a qué `Sale` (factura) —
    el ledger de cuentas por cobrar. Un pago puede tener varias
    asignaciones (a varias facturas distintas); una factura puede
    recibir asignaciones de varios pagos distintos. Nunca se borra
    físicamente: `status=REVERSED` (con auditoría) deshace una
    asignación equivocada sin perder el rastro — misma filosofía que
    `Return` (FASE 10 original): inmutable, las correcciones son
    operaciones nuevas, no ediciones silenciosas."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        REVERSED = "reversed", "Reversada"

    payment = models.ForeignKey(Payment, verbose_name="pago", on_delete=models.PROTECT, related_name="allocations")
    sale = models.ForeignKey(Sale, verbose_name="venta", on_delete=models.PROTECT, related_name="payment_allocations")
    amount = models.DecimalField("monto aplicado", max_digits=12, decimal_places=2)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="aplicada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField("fecha", auto_now_add=True)
    reversed_at = models.DateTimeField("reversada el", null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="reversada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "asignación de pago"
        verbose_name_plural = "asignaciones de pago"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="paymentallocation_monto_positivo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "payment", "status"], name="idx_alloc_tenant_pago"),
            models.Index(fields=["tenant", "sale", "status"], name="idx_alloc_tenant_venta"),
        ]

    def __str__(self):
        return f"{self.amount} — pago #{self.payment_id} → {self.sale.number}"


class Refund(TenantScopedModel):
    """Devolución de DINERO, separada de `Return` (devolución de
    MERCANCÍA) — ver docstring del módulo. Sin integración real de
    pasarela todavía: se registra como `COMPLETED` de inmediato; FASE 16
    (PayPal) podrá introducir estados intermedios reales."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        COMPLETED = "completed", "Completado"
        FAILED = "failed", "Fallido"

    payment = models.ForeignKey(Payment, verbose_name="pago", on_delete=models.PROTECT, related_name="refunds")
    return_document = models.ForeignKey(
        "Return",
        verbose_name="devolución de mercancía asociada",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="refunds",
    )
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    reason = models.CharField("motivo", max_length=255, blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.COMPLETED)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "reembolso"
        verbose_name_plural = "reembolsos"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="refund_monto_positivo"),
        ]

    def __str__(self):
        return f"Reembolso {self.amount} — pago #{self.payment_id}"


# ---------------------------------------------------------------------
# Notas de crédito (FASE 11: cuentas por cobrar reales — ver
# docs/accounts-receivable.md, especificado desde la sincronización
# previa a FASE 11). Estructuralmente análoga a Payment/PaymentAllocation:
# `CreditNoteApplication` es el mismo tipo de ledger append-only, con la
# misma disciplina de validación (nunca sobre-aplica, nunca cruza
# tenant/cliente, corrige con reversa nunca con edición). El saldo a
# favor del cliente (`services.get_customer_credit_balance`) se
# generaliza para sumar también el saldo sin aplicar de sus notas de
# crédito — nunca un segundo balance paralelo al de `Payment`.
# ---------------------------------------------------------------------


class CreditNote(TenantScopedModel):
    """Crédito compensatorio a favor de un cliente, independiente de que
    exista o no una devolución física asociada. Nunca altera una factura
    histórica — la nota de crédito es el instrumento que compensa la
    diferencia, no una edición retroactiva."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        ISSUED = "issued", "Emitida"
        PARTIALLY_APPLIED = "partially_applied", "Aplicada parcialmente"
        FULLY_APPLIED = "fully_applied", "Aplicada por completo"
        CANCELED = "canceled", "Cancelada"

    class SourceType(models.TextChoices):
        MANUAL = "manual", "Manual"
        RETURN = "return", "Devolución de mercancía"
        REFUND = "refund", "Reembolso convertido a crédito"

    customer = models.ForeignKey(Customer, verbose_name="cliente", on_delete=models.PROTECT, related_name="+")
    number = models.CharField("número", max_length=30)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    currency = models.CharField(
        "moneda", max_length=3, default="USD",
        help_text="Snapshot de la moneda del cliente al momento de emitirse — nunca recalculado si "
        "el cliente cambia de moneda después (mismo principio de snapshot que Sale.currency).",
    )
    reason = models.CharField("motivo", max_length=255, blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    source_type = models.CharField("origen", max_length=20, choices=SourceType.choices, default=SourceType.MANUAL)
    source_return = models.ForeignKey(
        "Return",
        verbose_name="devolución de origen",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="credit_notes",
    )
    source_payment = models.ForeignKey(
        Payment,
        verbose_name="pago de origen (reembolso convertido a crédito)",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="credit_notes_generated",
    )
    issue_date = models.DateField("fecha de emisión", default=timezone.localdate)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="emitida por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField("creada", auto_now_add=True)
    canceled_at = models.DateTimeField("cancelada el", null=True, blank=True)
    canceled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="cancelada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "nota de crédito"
        verbose_name_plural = "notas de crédito"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_creditnote_tenant_numero"),
            models.CheckConstraint(check=models.Q(amount__gt=0), name="creditnote_monto_positivo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "customer", "status"], name="idx_creditnote_tenant_cliente"),
        ]

    def __str__(self):
        return self.number


class CreditNoteApplication(TenantScopedModel):
    """Cuánto de una `CreditNote` se aplicó a qué `Sale` — el ledger
    append-only, mismo patrón que `PaymentAllocation`. Nunca se edita:
    una aplicación equivocada se corrige con `status=REVERSED`."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        REVERSED = "reversed", "Reversada"

    credit_note = models.ForeignKey(
        CreditNote, verbose_name="nota de crédito", on_delete=models.PROTECT, related_name="applications"
    )
    sale = models.ForeignKey(
        Sale, verbose_name="venta", on_delete=models.PROTECT, related_name="credit_note_applications"
    )
    amount = models.DecimalField("monto aplicado", max_digits=12, decimal_places=2)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="aplicada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField("fecha", auto_now_add=True)
    reversed_at = models.DateTimeField("reversada el", null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="reversada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "aplicación de nota de crédito"
        verbose_name_plural = "aplicaciones de nota de crédito"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="creditnoteapp_monto_positivo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "credit_note", "status"], name="idx_cnapp_tenant_nota"),
            models.Index(fields=["tenant", "sale", "status"], name="idx_cnapp_tenant_venta"),
        ]

    def __str__(self):
        return f"{self.amount} — nota {self.credit_note.number} → {self.sale.number}"


# ---------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------


class Reservation(TenantScopedModel):
    """Capa "blanda" sobre el inventario real — ver docstring del
    módulo. NUNCA crea un `StockMovement`; para SERIALIZED transiciona
    `InventoryUnit.status` a `RESERVADO` reutilizando la máquina de
    estados de FASE 8."""

    class SourceType(models.TextChoices):
        QUOTATION = "quotation", "Cotización"
        PROFORMA = "proforma", "Proforma"
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        RELEASED = "released", "Liberada"
        CONVERTED = "converted", "Convertida en venta"
        EXPIRED = "expired", "Vencida"

    source_type = models.CharField("origen", max_length=20, choices=SourceType.choices, default=SourceType.MANUAL)
    source_id = models.PositiveBigIntegerField("ID del documento de origen", null=True, blank=True)
    customer = models.ForeignKey(
        Customer, verbose_name="cliente", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    product = models.ForeignKey(Product, verbose_name="producto", on_delete=models.PROTECT, related_name="+")
    inventory_unit = models.ForeignKey(
        InventoryUnit,
        verbose_name="unidad de inventario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    quantity = models.DecimalField(
        "cantidad reservada", max_digits=12, decimal_places=3, null=True, blank=True
    )
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField("vence el", null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="creada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    released_at = models.DateTimeField("liberada el", null=True, blank=True)
    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "reserva"
        verbose_name_plural = "reservas"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(quantity__isnull=False) & models.Q(inventory_unit__isnull=True))
                    | (models.Q(quantity__isnull=True) & models.Q(inventory_unit__isnull=False))
                ),
                name="reservation_cantidad_xor_unidad",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "product", "status"], name="idx_reservation_tenant_prod"),
            models.Index(fields=["tenant", "status"], name="idx_reservation_tenant_estado"),
        ]

    def __str__(self):
        objetivo = self.inventory_unit_id or f"{self.quantity} x {self.product.sku}"
        return f"Reserva {objetivo} ({self.get_status_display()})"


# ---------------------------------------------------------------------
# Devoluciones (mercancía) y Reembolsos (dinero, ver arriba)
# ---------------------------------------------------------------------


class Return(TenantScopedModel):
    """Devolución de MERCANCÍA. Inmutable una vez creada (sin estados ni
    cancelación) — ver docstring del módulo."""

    sale = models.ForeignKey(Sale, verbose_name="venta", on_delete=models.PROTECT, related_name="returns")
    number = models.CharField("número", max_length=30)
    reason = models.CharField("motivo", max_length=255, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "devolución"
        verbose_name_plural = "devoluciones"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_return_tenant_numero"),
        ]

    def __str__(self):
        return self.number


class ReturnItem(TenantScopedModel):
    return_document = models.ForeignKey(Return, verbose_name="devolución", on_delete=models.CASCADE, related_name="items")
    sale_item = models.ForeignKey(SaleItem, verbose_name="línea de venta", on_delete=models.PROTECT, related_name="+")
    inventory_unit = models.ForeignKey(
        InventoryUnit,
        verbose_name="unidad de inventario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    quantity_returned = models.DecimalField(
        "cantidad devuelta", max_digits=12, decimal_places=3, null=True, blank=True
    )
    condition_notes = models.CharField("condición / notas", max_length=255, blank=True)

    class Meta:
        verbose_name = "línea de devolución"
        verbose_name_plural = "líneas de devolución"
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(quantity_returned__isnull=False) & models.Q(inventory_unit__isnull=True))
                    | (models.Q(quantity_returned__isnull=True) & models.Q(inventory_unit__isnull=False))
                ),
                name="returnitem_cantidad_xor_unidad",
            ),
        ]

    def __str__(self):
        objetivo = self.inventory_unit_id or self.quantity_returned
        return f"Devolución {objetivo} ({self.return_document.number})"


# ---------------------------------------------------------------------
# Documentos adjuntos (reutiliza FASE 9 — "no crear un segundo sistema de archivos")
# ---------------------------------------------------------------------


def _ruta_documento_comercial(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"ventas/{instance.tenant_id}/{instance.document_type}/{instance.document_id}/{uuid.uuid4().hex}{extension}"


class SalesDocumentAttachment(TenantScopedModel, DocumentoBaseMixin):
    """Adjunto de Cotización/Proforma/Venta. Reutiliza literalmente la
    validación de archivos y las categorías de FASE 9
    (`apps.customers.file_validation`/`DocumentCategory`) — nunca se
    reimplementa esa lógica aquí."""

    class DocumentType(models.TextChoices):
        QUOTATION = "quotation", "Cotización"
        PROFORMA = "proforma", "Proforma"
        SALE = "sale", "Venta / Factura"

    document_type = models.CharField("tipo de documento", max_length=20, choices=DocumentType.choices)
    document_id = models.PositiveBigIntegerField("ID del documento")
    file = models.FileField(
        "archivo",
        upload_to=_ruta_documento_comercial,
        validators=[FileExtensionValidator(allowed_extensions=EXTENSIONES_DOCUMENTO_PERMITIDAS)],
    )

    class Meta:
        verbose_name = "documento adjunto de venta"
        verbose_name_plural = "documentos adjuntos de venta"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(
                fields=["tenant", "document_type", "document_id"], name="idx_salesdoc_tenant_documento"
            ),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.document_type} #{self.document_id})"


@receiver(post_delete, sender=SalesDocumentAttachment)
def _eliminar_archivo_adjunto_venta(sender, instance, **kwargs):
    """Mismo patrón que FASE 9 (`apps.customers.models`): limpia el
    archivo físico ante cualquier camino de borrado, capturando
    `OSError` sin propagarlo (ver esa nota para el razonamiento
    completo)."""
    if instance.file:
        try:
            instance.file.delete(save=False)
        except OSError:
            logger.exception(
                "No se pudo borrar el archivo físico del adjunto eliminado: %s", instance.file.name
            )


# ---------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo — ver docstring del módulo)
# ---------------------------------------------------------------------


class SalesActivityLog(TenantScopedModel):
    class Action(models.TextChoices):
        CREATED = "created", "Creación"
        UPDATED = "updated", "Edición"
        SENT = "sent", "Enviada"
        ACCEPTED = "accepted", "Aceptada"
        REJECTED = "rejected", "Rechazada"
        EXPIRED = "expired", "Vencida"
        CANCELED = "canceled", "Cancelada"
        CONVERTED = "converted", "Convertida"
        ISSUED = "issued", "Emitida"
        RESERVED = "reserved", "Reservada"
        RELEASED = "released", "Liberada"
        CONFIRMED = "confirmed", "Confirmada"
        PAYMENT_RECORDED = "payment_recorded", "Pago registrado"
        PAYMENT_VOIDED = "payment_voided", "Pago anulado"
        PAYMENT_ALLOCATED = "payment_allocated", "Pago aplicado a factura"
        PAYMENT_ALLOCATION_REVERSED = "payment_allocation_reversed", "Aplicación de pago reversada"
        RETURNED = "returned", "Devuelta"
        REFUNDED = "refunded", "Reembolsada"
        REFUND_CONVERTED_TO_CREDIT = "refund_converted_to_credit", "Reembolso convertido a crédito"
        CREDIT_NOTE_ISSUED = "credit_note_issued", "Nota de crédito emitida"
        CREDIT_NOTE_APPLIED = "credit_note_applied", "Nota de crédito aplicada a factura"
        CREDIT_NOTE_APP_REVERSED = "credit_note_app_reversed", "Aplicación de nota de crédito reversada"
        CREDIT_NOTE_CANCELED = "credit_note_canceled", "Nota de crédito cancelada"
        ATTACHMENT_UPLOADED = "attachment_uploaded", "Adjunto subido"
        ATTACHMENT_DELETED = "attachment_deleted", "Adjunto eliminado"

    entity_type = models.CharField("tipo de entidad", max_length=20)  # "quotation" | "proforma" | "sale"
    entity_id = models.PositiveBigIntegerField("id de la entidad")
    entity_label = models.CharField("identificador de la entidad (al momento del evento)", max_length=255, blank=True)
    action = models.CharField("acción", max_length=30, choices=Action.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    details = models.CharField("detalles", max_length=255, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "registro de actividad (ventas)"
        verbose_name_plural = "registros de actividad (ventas)"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["tenant", "entity_type", "entity_id", "created_at"], name="idx_salesactivity_tenant_ent"
            ),
        ]

    def __str__(self):
        return f"{self.get_action_display()} · {self.entity_type} #{self.entity_id}"
