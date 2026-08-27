"""
Auditoría transversal (FASE 15, ver `docs/audit.md`). Este es el ÚNICO
log genuinamente transversal del proyecto — NO reemplaza los 7 logs
ya existentes por dominio (`SalesActivityLog`, `ActivityLog` de
`apps.customers`, `AccountingActivityLog`, `ExpensesActivityLog`,
`HRActivityLog`, `PayrollActivityLog`, `PurchasesActivityLog`), que
siguen siendo la fuente de verdad de la actividad operativa de cada
módulo. `AuditLog` complementa esos 7 registrando lo que ninguno de
ellos puede: eventos que no pertenecen a un solo dominio de negocio
(login/logout/login fallido, cambios de permisos/roles, acceso a la
API de Inventario, lecturas de datos sensibles fuera de RRHH que ya
tenía su propio registro). `services.search_audit_events` federa
TODOS estos orígenes (los 7 existentes + `AuditLog` + movimientos de
inventario) en una sola búsqueda vía `UNION` SQL — nunca copiándolos a
una tabla nueva.

`tenant` es deliberadamente NULABLE — a diferencia de
`TenantScopedModel` (donde toda entidad de negocio pertenece siempre a
exactamente un tenant), un intento de login fallido con un email que
no pertenece a ningún tenant, o que ni siquiera existe como usuario,
no tiene un tenant que asignarle. Mismo principio ya usado por
`apps.tenants.Membership` (que tampoco hereda `TenantScopedModel`,
por una razón distinta pero relacionada: es el modelo que se usa para
*determinar* el tenant, no uno que ya presupone tener uno)."""

from django.conf import settings
from django.db import models

from apps.tenants.models import Tenant


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login", "Inicio de sesión"
        LOGOUT = "logout", "Cierre de sesión"
        LOGIN_FAILED = "login_failed", "Inicio de sesión fallido"
        PERMISSION_CHANGED = "permission_changed", "Permiso modificado"
        ROLE_CHANGED = "role_changed", "Rol modificado"
        API_KEY_CREATED = "api_key_created", "Clave de API creada"
        API_KEY_ROTATED = "api_key_rotated", "Clave de API rotada"
        API_KEY_REVOKED = "api_key_revoked", "Clave de API revocada"
        API_ACCESS = "api_access", "Acceso a la API"
        # Integraciones externas / Catalog API (ampliación final de FASE 15,
        # ver docs/integrations.md) — distintas de API_KEY_* (esas son de
        # la API administrativa de Inventario, `ApiKey`).
        INTEGRATION_CREATED = "integration_created", "Integración creada"
        INTEGRATION_ROTATED = "integration_rotated", "Integración rotada"
        INTEGRATION_REVOKED = "integration_revoked", "Integración revocada"
        INTEGRATION_ENABLED = "integration_enabled", "Integración habilitada"
        INTEGRATION_DISABLED = "integration_disabled", "Integración deshabilitada"
        # Billing SaaS / PayPal (FASE 16, ver docs/paypal.md) — dominio
        # "billing_paypal", nunca mezclado con auditoría del ERP del
        # tenant. `tenant` puede ser None aquí (prueba de conexión de la
        # plataforma, webhook sin transacción asociada).
        PAYPAL_CONFIG_TESTED = "paypal_config_tested", "Conexión de PayPal probada"
        PAYPAL_CHECKOUT_CREATED = "paypal_checkout_created", "Checkout de PayPal creado"
        PAYPAL_PAYMENT_CONFIRMED = "paypal_payment_confirmed", "Pago de PayPal confirmado"
        PAYPAL_PAYMENT_FAILED = "paypal_payment_failed", "Pago de PayPal fallido"
        PAYPAL_CHECKOUT_CANCELLED = "paypal_checkout_cancelled", "Checkout de PayPal cancelado"
        PAYPAL_REFUND_REQUESTED = "paypal_refund_requested", "Reembolso de PayPal solicitado"
        PAYPAL_REFUND_COMPLETED = "paypal_refund_completed", "Reembolso de PayPal completado"
        PAYPAL_REFUND_FAILED = "paypal_refund_failed", "Reembolso de PayPal fallido"
        PAYPAL_WEBHOOK_PROCESSED = "paypal_webhook_processed", "Webhook de PayPal procesado"
        SENSITIVE_DATA_VIEWED = "sensitive_data_viewed", "Datos sensibles vistos"
        EXPORT_PERFORMED = "export_performed", "Exportación realizada"
        GENERIC = "generic", "Evento genérico"

    tenant = models.ForeignKey(
        Tenant, verbose_name="tenant", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    action = models.CharField("acción", max_length=30, choices=Action.choices)
    # Dominio de negocio del evento ("auth", "permissions", "hr",
    # "payroll", "accounting", "reports", "api", ...) — texto libre
    # deliberadamente (no un TextChoices cerrado): un dominio nuevo es
    # una cadena nueva, nunca una migración.
    domain = models.CharField("dominio", max_length=30)
    object_type = models.CharField("tipo de objeto", max_length=50, blank=True)
    object_id = models.CharField("id del objeto", max_length=64, blank=True)
    request_id = models.CharField("id de la request", max_length=64, blank=True)
    ip_address = models.GenericIPAddressField("dirección IP", null=True, blank=True)
    user_agent = models.CharField("user agent", max_length=255, blank=True)
    # Snapshots antes/después — JAMÁS contraseñas, tokens, claves de
    # API completas ni otros secretos (ver `docs/audit.md`).
    before = models.JSONField("antes", null=True, blank=True)
    after = models.JSONField("después", null=True, blank=True)
    reason = models.CharField("motivo", max_length=255, blank=True)
    metadata = models.JSONField("metadatos", default=dict, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "evento de auditoría"
        verbose_name_plural = "eventos de auditoría"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "created_at"], name="idx_auditlog_tenant_fecha"),
            models.Index(fields=["tenant", "domain", "created_at"], name="idx_auditlog_tenant_dominio"),
            models.Index(fields=["tenant", "user", "created_at"], name="idx_auditlog_tenant_usuario"),
            models.Index(fields=["tenant", "action", "created_at"], name="idx_auditlog_tenant_accion"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.domain} ({self.created_at:%Y-%m-%d %H:%M})"
