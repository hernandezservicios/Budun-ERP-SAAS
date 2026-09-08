"""Monitoring (FASE 20, sección 20).

Ninguna infraestructura de alertas nueva (email/Slack/webhook) se
agrega en esta fase — no está aprobada ni justificada todavía (ver
CLAUDE.md: "Redis solo si una fase posterior demuestra necesidad
real", mismo criterio para un canal de notificaciones). Esta función
es el DATO que una integración futura consumiría (un comando de cron
que la llame y envíe un correo si `healthy=False`, por ejemplo) —
queda preparada, documentada, no inventada como ya activa."""

from __future__ import annotations

import datetime as dt

from django.utils import timezone


def get_backup_health_summary(*, max_age_hours: int = 30) -> dict:
    """`max_age_hours` por defecto es 30 (24h de cadencia diaria +
    6h de margen) — coherente con el RPO propuesto de 24h (ver
    `docs/backup-recovery.md` sección 13)."""
    from ..models import BackupRun

    now = timezone.now()
    threshold = now - dt.timedelta(hours=max_age_hours)

    summary = {"checked_at": now.isoformat(), "healthy": True, "kinds": {}}
    for kind, label in BackupRun.Kind.choices:
        latest = BackupRun.objects.filter(kind=kind).order_by("-started_at").first()
        latest_success = (
            BackupRun.objects.filter(kind=kind, status=BackupRun.Status.SUCCESS).order_by("-started_at").first()
        )
        kind_healthy = bool(latest_success and latest_success.started_at >= threshold)
        summary["kinds"][kind] = {
            "label": label,
            "last_run_status": latest.status if latest else None,
            "last_run_at": latest.started_at.isoformat() if latest else None,
            "last_success_at": latest_success.started_at.isoformat() if latest_success else None,
            "healthy": kind_healthy,
            "reason": (
                "OK"
                if kind_healthy
                else ("Nunca se ha ejecutado un backup exitoso de este tipo." if not latest_success
                      else f"El último backup exitoso tiene más de {max_age_hours}h.")
            ),
        }
        if not kind_healthy:
            summary["healthy"] = False

    return summary
