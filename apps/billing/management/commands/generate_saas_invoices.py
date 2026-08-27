"""
Genera las facturas recurrentes vencidas (FASE 17, sección 11) — mismo
criterio que `apply_billing_past_due_policy`: pensado para cron real en
producción, idempotente por diseño
(`SaaSInvoice.UniqueConstraint(subscription, period_start)`)."""

from django.core.management.base import BaseCommand

from apps.billing.services import invoicing as invoicing_services


class Command(BaseCommand):
    help = "Genera la factura del siguiente período para toda suscripción ACTIVE/PAST_DUE cuyo período vigente ya terminó."

    def handle(self, *args, **options):
        generadas = invoicing_services.generate_due_renewal_invoices()
        self.stdout.write(self.style.SUCCESS(f"{len(generadas)} factura(s) de renovación generada(s)."))
