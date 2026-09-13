"""
Notas de crédito y saldo a favor (FASE 17, secciones 20-22). El saldo a
favor NUNCA es una tabla separada — se deriva SIEMPRE sumando el saldo
sin aplicar de `SaaSPayment` + el saldo sin aplicar de `CreditNote`,
exactamente el mismo criterio ya usado en `apps.sales`/`apps.purchases`
para Cuentas por Cobrar/Pagar del ERP (`CustomerCreditLedger`
descartado explícitamente, ver `docs/accounts-receivable.md` y
`docs/billing.md`)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import AuditLog
from apps.sales.models import DocumentSequence
from apps.sales.services import generate_document_number

from ..models import CreditNote, CreditNoteApplication, SaaSInvoice, SaaSPayment, SaaSPaymentAllocation
from . import notifications
from ._saas_audit import audit_event
from .invoicing import _recompute_invoice_status, get_invoice_balance_due
from .payments import get_unallocated_payment_amount


class InvalidCreditOperation(ValidationError):
    pass


def issue_credit_note(*, tenant, saas_customer, amount, currency, reason, subscription=None, user=None):
    numero = generate_document_number(tenant, DocumentSequence.DocumentType.SAAS_CREDIT_NOTE)
    credit_note = CreditNote.all_objects.create(
        tenant=tenant, saas_customer=saas_customer, subscription=subscription, number=numero,
        amount=amount, currency=currency, reason=reason, created_by=user,
    )
    audit_event(tenant, action=AuditLog.Action.GENERIC, user=user, object_type="credit_note", object_id=credit_note.pk,
                after={"number": numero, "amount": str(amount)}, reason=reason)
    # FASE DE CORRECCIÓN 5: antes de esta corrección, ninguna notificación
    # avisaba al tenant que recibió una nota de crédito — solo era
    # visible si entraba por su cuenta a revisar su Portal de Facturación.
    notifications.notify_credit_note_issued(credit_note)
    return credit_note


def get_unapplied_credit_note_amount(credit_note):
    """`all_objects` explícito — nunca `credit_note.applications`
    (relación inversa tenant-scoped, ver
    `apps.billing.services.invoicing.get_invoice_balance_due`)."""
    aplicado = sum(
        (a.amount for a in CreditNoteApplication.all_objects.filter(credit_note=credit_note, status=CreditNoteApplication.Status.ACTIVE)),
        Decimal("0"),
    )
    return credit_note.amount - aplicado


def apply_credit_note_to_invoice(credit_note, invoice, amount, *, user=None):
    with transaction.atomic():
        credit_note = CreditNote.all_objects.select_for_update().get(pk=credit_note.pk)
        invoice = SaaSInvoice.all_objects.select_for_update().get(pk=invoice.pk)
        if credit_note.tenant_id != invoice.tenant_id:
            raise InvalidCreditOperation("La nota de crédito y la factura deben pertenecer al mismo tenant.")
        disponible = get_unapplied_credit_note_amount(credit_note)
        amount = Decimal(amount)
        if amount > disponible:
            raise InvalidCreditOperation(f"El monto ({amount}) excede el saldo disponible de la nota de crédito ({disponible}).")
        saldo_factura = get_invoice_balance_due(invoice)
        if amount > saldo_factura:
            raise InvalidCreditOperation(f"El monto ({amount}) excede el saldo pendiente de la factura ({saldo_factura}).")

        application = CreditNoteApplication.all_objects.create(
            tenant=invoice.tenant, credit_note=credit_note, invoice=invoice, amount=amount,
        )
        _recompute_invoice_status(invoice)
        audit_event(invoice.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="credit_note", object_id=credit_note.pk,
                    after={"aplicado_a": invoice.number, "amount": str(amount)})
        return application


def reverse_credit_note_application(application, *, user=None, reason=""):
    from django.utils import timezone

    with transaction.atomic():
        application = CreditNoteApplication.all_objects.select_for_update().get(pk=application.pk)
        if application.status == CreditNoteApplication.Status.REVERSED:
            return application
        application.status = CreditNoteApplication.Status.REVERSED
        application.reversed_at = timezone.now()
        application.save(update_fields=["status", "reversed_at"])
        _recompute_invoice_status(SaaSInvoice.all_objects.get(pk=application.invoice_id))
        audit_event(application.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="credit_note_application",
                    object_id=application.pk, reason=reason)
        return application


def auto_apply_available_credit_notes(subscription, *, user=None):
    """Aplica automáticamente el saldo disponible de las notas de
    crédito de esta suscripción a sus facturas ABIERTAS más antiguas —
    equivalente de `apps.billing.services.payments.auto_apply_payment`
    pero para notas de crédito. FASE DE CORRECCIÓN 3 (Lifecycle
    integral, sección "crédito"): antes de esta corrección,
    `apply_credit_note_to_invoice` existía pero solo se ejercitaba desde
    pruebas — ninguna vista ni proceso automático la invocaba nunca, así
    que una nota de crédito emitida por un downgrade (`subscriptions.
    change_plan`) jamás se "aplicaba a la próxima factura" salvo que un
    humano lo hiciera a mano (y no existe ninguna pantalla para eso).
    Se llama automáticamente cada vez que se emite una factura NUEVA
    para la suscripción (`invoicing.generate_invoice_for_subscription`/
    `issue_proration_charge_invoice`) — nunca al revisar una factura ya
    existente, para no reabrir una ya resuelta de otra forma."""
    aplicadas = []
    notas = CreditNote.all_objects.filter(subscription=subscription).order_by("created_at")
    for nota in notas:
        disponible = get_unapplied_credit_note_amount(nota)
        if disponible <= 0:
            continue
        facturas_abiertas = SaaSInvoice.all_objects.filter(
            tenant=nota.tenant, subscription=subscription,
            status__in=[SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID],
        ).order_by("due_date", "id")
        for invoice in facturas_abiertas:
            if disponible <= 0:
                break
            saldo_factura = get_invoice_balance_due(invoice)
            if saldo_factura <= 0:
                continue
            monto = min(disponible, saldo_factura)
            aplicadas.append(apply_credit_note_to_invoice(nota, invoice, monto, user=user))
            disponible -= monto
    return aplicadas


def get_subscription_credit_balance(*, tenant, subscription=None):
    """Saldo a favor = pagos CONFIRMADOS sin aplicar + notas de crédito
    sin aplicar, del tenant (opcionalmente acotado a una suscripción
    concreta) — nunca una tercera fuente de verdad."""
    pagos = SaaSPayment.all_objects.filter(tenant=tenant, status=SaaSPayment.Status.CONFIRMED)
    notas = CreditNote.all_objects.filter(tenant=tenant)
    if subscription is not None:
        pagos = pagos.filter(subscription=subscription)
        notas = notas.filter(subscription=subscription)

    saldo_pagos = sum((get_unallocated_payment_amount(p) for p in pagos), Decimal("0"))
    saldo_notas = sum((get_unapplied_credit_note_amount(n) for n in notas), Decimal("0"))
    return saldo_pagos + saldo_notas


def convert_payment_to_credit(payment, *, user=None, reason=""):
    """"Refund convertido a crédito" (sección 21): en vez de devolver
    dinero de verdad, se reversan las asignaciones activas de este pago
    — el monto vuelve a quedar SIN APLICAR, que es exactamente la
    definición de saldo a favor (ver arriba), sin crear ningún modelo
    nuevo."""
    from .payments import reverse_allocation

    reversadas = []
    for allocation in SaaSPaymentAllocation.all_objects.filter(payment=payment, status=SaaSPaymentAllocation.Status.ACTIVE):
        reversadas.append(reverse_allocation(allocation, user=user, reason=reason or "Convertido a saldo a favor"))
    return reversadas
