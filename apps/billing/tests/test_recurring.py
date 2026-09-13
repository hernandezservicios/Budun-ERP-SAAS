"""
FASE DE CORRECCIÓN 2C — Cobro recurrente automático de PayPal (Gate
Local). Ver `apps.billing.services.recurring` para la arquitectura
elegida (PayPal Subscriptions API) y el razonamiento completo."""

import threading
from decimal import Decimal

from django.db import connection
from django.test import TestCase, TransactionTestCase

from apps.billing.models import (
    PlanVersion,
    SaaSInvoice,
    SaaSPayment,
    SaaSPaymentAllocation,
    Subscription,
)
from apps.billing.services import recurring as recurring_services
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import subscriptions as subscription_services
from apps.sales.models import Payment as SalesPayment
from apps.tenants.models import Tenant

from ._helpers import build_webhook_body, fake_provider
from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


class EnsurePaypalBillingPlanTests(TestCase):
    def setUp(self):
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))

    def test_crea_producto_y_plan_la_primera_vez(self):
        with fake_provider() as fake:
            version = recurring_services.ensure_paypal_billing_plan(self.version)
        self.assertTrue(version.paypal_product_id)
        self.assertTrue(version.paypal_plan_id)
        self.assertEqual(len([c for c in fake.calls if c[0] == "create_product"]), 1)
        self.assertEqual(len([c for c in fake.calls if c[0] == "create_billing_plan"]), 1)

    def test_es_idempotente_no_crea_dos_veces(self):
        with fake_provider() as fake:
            recurring_services.ensure_paypal_billing_plan(self.version)
            self.version.refresh_from_db()
            recurring_services.ensure_paypal_billing_plan(self.version)
        self.assertEqual(len([c for c in fake.calls if c[0] == "create_product"]), 1)
        self.assertEqual(len([c for c in fake.calls if c[0] == "create_billing_plan"]), 1)

    def test_un_cambio_de_precio_del_plan_crea_su_propio_producto_y_plan_de_paypal_separados(self):
        # Sección 6 de la corrección: el snapshot contractual de una
        # PlanVersion ya creada nunca cambia — una PlanVersion NUEVA
        # (precio distinto) tiene su PROPIO Producto/Plan de PayPal,
        # nunca reutiliza ni sobrescribe el de la anterior. Un único
        # `fake_provider()` para ambas llamadas — dos bloques separados
        # generarían cada uno su propia secuencia de IDs falsos desde 1,
        # lo que coincidiría por construcción y no probaría nada real.
        PlanVersion.objects.filter(plan=self.plan, frequency=self.version.frequency, is_current=True).update(is_current=False)
        nueva_version = PlanVersion.objects.create(
            plan=self.plan, frequency=self.version.frequency, price_amount=Decimal("39.00"), price_currency="USD", is_current=True,
        )
        with fake_provider():
            version_actualizada = recurring_services.ensure_paypal_billing_plan(self.version)
            nueva_version = recurring_services.ensure_paypal_billing_plan(nueva_version)

        plan_id_original = version_actualizada.paypal_plan_id
        self.assertTrue(plan_id_original)
        self.version.refresh_from_db()
        self.assertEqual(self.version.paypal_plan_id, plan_id_original)  # nunca cambia retroactivamente.
        self.assertNotEqual(nueva_version.paypal_plan_id, plan_id_original)

    def test_fallo_de_paypal_al_crear_producto_no_deja_estado_a_medias(self):
        with fake_provider(should_fail_create_product=True):
            with self.assertRaises(recurring_services.InvalidRecurringOperation):
                recurring_services.ensure_paypal_billing_plan(self.version)
        self.version.refresh_from_db()
        self.assertFalse(self.version.paypal_product_id)
        self.assertFalse(self.version.paypal_plan_id)


class CreateRecurringCheckoutTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)

    def _iniciar(self):
        return recurring_services.create_recurring_checkout(
            self.subscription, user=self.owner, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
        )

    def test_autoriza_y_guarda_la_referencia_de_paypal(self):
        with fake_provider() as fake:
            subscription, approve_url = self._iniciar()
        self.assertTrue(subscription.paypal_subscription_id)
        self.assertEqual(subscription.paypal_subscription_status, "APPROVAL_PENDING")
        self.assertTrue(approve_url.startswith("https://sandbox.paypal.test/subscribe/"))
        self.assertEqual(len([c for c in fake.calls if c[0] == "create_recurring_subscription"]), 1)
        # No activa nada todavía: eso solo ocurre al confirmar el cobro.
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.PENDING)

    def test_rechaza_una_segunda_autorizacion_mientras_la_primera_sigue_pendiente(self):
        with fake_provider():
            self._iniciar()
        with fake_provider() as fake:
            with self.assertRaises(recurring_services.InvalidRecurringOperation):
                self._iniciar()
        self.assertEqual(len([c for c in fake.calls if c[0] == "create_recurring_subscription"]), 0)

    def test_no_crea_apps_sales_payment(self):
        with fake_provider():
            self._iniciar()
        self.assertEqual(SalesPayment.all_objects.filter(tenant=self.tenant).count(), 0)


class ReconcileAndConfirmRecurringChargeTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        with fake_provider():
            self.subscription, _url = recurring_services.create_recurring_checkout(
                self.subscription, user=self.owner, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )

    def test_reconciliar_con_estado_active_confirma_el_primer_cobro_y_activa_todo(self):
        with fake_provider(next_recurring_subscription_status="ACTIVE"):
            recurring_services.reconcile_recurring_subscription(self.subscription, user=self.owner)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PAID)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(self.subscription.paypal_subscription_status, "ACTIVE")
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)
        pago = SaaSPayment.all_objects.get(tenant=self.tenant)
        self.assertEqual(pago.amount, Decimal("29.00"))
        self.assertEqual(pago.method, SaaSPayment.Method.PAYPAL)
        self.assertTrue(SaaSPaymentAllocation.all_objects.filter(payment=pago, invoice=self.invoice).exists())
        self.assertEqual(SalesPayment.all_objects.filter(tenant=self.tenant).count(), 0)

    def test_reconciliar_con_estado_todavia_pendiente_no_activa_nada(self):
        with fake_provider(next_recurring_subscription_status="APPROVAL_PENDING"):
            recurring_services.reconcile_recurring_subscription(self.subscription, user=self.owner)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.PENDING)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.OPEN)

    def test_confirmar_un_cobro_de_renovacion_sin_factura_existente_la_genera_reactivamente(self):
        # Simula que ya pasó un período completo (el cron de renovación
        # todavía no corrió) y llega el webhook de la 2da cobranza.
        with fake_provider(next_recurring_subscription_status="ACTIVE"):
            recurring_services.reconcile_recurring_subscription(self.subscription, user=self.owner)
        self.subscription.refresh_from_db()
        self.assertEqual(SaaSInvoice.all_objects.filter(subscription=self.subscription).count(), 1)

        recurring_services.confirm_recurring_charge(
            self.subscription, amount=Decimal("29.00"), currency="USD", external_reference="SALE-2", user=self.owner,
        )
        self.assertEqual(SaaSInvoice.all_objects.filter(subscription=self.subscription).count(), 2)
        segunda_factura = SaaSInvoice.all_objects.filter(subscription=self.subscription).order_by("-period_start").first()
        self.assertEqual(segunda_factura.status, SaaSInvoice.Status.PAID)
        self.assertEqual(SaaSPayment.all_objects.filter(tenant=self.tenant).count(), 2)

    def test_confirmar_cobro_sobre_suscripcion_suspendida_reactiva_no_activa(self):
        # FASE DE CORRECCIÓN 3: `ACTIVATE != REACTIVATE` — un cobro
        # recurrente confirmado sobre una suscripción SUSPENDED debe
        # usar `reactivate_subscription`, nunca el primitivo de
        # activación INICIAL.
        from datetime import date

        subscription_services.activate_subscription(self.subscription, user=self.owner)
        self.subscription.current_period_start = date(2026, 1, 1)
        self.subscription.current_period_end = date(2026, 1, 31)
        self.subscription.save(update_fields=["current_period_start", "current_period_end"])
        subscription_services.suspend_subscription(self.subscription)

        recurring_services.confirm_recurring_charge(
            self.subscription, amount=Decimal("29.00"), currency="USD", external_reference="SALE-REACT", user=self.owner,
        )
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.assertNotEqual(self.subscription.current_period_end, date(2026, 1, 31))


class PriceChangeDuringRecurringLifecycleTests(TestCase):
    """Sección 6 de la corrección: factura mes 1 en USD 29, el plan sube
    a USD 39 después — la renovación (ligada a la MISMA PlanVersion/
    Billing Plan originales) sigue cobrando USD 29, nunca el nuevo
    precio."""

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        with fake_provider(next_recurring_subscription_status="ACTIVE"):
            self.subscription, _url = recurring_services.create_recurring_checkout(
                self.subscription, user=self.owner, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
            recurring_services.reconcile_recurring_subscription(self.subscription, user=self.owner)

    def test_renovacion_tras_cambio_de_precio_del_plan_sigue_cobrando_el_precio_original(self):
        self.assertEqual(self.invoice.total, Decimal("29.00"))

        PlanVersion.objects.filter(plan=self.plan, frequency=self.version.frequency, is_current=True).update(is_current=False)
        PlanVersion.objects.create(plan=self.plan, frequency=self.version.frequency, price_amount=Decimal("39.00"), price_currency="USD", is_current=True)

        # La suscripción sigue ligada a `self.version` (USD 29) — nunca
        # se reasigna sola a la nueva versión vigente.
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.version.pk)

        # Llega el webhook de la 2da cobranza (PayPal solo puede cobrar
        # lo que el Billing Plan original — USD 29 — tiene configurado).
        recurring_services.confirm_recurring_charge(
            self.subscription, amount=Decimal("29.00"), currency="USD", external_reference="SALE-RENOVACION", user=self.owner,
        )
        segunda_factura = SaaSInvoice.all_objects.filter(subscription=self.subscription).exclude(pk=self.invoice.pk).first()
        self.assertIsNotNone(segunda_factura)
        self.assertEqual(segunda_factura.total, Decimal("29.00"))

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total, Decimal("29.00"))  # el historial nunca cambia retroactivamente.


class MultiCurrencyRecurringTests(TestCase):
    def test_billing_plan_y_cobro_respetan_la_moneda_de_la_planversion_sin_convertir(self):
        tenant, owner = crear_tenant_con_owner(name="Empresa EUR", slug="empresa-eur", email="owner.eur@example.com")
        plan, version = crear_plan_con_version(slug="plan-eur", precio=Decimal("25.00"), currency="EUR")
        saas_customer = crear_saas_customer(email="cliente.eur@example.com")
        subscription = subscription_services.create_subscription(tenant, saas_customer=saas_customer, plan_version=version)
        invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription)
        self.assertEqual(invoice.currency, "EUR")

        with fake_provider(next_recurring_subscription_status="ACTIVE") as fake:
            subscription, _url = recurring_services.create_recurring_checkout(
                subscription, user=owner, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
            recurring_services.reconcile_recurring_subscription(subscription, user=owner)

        pago = SaaSPayment.all_objects.get(tenant=tenant)
        self.assertEqual(pago.currency, "EUR")
        self.assertEqual(pago.amount, Decimal("25.00"))
        llamada_plan = [c for c in fake.calls if c[0] == "create_billing_plan"]
        self.assertEqual(len(llamada_plan), 1)


class CancelRecurringSubscriptionTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        with fake_provider(next_recurring_subscription_status="ACTIVE"):
            self.subscription, _url = recurring_services.create_recurring_checkout(
                self.subscription, user=self.owner, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
            recurring_services.reconcile_recurring_subscription(self.subscription, user=self.owner)

    def test_cancelar_coordina_paypal_y_budun_y_conserva_el_historial(self):
        with fake_provider() as fake:
            recurring_services.cancel_recurring_subscription(self.subscription, immediate=True, reason="El tenant canceló", user=self.owner)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.CANCELLED)
        self.assertEqual(self.subscription.paypal_subscription_status, "CANCELLED")
        self.assertEqual(len([c for c in fake.calls if c[0] == "cancel_recurring_subscription"]), 1)
        # El historial de factura/pago sigue intacto — nunca se borra.
        self.assertEqual(SaaSInvoice.all_objects.filter(subscription=self.subscription).count(), 1)
        self.assertEqual(SaaSPayment.all_objects.filter(tenant=self.tenant).count(), 1)

    def test_cancelar_impide_que_un_cobro_tardio_reactive_la_suscripcion(self):
        with fake_provider():
            recurring_services.cancel_recurring_subscription(self.subscription, immediate=True, reason="cancelado", user=self.owner)

        from apps.billing import services

        # Un cobro tardío/fuera de orden llega DESPUÉS de la cancelación
        # (PayPal reintentando algo que ya no debería reintentar, o
        # simplemente un evento demorado) — nunca debe reactivar nada.
        body = build_webhook_body(
            event_id="WH-CANCEL-TARDIO", event_type="PAYMENT.SALE.COMPLETED",
            resource={"id": "SALE-TARDIA", "billing_agreement_id": self.subscription.paypal_subscription_id, "amount": {"total": "29.00", "currency": "USD"}},
        )
        with fake_provider():
            services.process_webhook_event(headers={}, raw_body=body)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.CANCELLED)


class SubscriptionWebhookTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        with fake_provider():
            self.subscription, _url = recurring_services.create_recurring_checkout(
                self.subscription, user=self.owner, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
        subscription_services.activate_subscription(self.subscription, user=self.owner)  # simula ya-autorizada y activa.

    def _webhook(self, event_id, event_type, resource):
        from apps.billing import services

        body = build_webhook_body(event_id=event_id, event_type=event_type, resource=resource)
        with fake_provider():
            return services.process_webhook_event(headers={}, raw_body=body)

    def test_payment_sale_completed_confirma_el_cobro_y_aplica_a_la_factura_abierta(self):
        from apps.billing.models import PayPalWebhookEvent

        evento = self._webhook(
            "WH-SUB-1", "PAYMENT.SALE.COMPLETED",
            {"id": "SALE-1", "billing_agreement_id": self.subscription.paypal_subscription_id, "amount": {"total": "29.00", "currency": "USD"}},
        )
        self.assertEqual(evento.status, PayPalWebhookEvent.Status.PROCESSED)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PAID)

    def test_evento_duplicado_no_se_procesa_dos_veces(self):
        from apps.billing.models import PayPalWebhookEvent

        resource = {"id": "SALE-DUP", "billing_agreement_id": self.subscription.paypal_subscription_id, "amount": {"total": "29.00", "currency": "USD"}}
        primero = self._webhook("WH-SUB-DUP", "PAYMENT.SALE.COMPLETED", resource)
        segundo = self._webhook("WH-SUB-DUP", "PAYMENT.SALE.COMPLETED", resource)
        self.assertEqual(primero.pk, segundo.pk)
        self.assertEqual(PayPalWebhookEvent.objects.filter(event_id="WH-SUB-DUP").count(), 1)
        self.assertEqual(SaaSPayment.all_objects.filter(tenant=self.tenant).count(), 1)

    def test_payment_failed_marca_past_due(self):
        self._webhook("WH-SUB-2", "BILLING.SUBSCRIPTION.PAYMENT.FAILED", {"id": self.subscription.paypal_subscription_id, "status": "ACTIVE"})
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.PAST_DUE)

    def test_suspended_suspende_la_suscripcion(self):
        self._webhook("WH-SUB-3", "BILLING.SUBSCRIPTION.SUSPENDED", {"id": self.subscription.paypal_subscription_id, "status": "SUSPENDED"})
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.SUSPENDED)

    def test_cancelled_cancela_la_suscripcion(self):
        self._webhook("WH-SUB-4", "BILLING.SUBSCRIPTION.CANCELLED", {"id": self.subscription.paypal_subscription_id, "status": "CANCELLED"})
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.CANCELLED)

    def test_evento_fuera_de_orden_tras_cancelacion_no_reactiva_nada(self):
        self._webhook("WH-SUB-5", "BILLING.SUBSCRIPTION.CANCELLED", {"id": self.subscription.paypal_subscription_id, "status": "CANCELLED"})
        # Un PAYMENT.SALE.COMPLETED tardío/fuera de orden llega DESPUÉS
        # de la cancelación — nunca debe reactivar la suscripción.
        self._webhook(
            "WH-SUB-6", "PAYMENT.SALE.COMPLETED",
            {"id": "SALE-TARDIA", "billing_agreement_id": self.subscription.paypal_subscription_id, "amount": {"total": "29.00", "currency": "USD"}},
        )
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.CANCELLED)

    def test_evento_sin_suscripcion_asociada_se_ignora_sin_error(self):
        from apps.billing.models import PayPalWebhookEvent

        evento = self._webhook("WH-SUB-7", "BILLING.SUBSCRIPTION.SUSPENDED", {"id": "SUB-QUE-NO-EXISTE", "status": "SUSPENDED"})
        self.assertEqual(evento.status, PayPalWebhookEvent.Status.IGNORED)

    def test_nunca_crea_apps_sales_payment(self):
        self._webhook(
            "WH-SUB-8", "PAYMENT.SALE.COMPLETED",
            {"id": "SALE-8", "billing_agreement_id": self.subscription.paypal_subscription_id, "amount": {"total": "29.00", "currency": "USD"}},
        )
        self.assertEqual(SalesPayment.all_objects.filter(tenant=self.tenant).count(), 0)


class RecurringConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)

    def test_dos_intentos_simultaneos_de_autorizar_cobro_recurrente_solo_crean_una_autorizacion(self):
        resultados = []
        barrera = threading.Barrier(2)

        def autorizar():
            barrera.wait()
            try:
                recurring_services.create_recurring_checkout(
                    self.subscription, user=self.owner, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
                )
                resultados.append("ok")
            except recurring_services.InvalidRecurringOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=autorizar) for _ in range(2)]
        with fake_provider():
            for hilo in hilos:
                hilo.start()
            for hilo in hilos:
                hilo.join()

        self.assertEqual(resultados.count("ok"), 1)
        self.assertEqual(resultados.count("rechazado"), 1)
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.paypal_subscription_id)

    def test_dos_workers_procesando_el_mismo_webhook_de_cobro_solo_aplican_una_vez(self):
        with fake_provider():
            subscription, _url = recurring_services.create_recurring_checkout(
                self.subscription, user=self.owner, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
        subscription_services.activate_subscription(subscription, user=self.owner)

        from apps.billing import services

        body = build_webhook_body(
            event_id="WH-CONCURRENCY-1", event_type="PAYMENT.SALE.COMPLETED",
            resource={"id": "SALE-CONC-1", "billing_agreement_id": subscription.paypal_subscription_id, "amount": {"total": "29.00", "currency": "USD"}},
        )
        resultados = []
        barrera = threading.Barrier(2)

        def procesar():
            barrera.wait()
            try:
                with fake_provider():
                    evento = services.process_webhook_event(headers={}, raw_body=body)
                resultados.append(evento.pk)
            finally:
                connection.close()

        hilos = [threading.Thread(target=procesar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados[0], resultados[1])  # misma fila de evento — nunca dos.
        self.assertEqual(SaaSPayment.all_objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(SaaSPaymentAllocation.all_objects.filter(invoice=self.invoice).count(), 1)
