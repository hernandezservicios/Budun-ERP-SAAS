"""
Gastos (FASE 13, ver `docs/expenses.md`): dominio de gastos operativos
del tenant — categorías configurables, gasto con máquina de estados y
autorización, pagos (ledger append-only, mismo principio que
`apps.sales.Payment`), documentos adjuntos y gastos recurrentes.

Reutiliza literalmente, nunca duplica:
- `apps.customers.models.Supplier` — proveedor opcional del gasto.
- `apps.customers.models.DocumentoBaseMixin`/`DocumentCategory`/
  `EXTENSIONES_DOCUMENTO_PERMITIDAS` (FASE 9) — mismo sistema de
  archivos seguro que `apps.sales.SalesDocumentAttachment`/
  `apps.purchases.PurchaseDocumentAttachment`.
- `apps.sales.models.PaymentMethod`/`DocumentSequence` — mismo
  vocabulario de métodos de pago y la misma tabla de numeración
  (`DocumentType.EXPENSE`, prefijo "GAS-").
- `apps.approvals.services` — gasto sobre el límite / excepcional,
  mismas primitivas que ya usan POS y Compras.
- `apps.pos.models.CashSession`/`apps.pos.services` — un pago de gasto
  en efectivo exige sesión de caja abierta y genera `CashMovement`.

`Expense` NUNCA guarda `paid_amount`/`balance_due` como campo: se
calculan siempre agregando sobre `ExpensePayment` (mismo principio de
"nunca una segunda fuente de verdad" desde FASE 8/10).
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

import logging
import os
import uuid

from apps.customers.models import (
    DocumentoBaseMixin,
    EXTENSIONES_DOCUMENTO_PERMITIDAS,
    Supplier,
)
from apps.pos.models import CashSession
from apps.sales.models import PaymentMethod
from apps.tenants.models import TenantScopedModel

logger = logging.getLogger("apps.expenses.documents")


# ---------------------------------------------------------------------
# Categorías de gasto — tenant-configurable, nunca una lista cerrada en
# código (ver `services.DEFAULT_EXPENSE_CATEGORIES` para las sugeridas).
# ---------------------------------------------------------------------


class ExpenseCategory(TenantScopedModel):
    name = models.CharField("nombre", max_length=100)
    description = models.CharField("descripción", max_length=255, blank=True)
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "categoría de gasto"
        verbose_name_plural = "categorías de gasto"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_expense_category_tenant_nombre"),
        ]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------
# Gasto
# ---------------------------------------------------------------------


class Expense(TenantScopedModel):
    """Un gasto operativo. Numerado vía `generate_document_number`
    (`DocumentSequence.DocumentType.EXPENSE`, prefijo "GAS-"). `total`
    se recalcula siempre en `services.py`, nunca se asigna a mano desde
    una vista/formulario."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PENDING_APPROVAL = "pending_approval", "Pendiente de aprobación"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"
        PARTIALLY_PAID = "partially_paid", "Parcialmente pagado"
        PAID = "paid", "Pagado"
        CANCELED = "canceled", "Cancelado"

    number = models.CharField("número", max_length=20, unique=False, db_index=True)
    category = models.ForeignKey(
        ExpenseCategory, verbose_name="categoría", on_delete=models.PROTECT, related_name="expenses"
    )
    supplier = models.ForeignKey(
        Supplier, verbose_name="proveedor", on_delete=models.PROTECT, related_name="expenses",
        null=True, blank=True, help_text="Opcional — no todo gasto tiene un proveedor formal (ej. propinas, peajes).",
    )
    description = models.CharField("descripción", max_length=255)
    expense_date = models.DateField("fecha del gasto")
    due_date = models.DateField("fecha de vencimiento", null=True, blank=True)
    currency = models.CharField(
        "moneda", max_length=3, default="USD",
        help_text="Snapshot al crearse (ver docs/currency.md) — nunca recalculado después.",
    )
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField("impuesto", max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_amount = models.DecimalField("descuento", max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("total", max_digits=12, decimal_places=2, default=Decimal("0"))
    preferred_payment_method = models.CharField(
        "método de pago previsto", max_length=20, choices=PaymentMethod.choices, blank=True,
        help_text="Método esperado — el/los pago(s) reales (`ExpensePayment`) pueden diferir.",
    )
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_exceptional = models.BooleanField(
        "excepcional", default=False,
        help_text="Marca el gasto como excepcional/sensible — exige autorización explícita "
        "independientemente del monto (ver docs/expenses.md).",
    )
    exceptional_reason = models.CharField("motivo de excepcionalidad", max_length=255, blank=True)
    source_recurrence = models.ForeignKey(
        "ExpenseRecurrence", verbose_name="generado por recurrencia", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="generated_expenses",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "gasto"
        verbose_name_plural = "gastos"
        ordering = ["-expense_date", "-id"]
        indexes = [
            models.Index(fields=["tenant", "status", "expense_date"], name="idx_expense_tenant_estado"),
            models.Index(fields=["tenant", "category"], name="idx_expense_tenant_categoria"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_expense_tenant_numero"),
            models.CheckConstraint(
                check=models.Q(amount__gte=0) & models.Q(tax_amount__gte=0) & models.Q(discount_amount__gte=0),
                name="expense_montos_no_negativos",
            ),
        ]

    def __str__(self):
        return f"{self.number} — {self.description}"


# ---------------------------------------------------------------------
# Pagos de gasto (ledger append-only, mismo principio que
# apps.sales.Payment/apps.purchases.SupplierPayment)
# ---------------------------------------------------------------------


class ExpensePayment(TenantScopedModel):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmado"
        VOIDED = "voided", "Anulado"

    expense = models.ForeignKey(Expense, verbose_name="gasto", on_delete=models.PROTECT, related_name="payments")
    method = models.CharField("método", max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    cash_session = models.ForeignKey(
        CashSession, verbose_name="sesión de caja", on_delete=models.PROTECT,
        null=True, blank=True, related_name="expense_payments",
        help_text="Solo cuando method=CASH — el efectivo físico se ve afectado únicamente en ese caso.",
    )
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    reference = models.CharField("referencia", max_length=100, blank=True)
    notes = models.CharField("notas", max_length=255, blank=True)
    idempotency_key = models.CharField("clave de idempotencia", max_length=100, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="registrado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "pago de gasto"
        verbose_name_plural = "pagos de gasto"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "expense"], name="idx_expensepay_tenant_gasto"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="unique_expensepayment_tenant_idempotency",
            ),
            models.CheckConstraint(check=models.Q(amount__gt=0), name="expensepayment_monto_positivo"),
        ]

    def __str__(self):
        return f"{self.get_method_display()} {self.amount} ({self.expense.number})"


# ---------------------------------------------------------------------
# Gastos recurrentes
# ---------------------------------------------------------------------


class ExpenseRecurrence(TenantScopedModel):
    """Plantilla de gasto recurrente. `generate_due_expense` crea un
    `Expense` DRAFT idempotente por (tenant, recurrencia, next_run_date)
    — nunca genera dos gastos para el mismo período."""

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Semanal"
        BIWEEKLY = "biweekly", "Quincenal"
        MONTHLY = "monthly", "Mensual"
        YEARLY = "yearly", "Anual"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        PAUSED = "paused", "Pausada"
        CANCELED = "canceled", "Cancelada"

    category = models.ForeignKey(
        ExpenseCategory, verbose_name="categoría", on_delete=models.PROTECT, related_name="recurrences"
    )
    supplier = models.ForeignKey(
        Supplier, verbose_name="proveedor", on_delete=models.PROTECT, related_name="expense_recurrences",
        null=True, blank=True,
    )
    description = models.CharField("descripción", max_length=255)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    frequency = models.CharField("frecuencia", max_length=20, choices=Frequency.choices)
    start_date = models.DateField("fecha de inicio")
    end_date = models.DateField("fecha de fin", null=True, blank=True)
    next_run_date = models.DateField("próxima fecha")
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "gasto recurrente"
        verbose_name_plural = "gastos recurrentes"
        ordering = ["next_run_date"]
        indexes = [
            models.Index(fields=["tenant", "status", "next_run_date"], name="idx_exprecur_tenant_estado"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="exprecurrence_monto_positivo"),
        ]

    def __str__(self):
        return f"{self.description} ({self.get_frequency_display()})"


# ---------------------------------------------------------------------
# Documentos adjuntos (reutiliza FASE 9 — no se crea un segundo sistema
# de archivos)
# ---------------------------------------------------------------------


def _ruta_documento_gasto(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"gastos/{instance.tenant_id}/{instance.expense_id}/{uuid.uuid4().hex}{extension}"


class ExpenseDocument(TenantScopedModel, DocumentoBaseMixin):
    """Adjunto de un gasto (comprobante/factura del proveedor/otro).
    Reutiliza literalmente `DocumentCategory`/la validación de FASE 9 —
    mismo patrón que `SalesDocumentAttachment`/`PurchaseDocumentAttachment`."""

    expense = models.ForeignKey(Expense, verbose_name="gasto", on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(
        "archivo",
        upload_to=_ruta_documento_gasto,
        validators=[FileExtensionValidator(allowed_extensions=EXTENSIONES_DOCUMENTO_PERMITIDAS)],
    )

    class Meta:
        verbose_name = "documento de gasto"
        verbose_name_plural = "documentos de gasto"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["tenant", "expense"], name="idx_expensedoc_tenant_gasto"),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.expense.number})"


@receiver(post_delete, sender=ExpenseDocument)
def _eliminar_archivo_adjunto_gasto(sender, instance, **kwargs):
    """Mismo patrón que FASE 9/10/12: limpia el archivo físico ante
    cualquier camino de borrado, capturando `OSError` sin propagarlo."""
    if instance.file:
        try:
            instance.file.delete(save=False)
        except OSError:
            logger.exception("No se pudo borrar el archivo físico del adjunto de gasto eliminado: %s", instance.file.name)


# ---------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo — mismo principio que
# apps.purchases.PurchasesActivityLog)
# ---------------------------------------------------------------------


class ExpensesActivityLog(TenantScopedModel):
    class Action(models.TextChoices):
        CREATED = "created", "Creación"
        UPDATED = "updated", "Edición"
        SUBMITTED = "submitted", "Enviado a aprobación"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"
        CANCELED = "canceled", "Cancelado"
        PAYMENT_RECORDED = "payment_recorded", "Pago registrado"
        PAYMENT_VOIDED = "payment_voided", "Pago anulado"
        RECURRENCE_GENERATED = "recurrence_generated", "Generado por recurrencia"
        RECURRENCE_PAUSED = "recurrence_paused", "Recurrencia pausada"
        RECURRENCE_RESUMED = "recurrence_resumed", "Recurrencia reanudada"
        RECURRENCE_CANCELED = "recurrence_canceled", "Recurrencia cancelada"
        ATTACHMENT_UPLOADED = "attachment_uploaded", "Adjunto subido"
        ATTACHMENT_DELETED = "attachment_deleted", "Adjunto eliminado"

    entity_type = models.CharField("tipo de entidad", max_length=25)
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
        verbose_name = "registro de actividad (gastos)"
        verbose_name_plural = "registros de actividad (gastos)"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "entity_type", "entity_id"], name="idx_expenselog_tenant_entidad"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.entity_type} #{self.entity_id}"
