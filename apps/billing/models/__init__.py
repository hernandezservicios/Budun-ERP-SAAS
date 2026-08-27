"""
Billing SaaS — PayPal (FASE 16, ver `docs/paypal.md`).

Estos modelos son deliberadamente del **Billing SaaS** (lo que un
`Tenant` le paga a Budun ERP), NUNCA del ERP operativo de cada tenant:
no heredan `TenantScopedModel` (ese mecanismo filtra automáticamente
por el tenant ACTIVO de la request, pensado para datos operativos de
un tenant — aquí el actor es el Super Admin de la PLATAFORMA, que
necesita ver/operar sobre transacciones de CUALQUIER tenant). Mismo
principio ya usado por `apps.audit.AuditLog`/`apps.tenants.Membership`
(ver sus propios docstrings): `tenant` es una FK de referencia normal,
nunca un campo tenant-scoping.

No se crea aquí ningún modelo de `Plan`/`Subscription`/`SaaS Invoice`
(eso es FASE 17, ver `docs/billing.md`) — `PayPalTransaction`
representa únicamente un intento de cobro vía PayPal (una orden de la
Orders API v2), identificado por sus propios IDs externos. FASE 17
decidirá cómo su futuro `SaaS Payment` referencia estas transacciones
(o las adopta como su propio detalle de proveedor) — el vocabulario de
eventos (`services.payment_confirmed`/`refund_completed`, señales de
Django) es el contrato estable que FASE 17 consumirá, documentado en
`docs/paypal.md`.
"""

from django.conf import settings
from django.db import models

from apps.tenants.models import Tenant


class PayPalGatewayStatus(models.Model):
    """Estado operativo del gateway de PayPal de la PLATAFORMA — fila
    única (singleton, `pk=1`, ver `services.get_gateway_status`). Las
    credenciales (Client ID/Secret) NUNCA viven aquí: son variables de
    entorno de la plataforma (`PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`
    /`PAYPAL_ENVIRONMENT`/`PAYPAL_WEBHOOK_ID` en `.env`, mismo criterio
    que `DJANGO_SECRET_KEY`/`DB_PASSWORD`) — esta fila solo registra el
    resultado de la última "Probar Conexión" y un interruptor
    administrativo para desactivar el checkout sin tocar variables de
    entorno ni reiniciar el proceso."""

    is_enabled = models.BooleanField("checkout habilitado", default=True)
    last_tested_at = models.DateTimeField("última prueba", null=True, blank=True)
    last_test_ok = models.BooleanField("última prueba exitosa", null=True, blank=True)
    last_test_error = models.CharField("último error", max_length=255, blank=True)
    last_tested_environment = models.CharField("ambiente probado", max_length=10, blank=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "estado del gateway PayPal"
        verbose_name_plural = "estado del gateway PayPal"

    def __str__(self):
        return f"PayPal gateway ({'habilitado' if self.is_enabled else 'deshabilitado'})"


class PayPalTransaction(models.Model):
    """Un intento de cobro vía PayPal Orders API v2 (pago inicial o
    renovación de la suscripción de un tenant al SaaS). NUNCA
    `apps.sales.Payment` — dominio completamente distinto (ver
    `docs/paypal.md` sección 1).

    `environment` es un snapshot (nunca cambia aunque la configuración
    de la plataforma cambie después) — mismo principio de snapshot ya
    usado en `SaleItem`/`PurchaseOrderItem`/`Subscription.currency`
    (spec). Los identificadores externos se mantienen SEPARADOS entre
    sí (orden/captura/reembolso) y separados del estado interno
    (`status`) — nunca un único campo que confunda los tres (ver
    `docs/paypal.md` sección 5)."""

    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Alta inicial"
        RENEWAL = "renewal", "Renovación"

    class Environment(models.TextChoices):
        SANDBOX = "SANDBOX", "Sandbox"
        LIVE = "LIVE", "Live"

    class Status(models.TextChoices):
        CREATED = "created", "Creada (esperando aprobación del pagador)"
        PENDING_CAPTURE = "pending_capture", "Captura pendiente (asíncrona)"
        CONFIRMED = "confirmed", "Confirmada (dinero capturado)"
        FAILED = "failed", "Fallida"
        CANCELLED = "cancelled", "Cancelada por el pagador"
        REFUND_PENDING = "refund_pending", "Reembolso pendiente"
        REFUNDED = "refunded", "Reembolsada"
        REFUND_FAILED = "refund_failed", "Reembolso fallido"

    tenant = models.ForeignKey(
        Tenant, verbose_name="tenant", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Puede ser nulo: un alta inicial puede ocurrir antes de que exista el Tenant (FASE 17 lo resolverá).",
    )
    plan_id = models.CharField("plan", max_length=50, help_text="Referencia a apps.core.pricing.PLANS[].id.")
    purpose = models.CharField("propósito", max_length=10, choices=Purpose.choices)
    environment = models.CharField("ambiente", max_length=10, choices=Environment.choices)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.CREATED)

    amount = models.DecimalField("monto interno", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda interna", max_length=3, default="USD")
    provider_amount = models.DecimalField("monto reportado por PayPal", max_digits=12, decimal_places=2, null=True, blank=True)
    provider_currency = models.CharField("moneda reportada por PayPal", max_length=3, blank=True)

    client_reference = models.UUIDField("referencia de idempotencia propia", unique=True, editable=False)
    external_order_id = models.CharField("ID de orden PayPal", max_length=64, blank=True, db_index=True)
    external_capture_id = models.CharField("ID de captura PayPal", max_length=64, blank=True, db_index=True)
    external_refund_id = models.CharField("ID de reembolso PayPal", max_length=64, blank=True, db_index=True)

    failure_reason = models.CharField("motivo del fallo", max_length=255, blank=True)

    created_at = models.DateTimeField("creada", auto_now_add=True)
    updated_at = models.DateTimeField("actualizada", auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    confirmed_at = models.DateTimeField("confirmada", null=True, blank=True)
    cancelled_at = models.DateTimeField("cancelada", null=True, blank=True)
    refunded_at = models.DateTimeField("reembolsada", null=True, blank=True)

    class Meta:
        verbose_name = "transacción PayPal"
        verbose_name_plural = "transacciones PayPal"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["external_order_id"], name="unique_paypaltransaction_order",
                condition=~models.Q(external_order_id=""),
            ),
            models.UniqueConstraint(
                fields=["external_capture_id"], name="unique_paypaltransaction_capture",
                condition=~models.Q(external_capture_id=""),
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "created_at"], name="idx_paypaltx_tenant_fecha"),
            models.Index(fields=["status", "created_at"], name="idx_paypaltx_estado_fecha"),
        ]

    def __str__(self):
        return f"PayPal {self.external_order_id or '(sin orden)'} — {self.get_status_display()}"


class PayPalWebhookEvent(models.Model):
    """Registro/ledger de idempotencia de webhooks (FASE 16, ver
    `docs/paypal.md` sección 6 y `docs/phases/PHASE-16-paypal-sandbox.md`
    sección 16). `event_id` (el `id` que PayPal asigna a cada evento) es
    la llave de idempotencia real — su `UniqueConstraint` es lo que
    garantiza a nivel de BASE DE DATOS que dos entregas simultáneas del
    mismo evento (reintento de PayPal, o dos workers) nunca se procesen
    dos veces (ver `services.process_webhook_event`). `summary` guarda
    solo un subconjunto mínimo y seguro del payload (nunca el payload
    completo, que podría incluir datos del pagador) — y NUNCA se guarda
    aquí ninguna cabecera/firma/token."""

    class Status(models.TextChoices):
        RECEIVED = "received", "Recibido"
        PROCESSED = "processed", "Procesado"
        DUPLICATE = "duplicate", "Duplicado (ignorado)"
        IGNORED = "ignored", "Ignorado (sin transacción asociada o evento no relevante)"
        REJECTED = "rejected", "Rechazado (firma inválida)"
        ERROR = "error", "Error al procesar"

    event_id = models.CharField("ID del evento PayPal", max_length=64, unique=True)
    event_type = models.CharField("tipo de evento", max_length=64, blank=True)
    transaction = models.ForeignKey(
        PayPalTransaction, verbose_name="transacción", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="webhook_events",
    )
    verification_status = models.CharField("resultado de verificación de firma", max_length=20, blank=True)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.RECEIVED)
    error_message = models.CharField("mensaje de error", max_length=255, blank=True)
    summary = models.JSONField("resumen seguro del evento", default=dict, blank=True)
    received_at = models.DateTimeField("recibido", auto_now_add=True)
    processed_at = models.DateTimeField("procesado", null=True, blank=True)

    class Meta:
        verbose_name = "evento de webhook PayPal"
        verbose_name_plural = "eventos de webhook PayPal"
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["event_type", "received_at"], name="idx_paypalwh_tipo_fecha"),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.event_id}) — {self.get_status_display()}"


# ------------------------------------------------------------------
# FASE 17 — Billing SaaS completo (ver docs/billing.md). Los modelos
# arriba (PayPalGatewayStatus/PayPalTransaction/PayPalWebhookEvent) son
# de FASE 16 y quedan sin cambios. Los de abajo se definieron en
# archivos separados (`core.py`/`policy.py`/`invoicing.py`/
# `transfers.py`/`coupons.py`) por volumen — Django los registra igual
# sin importar el archivo, siempre que se importen aquí, en el módulo
# canónico `apps.billing.models` que el registro de apps sí escanea.
# ------------------------------------------------------------------

from .policy import BillingPolicy  # noqa: E402,F401
from .core import Plan, PlanVersion, SaaSCustomer, Subscription  # noqa: E402,F401
from .coupons import Coupon  # noqa: E402,F401
from .invoicing import (  # noqa: E402,F401
    BillingRefund,
    CreditNote,
    CreditNoteApplication,
    SaaSInvoice,
    SaaSInvoiceLine,
    SaaSPayment,
    SaaSPaymentAllocation,
)
from .transfers import BankAccount, PaymentProof  # noqa: E402,F401
