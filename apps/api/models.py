"""
`ApiKey` — API de Inventario v1 (FASE 15, ver `docs/api-inventory.md`).
Una API Key pertenece a exactamente un tenant (regla permanente,
`CLAUDE.md`), y un tenant tiene como máximo una — nunca varias claves
activas a la vez: "regenerar"/"rotar" reescribe el hash de la MISMA
fila (nunca crea una segunda), por lo que revocar+generar de nuevo es
la única forma de tener una clave distinta.

El secreto completo NUNCA se guarda en texto plano — solo su hash
SHA-256 (`key_hash`, lookup por igualdad exacta; un hash rápido es
apropiado aquí porque el secreto ya es aleatorio de alta entropía,
a diferencia de una contraseña humana que sí necesita un hash lento).
`key_prefix` es lo único que se muestra permanentemente en la UI
después de la creación/rotación (enmascarado vía
`apps.core.utils.mask_secret`, mismo criterio que IMEI/serie)."""

from django.conf import settings
from django.db import models

from apps.tenants.models import TenantScopedModel


class ApiKey(TenantScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        REVOKED = "revoked", "Revocada"

    key_prefix = models.CharField("prefijo", max_length=16)
    key_hash = models.CharField("hash de la clave", max_length=64, unique=True)
    scopes = models.JSONField("scopes", default=list)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField("expira", null=True, blank=True)

    created_at = models.DateTimeField("creada", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    rotated_at = models.DateTimeField("última rotación", null=True, blank=True)
    revoked_at = models.DateTimeField("revocada", null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="revocada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    last_tested_at = models.DateTimeField("última prueba", null=True, blank=True)
    last_test_ok = models.BooleanField("última prueba exitosa", null=True, blank=True)
    last_test_error = models.CharField("último error", max_length=255, blank=True)
    last_used_at = models.DateTimeField("último uso", null=True, blank=True)

    class Meta:
        verbose_name = "clave de API"
        verbose_name_plural = "claves de API"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="unique_apikey_por_tenant"),
        ]

    def __str__(self):
        return f"{self.key_prefix}… ({self.tenant})"

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE


class Integration(TenantScopedModel):
    """Aplicación/integración externa conectada a la Catalog API
    (ampliación final de FASE 15, ver `docs/integrations.md`) — un
    tenant puede tener VARIAS (a diferencia de `ApiKey`, que es una
    sola por tenant para la API administrativa de Inventario). Espejo
    estructural deliberado de `ApiKey` (mismo criterio ya usado en el
    proyecto para `SupplierPayment`/`Payment`: dos conceptos separados
    que nunca comparten tabla, aunque su forma sea casi idéntica) —
    nunca la misma fila que `ApiKey`, nunca comparten scopes.

    `provider` identifica QUIÉN construyó el consumidor (hoy solo
    `BUDUN` tiene soporte real) — separado del concepto de "tool" que
    un consumidor externo (p. ej. WACRM) construye sobre su PROPIA
    arquitectura; este proyecto nunca implementa tools de terceros.

    `app_key` es un identificador público (visible siempre, útil para
    logs/soporte) — nunca se usa para resolver la autenticación por sí
    solo; la request se autentica exclusivamente por el hash del
    secreto (`secret_hash`), igual que `ApiKey.key_hash`. `is_enabled`
    es un interruptor reversible (activar/desactivar) — distinto de
    `status=REVOKED`, que es terminal (revocar no tiene "reactivar")."""

    class Provider(models.TextChoices):
        BUDUN = "budun", "Budun ERP"
        OTHER_ERP = "other_erp", "Otro ERP"
        FUTURE = "future", "Futuro"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        REVOKED = "revoked", "Revocada"

    name = models.CharField("nombre", max_length=100)
    provider = models.CharField("provider", max_length=20, choices=Provider.choices, default=Provider.BUDUN)
    app_key = models.CharField("app key", max_length=32, unique=True)
    secret_hash = models.CharField("hash del secreto", max_length=64, unique=True)
    scopes = models.JSONField("scopes", default=list)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_enabled = models.BooleanField("habilitada", default=True)
    expires_at = models.DateTimeField("expira", null=True, blank=True)

    created_at = models.DateTimeField("creada", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    rotated_at = models.DateTimeField("última rotación", null=True, blank=True)
    revoked_at = models.DateTimeField("revocada", null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="revocada por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    last_tested_at = models.DateTimeField("última prueba", null=True, blank=True)
    last_test_ok = models.BooleanField("última prueba exitosa", null=True, blank=True)
    last_test_error = models.CharField("último error", max_length=255, blank=True)
    last_used_at = models.DateTimeField("último uso", null=True, blank=True)

    class Meta:
        verbose_name = "integración"
        verbose_name_plural = "integraciones"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_integration_tenant_nombre"),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_provider_display()}) — {self.tenant}"

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE and self.is_enabled
