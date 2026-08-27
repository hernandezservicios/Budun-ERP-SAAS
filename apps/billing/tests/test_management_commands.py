from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.billing.models import BillingPolicy, Plan, PlanVersion, SaaSInvoice, Subscription
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import subscriptions as subscription_services

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


class SeedBillingPlansCommandTests(TestCase):
    def test_siembra_los_3_planes_estaticos(self):
        salida = StringIO()
        call_command("seed_billing_plans", stdout=salida)
        self.assertEqual(Plan.objects.count(), 3)
        self.assertTrue(BillingPolicy.objects.filter(pk=1).exists())
        version_profesional = PlanVersion.objects.get(plan__slug="profesional", is_current=True)
        self.assertEqual(version_profesional.price_amount, Decimal("29.00"))

    def test_es_seguro_correr_dos_veces(self):
        call_command("seed_billing_plans", stdout=StringIO())
        call_command("seed_billing_plans", stdout=StringIO())
        self.assertEqual(Plan.objects.count(), 3)


class GenerateSaasInvoicesCommandTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)

    def test_genera_facturas_de_renovacion_vencidas(self):
        Subscription.all_objects.filter(pk=self.subscription.pk).update(
            current_period_end=date.today() - timedelta(days=1),
        )
        call_command("generate_saas_invoices", stdout=StringIO())
        self.assertEqual(SaaSInvoice.all_objects.filter(subscription=self.subscription).count(), 1)


class ApplyPastDuePolicyCommandTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)

    def test_factura_vencida_mas_alla_de_la_gracia_marca_past_due(self):
        SaaSInvoice.all_objects.filter(pk=self.invoice.pk).update(due_date=date.today() - timedelta(days=10))
        call_command("apply_billing_past_due_policy", stdout=StringIO())
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.PAST_DUE)

    def test_factura_recien_vencida_dentro_de_la_gracia_no_marca_past_due(self):
        SaaSInvoice.all_objects.filter(pk=self.invoice.pk).update(due_date=date.today() - timedelta(days=1))
        call_command("apply_billing_past_due_policy", stdout=StringIO())
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)

    def test_past_due_agotado_suspende(self):
        BillingPolicy.objects.update_or_create(pk=1, defaults={"grace_period_days": 1, "past_due_to_suspend_days": 1})
        SaaSInvoice.all_objects.filter(pk=self.invoice.pk).update(due_date=date.today() - timedelta(days=5))
        call_command("apply_billing_past_due_policy", stdout=StringIO())
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.SUSPENDED)
