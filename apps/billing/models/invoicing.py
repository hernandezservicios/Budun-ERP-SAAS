"""
Facturación y pagos de Billing SaaS (FASE 17, ver `docs/billing.md`).
Todos estos modelos heredan `TenantScopedModel` (a diferencia de los de
FASE 16): pertenecen a exactamente un tenant y ese mismo tenant los
consulta en su Portal de Billing dentro de una request normal — el
Super Admin cruza tenants vía `all_objects`, mismo patrón dual que
`ApiKey`/`Integration` (FASE 15) y que `Subscription` (`core.py`).

Anticipo/saldo a favor (secciones 20-21 de la fase) se generalizan
EXACTAMENTE como ya se decidió para Cuentas por Cobrar del ERP
(`docs/accounts-receivable.md`, `CustomerCreditLedger` descartado): NO
existe una tabla de "saldo a favor" separada — se calculan siempre
sumando `SaaSPayment`/`SaaSPaymentAllocation` y `CreditNote`/
`CreditNoteApplication` (ver `apps.billing.services.credits`), nunca
una tercera fuente de verdad."""

from django.conf import settings
from django.db import models

from apps.tenants.models import TenantScopedModel

from .core import SaaSCustomer, Subscription


class SaaSInvoice(TenantScopedModel):
    """Factura de Billing SaaS — inmutable en sus datos económicos una
    vez emitida (nunca se edita `subtotal`/`total`/etc. después; una
    corrección real es una `CreditNote`, mismo principio de
    inmutabilidad que `Sale`/`JournalEntry`). `UniqueConstraint` sobre
    `(subscription, period_start)` es la garantía de idempotencia real
    de la generación recurrente (sección 11 de la fase: "debe evitar
    duplicar la misma factura para el mismo período") — nunca depende
    solo de que el código "no se llame dos veces"."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        OPEN = "open", "Pendiente de pago"
        PAID = "paid", "Pagada"
        PARTIALLY_PAID = "partially_paid", "Parcialmente pagada"
        VOID = "void", "Anulada"

    subscription = models.ForeignKey(Subscription, verbose_name="suscripción", on_delete=models.PROTECT, related_name="invoices")
    number = models.CharField("número", max_length=30)
    period_start = models.DateField("inicio del período")
    period_end = models.DateField("fin del período")
    issue_date = models.DateField("fecha de emisión")
    due_date = models.DateField("fecha de vencimiento")
    currency = models.CharField("moneda", max_length=3, default="USD")
    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField("descuento", max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField("impuesto", max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField("total", max_digits=12, decimal_places=2, default=0)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    coupon_code_snapshot = models.CharField("cupón aplicado", max_length=50, blank=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "factura de Billing SaaS"
        verbose_name_plural = "facturas de Billing SaaS"
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["subscription", "period_start"], name="unique_saasinvoice_periodo"),
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_saasinvoice_numero_tenant"),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "due_date"], name="idx_saasinvoice_tenant_estado"),
        ]

    def __str__(self):
        return self.number


class SaaSInvoiceLine(TenantScopedModel):
    invoice = models.ForeignKey(SaaSInvoice, verbose_name="factura", on_delete=models.CASCADE, related_name="lines")
    description = models.CharField("descripción", max_length=255)
    quantity = models.DecimalField("cantidad", max_digits=10, decimal_places=2, default=1)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "línea de factura de Billing SaaS"
        verbose_name_plural = "líneas de factura de Billing SaaS"

    def __str__(self):
        return f"{self.description} — {self.amount}"


class SaaSPayment(TenantScopedModel):
    """Pago SaaS — espejo estructural de `apps.sales.Payment`, nunca la
    misma tabla (mismo criterio ya aplicado en todo el proyecto a
    `SupplierPayment`/`Payment`). `paypal_transaction` referencia el
    detalle específico de PayPal (FASE 16, `apps.billing.models.
    PayPalTransaction`) cuando `method=PAYPAL` — nunca se duplican sus
    campos aquí (external_order_id/capture_id, etc. viven solo allá)."""

    class Method(models.TextChoices):
        PAYPAL = "paypal", "PayPal"
        BANK_TRANSFER = "bank_transfer", "Transferencia bancaria"
        MANUAL_OTHER = "manual_other", "Otro (manual)"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        CONFIRMED = "confirmed", "Confirmado"
        FAILED = "failed", "Fallido"
        REFUNDED = "refunded", "Reembolsado"
        PARTIALLY_REFUNDED = "partially_refunded", "Parcialmente reembolsado"

    saas_customer = models.ForeignKey(SaaSCustomer, verbose_name="cliente SaaS", on_delete=models.PROTECT, related_name="payments")
    subscription = models.ForeignKey(
        Subscription, verbose_name="suscripción", on_delete=models.SET_NULL, null=True, blank=True, related_name="payments",
    )
    method = models.CharField("método", max_length=15, choices=Method.choices)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.PENDING)
    paypal_transaction = models.ForeignKey(
        "billing.PayPalTransaction", verbose_name="transacción PayPal", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    payment_proof = models.ForeignKey(
        "billing.PaymentProof", verbose_name="comprobante", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    external_reference = models.CharField("referencia externa", max_length=100, blank=True)
    received_at = models.DateTimeField("recibido", null=True, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "pago SaaS"
        verbose_name_plural = "pagos SaaS"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_saaspayment_tenant_estado"),
        ]

    def __str__(self):
        return f"{self.amount} {self.currency} — {self.get_method_display()} ({self.get_status_display()})"


class SaaSPaymentAllocation(TenantScopedModel):
    """Ledger append-only — espejo exacto de `apps.sales.
    PaymentAllocation`: un `SaaSPayment` puede aplicarse a una o varias
    `SaaSInvoice`, nunca excede lo disponible del pago ni el saldo
    pendiente de la factura, y una corrección es un reverso
    (`status=REVERSED`), nunca una edición in-place."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        REVERSED = "reversed", "Reversada"

    payment = models.ForeignKey(SaaSPayment, verbose_name="pago", on_delete=models.PROTECT, related_name="allocations")
    invoice = models.ForeignKey(SaaSInvoice, verbose_name="factura", on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField("monto aplicado", max_digits=12, decimal_places=2)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField("creada", auto_now_add=True)
    reversed_at = models.DateTimeField("reversada", null=True, blank=True)
    reversal_reason = models.CharField("motivo del reverso", max_length=255, blank=True)

    class Meta:
        verbose_name = "aplicación de pago SaaS"
        verbose_name_plural = "aplicaciones de pago SaaS"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.amount} → {self.invoice.number}"


class CreditNote(TenantScopedModel):
    """Nota de crédito de Billing SaaS — espejo de `apps.sales.
    CreditNote`, nunca la misma tabla. Inmutable una vez emitida (nunca
    se edita el monto): el saldo disponible se deriva siempre de
    `amount - SUM(CreditNoteApplication activas)`, nunca un campo
    desnormalizado."""

    saas_customer = models.ForeignKey(SaaSCustomer, verbose_name="cliente SaaS", on_delete=models.PROTECT, related_name="credit_notes")
    subscription = models.ForeignKey(
        Subscription, verbose_name="suscripción", on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_notes",
    )
    number = models.CharField("número", max_length=30)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    reason = models.CharField("motivo", max_length=255)
    created_at = models.DateTimeField("creada", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "nota de crédito de Billing SaaS"
        verbose_name_plural = "notas de crédito de Billing SaaS"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_saascreditnote_numero_tenant"),
        ]

    def __str__(self):
        return self.number


class CreditNoteApplication(TenantScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        REVERSED = "reversed", "Reversada"

    credit_note = models.ForeignKey(CreditNote, verbose_name="nota de crédito", on_delete=models.PROTECT, related_name="applications")
    invoice = models.ForeignKey(SaaSInvoice, verbose_name="factura", on_delete=models.PROTECT, related_name="credit_note_applications")
    amount = models.DecimalField("monto aplicado", max_digits=12, decimal_places=2)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField("creada", auto_now_add=True)
    reversed_at = models.DateTimeField("reversada", null=True, blank=True)

    class Meta:
        verbose_name = "aplicación de nota de crédito de Billing SaaS"
        verbose_name_plural = "aplicaciones de nota de crédito de Billing SaaS"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.amount} → {self.invoice.number}"


class BillingRefund(TenantScopedModel):
    """Refund de Billing SaaS — llamado `BillingRefund` (no `Refund`)
    para nunca confundirse con `apps.sales.Refund` (ERP del tenant) ni
    con el seguimiento interno de refund de `PayPalTransaction` (FASE
    16, que ya registra el estado del lado de PayPal — este modelo es
    el registro de NEGOCIO: "este pago SaaS fue reembolsado", sin
    importar el método)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        COMPLETED = "completed", "Completado"
        FAILED = "failed", "Fallido"

    payment = models.ForeignKey(SaaSPayment, verbose_name="pago", on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDING)
    reason = models.CharField("motivo", max_length=255, blank=True)
    paypal_transaction = models.ForeignKey(
        "billing.PayPalTransaction", verbose_name="transacción PayPal", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("creado", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    completed_at = models.DateTimeField("completado", null=True, blank=True)

    class Meta:
        verbose_name = "reembolso de Billing SaaS"
        verbose_name_plural = "reembolsos de Billing SaaS"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.amount} {self.currency} ({self.get_status_display()})"
