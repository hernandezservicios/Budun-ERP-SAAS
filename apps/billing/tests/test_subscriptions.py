from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.billing.models import PlanVersion, Subscription
from apps.billing.services import subscriptions as services
from apps.tenants.models import Tenant

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


class SubscriptionLifecycleTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version()
        self.saas_customer = crear_saas_customer()

    def test_crear_suscripcion_queda_pending(self):
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.assertEqual(subscription.status, Subscription.Status.PENDING)

    def test_no_se_puede_crear_dos_suscripciones_operativas_para_el_mismo_tenant(self):
        services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        with self.assertRaises(services.InvalidSubscriptionOperation):
            services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)

    def test_activar_suscripcion_activa_el_tenant(self):
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(subscription.current_period_start)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)

    def test_activar_dos_veces_es_idempotente(self):
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        periodo_original = subscription.current_period_start
        subscription = services.activate_subscription(subscription)
        self.assertEqual(subscription.current_period_start, periodo_original)

    def test_marcar_past_due_y_suspender_reflejan_en_el_tenant(self):
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        subscription = services.mark_past_due(subscription)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.PAST_DUE)
        self.assertFalse(self.tenant.billing_status_blocks_operation, "PAST_DUE (gracia) no debe bloquear la operación.")

        subscription = services.suspend_subscription(subscription, reason="falta de pago")
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.SUSPENDED)
        self.assertTrue(self.tenant.billing_status_blocks_operation)

    def test_reactivar_suscripcion_suspendida(self):
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        subscription = services.suspend_subscription(subscription)
        subscription = services.reactivate_subscription(subscription)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)

    def test_no_se_puede_reactivar_una_suscripcion_activa(self):
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        with self.assertRaises(services.InvalidSubscriptionOperation):
            services.reactivate_subscription(subscription)

    def test_cancelar_inmediatamente_cancela_el_tenant(self):
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        subscription = services.cancel_subscription(subscription, immediate=True, reason="a pedido del cliente")
        self.assertEqual(subscription.status, Subscription.Status.CANCELLED)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.CANCELLED)

    def test_cancelar_al_finalizar_periodo_no_cancela_de_inmediato(self):
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        subscription = services.cancel_subscription(subscription, immediate=False, reason="probando")
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertTrue(subscription.cancel_at_period_end)


class ResolvePlanPricingTests(TestCase):
    def setUp(self):
        self.plan, self.version = crear_plan_con_version(slug="profesional", precio=Decimal("29.00"))

    def test_resuelve_precio_real_cuando_existe_planversion(self):
        nombre, monto, moneda, version = services.resolve_plan_pricing("profesional")
        self.assertEqual(monto, Decimal("29.00"))
        self.assertEqual(version, self.version)

    def test_cae_al_fallback_estatico_si_no_hay_planversion_real(self):
        nombre, monto, moneda, version = services.resolve_plan_pricing("starter")
        # "starter" no tiene price_amount en el fallback estático (es gratis).
        self.assertIsNone(monto)

    def test_plan_desconocido_devuelve_todo_none(self):
        nombre, monto, moneda, version = services.resolve_plan_pricing("no-existe-en-ningun-lado")
        self.assertIsNone(nombre)
        self.assertIsNone(monto)


class ProrationTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("30.00"))
        self.saas_customer = crear_saas_customer()
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = services.activate_subscription(subscription)
        # Fija un período conocido de 30 días para que el cálculo sea determinístico.
        self.subscription.current_period_start = date(2026, 1, 1)
        self.subscription.current_period_end = date(2026, 1, 31)
        self.subscription.save(update_fields=["current_period_start", "current_period_end"])

    def test_upgrade_a_mitad_de_periodo_calcula_cargo_neto_positivo(self):
        _plan_nuevo, version_nueva = crear_plan_con_version(slug="empresarial", precio=Decimal("60.00"))
        desglose = services.calculate_proration(self.subscription, new_plan_version=version_nueva, change_date=date(2026, 1, 16))
        self.assertEqual(desglose["dias_totales"], 30)
        self.assertEqual(desglose["dias_restantes"], 15)
        self.assertGreater(desglose["monto_neto"], 0)

    def test_downgrade_a_mitad_de_periodo_calcula_credito_neto_negativo(self):
        _plan_nuevo, version_nueva = crear_plan_con_version(slug="basico", precio=Decimal("10.00"))
        desglose = services.calculate_proration(self.subscription, new_plan_version=version_nueva, change_date=date(2026, 1, 16))
        self.assertLess(desglose["monto_neto"], 0)

    def test_change_plan_downgrade_emite_nota_de_credito(self):
        _plan_nuevo, version_nueva = crear_plan_con_version(slug="basico2", precio=Decimal("5.00"))
        subscription, desglose, nota_credito = services.change_plan(
            self.subscription, new_plan_version=version_nueva, change_date=date(2026, 1, 16),
        )
        self.assertEqual(subscription.plan_version, version_nueva)
        self.assertIsNotNone(nota_credito)
        self.assertEqual(nota_credito.amount, abs(desglose["monto_neto"]))

    def test_change_plan_upgrade_no_emite_nota_de_credito(self):
        _plan_nuevo, version_nueva = crear_plan_con_version(slug="premium2", precio=Decimal("90.00"))
        subscription, desglose, nota_credito = services.change_plan(
            self.subscription, new_plan_version=version_nueva, change_date=date(2026, 1, 16),
        )
        self.assertIsNone(nota_credito)
