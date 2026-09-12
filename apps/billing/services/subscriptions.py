"""
Ciclo de vida de `Subscription` (FASE 17, ver `docs/billing.md`):
creación, activación, cambio de plan (con prorrateo), cancelación,
PAST_DUE/suspensión/reactivación. Cada transición de estado también
sincroniza `Tenant.billing_status` vía `apps.billing.services.tenants`
(dependencia en UN solo sentido: este módulo llama a `tenants.py`,
nunca al revés, para evitar un ciclo)."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.pricing import get_plan

from ..models import PlanVersion, Subscription
from . import tenants as tenant_services
from ._saas_audit import audit_event

_DIAS_POR_FRECUENCIA = {
    PlanVersion.Frequency.MONTHLY: 30,
    PlanVersion.Frequency.ANNUAL: 365,
}


class InvalidSubscriptionOperation(ValidationError):
    pass


def resolve_plan_pricing(plan_id, *, frequency=PlanVersion.Frequency.MONTHLY):
    """Resuelve nombre/monto/moneda/`PlanVersion` a partir de un `slug`.
    Prueba PRIMERO el `Plan`/`PlanVersion` real (FASE 17); si no existe
    todavía (p. ej. antes de sembrar los planes reales, o en el flujo de
    prueba manual de FASE 16 con los slugs estáticos de
    `apps.core.pricing.PLANS`), cae al fallback estático — mismo criterio
    de compatibilidad ya usado en el resto del proyecto para no romper
    lo ya construido."""
    version = (
        PlanVersion.objects.filter(plan__slug=plan_id, frequency=frequency, is_current=True)
        .select_related("plan").first()
    )
    if version is not None:
        return version.plan.name, version.price_amount, version.price_currency, version

    plan = get_plan(plan_id)
    if plan is not None and plan.get("price_amount") is not None:
        return plan["nombre"], plan["price_amount"], plan.get("price_currency", "USD"), None
    return None, None, None, None


def _periodo_para_frecuencia(frequency, *, start=None):
    inicio = start or date.today()
    dias = _DIAS_POR_FRECUENCIA.get(frequency, 30)
    return inicio, inicio + timedelta(days=dias)


def create_subscription(tenant, *, saas_customer, plan_version, coupon=None, user=None):
    """Crea una suscripción PENDING (todavía no ACTIVE — eso ocurre
    cuando se confirma el primer pago, ver `activate_subscription`).
    Un tenant no puede tener dos suscripciones simultáneamente
    operativas (PENDING/ACTIVE/PAST_DUE) — verificado aquí, no solo
    documentado."""
    existentes = Subscription.all_objects.filter(
        tenant=tenant, status__in=[Subscription.Status.PENDING, Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE],
    )
    if existentes.exists():
        raise InvalidSubscriptionOperation("Este tenant ya tiene una suscripción activa o pendiente.")

    subscription = Subscription.all_objects.create(
        tenant=tenant, saas_customer=saas_customer, plan_version=plan_version, coupon=coupon,
        status=Subscription.Status.PENDING,
    )
    audit_event(tenant, action=AuditLog.Action.GENERIC, user=user, object_type="subscription", object_id=subscription.pk,
                after={"plan": plan_version.plan.slug, "frequency": plan_version.frequency})
    return subscription


def activate_subscription(subscription, *, user=None):
    """Activa la suscripción (llamada tras confirmar el primer pago) —
    fija el período vigente si es la primera activación, nunca lo pisa
    si ya venía de una renovación en curso."""
    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        if subscription.status == Subscription.Status.ACTIVE:
            return subscription
        if subscription.current_period_start is None:
            inicio, fin = _periodo_para_frecuencia(subscription.plan_version.frequency)
            subscription.current_period_start = inicio
            subscription.current_period_end = fin
        if subscription.started_at is None:
            subscription.started_at = timezone.now()
        subscription.status = Subscription.Status.ACTIVE
        subscription.save(update_fields=["status", "current_period_start", "current_period_end", "started_at", "updated_at"])
        tenant_services.activate_tenant(subscription.tenant, user=user)
        audit_event(subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="subscription", object_id=subscription.pk,
                    after={"status": "active"})
        return subscription


def activate_pending_subscription(subscription, *, user=None, reference=""):
    """Activación INICIAL explícita de una `Subscription` en `PENDING`
    (Gate Local, alta manual + activación) — NUNCA reutiliza
    `reactivate_subscription` (que exige `SUSPENDED`/`PAST_DUE`, sin
    modificar: `ACTIVATE != REACTIVATE` son dos operaciones distintas,
    con guardas distintas). Pensada para un Super Admin que confirma
    manualmente que el pago inicial de una venta manual ya está
    cubierto por una vía fuera de los flujos automáticos (PayPal Portal
    del tenant / comprobante de transferencia ya aprobado por
    `apps.billing.services.transfers.approve_payment_proof`).

    Nunca activa "porque sí": jamás se salta la evidencia de pago.
    Genera (o recupera, idempotente) la factura inicial y, si todavía
    tiene saldo pendiente, registra y confirma un `SaaSPayment`
    (`method=MANUAL_OTHER`) que lo cubre — exactamente el mismo motivo
    de seguridad por el que la Transacción de PayPal de la herramienta
    de prueba de FASE 16 nunca activa nada por sí sola (no tiene un
    `SaaSPayment` asociado, ver `services.paypal_integration`): aquí SÍ
    se crea esa evidencia real antes de activar, nunca se activa sin
    ella."""
    from . import invoicing as invoicing_services
    from . import payments as payment_services
    from ..models import SaaSPayment

    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        if subscription.status == Subscription.Status.ACTIVE:
            # Idempotente: doble clic / doble envío del formulario —
            # nunca un error, nunca una segunda factura/pago.
            return subscription
        if subscription.status != Subscription.Status.PENDING:
            raise InvalidSubscriptionOperation(
                "Solo se puede ACTIVAR una suscripción pendiente — use Reactivar para una suspendida o en PAST_DUE."
            )

        invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription, user=user)
        saldo = invoicing_services.get_invoice_balance_due(invoice)
        if saldo > 0:
            pago = payment_services.record_payment(
                tenant=subscription.tenant, saas_customer=subscription.saas_customer, subscription=subscription,
                method=SaaSPayment.Method.MANUAL_OTHER, amount=saldo, currency=invoice.currency,
                external_reference=reference, user=user, status=SaaSPayment.Status.CONFIRMED,
            )
            pago.received_at = timezone.now()
            pago.save(update_fields=["received_at"])
            payment_services.auto_apply_payment(pago, user=user)

    return activate_subscription(subscription, user=user)


def mark_past_due(subscription, *, user=None):
    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        if subscription.status != Subscription.Status.ACTIVE:
            return subscription
        subscription.status = Subscription.Status.PAST_DUE
        subscription.save(update_fields=["status", "updated_at"])
        tenant_services.mark_tenant_past_due(subscription.tenant, user=user)
        audit_event(subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="subscription", object_id=subscription.pk,
                    after={"status": "past_due"})
        return subscription


def suspend_subscription(subscription, *, user=None, reason=""):
    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        if subscription.status == Subscription.Status.SUSPENDED:
            return subscription
        subscription.status = Subscription.Status.SUSPENDED
        subscription.save(update_fields=["status", "updated_at"])
        tenant_services.suspend_tenant(subscription.tenant, user=user, reason=reason)
        audit_event(subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="subscription", object_id=subscription.pk,
                    after={"status": "suspended"}, reason=reason)
        return subscription


def reactivate_subscription(subscription, *, user=None):
    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        if subscription.status not in (Subscription.Status.SUSPENDED, Subscription.Status.PAST_DUE):
            raise InvalidSubscriptionOperation("Solo se puede reactivar una suscripción suspendida o en PAST_DUE.")
        subscription.status = Subscription.Status.ACTIVE
        subscription.save(update_fields=["status", "updated_at"])
        tenant_services.reactivate_tenant(subscription.tenant, user=user)
        audit_event(subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="subscription", object_id=subscription.pk,
                    after={"status": "active"})
        return subscription


def cancel_subscription(subscription, *, immediate=False, reason="", user=None):
    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        if subscription.status == Subscription.Status.CANCELLED:
            return subscription
        if immediate:
            subscription.status = Subscription.Status.CANCELLED
            subscription.cancelled_at = timezone.now()
            subscription.cancel_reason = reason
            subscription.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
            tenant_services.cancel_tenant(subscription.tenant, user=user, reason=reason)
        else:
            subscription.cancel_at_period_end = True
            subscription.cancel_reason = reason
            subscription.save(update_fields=["cancel_at_period_end", "cancel_reason", "updated_at"])
        audit_event(subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="subscription", object_id=subscription.pk,
                    after={"cancel_at_period_end": subscription.cancel_at_period_end, "immediate": immediate}, reason=reason)
        return subscription


# ---------------------------------------------------------------------
# Cambio de plan (upgrade/downgrade) + prorrateo
# ---------------------------------------------------------------------

def calculate_proration(subscription, *, new_plan_version, change_date=None):
    """Prorrateo lineal por DÍA — política explícita y documentada
    (sección 32 de la fase: "no existe un precedente en el proyecto, se
    elige la fórmula estándar más simple y se documenta como decisión",
    ver `DECISIONS.md`). Nunca implícito: devuelve el desglose completo
    para que quede registrado en la auditoría/factura.

    fórmula: valor_diario = precio / días_del_período;
    crédito = valor_diario_actual * días_restantes;
    cargo = valor_diario_nuevo * días_restantes;
    monto_neto = cargo - crédito (positivo = se cobra más, negativo =
    se acredita)."""
    hoy = change_date or date.today()
    inicio = subscription.current_period_start or hoy
    fin = subscription.current_period_end or hoy
    dias_totales = max((fin - inicio).days, 1)
    dias_restantes = max((fin - hoy).days, 0)

    precio_actual = subscription.plan_version.price_amount
    precio_nuevo = new_plan_version.price_amount
    valor_diario_actual = (precio_actual / Decimal(dias_totales)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    valor_diario_nuevo = (precio_nuevo / Decimal(dias_totales)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    credito = (valor_diario_actual * dias_restantes).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cargo = (valor_diario_nuevo * dias_restantes).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "dias_totales": dias_totales, "dias_restantes": dias_restantes,
        "valor_diario_actual": valor_diario_actual, "valor_diario_nuevo": valor_diario_nuevo,
        "credito": credito, "cargo": cargo, "monto_neto": cargo - credito,
    }


def change_plan(subscription, *, new_plan_version, user=None, prorate=True, change_date=None):
    """Upgrade/downgrade/cambio de frecuencia — el período NO cambia
    (mismo `current_period_start`/`current_period_end`), solo la
    versión de plan referenciada; el efecto económico se resuelve con
    una nota de crédito (si el prorrateo da un neto negativo, se
    acredita) o una línea de cargo en la próxima factura (si da un neto
    positivo) — nunca editando una factura ya emitida. `change_date`
    (por defecto hoy) es explícito, mismo criterio que
    `generate_due_renewal_invoices`, para que el cálculo sea
    determinístico en pruebas."""
    from . import credits as credit_services  # import diferido: evita un ciclo (credits.py no importa subscriptions.py)

    with transaction.atomic():
        subscription = Subscription.all_objects.select_for_update().get(pk=subscription.pk)
        if subscription.status not in (Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE):
            raise InvalidSubscriptionOperation("Solo se puede cambiar el plan de una suscripción activa.")

        desglose = calculate_proration(subscription, new_plan_version=new_plan_version, change_date=change_date) if prorate else None
        plan_anterior = subscription.plan_version
        subscription.plan_version = new_plan_version
        subscription.save(update_fields=["plan_version", "updated_at"])

        nota_credito = None
        if desglose is not None and desglose["monto_neto"] < 0:
            nota_credito = credit_services.issue_credit_note(
                tenant=subscription.tenant, saas_customer=subscription.saas_customer, subscription=subscription,
                amount=abs(desglose["monto_neto"]), currency=new_plan_version.price_currency,
                reason=f"Prorrateo por cambio de plan ({plan_anterior.plan.name} → {new_plan_version.plan.name})",
                user=user,
            )

        audit_event(
            subscription.tenant, action=AuditLog.Action.GENERIC, user=user, object_type="subscription", object_id=subscription.pk,
            before={"plan": plan_anterior.plan.slug}, after={"plan": new_plan_version.plan.slug},
            metadata={"prorrateo": {k: str(v) for k, v in (desglose or {}).items()}},
        )
        return subscription, desglose, nota_credito
