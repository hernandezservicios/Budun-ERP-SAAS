"""
Siembra los planes reales de Billing SaaS (FASE 17) a partir de
`apps.core.pricing.PLANS` (FASE 6) — idempotente (`update_or_create`),
seguro de correr varias veces. Reemplaza el placeholder estático como
fuente de verdad de precios una vez ejecutado (ver `docs/billing.md`).
No crea nada si ya existe un `Plan` con el mismo `slug`."""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import BillingPolicy, Plan, PlanVersion
from apps.core.pricing import PLANS


class Command(BaseCommand):
    help = "Siembra los planes reales (Plan/PlanVersion) a partir de apps.core.pricing.PLANS."

    def handle(self, *args, **options):
        BillingPolicy.objects.get_or_create(pk=1)
        for datos in PLANS:
            plan, _creado = Plan.objects.update_or_create(
                slug=datos["id"],
                defaults={
                    "name": datos["nombre"], "description": datos.get("descripcion", ""),
                    "is_active": True, "sort_order": PLANS.index(datos),
                },
            )
            monto = datos.get("price_amount")
            if monto is None:
                self.stdout.write(f"Plan «{plan.name}» sin precio fijo — sin PlanVersion (checkout de autoservicio no aplica).")
                continue
            with transaction.atomic():
                PlanVersion.objects.filter(plan=plan, frequency=PlanVersion.Frequency.MONTHLY, is_current=True).update(is_current=False)
                PlanVersion.objects.update_or_create(
                    plan=plan, frequency=PlanVersion.Frequency.MONTHLY, is_current=True,
                    defaults={"price_amount": Decimal(monto), "price_currency": datos.get("price_currency", "USD")},
                )
            self.stdout.write(self.style.SUCCESS(f"Plan «{plan.name}» sembrado ({monto} {datos.get('price_currency', 'USD')}/mes)."))
