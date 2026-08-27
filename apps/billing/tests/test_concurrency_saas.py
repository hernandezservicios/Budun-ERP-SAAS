"""
Concurrencia real de Billing SaaS completo (FASE 17, sección 43) —
mismo patrón `TransactionTestCase` + hilos reales que el resto del
proyecto desde FASE 10."""

import threading
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase

from apps.billing.models import SaaSInvoice, SaaSPayment
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import payments as payment_services
from apps.billing.services import subscriptions as subscription_services
from apps.billing.services import transfers as transfer_services
from apps.billing.models import BankAccount

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
