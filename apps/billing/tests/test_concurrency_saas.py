"""
Concurrencia real de Billing SaaS completo (FASE 17, sección 43) —
mismo patrón `TransactionTestCase` + hilos reales que el resto del
proyecto desde FASE 10."""

import threading
from datetime import date
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase

from apps.billing import services as billing_services
from apps.billing.models import BankAccount, BillingRefund, PayPalTransaction, SaaSInvoice, SaaSPayment, SaaSPaymentAllocation, Subscription
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import payments as payment_services
from apps.billing.services import refunds as refund_services
from apps.billing.services import subscriptions as subscription_services
from apps.billing.services import transfers as transfer_services
from apps.tenants.models import Tenant

from ._helpers import fake_provider
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


class CreateCheckoutForInvoiceConcurrencyTests(TransactionTestCase):
    """FASE DE CORRECCIÓN 2B — dos clics simultáneos en "Pagar con
    PayPal" sobre la MISMA factura (dos pestañas, doble clic) nunca
    deben crear dos órdenes de PayPal en paralelo — ver
    `create_checkout_for_invoice`, `KNOWN_ISSUES.md` #131."""

    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(
            self.tenant, saas_customer=self.saas_customer, plan_version=self.version,
        )
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)

    def test_dos_intentos_simultaneos_de_pagar_la_misma_factura_por_paypal_solo_crean_un_checkout(self):
        resultados = []
        barrera = threading.Barrier(2)

        def iniciar_checkout():
            barrera.wait()
            try:
                billing_services.create_checkout_for_invoice(
                    invoice=self.invoice, user=self.owner,
                    return_url="https://example.test/return", cancel_url="https://example.test/cancel",
                )
                resultados.append("ok")
            except billing_services.InvalidBillingOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=iniciar_checkout) for _ in range(2)]
        with fake_provider():
            for hilo in hilos:
                hilo.start()
            for hilo in hilos:
                hilo.join()

        self.assertEqual(resultados.count("ok"), 1)
        self.assertEqual(resultados.count("rechazado"), 1)
        self.assertEqual(PayPalTransaction.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(SaaSPayment.all_objects.filter(tenant=self.tenant).count(), 1)


class ReactivationConcurrencyTests(TransactionTestCase):
    """FASE DE CORRECCIÓN 3 (Lifecycle integral, sección 23) — dos
    reactivaciones simultáneas de la MISMA suscripción SUSPENDED nunca
    deben producir dos transiciones/notificaciones ni un período
    restaurado dos veces."""

    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = subscription_services.activate_subscription(subscription)
        self.subscription = subscription_services.suspend_subscription(subscription)

    def test_dos_reactivaciones_simultaneas_solo_una_transiciona(self):
        resultados = []
        barrera = threading.Barrier(2)

        def reactivar():
            barrera.wait()
            try:
                subscription_services.reactivate_subscription(self.subscription)
                resultados.append("ok")
            except subscription_services.InvalidSubscriptionOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=reactivar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1)
        self.assertEqual(resultados.count("rechazado"), 1)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)


class RefundConcurrencyTests(TransactionTestCase):
    """FASE DE CORRECCIÓN 3 (Lifecycle integral, sección 23) — dos
    solicitudes de reembolso simultáneas sobre el MISMO pago nunca deben
    poder exceder juntas el monto disponible del pago."""

    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.saas_customer = crear_saas_customer()
        pago = payment_services.record_payment(
            tenant=self.tenant, saas_customer=self.saas_customer, method=SaaSPayment.Method.MANUAL_OTHER,
            amount=Decimal("50.00"), currency="USD",
        )
        self.payment = payment_services.confirm_payment(pago)

    def test_dos_solicitudes_de_reembolso_simultaneas_nunca_exceden_el_monto_disponible(self):
        resultados = []
        barrera = threading.Barrier(2)

        def solicitar():
            barrera.wait()
            try:
                refund_services.request_billing_refund(self.payment, amount=Decimal("30.00"))
                resultados.append("ok")
            except refund_services.InvalidRefundOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=solicitar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1)
        self.assertEqual(resultados.count("rechazado"), 1)
        total_solicitado = sum((r.amount for r in BillingRefund.all_objects.filter(payment=self.payment)), Decimal("0"))
        self.assertEqual(total_solicitado, Decimal("30.00"))


class UpgradeProrationInvoiceConcurrencyTests(TransactionTestCase):
    """FASE DE CORRECCIÓN 3 — dos envíos simultáneos del formulario de
    cambio de plan (mismo `change_date`) nunca deben generar dos
    facturas de cargo por prorrateo para el mismo día."""

    reset_sequences = True

    def setUp(self):
        from datetime import date

        self.change_date = date(2026, 1, 16)
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("30.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        subscription = subscription_services.activate_subscription(subscription)
        subscription.current_period_start = date(2026, 1, 1)
        subscription.current_period_end = date(2026, 1, 31)
        subscription.save(update_fields=["current_period_start", "current_period_end"])
        self.subscription = subscription
        self.plan2, self.version2 = crear_plan_con_version(slug="empresarial-conc", precio=Decimal("90.00"))

    def test_dos_llamadas_simultaneas_a_issue_proration_charge_invoice_no_duplican(self):
        # Prueba directa de la garantía de idempotencia real (`UniqueConstraint
        # (subscription, period_start)`), mismo patrón que
        # `InvoiceGenerationConcurrencyTests` para la renovación normal —
        # `change_plan` en sí serializa por el lock de `Subscription`, así
        # que la carrera real que puede ocurrir es sobre esta función.
        resultados = []
        barrera = threading.Barrier(2)

        def emitir():
            barrera.wait()
            try:
                invoicing_services.issue_proration_charge_invoice(
                    self.subscription, amount=Decimal("30.00"), currency="USD", change_date=self.change_date,
                    description="Prorrateo por cambio de plan (prueba de concurrencia)",
                )
                resultados.append("ok")
            finally:
                connection.close()

        hilos = [threading.Thread(target=emitir) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 2)
        self.assertEqual(
            SaaSInvoice.all_objects.filter(subscription=self.subscription, period_start=self.change_date).count(), 1,
        )


class SubmitPaymentProofConcurrencyTests(TransactionTestCase):
    """FASE DE CORRECCIÓN 4 (sección 18, "doble submit"/"dos comprobantes
    concurrentes"): antes de esta corrección, el guard de "factura vigente
    + sin comprobante pendiente" era un `.exists()` sin ningún lock — dos
    envíos concurrentes del mismo formulario podían crear dos
    `PaymentProof` `SUBMITTED` para la MISMA factura."""

    reset_sequences = True

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        self.bank_account = BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD", account_holder="Budun ERP", account_number="0000",
        )

    def test_dos_envios_simultaneos_del_mismo_comprobante_solo_uno_se_crea(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        resultados = []
        barrera = threading.Barrier(2)

        def enviar():
            barrera.wait()
            try:
                transfer_services.submit_payment_proof(
                    subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
                    declared_amount=self.invoice.total, declared_currency="USD",
                    file=SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
                )
                resultados.append("ok")
            except transfer_services.InvalidTransferOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=enviar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1)
        self.assertEqual(resultados.count("rechazado"), 1)
        from apps.billing.models import PaymentProof

        self.assertEqual(PaymentProof.all_objects.filter(invoice=self.invoice).count(), 1)


class ApproveRejectRaceConcurrencyTests(TransactionTestCase):
    """FASE DE CORRECCIÓN 4 (sección 18, "aprobación + rechazo
    simultáneos"): la carrera real entre un Super Admin que aprueba y otro
    (u otra pestaña del mismo) que rechaza el MISMO comprobante a la vez
    debe resolverse en una única transición consistente, nunca en un
    estado contradictorio (comprobante `REJECTED` con un `SaaSPayment`
    `CONFIRMED`/`Subscription ACTIVE` ya generados por la aprobación)."""

    reset_sequences = True

    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        self.bank_account = BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD", account_holder="Budun ERP", account_number="0000",
        )
        self.proof = transfer_services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD",
            file=SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )

    def test_aprobar_y_rechazar_el_mismo_comprobante_a_la_vez_converge_en_un_estado_consistente(self):
        resultados = []
        barrera = threading.Barrier(2)

        def aprobar():
            barrera.wait()
            try:
                transfer_services.approve_payment_proof(self.proof)
                resultados.append("aprobado")
            except transfer_services.InvalidTransferOperation:
                resultados.append("aprobacion_rechazada")
            finally:
                connection.close()

        def rechazar():
            barrera.wait()
            try:
                transfer_services.reject_payment_proof(self.proof, reason="carrera de prueba")
                resultados.append("rechazado")
            except transfer_services.InvalidTransferOperation:
                resultados.append("rechazo_rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=aprobar), threading.Thread(target=rechazar)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        # Exactamente uno de los dos debe haber ganado la carrera.
        self.assertEqual(len(resultados), 2)
        self.assertEqual(sum(1 for r in resultados if r in ("aprobado", "rechazado")), 1)

        self.proof.refresh_from_db()
        if self.proof.status == "approved":
            self.assertEqual(SaaSPayment.all_objects.filter(payment_proof=self.proof, status="confirmed").count(), 1)
        else:
            self.assertEqual(self.proof.status, "rejected")
            self.assertEqual(SaaSPayment.all_objects.filter(payment_proof=self.proof).count(), 0)


class TransferAndPayPalRaceConcurrencyTests(TransactionTestCase):
    """FASE DE CORRECCIÓN 4 (sección 18, "comprobante + PayPal sobre la
    misma factura"): PayPal y Transferencia son métodos INDEPENDIENTES
    (sección 19) — nada impide que un tenant tenga ambos en curso a la
    vez para la misma factura, así que la aprobación de uno y la captura
    del otro deben poder converger sin duplicar cobros ni corromper el
    saldo (un sobrepago resultante queda como saldo a favor, nunca se
    pierde ni se rechaza con un error, ver sección 8)."""

    reset_sequences = True

    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        self.bank_account = BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD", account_holder="Budun ERP", account_number="0000",
        )
        self.proof = transfer_services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD",
            file=SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )

    def test_aprobar_transferencia_y_capturar_paypal_a_la_vez_nunca_duplica_ni_corrompe(self):
        with fake_provider():
            pago_paypal, txn, _approve_url = billing_services.create_checkout_for_invoice(
                invoice=self.invoice, user=self.owner,
                return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )

        resultados = []
        barrera = threading.Barrier(2)

        def aprobar_transferencia():
            barrera.wait()
            try:
                transfer_services.approve_payment_proof(self.proof)
                resultados.append("transferencia_ok")
            except Exception as error:  # noqa: BLE001 -- cualquier resultado se registra, nunca se descarta.
                resultados.append(f"transferencia_error:{error}")
            finally:
                connection.close()

        def capturar_paypal():
            barrera.wait()
            try:
                with fake_provider():
                    billing_services.capture_checkout(txn, user=self.owner)
                resultados.append("paypal_ok")
            except Exception as error:  # noqa: BLE001
                resultados.append(f"paypal_error:{error}")
            finally:
                connection.close()

        hilos = [threading.Thread(target=aprobar_transferencia), threading.Thread(target=capturar_paypal)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertIn("transferencia_ok", resultados)
        self.assertIn("paypal_ok", resultados)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "paid")
        # Los dos pagos (29.00 transferencia + 29.00 PayPal) suman 58.00;
        # la factura (29.00) queda PAID y el resto (29.00) es saldo a
        # favor trazable -- nunca se pierde ni duplica la aplicación.
        from apps.billing.services import credits as credit_services

        saldo = credit_services.get_subscription_credit_balance(tenant=self.tenant, subscription=self.subscription)
        self.assertEqual(saldo, Decimal("29.00"))
        self.assertEqual(SaaSPayment.all_objects.filter(tenant=self.tenant, status="confirmed").count(), 2)


class AutoApplyCreditNoteConcurrencyTests(TransactionTestCase):
    """FASE DE CORRECCIÓN 6: dos barridos concurrentes de `auto_apply_
    available_credit_notes` sobre la MISMA suscripción (p. ej. dos
    facturas generándose casi a la vez -- el cron de renovación y una
    reconciliación reactiva) pueden intentar aplicar la MISMA nota de
    crédito a la vez. Antes de esta corrección, la excepción de la
    carrera (`InvalidCreditOperation`) se propagaba sin atrapar y podía
    romper la generación de la factura que disparó el barrido."""

    reset_sequences = True

    def setUp(self):
        from apps.billing.services import credits as credit_services

        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("15.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice_a, _creada = invoicing_services.generate_invoice_for_subscription(
            self.subscription, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        )
        self.invoice_b, _creada = invoicing_services.generate_invoice_for_subscription(
            self.subscription, period_start=date(2026, 2, 1), period_end=date(2026, 2, 28),
        )
        self.nota = credit_services.issue_credit_note(
            tenant=self.tenant, saas_customer=self.saas_customer, subscription=self.subscription,
            amount=Decimal("20.00"), currency="USD", reason="prueba de concurrencia",
        )

    def test_dos_barridos_simultaneos_de_la_misma_nota_de_credito_nunca_rompen_ni_sobre_aplican(self):
        from apps.billing.services import credits as credit_services

        resultados = []
        barrera = threading.Barrier(2)

        def barrer():
            barrera.wait()
            try:
                credit_services.auto_apply_available_credit_notes(self.subscription)
                resultados.append("ok")
            except credit_services.InvalidCreditOperation as error:
                resultados.append(f"error:{error}")
            finally:
                connection.close()

        hilos = [threading.Thread(target=barrer) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados, ["ok", "ok"], "Ninguno de los dos barridos debe propagar una excepción sin atrapar.")
        self.assertEqual(credit_services.get_unapplied_credit_note_amount(self.nota), Decimal("0"))
        aplicado_total = sum(
            invoicing_services.get_invoice_balance_due(f) for f in (self.invoice_a, self.invoice_b)
        )
        # Las dos facturas (15.00 + 15.00 = 30.00) menos el crédito
        # aplicado (20.00, nunca más de eso) deben sumar exactamente 10.00
        # pendiente -- nunca de más ni de menos.
        self.invoice_a.refresh_from_db()
        self.invoice_b.refresh_from_db()
        saldo_restante = invoicing_services.get_invoice_balance_due(self.invoice_a) + invoicing_services.get_invoice_balance_due(self.invoice_b)
        self.assertEqual(saldo_restante, Decimal("10.00"))
