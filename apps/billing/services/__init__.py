"""
Única vía sancionada para operar sobre PayPal/Billing SaaS (FASE 16,
ver `docs/paypal.md`). Ninguna vista escribe `PayPalTransaction`/
`PayPalWebhookEvent` directamente ni llama a `apps.billing.providers`
directamente — todo pasa por aquí (mismo principio que
`apps.api.services`/`apps.sales.services`).

Principios aplicados en todo el archivo:
- `transaction.atomic()` + `select_for_update()` en toda operación que
  lee-y-luego-escribe una `PayPalTransaction` (captura, reembolso,
  aplicar un webhook) — dos eventos concurrentes sobre la misma fila
  (dos webhooks duplicados, un webhook compitiendo con nuestra propia
  captura síncrona) producen exactamente UNA transición válida.
- Idempotencia en dos niveles: (1) hacia PayPal, vía `PayPal-Request-Id`
  derivado de `PayPalTransaction.client_reference` (estable por fila);
  (2) hacia nosotros mismos, vía el `UniqueConstraint` de
  `PayPalWebhookEvent.event_id` (nunca se procesa el mismo evento dos
  veces) y guards de estado (un evento que describe una transición ya
  alcanzada es un no-op idempotente, nunca un error).
- Ningún secreto (client secret, access token, firma cruda) se guarda
  jamás en `PayPalTransaction`/`PayPalWebhookEvent`/auditoría.
"""

import json
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog

from .. import signals
from ..models import PayPalGatewayStatus, PayPalTransaction, PayPalWebhookEvent
from ..providers import PaymentProviderError, get_default_provider
from .subscriptions import resolve_plan_pricing

_GATEWAY_STATUS_PK = 1


class InvalidBillingOperation(ValidationError):
    """Plan sin precio de autoservicio, transacción en un estado que no
    admite la operación solicitada (capturar dos veces, reembolsar una
    transacción no confirmada, reembolsar dos veces), etc."""


def _audit(tenant, *, action, user=None, txn=None, before=None, after=None, metadata=None, reason=""):
    """`apps.billing` depende directamente de `apps.audit` (ambas
    apps ya existen para cuando se construye ésta, mismo criterio que
    `apps.api`) — aun así, la auditoría nunca debe poder romper una
    operación de pago real: se envuelve en `try/except`."""
    try:
        from apps.audit.services import log_event

        log_event(
            tenant, user=user, action=action, domain="billing_paypal",
            object_type="paypal_transaction", object_id=(txn.pk if txn is not None else None),
            before=before, after=after, metadata=metadata or {}, reason=reason,
        )
    except Exception:  # noqa: BLE001 — la auditoría nunca debe romper la operación.
        pass


# ---------------------------------------------------------------------
# Configuración/estado del gateway (plataforma)
# ---------------------------------------------------------------------

def get_gateway_status():
    status, _creada = PayPalGatewayStatus.objects.get_or_create(pk=_GATEWAY_STATUS_PK)
    return status


def set_gateway_enabled(*, is_enabled, user):
    status = get_gateway_status()
    status.is_enabled = is_enabled
    status.save(update_fields=["is_enabled", "updated_at"])
    _audit(None, action=AuditLog.Action.GENERIC, user=user, metadata={"paypal_gateway_enabled": is_enabled})
    return status


def test_paypal_connection(*, user):
    """"Probar Conexión": obtiene un access token real (nunca una
    compra), sin exponerlo. Nunca guarda el token, solo el resultado
    booleano y el mensaje de error (si lo hubo) — ver
    `docs/phases/PHASE-16-paypal-sandbox.md` sección 9."""
    from django.conf import settings

    status = get_gateway_status()
    provider = get_default_provider()
    ok, error = provider.test_connection()
    status.last_tested_at = timezone.now()
    status.last_test_ok = ok
    status.last_test_error = (error or "")[:255]
    status.last_tested_environment = settings.PAYPAL_ENVIRONMENT
    status.save(update_fields=["last_tested_at", "last_test_ok", "last_test_error", "last_tested_environment", "updated_at"])
    _audit(
        None, action=AuditLog.Action.PAYPAL_CONFIG_TESTED, user=user,
        metadata={"resultado": ok, "ambiente": settings.PAYPAL_ENVIRONMENT},
    )
    return ok, error


# ---------------------------------------------------------------------
# Checkout (Orders API v2): crear -> aprobar (redirect) -> capturar
# ---------------------------------------------------------------------

def create_checkout(*, tenant, plan_id, purpose, user, return_url, cancel_url, description=""):
    from django.conf import settings

    # Resuelve PRIMERO el `Plan`/`PlanVersion` real de FASE 17 (por
    # `slug`); si no existe todavía, cae al fallback estático de
    # `apps.core.pricing.PLANS` (FASE 6) — mismo criterio de
    # compatibilidad que el resto del proyecto, ver `docs/paypal.md`
    # sección 2 y `subscriptions.resolve_plan_pricing`.
    nombre_plan, amount, currency, _version = resolve_plan_pricing(plan_id)
    if amount is None:
        raise InvalidBillingOperation(f"«{plan_id}» no es un plan reconocido o no tiene checkout de autoservicio (sin precio fijo).")

    status = get_gateway_status()
    if not status.is_enabled:
        raise InvalidBillingOperation("El checkout de PayPal está deshabilitado por el Super Admin.")

    if purpose not in PayPalTransaction.Purpose.values:
        raise InvalidBillingOperation(f"«{purpose}» no es un propósito de pago reconocido.")

    txn = PayPalTransaction.objects.create(
        tenant=tenant, plan_id=plan_id, purpose=purpose, environment=settings.PAYPAL_ENVIRONMENT,
        amount=amount, currency=currency, client_reference=uuid4(), created_by=user,
    )
    provider = get_default_provider()
    try:
        orden = provider.create_order(
            amount=amount, currency=currency, reference_id=str(txn.pk),
            description=description or f"Budun ERP — Plan {nombre_plan}",
            return_url=return_url, cancel_url=cancel_url,
            idempotency_key=f"budun-order-create-{txn.client_reference}",
        )
    except PaymentProviderError as error:
        txn.status = PayPalTransaction.Status.FAILED
        txn.failure_reason = str(error)[:255]
        txn.save(update_fields=["status", "failure_reason", "updated_at"])
        _audit(tenant, action=AuditLog.Action.PAYPAL_PAYMENT_FAILED, user=user, txn=txn, reason=str(error)[:255])
        raise InvalidBillingOperation(f"No se pudo crear la orden en PayPal: {error}") from error

    txn.external_order_id = orden.external_order_id
    txn.save(update_fields=["external_order_id", "updated_at"])
    _audit(
        tenant, action=AuditLog.Action.PAYPAL_CHECKOUT_CREATED, user=user, txn=txn,
        after={"plan_id": plan_id, "amount": str(amount), "currency": currency, "external_order_id": orden.external_order_id},
    )
    return txn, orden.approve_url


def capture_checkout(txn, *, user=None):
    """Confirma el pago (captura la orden aprobada). Idempotente: si la
    transacción ya avanzó más allá de CREATED/PENDING_CAPTURE, es un
    no-op (nunca captura dos veces, ver sección 13 de la fase)."""
    with transaction.atomic():
        txn = PayPalTransaction.objects.select_for_update().get(pk=txn.pk)
        if txn.status not in (PayPalTransaction.Status.CREATED, PayPalTransaction.Status.PENDING_CAPTURE):
            return txn

        provider = get_default_provider()
        try:
            resultado = provider.capture_order(
                external_order_id=txn.external_order_id,
                idempotency_key=f"budun-order-capture-{txn.client_reference}",
            )
        except PaymentProviderError as error:
            txn.status = PayPalTransaction.Status.FAILED
            txn.failure_reason = str(error)[:255]
            txn.save(update_fields=["status", "failure_reason", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.PAYPAL_PAYMENT_FAILED, user=user, txn=txn, reason=str(error)[:255])
            signals.payment_failed.send(sender=PayPalTransaction, transaction=txn)
            return txn

        if resultado.status == "COMPLETED":
            txn.status = PayPalTransaction.Status.CONFIRMED
            txn.external_capture_id = resultado.external_capture_id
            txn.provider_amount = resultado.amount
            txn.provider_currency = resultado.currency
            txn.confirmed_at = timezone.now()
            txn.save(update_fields=[
                "status", "external_capture_id", "provider_amount", "provider_currency", "confirmed_at", "updated_at",
            ])
            _audit(
                txn.tenant, action=AuditLog.Action.PAYPAL_PAYMENT_CONFIRMED, user=user, txn=txn,
                after={"external_capture_id": resultado.external_capture_id, "amount": str(resultado.amount), "currency": resultado.currency},
            )
            signals.payment_confirmed.send(sender=PayPalTransaction, transaction=txn)
        elif resultado.status == "PENDING":
            txn.status = PayPalTransaction.Status.PENDING_CAPTURE
            txn.external_capture_id = resultado.external_capture_id
            txn.save(update_fields=["status", "external_capture_id", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.GENERIC, user=user, txn=txn, metadata={"captura_pendiente": True})
        else:
            txn.status = PayPalTransaction.Status.FAILED
            txn.failure_reason = f"PayPal devolvió el estado de captura «{resultado.status}»."
            txn.save(update_fields=["status", "failure_reason", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.PAYPAL_PAYMENT_FAILED, user=user, txn=txn, reason=txn.failure_reason)
            signals.payment_failed.send(sender=PayPalTransaction, transaction=txn)
        return txn


def cancel_checkout(txn, *, user=None):
    with transaction.atomic():
        txn = PayPalTransaction.objects.select_for_update().get(pk=txn.pk)
        if txn.status != PayPalTransaction.Status.CREATED:
            return txn
        txn.status = PayPalTransaction.Status.CANCELLED
        txn.cancelled_at = timezone.now()
        txn.save(update_fields=["status", "cancelled_at", "updated_at"])
        _audit(txn.tenant, action=AuditLog.Action.PAYPAL_CHECKOUT_CANCELLED, user=user, txn=txn)
        signals.checkout_cancelled.send(sender=PayPalTransaction, transaction=txn)
        return txn


# ---------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------

def request_refund(txn, *, user, amount=None, reason=""):
    with transaction.atomic():
        txn = PayPalTransaction.objects.select_for_update().get(pk=txn.pk)
        if txn.status != PayPalTransaction.Status.CONFIRMED:
            raise InvalidBillingOperation(
                "Solo se puede reembolsar una transacción CONFIRMADA — "
                "ya hay un reembolso en curso, completado, o el pago no fue confirmado."
            )
        _audit(
            txn.tenant, action=AuditLog.Action.PAYPAL_REFUND_REQUESTED, user=user, txn=txn,
            reason=reason, metadata={"monto": str(amount) if amount is not None else "total"},
        )
        signals.refund_requested.send(sender=PayPalTransaction, transaction=txn)

        provider = get_default_provider()
        try:
            resultado = provider.refund_capture(
                external_capture_id=txn.external_capture_id,
                amount=amount, currency=txn.provider_currency or txn.currency,
                idempotency_key=f"budun-refund-{txn.client_reference}",
            )
        except PaymentProviderError as error:
            txn.status = PayPalTransaction.Status.REFUND_FAILED
            txn.failure_reason = str(error)[:255]
            txn.save(update_fields=["status", "failure_reason", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.PAYPAL_REFUND_FAILED, user=user, txn=txn, reason=str(error)[:255])
            signals.refund_failed.send(sender=PayPalTransaction, transaction=txn)
            return txn

        txn.external_refund_id = resultado.external_refund_id
        if resultado.status == "COMPLETED":
            txn.status = PayPalTransaction.Status.REFUNDED
            txn.refunded_at = timezone.now()
            txn.save(update_fields=["status", "external_refund_id", "refunded_at", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.PAYPAL_REFUND_COMPLETED, user=user, txn=txn,
                   after={"external_refund_id": resultado.external_refund_id})
            signals.refund_completed.send(sender=PayPalTransaction, transaction=txn)
        else:
            txn.status = PayPalTransaction.Status.REFUND_PENDING
            txn.save(update_fields=["status", "external_refund_id", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.GENERIC, user=user, txn=txn, metadata={"reembolso_pendiente": True})
        return txn


# ---------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------

def _safe_summary(data):
    """Solo un subconjunto mínimo — nunca datos del pagador (nombre,
    email, dirección) ni el payload completo."""
    resource = data.get("resource", {}) or {}
    return {
        "event_type": data.get("event_type", ""),
        "resource_type": data.get("resource_type", ""),
        "resource_id": resource.get("id", ""),
        "resource_status": resource.get("status", ""),
        "amount": resource.get("amount", {}),
    }


def _resolve_transaction_from_resource(event_type, resource):
    resource_id = resource.get("id", "")
    if not resource_id:
        return None
    if event_type.startswith("CHECKOUT.ORDER."):
        return PayPalTransaction.objects.filter(external_order_id=resource_id).first()
    if event_type.startswith("PAYMENT.CAPTURE."):
        txn = PayPalTransaction.objects.filter(external_capture_id=resource_id).first()
        if txn is not None:
            return txn
        order_id = (resource.get("supplementary_data", {}) or {}).get("related_ids", {}).get("order_id", "")
        if order_id:
            return PayPalTransaction.objects.filter(external_order_id=order_id).first()
        return None
    if event_type.startswith("PAYMENT.REFUND."):
        # Un refund iniciado por nosotros ya tiene `external_refund_id`
        # guardado; un refund hecho fuera de banda (directo en el panel
        # de PayPal) no se puede correlacionar sin una llamada adicional
        # a la API — limitación documentada de FASE 16, el evento queda
        # registrado (IGNORED) para revisión manual.
        return PayPalTransaction.objects.filter(external_refund_id=resource_id).first()
    return None


def _apply_webhook_event(txn_pk, *, event_type, resource):
    """Aplica la transición correspondiente con `select_for_update()` —
    cada rama re-verifica el estado ACTUAL antes de escribir, así que un
    evento duplicado o fuera de orden que ya no aporta nada es un no-op
    idempotente, nunca un error ni una doble aplicación."""
    with transaction.atomic():
        txn = PayPalTransaction.objects.select_for_update().get(pk=txn_pk)
        estados_terminales_pago = (
            PayPalTransaction.Status.CONFIRMED, PayPalTransaction.Status.REFUND_PENDING,
            PayPalTransaction.Status.REFUNDED, PayPalTransaction.Status.REFUND_FAILED,
        )

        if event_type == "CHECKOUT.ORDER.APPROVED":
            return  # informativo: nuestro propio flujo captura sincrónicamente al volver del checkout.

        if event_type in ("PAYMENT.CAPTURE.COMPLETED", "CHECKOUT.ORDER.COMPLETED"):
            if txn.status in estados_terminales_pago:
                return
            txn.status = PayPalTransaction.Status.CONFIRMED
            if not txn.external_capture_id and resource.get("id"):
                txn.external_capture_id = resource["id"]
            amount_info = resource.get("amount") or {}
            if amount_info.get("value"):
                txn.provider_amount = Decimal(amount_info["value"])
                txn.provider_currency = amount_info.get("currency_code", "")
            txn.confirmed_at = timezone.now()
            txn.save(update_fields=["status", "external_capture_id", "provider_amount", "provider_currency", "confirmed_at", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.PAYPAL_PAYMENT_CONFIRMED, txn=txn, metadata={"origen": "webhook"})
            signals.payment_confirmed.send(sender=PayPalTransaction, transaction=txn)
            return

        if event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
            if txn.status in estados_terminales_pago:
                return  # ya se confirmó por otra vía — un evento denied tardío/fuera de orden no lo pisa.
            txn.status = PayPalTransaction.Status.FAILED
            txn.failure_reason = f"Webhook {event_type}"
            txn.save(update_fields=["status", "failure_reason", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.PAYPAL_PAYMENT_FAILED, txn=txn, metadata={"origen": "webhook"})
            signals.payment_failed.send(sender=PayPalTransaction, transaction=txn)
            return

        if event_type == "PAYMENT.CAPTURE.REFUNDED":
            if txn.status == PayPalTransaction.Status.REFUNDED:
                return
            txn.status = PayPalTransaction.Status.REFUNDED
            txn.refunded_at = timezone.now()
            txn.save(update_fields=["status", "refunded_at", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.PAYPAL_REFUND_COMPLETED, txn=txn, metadata={"origen": "webhook"})
            signals.refund_completed.send(sender=PayPalTransaction, transaction=txn)
            return

        if event_type == "PAYMENT.REFUND.PENDING":
            if txn.status == PayPalTransaction.Status.REFUNDED:
                return
            txn.status = PayPalTransaction.Status.REFUND_PENDING
            txn.save(update_fields=["status", "updated_at"])
            return

        if event_type == "PAYMENT.REFUND.FAILED":
            if txn.status == PayPalTransaction.Status.REFUNDED:
                return
            txn.status = PayPalTransaction.Status.REFUND_FAILED
            txn.save(update_fields=["status", "updated_at"])
            _audit(txn.tenant, action=AuditLog.Action.PAYPAL_REFUND_FAILED, txn=txn, metadata={"origen": "webhook"})
            signals.refund_failed.send(sender=PayPalTransaction, transaction=txn)
            return

        # Evento reconocido por PayPal pero irrelevante para el alcance de
        # FASE 16 (p. ej. eventos de disputas/chargebacks) — no-op
        # deliberado, nunca un error.


def process_webhook_event(*, headers, raw_body):
    """Punto de entrada único desde la vista de webhook. Nunca hace
    ORM directo desde la vista (sección 7 de la fase) — la vista solo
    captura headers/body y llama aquí."""
    provider = get_default_provider()
    try:
        verificacion = provider.verify_webhook_signature(headers=headers, raw_body=raw_body)
    except PaymentProviderError as error:
        evento = PayPalWebhookEvent.objects.create(
            event_id=f"unverified-{uuid4()}", status=PayPalWebhookEvent.Status.REJECTED,
            error_message=str(error)[:255],
        )
        _audit(None, action=AuditLog.Action.PAYPAL_WEBHOOK_PROCESSED, reason="verificación de firma falló")
        return evento

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        data = {}
    event_id = data.get("id", "")
    event_type = data.get("event_type", "")
    resource = data.get("resource", {}) or {}
    resumen = _safe_summary(data)

    if not verificacion.verified or not event_id:
        # Idempotente igual que la rama "procesado" de más abajo: una
        # entrega DUPLICADA de un evento que ya rechazamos antes (PayPal
        # reintenta cualquier respuesta no-2xx, y un rechazo por firma
        # responde 400 — ver `webhook_views.py`) nunca debe romper con un
        # `IntegrityError` sin capturar; debe devolver la misma fila.
        clave = event_id or f"unverified-{uuid4()}"
        try:
            with transaction.atomic():
                evento = PayPalWebhookEvent.objects.create(
                    event_id=clave, event_type=event_type,
                    verification_status=verificacion.verification_status, summary=resumen,
                    status=PayPalWebhookEvent.Status.REJECTED, error_message="Firma inválida.",
                )
        except IntegrityError:
            evento = PayPalWebhookEvent.objects.filter(event_id=clave).first()
        _audit(None, action=AuditLog.Action.PAYPAL_WEBHOOK_PROCESSED, reason="firma inválida", metadata={"event_type": event_type})
        return evento

    try:
        with transaction.atomic():
            evento = PayPalWebhookEvent.objects.create(
                event_id=event_id, event_type=event_type,
                verification_status=verificacion.verification_status, summary=resumen,
                status=PayPalWebhookEvent.Status.RECEIVED,
            )
    except IntegrityError:
        # `event_id` ya existe: entrega duplicada de PayPal (reintento) o
        # dos workers procesando el mismo evento a la vez — el
        # UniqueConstraint es la barrera real, nunca un `.exists()` previo
        # (que sí tendría una ventana de carrera).
        return PayPalWebhookEvent.objects.filter(event_id=event_id).first()

    txn = _resolve_transaction_from_resource(event_type, resource)
    if txn is None:
        evento.status = PayPalWebhookEvent.Status.IGNORED
        evento.processed_at = timezone.now()
        evento.save(update_fields=["status", "processed_at"])
        return evento

    evento.transaction = txn
    try:
        _apply_webhook_event(txn.pk, event_type=event_type, resource=resource)
        evento.status = PayPalWebhookEvent.Status.PROCESSED
    except Exception as error:  # noqa: BLE001 — un evento con error nunca debe tumbar la respuesta al webhook.
        evento.status = PayPalWebhookEvent.Status.ERROR
        evento.error_message = str(error)[:255]
    evento.processed_at = timezone.now()
    evento.save(update_fields=["transaction", "status", "error_message", "processed_at"])
    _audit(
        txn.tenant, action=AuditLog.Action.PAYPAL_WEBHOOK_PROCESSED, txn=txn,
        metadata={"event_type": event_type, "resultado": evento.status},
    )
    return evento
