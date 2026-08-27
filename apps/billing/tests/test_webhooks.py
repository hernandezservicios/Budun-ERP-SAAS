from django.test import TestCase

from apps.billing import services
from apps.billing.models import PayPalTransaction, PayPalWebhookEvent

from ._helpers import BillingTestCase, build_webhook_body, fake_provider


class WebhookProcessingTests(BillingTestCase, TestCase):
    def setUp(self):
        self._crear_base()

    def _transaccion_creada(self):
        with fake_provider():
            txn, _url = services.create_checkout(
                tenant=self.tenant, plan_id="profesional", purpose=PayPalTransaction.Purpose.SIGNUP,
                user=self.superadmin, return_url="https://example.test/return", cancel_url="https://example.test/cancel",
            )
        return txn

    def test_webhook_capture_completed_confirma_la_transaccion(self):
        txn = self._transaccion_creada()
        body = build_webhook_body(
            event_id="WH-1", event_type="PAYMENT.CAPTURE.COMPLETED",
            resource={"id": "CAPTURE-WEBHOOK-1", "status": "COMPLETED", "amount": {"value": "29.00", "currency_code": "USD"},
                      "supplementary_data": {"related_ids": {"order_id": txn.external_order_id}}},
        )
        with fake_provider():
            evento = services.process_webhook_event(headers={}, raw_body=body)
        self.assertEqual(evento.status, PayPalWebhookEvent.Status.PROCESSED)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PayPalTransaction.Status.CONFIRMED)
        self.assertEqual(txn.external_capture_id, "CAPTURE-WEBHOOK-1")

    def test_webhook_duplicado_no_se_procesa_dos_veces(self):
        txn = self._transaccion_creada()
        body = build_webhook_body(
            event_id="WH-DUP", event_type="PAYMENT.CAPTURE.COMPLETED",
            resource={"id": "CAPTURE-DUP", "amount": {"value": "29.00", "currency_code": "USD"},
                      "supplementary_data": {"related_ids": {"order_id": txn.external_order_id}}},
        )
        with fake_provider():
            primero = services.process_webhook_event(headers={}, raw_body=body)
            segundo = services.process_webhook_event(headers={}, raw_body=body)
        self.assertEqual(primero.status, PayPalWebhookEvent.Status.PROCESSED)
        # El segundo debe ser la MISMA fila (mismo pk) — nunca una segunda
        # aplicación del evento.
        self.assertEqual(primero.pk, segundo.pk)
        self.assertEqual(PayPalWebhookEvent.objects.filter(event_id="WH-DUP").count(), 1)

    def test_webhook_con_firma_invalida_duplicado_no_rompe_con_integrity_error(self):
        """Bug real encontrado por el smoke test de Sandbox (KNOWN_ISSUES
        #107): dos entregas del MISMO evento con firma inválida (PayPal
        reintenta cualquier respuesta no-2xx, y un rechazo por firma
        responde 400) no debían romper con un `IntegrityError` sin
        capturar en la segunda entrega."""
        txn = self._transaccion_creada()
        body = build_webhook_body(
            event_id="WH-FIRMA-INVALIDA-DUP", event_type="PAYMENT.CAPTURE.COMPLETED",
            resource={"id": "CAPTURE-X", "supplementary_data": {"related_ids": {"order_id": txn.external_order_id}}},
        )
        with fake_provider(next_verification=False):
            primero = services.process_webhook_event(headers={}, raw_body=body)
            segundo = services.process_webhook_event(headers={}, raw_body=body)
        self.assertEqual(primero.status, PayPalWebhookEvent.Status.REJECTED)
        self.assertEqual(primero.pk, segundo.pk)
        self.assertEqual(PayPalWebhookEvent.objects.filter(event_id="WH-FIRMA-INVALIDA-DUP").count(), 1)

    def test_webhook_con_firma_invalida_se_rechaza_y_no_se_procesa(self):
        txn = self._transaccion_creada()
        body = build_webhook_body(
            event_id="WH-BAD-SIG", event_type="PAYMENT.CAPTURE.COMPLETED",
            resource={"id": "CAPTURE-BAD", "supplementary_data": {"related_ids": {"order_id": txn.external_order_id}}},
        )
        with fake_provider(next_verification=False):
            evento = services.process_webhook_event(headers={}, raw_body=body)
        self.assertEqual(evento.status, PayPalWebhookEvent.Status.REJECTED)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PayPalTransaction.Status.CREATED)

    def test_webhook_sin_transaccion_asociada_se_ignora_sin_error(self):
        body = build_webhook_body(event_id="WH-HUERFANO", event_type="PAYMENT.CAPTURE.COMPLETED", resource={"id": "CAPTURE-INEXISTENTE"})
        with fake_provider():
            evento = services.process_webhook_event(headers={}, raw_body=body)
        self.assertEqual(evento.status, PayPalWebhookEvent.Status.IGNORED)

    def test_webhook_de_tipo_reconocible_pero_sin_manejador_no_falla_ni_cambia_estado(self):
        """`PAYMENT.CAPTURE.PENDING` SÍ se puede correlacionar con una
        transacción (prefijo `PAYMENT.CAPTURE.`), pero no tiene una rama
        explícita en `_apply_webhook_event` — debe quedar PROCESSED como
        no-op deliberado, nunca un error."""
        txn = self._transaccion_creada()
        body = build_webhook_body(
            event_id="WH-SIN-MANEJADOR", event_type="PAYMENT.CAPTURE.PENDING",
            resource={"id": "CAPTURE-SIN-MANEJADOR", "supplementary_data": {"related_ids": {"order_id": txn.external_order_id}}},
        )
        with fake_provider():
            evento = services.process_webhook_event(headers={}, raw_body=body)
        self.assertEqual(evento.status, PayPalWebhookEvent.Status.PROCESSED)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PayPalTransaction.Status.CREATED)

    def test_webhook_sin_prefijo_reconocido_se_ignora_sin_error(self):
        """Un tipo de evento cuyo prefijo no sabemos correlacionar en
        absoluto (p. ej. una disputa) se registra como IGNORED — nunca
        un error, y nunca se inventa una correlación."""
        txn = self._transaccion_creada()
        body = build_webhook_body(event_id="WH-DESCONOCIDO", event_type="CUSTOMER.DISPUTE.CREATED", resource={"id": txn.external_order_id})
        with fake_provider():
            evento = services.process_webhook_event(headers={}, raw_body=body)
        self.assertEqual(evento.status, PayPalWebhookEvent.Status.IGNORED)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PayPalTransaction.Status.CREATED)

    def test_webhook_fuera_de_orden_no_revierte_un_estado_ya_avanzado(self):
        """Un CAPTURE.COMPLETED que llega DESPUÉS de que ya procesamos el
        reembolso (por webhook o por nuestra propia acción) nunca debe
        regresar la transacción a CONFIRMED."""
        txn = self._transaccion_creada()
        with fake_provider():
            txn = services.capture_checkout(txn, user=self.superadmin)
            txn = services.request_refund(txn, user=self.superadmin)
        self.assertEqual(txn.status, PayPalTransaction.Status.REFUNDED)

        body_tardio = build_webhook_body(
            event_id="WH-TARDIO", event_type="PAYMENT.CAPTURE.COMPLETED",
            resource={"id": txn.external_capture_id, "amount": {"value": "29.00", "currency_code": "USD"}},
        )
        with fake_provider():
            evento = services.process_webhook_event(headers={}, raw_body=body_tardio)
        self.assertEqual(evento.status, PayPalWebhookEvent.Status.PROCESSED)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PayPalTransaction.Status.REFUNDED, "Un evento tardío/fuera de orden nunca debe regresar el estado.")

    def test_webhook_capture_refunded_marca_reembolsada_aunque_no_lo_hayamos_iniciado_nosotros(self):
        """Un reembolso hecho directamente en el panel de PayPal (fuera de
        nuestro propio `request_refund`) debe reflejarse igual vía webhook."""
        txn = self._transaccion_creada()
        with fake_provider():
            txn = services.capture_checkout(txn, user=self.superadmin)
        body = build_webhook_body(event_id="WH-REFUND-EXTERNO", event_type="PAYMENT.CAPTURE.REFUNDED", resource={"id": txn.external_capture_id})
        with fake_provider():
            evento = services.process_webhook_event(headers={}, raw_body=body)
        self.assertEqual(evento.status, PayPalWebhookEvent.Status.PROCESSED)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PayPalTransaction.Status.REFUNDED)
