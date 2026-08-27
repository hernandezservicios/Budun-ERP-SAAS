"""
Aplica la política de PAST_DUE/suspensión (FASE 17, sección 31) —
pensado para programarse vía cron real en el VPS de producción (no hay
Celery/Redis en este proyecto, ver CLAUDE.md: "Redis solo si una fase
posterior demuestra necesidad real"). Lee los tiempos de
`BillingPolicy` (nunca hardcodeados)."""

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from apps.billing.models import BillingPolicy, SaaSInvoice, Subscription
from apps.billing.services import subscriptions as subscription_services


class Command(BaseCommand):
    help = "Marca PAST_DUE las suscripciones con facturas vencidas, y SUSPENDED las que ya agotaron el período de gracia."

    def handle(self, *args, **options):
        politica, _creada = BillingPolicy.objects.get_or_create(pk=1)
        hoy = date.today()

        activas = Subscription.all_objects.filter(status=Subscription.Status.ACTIVE)
        marcadas_past_due = 0
        for subscription in activas:
            factura_vencida = SaaSInvoice.all_objects.filter(
                tenant=subscription.tenant, subscription=subscription,
                status__in=[SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID],
                due_date__lte=hoy - timedelta(days=politica.grace_period_days),
            ).exists()
            if factura_vencida:
                subscription_services.mark_past_due(subscription)
                marcadas_past_due += 1

        past_due = Subscription.all_objects.filter(status=Subscription.Status.PAST_DUE)
        suspendidas = 0
        for subscription in past_due:
            factura_vencida_hace_mucho = SaaSInvoice.all_objects.filter(
                tenant=subscription.tenant, subscription=subscription,
                status__in=[SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID],
                due_date__lte=hoy - timedelta(days=politica.grace_period_days + politica.past_due_to_suspend_days),
            ).exists()
            if factura_vencida_hace_mucho:
                subscription_services.suspend_subscription(subscription, reason="Política automática de PAST_DUE agotada")
                suspendidas += 1

        self.stdout.write(self.style.SUCCESS(f"{marcadas_past_due} suscripción(es) marcada(s) PAST_DUE, {suspendidas} suspendida(s)."))


# Referencia cruzada: generación de facturas recurrentes vive en
# `manage.py generate_saas_invoices` (invoicing_services.generate_due_renewal_invoices).
