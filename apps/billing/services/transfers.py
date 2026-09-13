"""
Transferencia bancaria (FASE 17, secciones 13/24-26). El comprobante
nunca activa el tenant por sí solo — solo la aprobación explícita del
Super Admin lo hace (sección 14: "Nunca activar únicamente porque
existe un comprobante"). Validación de archivo reutiliza literalmente
`apps.customers.file_validation` (mismo mecanismo ya establecido en
todo el proyecto para adjuntos sensibles) — nunca un segundo validador."""

import secrets

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.customers.file_validation import nombre_original_seguro, validar_archivo_adjunto

from ..models import BankAccount, PaymentProof, SaaSInvoice, SaaSPayment, Subscription
from ._saas_audit import audit_event
from . import notifications
from . import tenants as tenant_services


class InvalidTransferOperation(ValidationError):
    pass


def is_bank_transfer_available():
    """FASE DE CORRECCIÓN 2 (Billing del Tenant): única fuente de
    verdad de "¿el Portal debe ofrecer transferencia bancaria como
    método de pago?" — no existe un interruptor único como el de
    PayPal (`services.is_paypal_available`) porque la transferencia
    nunca tuvo uno: su disponibilidad real siempre fue "¿hay al menos
    una cuenta bancaria activa a la que transferir?" (la misma
    condición que `TransferInstructionsView` ya usa para listarlas).
    Se centraliza aquí para que el Portal (formulario de elegir plan,
    pantalla de estado) nunca duplique este `filter(is_active=True)`."""
    return BankAccount.objects.filter(is_active=True).exists()


def generate_transfer_reference(tenant):
    """Referencia única legible — reintenta si hay colisión (muy
    improbable con 8 hex, pero nunca confiar solo en la probabilidad:
    el `UniqueConstraint(tenant, reference)` es la garantía real)."""
    for _intento in range(10):
        referencia = f"PAY-{tenant.pk}-{secrets.token_hex(4).upper()}"
        if not PaymentProof.all_objects.filter(tenant=tenant, reference=referencia).exists():
            return referencia
    raise InvalidTransferOperation("No se pudo generar una referencia única — intenta de nuevo.")


def submit_payment_proof(*, subscription, invoice, bank_account, declared_amount, declared_currency,
                          file, declared_bank_name="", user=None, reference=None):
    # FASE DE CORRECCIÓN 2 (Billing del Tenant) — validaciones reales
    # que faltaban en el servicio (antes solo validaba el archivo): un
    # comprobante nunca es la fuente de verdad del pago (eso sigue
    # siendo `approve_payment_proof`, sin cambios), pero aceptar uno
    # para una factura que ya no admite pago, o un segundo comprobante
    # mientras otro sigue en revisión, o un monto/moneda claramente
    # inconsistentes, son errores detectables ANTES de crear la fila —
    # nunca una segunda fuente de verdad, solo defensa real en el punto
    # de entrada único del dominio.
    if declared_amount is None or declared_amount <= 0:
        raise InvalidTransferOperation("El monto declarado debe ser mayor que cero.")
    # FASE DE CORRECCIÓN 4 (sección 2): el formulario ya solo lista
    # cuentas activas, pero el servicio nunca debe confiar únicamente en
    # eso — mismo criterio de "el backend nunca confía solo en el
    # formulario" aplicado en todo el proyecto.
    if not bank_account.is_active:
        raise InvalidTransferOperation("La cuenta receptora seleccionada ya no está activa.")
    if (declared_currency or "").strip().upper() != bank_account.currency.upper():
        raise InvalidTransferOperation(
            f"La moneda declarada ({declared_currency}) no coincide con la moneda de la cuenta "
            f"receptora seleccionada ({bank_account.currency})."
        )
    # FASE DE CORRECCIÓN 4 (sección 9): sin motor de tipos de cambio
    # (`docs/currency.md`), una transferencia en una moneda distinta de
    # la factura nunca se acepta implícitamente — mismo criterio ya
    # establecido para Cuentas por Cobrar del ERP
    # (`apps.sales.services.allocate_payment`). Sumado a la validación de
    # arriba (declarada == cuenta receptora), esto garantiza que las TRES
    # monedas (factura/comprobante/cuenta) coincidan exactamente.
    if (declared_currency or "").strip().upper() != invoice.currency.upper():
        raise InvalidTransferOperation(
            f"La moneda declarada ({declared_currency}) no coincide con la moneda de la factura "
            f"{invoice.number} ({invoice.currency}) — no se realizan conversiones automáticas."
        )

    # Validación de archivo ANTES de tomar cualquier lock — su I/O
    # (lectura de los primeros bytes) no debe alargar el tiempo que la
    # fila de la factura queda bloqueada más abajo.
    _extension, content_type = validar_archivo_adjunto(file)
    nombre_seguro = nombre_original_seguro(file.name)
    tamano = file.size or 0

    # FASE DE CORRECCIÓN 4 (sección 18, "doble submit"): antes de esta
    # corrección, la comprobación de "factura vigente" + "sin comprobante
    # pendiente" era un simple `.exists()` sin ningún lock — dos envíos
    # concurrentes del mismo formulario (doble clic, dos pestañas) podían
    # AMBOS pasar la comprobación antes de que cualquiera comprometiera su
    # propia fila, creando dos `PaymentProof` `SUBMITTED` para la misma
    # factura. `select_for_update()` sobre la `SaaSInvoice` (mismo patrón
    # ya usado en `create_checkout_for_invoice`) serializa los dos
    # intentos: el segundo, tras esperar al primero, ve el comprobante ya
    # creado y es rechazado correctamente.
    with transaction.atomic():
        invoice = SaaSInvoice.all_objects.select_for_update().get(pk=invoice.pk)
        if invoice.status not in (SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID):
            raise InvalidTransferOperation(
                f"La factura {invoice.number} no admite un nuevo comprobante en su estado actual "
                f"({invoice.get_status_display()})."
            )
        if PaymentProof.all_objects.filter(
            invoice=invoice, status__in=[PaymentProof.Status.SUBMITTED, PaymentProof.Status.UNDER_REVIEW]
        ).exists():
            raise InvalidTransferOperation("Ya existe un comprobante pendiente de revisión para esta factura.")

        referencia = reference or generate_transfer_reference(subscription.tenant)
        proof = PaymentProof.all_objects.create(
            tenant=subscription.tenant, subscription=subscription, invoice=invoice, bank_account=bank_account,
            reference=referencia, declared_amount=declared_amount, declared_currency=declared_currency,
            declared_bank_name=declared_bank_name, file=file, original_filename=nombre_seguro,
            content_type=content_type, size_bytes=tamano, uploaded_by=user, status=PaymentProof.Status.SUBMITTED,
        )
        tenant_services.mark_tenant_pending_payment(subscription.tenant, user=user)
        audit_event(subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="payment_proof", object_id=proof.pk,
                    after={"reference": referencia, "amount": str(declared_amount)})
    notifications.notify_payment_proof_submitted(proof)
    return proof


def approve_payment_proof(proof, *, user=None):
    from . import payments as payment_services

    with transaction.atomic():
        proof = PaymentProof.all_objects.select_for_update().get(pk=proof.pk)
        if proof.status == PaymentProof.Status.APPROVED:
            return proof, None
        if proof.status not in (PaymentProof.Status.SUBMITTED, PaymentProof.Status.UNDER_REVIEW):
            raise InvalidTransferOperation("Solo se puede aprobar un comprobante enviado o en revisión.")

        proof.status = PaymentProof.Status.APPROVED
        proof.reviewed_by = user
        proof.reviewed_at = timezone.now()
        proof.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        payment = payment_services.record_payment(
            tenant=proof.tenant, saas_customer=proof.subscription.saas_customer, subscription=proof.subscription,
            method=SaaSPayment.Method.BANK_TRANSFER, amount=proof.declared_amount, currency=proof.declared_currency,
            external_reference=proof.reference, payment_proof=proof, user=user,
            status=SaaSPayment.Status.CONFIRMED,
        )
        payment.received_at = timezone.now()
        payment.save(update_fields=["received_at"])
        payment_services.auto_apply_payment(payment, user=user)

    from . import subscriptions as subscription_services

    # FASE DE CORRECCIÓN 3 (Lifecycle integral): `ACTIVATE != REACTIVATE`
    # (ver `subscriptions.activate_pending_subscription`) — antes de
    # esta corrección, aprobar un comprobante sobre una suscripción
    # PAST_DUE/SUSPENDED llamaba al primitivo de activación INICIAL
    # directamente, saltándose el guard/auditoría/notificación propios
    # de `reactivate_subscription` y sin restaurar el período si ya
    # había vencido durante la suspensión.
    estado_actual = proof.subscription.status
    if estado_actual == Subscription.Status.PENDING:
        subscription_services.activate_subscription(proof.subscription, user=user)
    elif estado_actual in (Subscription.Status.PAST_DUE, Subscription.Status.SUSPENDED):
        subscription_services.reactivate_subscription(proof.subscription, user=user)

    audit_event(proof.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="payment_proof", object_id=proof.pk,
                after={"status": "approved"})
    notifications.notify_payment_approved(payment)
    return proof, payment


def reject_payment_proof(proof, *, reason, user=None):
    with transaction.atomic():
        proof = PaymentProof.all_objects.select_for_update().get(pk=proof.pk)
        if proof.status == PaymentProof.Status.REJECTED:
            return proof
        # FASE DE CORRECCIÓN 4 (sección 18, "aprobación + rechazo
        # simultáneos"): antes de esta corrección, no existía ningún
        # guard aquí contra un comprobante YA `APPROVED` — rechazarlo de
        # todas formas dejaba el `PaymentProof` en `REJECTED` mientras el
        # `SaaSPayment`/`Allocation`/`Subscription ACTIVE` ya generados
        # por la aprobación seguían intactos, un estado contradictorio
        # (factura efectivamente pagada, comprobante que dice "rechazado").
        # `select_for_update()` serializa la carrera real (aprobar y
        # rechazar el MISMO comprobante a la vez): quien pierda la carrera
        # ve el estado ya transicionado y es rechazado con un error claro,
        # nunca sobrescribe una transición terminal distinta.
        if proof.status not in (PaymentProof.Status.SUBMITTED, PaymentProof.Status.UNDER_REVIEW):
            raise InvalidTransferOperation("Solo se puede rechazar un comprobante enviado o en revisión.")
        proof.status = PaymentProof.Status.REJECTED
        proof.reviewed_by = user
        proof.reviewed_at = timezone.now()
        proof.rejection_reason = reason
        proof.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])
    audit_event(proof.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="payment_proof", object_id=proof.pk,
                reason=reason, after={"status": "rejected"})
    notifications.notify_payment_rejected(proof)
    return proof


def list_pending_proofs():
    return PaymentProof.all_objects.filter(
        status__in=[PaymentProof.Status.SUBMITTED, PaymentProof.Status.UNDER_REVIEW],
    ).select_related("tenant", "subscription", "invoice", "bank_account").order_by("uploaded_at")
