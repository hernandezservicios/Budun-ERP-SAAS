"""
Concurrencia real de Billing SaaS completo (FASE 17, sección 43) —
mismo patrón `TransactionTestCase` + hilos reales que el resto del
proyecto desde FASE 10."""

import threading
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase

from apps.billing.models import BankAccount, SaaSInvoice, SaaSPayment, SaaSPaymentAllocation, Subscription
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import payments as payment_services
from apps.billing.services import subscriptions as subscription_services
from apps.billing.services import transfers as transfer_services
from apps.tenants.models import Tenant

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


class InvoiceGenerationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)

    def test_dos_generaciones_simultaneas_de_la_misma_factura_nunca_duplican(self):
        resultados = []
        barrera = threading.Barrier(2)

        def generar():
            barrera.wait()
            try:
                _invoice, creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
                resultados.append(creada)
            finally:
                connection.close()

        hilos = [threading.Thread(target=generar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(
            SaaSInvoice.all_objects.filter(subscription=self.subscription, period_start=self.subscription.current_period_start).count(), 1,
        )
        self.assertEqual(resultados.count(True), 1)


class PaymentAllocationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        pago = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            method=SaaSPayment.Method.MANUAL_OTHER, amount=self.invoice.total, currency="USD",
        )
        self.payment = payment_services.confirm_payment(pago)

    def test_dos_asignaciones_simultaneas_que_exceden_el_pago_solo_una_gana(self):
        """Dos hilos intentan aplicar el MISMO pago (saldo = 29.00) a la
        MISMA factura (saldo pendiente = 29.00) por 20.00 cada uno —
        juntos exceden lo disponible del pago; exactamente uno debe
        ganar."""
        resultados = []
        barrera = threading.Barrier(2)

        def aplicar():
            barrera.wait()
            try:
                payment_services.apply_payment_to_invoices(self.payment, [(self.invoice, Decimal("20.00"))])
                resultados.append("ok")
            except payment_services.InvalidPaymentOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=aplicar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1)
        self.assertEqual(resultados.count("rechazado"), 1)
        self.invoice.refresh_from_db()
        self.assertEqual(invoicing_services.get_invoice_balance_due(self.invoice), Decimal("9.00"))


class InitialActivationConcurrencyTests(TransactionTestCase):
    """Gate Local (KNOWN_ISSUES.md): `activate_pending_subscription`
    (la nueva acción explícita "Activar", distinta de "Reactivar") debe
    resolver una sola transición real sin importar cuántas veces se
    dispare a la vez — mismo criterio que el resto de la fase."""

    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(
            self.tenant, saas_customer=self.saas_customer, plan_version=self.version,
        )

    def test_dos_activaciones_iniciales_simultaneas_solo_generan_una_factura_un_pago_una_allocation(self):
        resultados = []
        barrera = threading.Barrier(2)

        def activar():
            barrera.wait()
            try:
                subscription_services.activate_pending_subscription(self.subscription)
                resultados.append("ok")
            except subscription_services.InvalidSubscriptionOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=activar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        # Ambos hilos pueden terminar "ok" (la segunda pasada es un
        # no-op idempotente sobre una suscripción ya ACTIVE) — lo que
        # nunca debe pasar es una segunda factura/pago/allocation real.
        self.assertEqual(SaaSInvoice.all_objects.filter(subscription=self.subscription).count(), 1)
        self.assertEqual(SaaSPayment.all_objects.filter(subscription=self.subscription).count(), 1)
        self.assertEqual(
            SaaSPaymentAllocation.all_objects.filter(payment__subscription=self.subscription).count(), 1,
        )
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)

    def test_activacion_manual_y_confirmacion_automatica_simultaneas_convergen_en_una_sola_activacion(self):
        """Simula el caso real de "activación + webhook simultáneos"
        (sección 9 del Gate Local): la factura/pago YA existen y están
        confirmados (precondición real de `_on_payment_confirmed`, que
        NUNCA llama a `activate_subscription` sin un `SaaSPayment` ya
        confirmado, ver `services.paypal_integration`) — lo que se
        prueba aquí es la carrera FINAL entre un admin que hace clic en
        "Activar" (`activate_pending_subscription`) y la confirmación
        automática del webhook (`activate_subscription` directo)
        disparándose al mismo tiempo para la MISMA suscripción. Ninguna
        debe fallar de forma inesperada, y el resultado debe ser una
        única activación consistente, sin factura ni pago duplicados."""
        invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        pago = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            method=SaaSPayment.Method.PAYPAL, amount=invoice.total, currency=invoice.currency,
            status=SaaSPayment.Status.CONFIRMED,
        )
        payment_services.auto_apply_payment(pago)

        resultados = []
        barrera = threading.Barrier(2)

        def activar_manual():
            barrera.wait()
            try:
                subscription_services.activate_pending_subscription(self.subscription)
                resultados.append("manual_ok")
            except subscription_services.InvalidSubscriptionOperation:
                resultados.append("manual_rechazado")
            finally:
                connection.close()

        def confirmar_automatico():
            barrera.wait()
            try:
                subscription_services.activate_subscription(self.subscription)
                resultados.append("auto_ok")
            finally:
                connection.close()

        hilos = [threading.Thread(target=activar_manual), threading.Thread(target=confirmar_automatico)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertIn("auto_ok", resultados)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        # La factura/pago ya existían antes de la carrera — ninguno de
        # los dos caminos debe haber creado una segunda factura ni un
        # segundo pago.
        self.assertEqual(SaaSInvoice.all_objects.filter(subscription=self.subscription).count(), 1)
        self.assertEqual(SaaSPayment.all_objects.filter(subscription=self.subscription).count(), 1)


class PaymentProofApprovalConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        self.bank_account = BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD", account_holder="Budun ERP", account_number="0000",
        )
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.proof = transfer_services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD",
            file=SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )

    def test_dos_aprobaciones_simultaneas_del_mismo_comprobante_nunca_crean_dos_pagos(self):
        resultados = []
        barrera = threading.Barrier(2)

        def aprobar():
            barrera.wait()
            try:
                _proof, payment = transfer_services.approve_payment_proof(self.proof)
                resultados.append(payment)
            finally:
                connection.close()

        hilos = [threading.Thread(target=aprobar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        pagos_creados = [r for r in resultados if r is not None]
        self.assertEqual(SaaSPayment.all_objects.filter(payment_proof=self.proof).count(), 1)
        self.assertEqual(len(pagos_creados), 1, "Exactamente una de las dos aprobaciones concurrentes debe crear el pago; la otra ve ya APROBADO y no crea uno segundo.")
