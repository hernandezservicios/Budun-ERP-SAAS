"""
Transferencia bancaria (FASE 17, ver `docs/billing.md` secciones 13/25/26).
`BankAccount` (cuentas de la PLATAFORMA, no de un tenant) NO hereda
`TenantScopedModel` — mismo criterio que `PayPalGatewayStatus`.
`PaymentProof` sí hereda `TenantScopedModel`: pertenece a un tenant
concreto y ese tenant lo sube/consulta desde su propio Portal de
Billing. El archivo se guarda con el mismo mecanismo ya establecido en
todo el proyecto para adjuntos sensibles (`MEDIA_ROOT="media-private/"`,
nunca servido públicamente, nombre de archivo generado — nunca el
original — ver `apps.customers.models`)."""

import os
import uuid

from django.conf import settings
from django.db import models

from apps.tenants.models import TenantScopedModel

from .core import Subscription
from .invoicing import SaaSInvoice


class BankAccount(models.Model):
    bank_name = models.CharField("banco", max_length=100)
    country = models.CharField("país", max_length=100, blank=True)
    currency = models.CharField("moneda", max_length=3, default="USD")
    account_holder = models.CharField("titular", max_length=150)
    account_number = models.CharField("cuenta / IBAN", max_length=50)
    account_type = models.CharField("tipo de cuenta", max_length=30, blank=True)
    is_active = models.BooleanField("activa", default=True)
    priority = models.PositiveIntegerField("prioridad", default=0, help_text="Menor número = se muestra primero.")
    notes = models.TextField("notas", blank=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "cuenta bancaria de la plataforma"
        verbose_name_plural = "cuentas bancarias de la plataforma"
        ordering = ["priority", "bank_name"]

    def __str__(self):
        return f"{self.bank_name} ({self.currency}) — {self.account_holder}"


def _ruta_comprobante_pago(instance, filename):
    """Nunca el nombre original — mismo criterio de defensa que
    `apps.customers.models._ruta_documento_cliente` (path traversal /
    colisiones)."""
    extension = os.path.splitext(filename)[1].lower()
    return f"billing/comprobantes/{instance.tenant_id}/{uuid.uuid4().hex}{extension}"


class PaymentProof(TenantScopedModel):
    """Comprobante de transferencia — nunca público (ver
    `apps.billing.portal_views`/`admin_views`, siempre servido por una
    vista protegida que verifica tenant/plataforma, nunca `MEDIA_URL`
    estático). Estados de verificación exactamente los pedidos en la
    sección 26 de la fase."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        SUBMITTED = "submitted", "Enviado"
        UNDER_REVIEW = "under_review", "En revisión"
        APPROVED = "approved", "Aprobado"
        REJECTED = "rejected", "Rechazado"
        REVERSED = "reversed", "Reversado"

    subscription = models.ForeignKey(Subscription, verbose_name="suscripción", on_delete=models.PROTECT, related_name="payment_proofs")
    invoice = models.ForeignKey(SaaSInvoice, verbose_name="factura", on_delete=models.PROTECT, related_name="payment_proofs")
    bank_account = models.ForeignKey(BankAccount, verbose_name="cuenta receptora", on_delete=models.PROTECT, related_name="+")
    reference = models.CharField("referencia", max_length=50)
    declared_amount = models.DecimalField("monto declarado", max_digits=12, decimal_places=2)
    declared_currency = models.CharField("moneda declarada", max_length=3, default="USD")
    declared_bank_name = models.CharField("banco de origen declarado", max_length=100, blank=True)
    file = models.FileField("archivo", upload_to=_ruta_comprobante_pago)
    original_filename = models.CharField("nombre original", max_length=255)
    content_type = models.CharField("tipo de contenido", max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField("tamaño (bytes)")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="subido por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    uploaded_at = models.DateTimeField("subido", auto_now_add=True)
    status = models.CharField("estado", max_length=15, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="revisado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    reviewed_at = models.DateTimeField("revisado", null=True, blank=True)
    rejection_reason = models.CharField("motivo de rechazo", max_length=255, blank=True)

    class Meta:
        verbose_name = "comprobante de pago"
        verbose_name_plural = "comprobantes de pago"
        ordering = ["-uploaded_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "reference"], name="unique_paymentproof_referencia_tenant"),
        ]

    def __str__(self):
        return f"{self.reference} ({self.get_status_display()})"


def _eliminar_archivo_al_borrar_comprobante(sender, instance, **kwargs):
    """Mismo patrón que `apps.customers.models`/`apps.inventory.models`:
    nunca deja un archivo huérfano en disco, nunca rompe el borrado si
    Windows todavía tiene el archivo abierto en el mismo proceso."""
    if instance.file:
        try:
            instance.file.delete(save=False)
        except OSError:
            pass


models.signals.post_delete.connect(_eliminar_archivo_al_borrar_comprobante, sender=PaymentProof)
