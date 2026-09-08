"""FASE 20, sección 20 — Monitoring. Sin infraestructura de alertas
nueva; solo el DATO consultable (`get_backup_health_summary`)."""

import datetime as dt

from django.test import TestCase
from django.utils import timezone

from apps.backups.models import BackupRun
from apps.backups.services import monitoring as monitoring_service


class BackupHealthSummaryTests(TestCase):
    def test_sin_ningun_backup_todo_esta_no_saludable(self):
        summary = monitoring_service.get_backup_health_summary()
        self.assertFalse(summary["healthy"])
        for info in summary["kinds"].values():
            self.assertFalse(info["healthy"])
            self.assertIsNone(info["last_success_at"])

    def test_backup_exitoso_reciente_marca_saludable(self):
        BackupRun.objects.create(
            kind=BackupRun.Kind.DATABASE, status=BackupRun.Status.SUCCESS,
            started_at=timezone.now(), finished_at=timezone.now(),
        )
        summary = monitoring_service.get_backup_health_summary(max_age_hours=30)
        self.assertTrue(summary["kinds"][BackupRun.Kind.DATABASE]["healthy"])
        # Los otros dos tipos (media) siguen sin ningún backup exitoso.
        self.assertFalse(summary["healthy"])

    def test_backup_exitoso_vencido_marca_no_saludable(self):
        BackupRun.objects.create(
            kind=BackupRun.Kind.DATABASE, status=BackupRun.Status.SUCCESS,
            started_at=timezone.now() - dt.timedelta(hours=100),
            finished_at=timezone.now() - dt.timedelta(hours=100),
        )
        summary = monitoring_service.get_backup_health_summary(max_age_hours=30)
        self.assertFalse(summary["kinds"][BackupRun.Kind.DATABASE]["healthy"])

    def test_ultimo_intento_fallido_no_cuenta_como_saludable_aunque_haya_uno_exitoso_previo(self):
        BackupRun.objects.create(
            kind=BackupRun.Kind.DATABASE, status=BackupRun.Status.SUCCESS,
            started_at=timezone.now() - dt.timedelta(hours=1),
            finished_at=timezone.now() - dt.timedelta(hours=1),
        )
        BackupRun.objects.create(
            kind=BackupRun.Kind.DATABASE, status=BackupRun.Status.SUCCESS,
            started_at=timezone.now(), finished_at=timezone.now(),
        )
        summary = monitoring_service.get_backup_health_summary(max_age_hours=30)
        info = summary["kinds"][BackupRun.Kind.DATABASE]
        self.assertTrue(info["healthy"])
        self.assertEqual(info["last_run_status"], BackupRun.Status.SUCCESS)
