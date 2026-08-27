"""
Pruebas de concurrencia real (mismo patrón que `apps.sales.tests.
test_concurrency`, FASE 10): `TransactionTestCase` + hilos reales, para
que `select_for_update()`/el `UniqueConstraint` de
`PayPalWebhookEvent.event_id` realmente sirvan de barrera entre
conexiones concurrentes distintas — sección 27 de la fase."""

import threading

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from apps.billing import services
from apps.billing.models import PayPalTransaction, PayPalWebhookEvent
from apps.tenants.models import Tenant

from ._helpers import build_webhook_body, fake_provider

User = get_user_model()


class WebhookConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrencia Billing", slug="concurrencia-billing")
        self.superadmin = User.objects.create_superuser(email="super.concurrencia@example.com", password="clave-de-prueba-987")
        with fake_provider():
            self.txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://x/return", cancel_url="https://x/cancel",
            )

    def test_dos_entregas_simultaneas_del_mismo_webhook_solo_se_procesan_una_vez(self):
        body = build_webhook_body(
            event_id="WH-CONCURRENTE", event_type="PAYMENT.CAPTURE.COMPLETED",
            resource={"id": "CAPTURE-CONCURRENTE", "amount": {"value": "29.00", "currency_code": "USD"},
                      "supplementary_data": {"related_ids": {"order_id": self.txn.external_order_id}}},
        )
        resultados = []
        barrera = threading.Barrier(2)

        def entregar():
            barrera.wait()
            try:
                with fake_provider():
                    evento = services.process_webhook_event(headers={}, raw_body=body)
                resultados.append(evento.status)
            finally:
                connection.close()

        hilos = [threading.Thread(target=entregar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(PayPalWebhookEvent.objects.filter(event_id="WH-CONCURRENTE").count(), 1, "Nunca debe crearse una segunda fila para el mismo event_id.")
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PayPalTransaction.Status.CONFIRMED)
        self.assertEqual(len(resultados), 2)


class RefundConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrencia Reembolso", slug="concurrencia-reembolso")
        self.superadmin = User.objects.create_superuser(email="super.reembolso@example.com", password="clave-de-prueba-987")
        with fake_provider():
            self.txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://x/return", cancel_url="https://x/cancel",
            )
            self.txn = services.capture_checkout(self.txn, user=self.superadmin)
        self.assertEqual(self.txn.status, PayPalTransaction.Status.CONFIRMED)

    def test_dos_solicitudes_de_reembolso_concurrentes_solo_una_gana(self):
        resultados = []
        barrera = threading.Barrier(2)

        def reembolsar():
            barrera.wait()
            try:
                with fake_provider():
                    services.request_refund(self.txn, user=self.superadmin)
                resultados.append("ok")
            except services.InvalidBillingOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=reembolsar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1, "Exactamente una de las dos solicitudes de reembolso concurrentes debe ganar.")
        self.assertEqual(resultados.count("rechazado"), 1)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PayPalTransaction.Status.REFUNDED)
