"""
Facturación recurrente de Billing SaaS (FASE 17). La idempotencia de
"nunca duplicar la misma factura para el mismo período" (sección 11 de
la fase) es una garantía de BASE DE DATOS
(`SaaSInvoice.UniqueConstraint(subscription, period_start)`), nunca
solo "el código no se llama dos veces" — mismo principio que
`PayPalWebhookEvent.event_id` en FASE 16."""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.audit.models import AuditLog
from apps.sales.models import DocumentSequence
from apps.sales.services import generate_document_number

from ..models import CreditNoteApplication, SaaSInvoice, SaaSInvoiceLine, SaaSPaymentAllocation
from . import notifications
from ._saas_audit import audit_event


class InvalidInvoiceOperation(ValidationError):
    pass


def get_invoice_balance_due(invoice):
    """Saldo pendiente derivado SIEMPRE del ledger — nunca un campo
    desnormalizado (mismo principio que `get_sale_balance_due` en
    `apps.sales.services`). Usa `all_objects` explícitamente (NUNCA la
    relación inversa `invoice.allocations`/`invoice.credit_note_applications`,
    que resuelve con el manager tenant-scoped por defecto, dependiente
    del `ContextVar` de una request HTTP real) — este servicio debe
    funcionar igual llamado desde una vista, un test, un comando de
    administración programado por cron, o un receptor de señal de
    webhook (ninguno de los tres últimos tiene el `ContextVar` activo)."""
    aplicado_pagos = sum(
        (a.amount for a in SaaSPaymentAllocation.all_objects.filter(invoice=invoice, status=SaaSPaymentAllocation.Status.ACTIVE)),
        Decimal("0"),
    )
    aplicado_notas = sum(
        (a.amount for a in CreditNoteApplication.all_objects.filter(invoice=invoice, status=CreditNoteApplication.Status.ACTIVE)),
        Decimal("0"),
    )
    return invoice.total - aplicado_pagos - aplicado_notas


def _recompute_invoice_status(invoice):
    saldo = get_invoice_balance_due(invoice)
    if saldo <= Decimal("0"):
        nuevo_estado = SaaSInvoice.Status.PAID
    elif saldo < invoice.total:
        nuevo_estado = SaaSInvoice.Status.PARTIALLY_PAID
    else:
        nuevo_estado = SaaSInvoice.Status.OPEN
    if invoice.status != SaaSInvoice.Status.VOID and invoice.status != nuevo_estado:
        invoice.status = nuevo_estado
        invoice.save(update_fields=["status"])
    return invoice


def generate_invoice_for_subscription(subscription, *, period_start=None, period_end=None, description="", user=None):
    """Genera (o recupera, si ya existe — idempotente) la factura de un
    período. `period_start`/`period_end` por defecto son el período
    VIGENTE de la suscripción."""
    inicio = period_start or subscription.current_period_start or date.today()
    fin = period_end or subscription.current_period_end or (inicio + timedelta(days=30))
    plan_version = subscription.plan_version
    monto = plan_version.price_amount
    moneda = plan_version.price_currency
    descuento = Decimal("0")
    cupon_snapshot = ""
    if subscription.coupon is not None:
        from . import coupons as coupon_services

        # FASE DE CORRECCIÓN 5: vigencia real (fecha + interruptor
        # manual), no solo `is_active` — un cupón por tiempo limitado
        # nunca debe seguir descontando en renovaciones posteriores a su
        # `valid_until` (ver `coupons.is_coupon_currently_valid`).
        if coupon_services.is_coupon_currently_valid(subscription.coupon):
            descuento = coupon_services.calculate_discount(subscription.coupon, monto)
            cupon_snapshot = subscription.coupon.code

    subtotal = monto
    total = max(subtotal - descuento, Decimal("0"))

    try:
        with transaction.atomic():
            numero = generate_document_number(subscription.tenant, DocumentSequence.DocumentType.SAAS_INVOICE)
            invoice = SaaSInvoice.all_objects.create(
                tenant=subscription.tenant, subscription=subscription, number=numero,
                period_start=inicio, period_end=fin, issue_date=date.today(), due_date=inicio,
                currency=moneda, subtotal=subtotal, discount_total=descuento, tax_total=Decimal("0"), total=total,
                status=SaaSInvoice.Status.OPEN, coupon_code_snapshot=cupon_snapshot,
            )
            SaaSInvoiceLine.all_objects.create(
                tenant=subscription.tenant, invoice=invoice,
                description=description or f"{plan_version.plan.name} — {plan_version.get_frequency_display()}",
                quantity=Decimal("1"), amount=subtotal,
            )
    except IntegrityError:
        # Ya existe una factura para este (subscription, period_start) —
        # nunca se duplica, se devuelve la existente.
        return SaaSInvoice.all_objects.get(subscription=subscription, period_start=inicio), False

    audit_event(subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_invoice", object_id=invoice.pk,
                after={"number": numero, "total": str(total)})
    # FASE DE CORRECCIÓN 3 (Lifecycle integral, sección "crédito"): antes
    # de esta corrección, `apply_credit_note_to_invoice` solo se ejercitaba
    # desde pruebas — ninguna vista ni proceso automático la llamaba
    # nunca, así que una nota de crédito emitida (p. ej. por un downgrade,
    # `subscriptions.change_plan`) nunca llegaba a "aplicarse a la
    # próxima factura" salvo que un humano lo hiciera a mano (y no existe
    # ninguna pantalla para eso). Toda factura NUEVA barre automáticamente
    # el saldo disponible de notas de crédito de la misma suscripción —
    # mismo principio que `auto_apply_payment` para pagos, nunca una
    # segunda fuente de verdad (`credits.py` sigue siendo la única dueña
    # del cálculo de saldo/aplicación).
    from . import credits as credit_services  # import diferido: evita un ciclo (credits.py importa de este módulo)

    credit_services.auto_apply_available_credit_notes(subscription, user=user)
    return invoice, True


def issue_proration_charge_invoice(subscription, *, amount, currency, change_date, description, user=None):
    """Factura inmediata y aparte del ciclo normal de renovación, para el
    cargo neto de un upgrade a mitad de período (FASE DE CORRECCIÓN 3,
    sección "upgrade") — `change_plan` nunca edita la factura del
    período vigente (inmutable, ya emitida) ni espera a la siguiente
    renovación para cobrar la diferencia (eso dejaría sin cobrar el
    resto del período actual al precio nuevo). `change_date` cumple el
    mismo rol que `period_start` en `generate_invoice_for_subscription`:
    el `UniqueConstraint(subscription, period_start)` de siempre es la
    garantía real de que un doble envío del formulario de cambio de plan
    (o un reintento) nunca duplica el cargo — un segundo upgrade
    genuinamente distinto el mismo día calendario queda documentado como
    fuera de alcance de esta corrección (`KNOWN_ISSUES.md` #133)."""
    try:
        with transaction.atomic():
            numero = generate_document_number(subscription.tenant, DocumentSequence.DocumentType.SAAS_INVOICE)
            invoice = SaaSInvoice.all_objects.create(
                tenant=subscription.tenant, subscription=subscription, number=numero,
                period_start=change_date, period_end=subscription.current_period_end or change_date,
                issue_date=change_date, due_date=change_date,
                currency=currency, subtotal=amount, discount_total=Decimal("0"), tax_total=Decimal("0"), total=amount,
                status=SaaSInvoice.Status.OPEN,
            )
            SaaSInvoiceLine.all_objects.create(
                tenant=subscription.tenant, invoice=invoice, description=description, quantity=Decimal("1"), amount=amount,
            )
    except IntegrityError:
        return SaaSInvoice.all_objects.get(subscription=subscription, period_start=change_date), False

    audit_event(subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_invoice", object_id=invoice.pk,
                after={"number": numero, "total": str(amount)}, reason="Cargo por prorrateo de upgrade")
    from . import credits as credit_services  # import diferido: mismo motivo que en generate_invoice_for_subscription

    credit_services.auto_apply_available_credit_notes(subscription, user=user)
    return invoice, True


def void_invoice(invoice, *, reason, user=None):
    if get_invoice_balance_due(invoice) < invoice.total:
        raise InvalidInvoiceOperation("No se puede anular una factura que ya tiene pagos/créditos aplicados.")
    invoice.status = SaaSInvoice.Status.VOID
    invoice.save(update_fields=["status"])
    audit_event(invoice.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_invoice", object_id=invoice.pk, reason=reason)
    return invoice


def ensure_next_renewal_invoice(subscription):
    """Genera (o recupera, idempotente) la factura del SIGUIENTE período
    de una suscripción cuyo período vigente ya terminó, y avanza
    `current_period_start/end`. Extraído de `generate_due_renewal_invoices`
    (FASE DE CORRECCIÓN 2C) para que el mismo cálculo lo use tanto el
    cron diario (abajo) como la reconciliación REACTIVA de un webhook de
    cobro recurrente confirmado (`apps.billing.services.recurring`) —
    cualquiera de los dos que se dispare primero genera la factura;
    el otro encuentra que ya existe y no hace nada más (mismo
    `UniqueConstraint` de siempre). Requiere `select_for_update()` ya
    tomado por el llamador sobre `subscription` — no lo toma aquí para
    poder componerse dentro de una transacción más grande."""
    siguiente_inicio = subscription.current_period_end
    dias = 365 if subscription.plan_version.frequency == "annual" else 30
    siguiente_fin = siguiente_inicio + timedelta(days=dias)
    invoice, creada = generate_invoice_for_subscription(
        subscription, period_start=siguiente_inicio, period_end=siguiente_fin,
        description=f"Renovación — {subscription.plan_version.plan.name}",
    )
    if creada:
        subscription.current_period_start = siguiente_inicio
        subscription.current_period_end = siguiente_fin
        subscription.save(update_fields=["current_period_start", "current_period_end", "updated_at"])
        # FASE DE CORRECCIÓN 3: `notifications.notify_renewal` existía
        # desde FASE 17 pero nunca se llamaba desde ningún punto real del
        # ciclo de renovación — se conecta aquí (el único lugar donde el
        # período efectivamente avanza), nunca en el cron/webhook que lo
        # invoca, para que sea el mismo aviso sin importar cuál de los
        # dos disparó la renovación primero.
        notifications.notify_renewal(subscription)
    return invoice, creada


def generate_due_renewal_invoices(*, today=None):
    """Callable idempotente para renovación recurrente — pensada para
    invocarse desde un comando de administración programado por cron
    (no hay Celery/Redis en este proyecto, ver CLAUDE.md: "Redis solo si
    una fase posterior demuestra necesidad real"). Para cada suscripción
    ACTIVE/PAST_DUE cuyo período vigente ya terminó, genera la factura
    del SIGUIENTE período y avanza `current_period_start/end` — nunca
    duplica gracias al `UniqueConstraint` de `SaaSInvoice`.

    Sigue siendo el mecanismo real para suscripciones de transferencia
    (que no se cobran solas — alguien debe ver la factura y pagarla). Para
    una suscripción con cobro recurrente de PayPal ya autorizado
    (`Subscription.paypal_subscription_id`), esta factura queda lista
    para reconciliarse en cuanto llegue el webhook de cobro confirmado —
    pero si el webhook llega ANTES de que este cron corra, la propia
    reconciliación (`services.recurring`) genera la factura ella misma
    vía `ensure_next_renewal_invoice` — nunca depende de que este cron
    se ejecute primero."""
    from ..models import Subscription

    hoy = today or date.today()
    generadas = []
    suscripciones = Subscription.all_objects.filter(
        status__in=[Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE],
        current_period_end__lte=hoy,
    ).select_related("plan_version__plan", "tenant")
    for subscription in suscripciones:
        with transaction.atomic():
            subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
            invoice, creada = ensure_next_renewal_invoice(subscription)
            if creada:
                generadas.append(invoice)
    return generadas
