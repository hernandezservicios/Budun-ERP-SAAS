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
