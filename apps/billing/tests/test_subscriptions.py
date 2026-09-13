from datetime import date, timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase

from apps.billing.models import PlanVersion, SaaSInvoice, Subscription
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

    def test_no_se_puede_reactivar_una_suscripcion_pendiente(self):
        # PENDING != SUSPENDED — reactivar exige haber estado ACTIVE
        # alguna vez (SUSPENDED/PAST_DUE); una PENDING se activa con
        # `activate_pending_subscription`, nunca con reactivar.
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        with self.assertRaises(services.InvalidSubscriptionOperation):
            services.reactivate_subscription(subscription)

    def test_reactivar_con_periodo_vencido_restaura_un_periodo_nuevo_desde_hoy(self):
        # FASE DE CORRECCIÓN 3: la suscripción estuvo suspendida más allá
        # de su período vigente — reactivar nunca debe reanudar un
        # período ya vencido (que dispararía de inmediato una renovación
        # retroactiva); le da un período fresco a partir de HOY.
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        subscription.current_period_start = date(2026, 1, 1)
        subscription.current_period_end = date(2026, 1, 31)
        subscription.save(update_fields=["current_period_start", "current_period_end"])
        subscription = services.suspend_subscription(subscription)

        subscription = services.reactivate_subscription(subscription, change_date=date(2026, 3, 1))
        self.assertEqual(subscription.current_period_start, date(2026, 3, 1))
        self.assertGreater(subscription.current_period_end, date(2026, 3, 1))

    def test_reactivar_con_periodo_todavia_vigente_no_lo_modifica(self):
        # Reactivación rápida, ANTES de que el período vigente terminara
        # — nunca se le "regala" un período adicional que no corresponde.
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        subscription.current_period_start = date(2026, 1, 1)
        subscription.current_period_end = date(2026, 1, 31)
        subscription.save(update_fields=["current_period_start", "current_period_end"])
        subscription = services.suspend_subscription(subscription)

        subscription = services.reactivate_subscription(subscription, change_date=date(2026, 1, 10))
        self.assertEqual(subscription.current_period_start, date(2026, 1, 1))
        self.assertEqual(subscription.current_period_end, date(2026, 1, 31))

    def test_marcar_past_due_suspender_y_reactivar_notifican_al_owner(self):
        # FASE DE CORRECCIÓN 3: las funciones de notificación existían
        # desde FASE 17 pero ninguna transición real las llamaba — se
        # conectan en esta corrección (ver KNOWN_ISSUES.md).
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = services.activate_subscription(subscription)
        mail.outbox.clear()

        services.mark_past_due(subscription)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.owner.email, mail.outbox[0].to)

        services.suspend_subscription(subscription)
        self.assertEqual(len(mail.outbox), 2)

        services.reactivate_subscription(subscription)
        self.assertEqual(len(mail.outbox), 3)
        self.assertIn("reactivada", mail.outbox[2].subject.lower())

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
        from apps.billing.services import invoicing as invoicing_services

        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("30.00"))
        self.saas_customer = crear_saas_customer()
        subscription = services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = services.activate_subscription(subscription)
        # Fija un período conocido de 30 días para que el cálculo sea determinístico.
        self.subscription.current_period_start = date(2026, 1, 1)
        self.subscription.current_period_end = date(2026, 1, 31)
        self.subscription.save(update_fields=["current_period_start", "current_period_end"])
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)

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

    def test_prorrateo_con_cambio_de_periodicidad_normaliza_por_frecuencia_propia(self):
        # FASE DE CORRECCIÓN 6: antes de esta corrección, AMBOS precios se
        # dividían entre los días del período VIGENTE (30, mensual) sin
        # importar la frecuencia del plan NUEVO — un cambio mensual->anual
        # comparaba un precio ANUAL contra un divisor de ~30 días. Plan
        # actual: 30.00/mes (1.00/día, sobre 30 días nominales). Plan
        # nuevo: 730.00/año (2.00/día, sobre 365 días nominales, NUNCA
        # sobre los 30 días del período vigente que se abandona). A mitad
        # de período (15 días restantes de 30): crédito = 1.00*15 = 15.00;
        # cargo = 2.00*15 = 30.00; neto = 15.00 -- la fórmula previa (con
        # el bug) habría dado ~349.95 (730/30 ≈ 24.33/día × 15 - 15.00).
        _plan_anual, version_anual = crear_plan_con_version(slug="anual-c6", precio=Decimal("730.00"), frecuencia="annual")
        desglose = services.calculate_proration(self.subscription, new_plan_version=version_anual, change_date=date(2026, 1, 16))
        self.assertEqual(desglose["valor_diario_actual"], Decimal("1.00"))
        self.assertEqual(desglose["valor_diario_nuevo"], Decimal("2.00"))
        self.assertEqual(desglose["credito"], Decimal("15.00"))
        self.assertEqual(desglose["cargo"], Decimal("30.00"))
        self.assertEqual(desglose["monto_neto"], Decimal("15.00"))

    def test_change_plan_downgrade_emite_nota_de_credito(self):
        _plan_nuevo, version_nueva = crear_plan_con_version(slug="basico2", precio=Decimal("5.00"))
        subscription, desglose, nota_credito, factura_cargo = services.change_plan(
            self.subscription, new_plan_version=version_nueva, change_date=date(2026, 1, 16),
        )
        self.assertEqual(subscription.plan_version, version_nueva)
        self.assertIsNotNone(nota_credito)
        self.assertEqual(nota_credito.amount, abs(desglose["monto_neto"]))
        self.assertIsNone(factura_cargo)

    def test_change_plan_upgrade_no_emite_nota_de_credito_pero_factura_el_cargo(self):
        # FASE DE CORRECCIÓN 3: antes de esta corrección, un upgrade a
        # mitad de período no cobraba la diferencia en ningún lado (ver
        # KNOWN_ISSUES.md #133) — ahora emite una factura inmediata,
        # separada de la del período vigente (que nunca se edita).
        _plan_nuevo, version_nueva = crear_plan_con_version(slug="premium2", precio=Decimal("90.00"))
        subscription, desglose, nota_credito, factura_cargo = services.change_plan(
            self.subscription, new_plan_version=version_nueva, change_date=date(2026, 1, 16),
        )
        self.assertIsNone(nota_credito)
        self.assertIsNotNone(factura_cargo)
        self.assertEqual(factura_cargo.total, desglose["monto_neto"])
        self.assertEqual(factura_cargo.status, SaaSInvoice.Status.OPEN)
        # La factura del período vigente (ya emitida antes del upgrade)
        # nunca se edita — sigue siendo una factura DISTINTA.
        self.assertNotEqual(factura_cargo.pk, self.invoice.pk)

    def test_change_plan_sin_prorrateo_no_genera_credito_ni_cargo(self):
        _plan_nuevo, version_nueva = crear_plan_con_version(slug="sinprorrateo", precio=Decimal("90.00"))
        subscription, desglose, nota_credito, factura_cargo = services.change_plan(
            self.subscription, new_plan_version=version_nueva, change_date=date(2026, 1, 16), prorate=False,
        )
        self.assertIsNone(desglose)
        self.assertIsNone(nota_credito)
        self.assertIsNone(factura_cargo)
