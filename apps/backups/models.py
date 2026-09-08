"""
Backups + Disaster Recovery (FASE 20, ver `docs/backup-recovery.md`).

`BackupRun` es deliberadamente PLATAFORMA, no `TenantScopedModel` —
mismo principio ya usado por `apps.audit.AuditLog`/
`apps.billing.models.PayPalTransaction`: un backup completo de la
base de datos contiene, por diseño, los datos de TODOS los tenants a
la vez (la separación multi-tenant es una columna `tenant_id` dentro
de la MISMA base, nunca bases separadas por tenant — ver
`ARCHITECTURE.md`), así que el registro de "se corrió un backup" no
pertenece a ningún tenant en particular. Ningún tenant puede leer ni
escribir esta tabla — es exclusivamente de infraestructura, visible
solo por `is_superuser` vía el admin de solo lectura
(`apps.backups.admin`).

Este modelo es el mecanismo de "Monitoring" (sección 20 de la
especificación de fase): `services.monitoring.get_backup_health_summary`
lo consulta para detectar backup faltante/fallido sin necesitar
ninguna infraestructura de alertas nueva todavía no aprobada."""

from django.db import models


class BackupRun(models.Model):
    class Kind(models.TextChoices):
        DATABASE = "database", "Base de datos (PostgreSQL)"
        MEDIA_PRIVATE = "media_private", "Media privada (media-private/)"
        MEDIA_CATALOG = "media_catalog", "Media de catálogo (catalog-media/)"

    class Status(models.TextChoices):
        SUCCESS = "success", "Exitoso"
        FAILED = "failed", "Fallido"

    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    status = models.CharField("resultado", max_length=10, choices=Status.choices)
    # Ruta RELATIVA a `settings.BACKUP_ROOT` — nunca la ruta absoluta del
    # sistema de archivos (evita filtrar la estructura de directorios
    # reales del servidor en un registro que, aunque solo lo ve un
    # superusuario, sigue siendo un dato a minimizar).
    relative_path = models.CharField("archivo (relativo a BACKUP_ROOT)", max_length=255, blank=True)
    size_bytes = models.BigIntegerField("tamaño en bytes", null=True, blank=True)
    duration_seconds = models.FloatField("duración en segundos", null=True, blank=True)
    checksum_sha256 = models.CharField("checksum SHA-256", max_length=64, blank=True)
    encrypted = models.BooleanField("cifrado", default=False)
    postgres_version = models.CharField("versión de PostgreSQL", max_length=50, blank=True)
    # Mensaje de error SANITIZADO (nunca la contraseña de la base de
    # datos, nunca `BACKUP_ENCRYPTION_KEY`) — ver
    # `services.database.sanitize_error_output`.
    error_message = models.TextField("mensaje de error", blank=True)
    started_at = models.DateTimeField("iniciado")
    finished_at = models.DateTimeField("finalizado", null=True, blank=True)
    created_at = models.DateTimeField("registrado", auto_now_add=True)

    class Meta:
        verbose_name = "ejecución de backup"
        verbose_name_plural = "ejecuciones de backup"
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["kind", "status", "started_at"], name="idx_backuprun_estado"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.get_status_display()} ({self.started_at:%Y-%m-%d %H:%M})"
