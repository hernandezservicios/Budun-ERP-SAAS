"""
`SaaSPayment`/`SaaSPaymentAllocation` (FASE 17) — espejo estructural de
`apps.sales.services` (`record_payment`/`apply_payment_to_sales`/
`reverse_allocation`), mismas reglas: nunca excede lo disponible del
pago ni el saldo pendiente de la factura, `select_for_update()` sobre
AMBAS filas antes de aplicar, todo-o-nada al repartir un pago entre
varias facturas, reverso en vez de edición in-place."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import AuditLog

from ..models import SaaSInvoice, SaaSPayment, SaaSPaymentAllocation
from ._saas_audit import audit_event
from .invoicing import _recompute_invoice_status, get_invoice_balance_due


class InvalidPaymentOperation(ValidationError):
    pass


def record_payment(*, tenant, saas_customer, method, amount, currency, subscription=None,
                    external_reference="", paypal_transaction=None, payment_proof=None, user=None,
                    status=SaaSPayment.Status.PENDING):
    payment = SaaSPayment.all_objects.create(
        tenant=tenant, saas_customer=saas_customer, subscription=subscription, method=method,
        amount=amount, currency=currency, status=status, external_reference=external_reference,
        paypal_transaction=paypal_transaction, payment_proof=payment_proof, created_by=user,
    )
    audit_event(tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_payment", object_id=payment.pk,
                after={"method": method, "amount": str(amount), "currency": currency})
    return payment


def confirm_payment(payment, *, user=None):
    from django.utils import timezone

    with transaction.atomic():
        payment = SaaSPayment.all_objects.select_for_update().get(pk=payment.pk)
        if payment.status == SaaSPayment.Status.CONFIRMED:
            return payment
        payment.status = SaaSPayment.Status.CONFIRMED
        payment.received_at = timezone.now()
        payment.save(update_fields=["status", "received_at"])
        audit_event(payment.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_payment", object_id=payment.pk,
                    after={"status": "confirmed"})
        return payment


def get_unallocated_payment_amount(payment):
    """`all_objects` explícito — nunca `payment.allocations` (relación
    inversa tenant-scoped, ver `apps.billing.services.invoicing.
    get_invoice_balance_due`)."""
    aplicado = sum(
        (a.amount for a in SaaSPaymentAllocation.all_objects.filter(payment=payment, status=SaaSPaymentAllocation.Status.ACTIVE)),
        Decimal("0"),
    )
    return payment.amount - aplicado


def apply_payment_to_invoices(payment, allocations, *, user=None):
    """`allocations`: lista de `(invoice, amount)`. Todo-o-nada: si
    cualquier asignación excede lo disponible del pago o el saldo
    pendiente de la factura correspondiente, ninguna se aplica."""
    with transaction.atomic():
        payment = SaaSPayment.all_objects.select_for_update().get(pk=payment.pk)
        if payment.tenant_id is None or payment.status != SaaSPayment.Status.CONFIRMED:
            raise InvalidPaymentOperation("Solo un pago CONFIRMADO puede aplicarse a facturas.")

        disponible = get_unallocated_payment_amount(payment)
        total_solicitado = sum((Decimal(monto) for _factura, monto in allocations), Decimal("0"))
        if total_solicitado > disponible:
            raise InvalidPaymentOperation(f"El monto solicitado ({total_solicitado}) excede el saldo disponible del pago ({disponible}).")

        creadas = []
        for invoice, monto in allocations:
            monto = Decimal(monto)
            invoice_bloqueada = SaaSInvoice.all_objects.select_for_update().get(pk=invoice.pk)
            if invoice_bloqueada.tenant_id != payment.tenant_id:
                raise InvalidPaymentOperation("El pago y la factura deben pertenecer al mismo tenant.")
            # FASE DE CORRECCIÓN 4 (Transferencias/comprobantes, sección 9):
            # mismo criterio ya establecido para Cuentas por Cobrar del ERP
            # (`apps.sales.services.allocate_payment` rechaza cross-currency
            # sin motor de tipos de cambio, ver `docs/currency.md`) — nunca
            # una conversión implícita. Defensa EN el núcleo del ledger,
            # nunca solo en el punto de entrada (`transfers.submit_payment_
            # proof` ya valida esto también, pero el ledger no debe confiar
            # solo en eso).
            if invoice_bloqueada.currency != payment.currency:
                raise InvalidPaymentOperation(
                    f"La moneda del pago ({payment.currency}) no coincide con la moneda de la factura "
                    f"{invoice_bloqueada.number} ({invoice_bloqueada.currency}) — no se realizan conversiones automáticas."
                )
            saldo_factura = get_invoice_balance_due(invoice_bloqueada)
            if monto > saldo_factura:
                raise InvalidPaymentOperation(f"El monto ({monto}) excede el saldo pendiente de la factura {invoice_bloqueada.number} ({saldo_factura}).")
            allocation = SaaSPaymentAllocation.all_objects.create(
                tenant=payment.tenant, payment=payment, invoice=invoice_bloqueada, amount=monto,
            )
            _recompute_invoice_status(invoice_bloqueada)
            creadas.append(allocation)

        audit_event(payment.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_payment", object_id=payment.pk,
                    after={"aplicaciones": [{"invoice": a.invoice.number, "amount": str(a.amount)} for a in creadas]})
        return creadas


def auto_apply_payment(payment, *, user=None):
    """Aplica el pago a las facturas ABIERTAS más antiguas del tenant en
    orden, hasta agotar el monto disponible del pago o las facturas
    pendientes — el sobrante (si el pago excede todas las facturas
    pendientes) queda simplemente SIN APLICAR, lo cual ya es, por
    definición, el "saldo a favor" del tenant (ver
    `apps.billing.services.credits.get_subscription_credit_balance`) —
    nunca se pierde, nunca requiere un modelo nuevo.

    FASE DE CORRECCIÓN 4 (sección 18/19, "comprobante + PayPal sobre la
    misma factura"): el plan de asignación (`asignaciones`) se calcula
    leyendo `get_invoice_balance_due` SIN lock — entre ese cálculo y el
    `select_for_update()` real dentro de `apply_payment_to_invoices`,
    OTRO método de pago completamente independiente (p. ej. una
    aprobación de transferencia y una captura de PayPal sobre la MISMA
    factura, ejecutándose en hilos distintos) puede haber cubierto esa
    factura primero — un hallazgo real de esta corrección, encontrado
    por la propia prueba de concurrencia nueva
    (`TransferAndPayPalRaceConcurrencyTests`). Sin este reintento, esa
    carrera legítima (nadie hizo nada mal, dos pagos válidos llegaron a
    la vez) hacía que `apply_payment_to_invoices` lanzara
    `InvalidPaymentOperation` sin atrapar — y como `auto_apply_payment`
    se llama typically desde dentro de la transacción de OTRA operación
    (una captura de PayPal, un webhook), esa excepción sin atrapar
    revertía la transacción COMPLETA del llamador (p. ej. deshacía la
    propia confirmación de la captura de PayPal ya exitosa). Un
    reintento ACOTADO (una sola vez, con el saldo recalculado) es
    suficiente: si tras recalcular ya no queda ninguna factura con
    saldo real, el pago simplemente queda sin aplicar — nunca se
    pierde, nunca rompe la operación del llamador."""
    for _intento in range(2):
        disponible = get_unallocated_payment_amount(payment)
        if disponible <= 0:
            return []
        # Nunca considera una factura en otra moneda — `apply_payment_
        # to_invoices` la rechazaría igual, pero filtrarla aquí evita que
        # un pago legítimamente sin aplicar (p. ej. una anomalía de cobro
        # recurrente reportada en otra moneda, ver `services.recurring.
        # confirm_recurring_charge`) intente aplicarse contra una factura
        # que nunca podría cubrir, en vez de quedar simplemente como
        # saldo a favor (nunca se pierde, ver `credits.
        # get_subscription_credit_balance`).
        facturas_abiertas = SaaSInvoice.all_objects.filter(
            tenant=payment.tenant, status__in=[SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID],
            currency=payment.currency,
        ).order_by("due_date", "id")
        if payment.subscription_id:
            facturas_abiertas = facturas_abiertas.filter(subscription_id=payment.subscription_id)

        asignaciones = []
        restante = disponible
        for invoice in facturas_abiertas:
            if restante <= 0:
                break
            saldo = get_invoice_balance_due(invoice)
            if saldo <= 0:
                continue
            monto = min(saldo, restante)
            asignaciones.append((invoice, monto))
            restante -= monto
        if not asignaciones:
            return []
        try:
            return apply_payment_to_invoices(payment, asignaciones, user=user)
        except InvalidPaymentOperation:
            if _intento == 1:
                # Ya se recalculó una vez con datos frescos y sigue sin
                # poder aplicarse (otra carrera, o el pago genuinamente ya
                # no tiene ninguna factura válida a la que aplicarse) —
                # nunca insistir indefinidamente; el monto simplemente
                # queda sin aplicar, contabilizado como saldo a favor.
                return []
            continue
    return []


def reverse_allocation(allocation, *, user=None, reason=""):
    from django.utils import timezone

    with transaction.atomic():
        allocation = SaaSPaymentAllocation.all_objects.select_for_update().get(pk=allocation.pk)
        if allocation.status == SaaSPaymentAllocation.Status.REVERSED:
            return allocation
        allocation.status = SaaSPaymentAllocation.Status.REVERSED
        allocation.reversed_at = timezone.now()
        allocation.reversal_reason = reason
        allocation.save(update_fields=["status", "reversed_at", "reversal_reason"])
        _recompute_invoice_status(SaaSInvoice.all_objects.get(pk=allocation.invoice_id))
        audit_event(allocation.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="saas_payment_allocation",
                    object_id=allocation.pk, reason=reason)
        return allocation
