import datetime as dt

from django.test import TestCase
from django.utils import timezone

from apps.backups.models import BackupRun


class BackupRunModelTests(TestCase):
    def test_str_incluye_tipo_y_resultado(self):
        run = BackupRun.objects.create(
            kind=BackupRun.Kind.DATABASE, status=BackupRun.Status.SUCCESS, started_at=timezone.now()
        )
        text = str(run)
        self.assertIn("PostgreSQL", text)
        self.assertIn("Exitoso", text)

    def test_ordering_mas_reciente_primero(self):
        older = BackupRun.objects.create(
            kind=BackupRun.Kind.DATABASE, status=BackupRun.Status.SUCCESS,
            started_at=timezone.now() - dt.timedelta(days=1),
        )
        newer = BackupRun.objects.create(
            kind=BackupRun.Kind.DATABASE, status=BackupRun.Status.SUCCESS, started_at=timezone.now()
        )
        self.assertEqual(list(BackupRun.objects.all())[:2], [newer, older])
