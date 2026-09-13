"""
Reportes de Billing SaaS (FASE 17, secciones 38-39). Viven en
`apps.billing` (nunca en `apps.reports`, que es exclusivamente
tenant-scoped) — el actor es el Super Admin de PLATAFORMA agregando
sobre TODOS los tenants. Ningún modelo propio: cada función agrega
sobre los modelos ya existentes (`{"summary": ..., "rows": ...}`,
mismo contrato que `apps.reports.services`). Exportación reutiliza
`apps.reports.exports` (PDF/XLSX) — nunca un segundo motor."""

from datetime import date, datetime, time
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from ..models import (
    BillingRefund,
    CreditNote,
    PaymentProof,
    PlanVersion,
    SaaSInvoice,
    SaaSPayment,
    Subscription,
)


def _mrr_de_suscripcion(subscription):
    """FASE DE CORRECCIÓN 5: el precio de lista (`plan_version.
    price_amount`) NUNCA es lo que un tenant con cupón vigente paga
    realmente — antes de esta corrección, el MRR/ARR reportado
    sobreestimaba el ingreso real de cualquier suscripción con un
    cupón activo, porque nunca aplicaba el mismo descuento que
    `invoicing.generate_invoice_for_subscription` ya calcula al
    facturar. Reutiliza exactamente la misma vigencia/cálculo de
    descuento (`coupons.is_coupon_currently_valid`/`calculate_discount`)
    — nunca una segunda fórmula de descuento."""
    precio = subscription.plan_version.price_amount
    if subscription.coupon is not None:
        from . import coupons as coupon_services

        if coupon_services.is_coupon_currently_valid(subscription.coupon):
            descuento = coupon_services.calculate_discount(subscription.coupon, precio)
            precio = max(precio - descuento, Decimal("0"))
    if subscription.plan_version.frequency == PlanVersion.Frequency.ANNUAL:
        return (precio / Decimal("12")).quantize(Decimal("0.01"))
    return precio


def get_billing_dashboard_summary(*, today=None):
    hoy = today or date.today()
    inicio_mes = hoy.replace(day=1)
    # Los campos comparados abajo (created_at/cancelled_at/received_at/
    # completed_at) son DateTimeField — comparar contra un `date` puro
    # hace que Django lo convierta a medianoche NAIVE internamente
    # (warning real de "naive datetime... time zone support is active",
    # ver KNOWN_ISSUES.md) — se construye aquí, una sola vez, el
    # datetime CONSCIENTE equivalente para esos filtros.
    inicio_mes_dt = timezone.make_aware(datetime.combine(inicio_mes, time.min))

    activas = Subscription.all_objects.filter(status=Subscription.Status.ACTIVE).select_related("plan_version")
    mrr = sum((_mrr_de_suscripcion(s) for s in activas), Decimal("0"))

    return {
        "mrr": mrr,
        "arr": mrr * 12,
        "active_subscriptions": activas.count(),
        "past_due_subscriptions": Subscription.all_objects.filter(status=Subscription.Status.PAST_DUE).count(),
        "suspended_subscriptions": Subscription.all_objects.filter(status=Subscription.Status.SUSPENDED).count(),
        "new_signups_this_month": Subscription.all_objects.filter(created_at__gte=inicio_mes_dt).count(),
        "cancellations_this_month": Subscription.all_objects.filter(
            status=Subscription.Status.CANCELLED, cancelled_at__gte=inicio_mes_dt,
        ).count(),
        "pending_transfers": PaymentProof.all_objects.filter(
            status__in=[PaymentProof.Status.SUBMITTED, PaymentProof.Status.UNDER_REVIEW],
        ).count(),
        "revenue_this_month": SaaSPayment.all_objects.filter(
            status=SaaSPayment.Status.CONFIRMED, received_at__gte=inicio_mes_dt,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0"),
        "refunds_this_month": BillingRefund.all_objects.filter(
            status=BillingRefund.Status.COMPLETED, completed_at__gte=inicio_mes_dt,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0"),
        "credit_notes_this_month": CreditNote.all_objects.filter(created_at__gte=inicio_mes_dt).aggregate(total=Sum("amount"))["total"] or Decimal("0"),
        "overdue_invoices": SaaSInvoice.all_objects.filter(
            status__in=[SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID], due_date__lt=hoy,
        ).count(),
    }


def get_revenue_report(*, date_from=None, date_to=None):
    pagos = SaaSPayment.all_objects.filter(status=SaaSPayment.Status.CONFIRMED).select_related("tenant", "subscription__plan_version__plan")
    if date_from is not None:
        pagos = pagos.filter(received_at__date__gte=date_from)
    if date_to is not None:
        pagos = pagos.filter(received_at__date__lte=date_to)

    filas = [
        {
            "fecha": pago.received_at.date() if pago.received_at else None,
            "tenant": str(pago.tenant) if pago.tenant else "—",
            "plan": pago.subscription.plan_version.plan.name if pago.subscription else "—",
            "metodo": pago.get_method_display(),
            "monto": pago.amount,
            "moneda": pago.currency,
        }
        for pago in pagos.order_by("-received_at")
    ]
    return {
        "summary": {
            "total": sum((f["monto"] for f in filas), Decimal("0")),
            "cantidad_pagos": len(filas),
            "por_metodo": {
                metodo: sum((f["monto"] for f in filas if f["metodo"] == metodo), Decimal("0"))
                for metodo in {f["metodo"] for f in filas}
            },
        },
        "rows": filas,
    }


def get_subscriptions_report():
    return {
        "summary": {
            "activas": Subscription.all_objects.filter(status=Subscription.Status.ACTIVE).count(),
            "pendientes": Subscription.all_objects.filter(status=Subscription.Status.PENDING).count(),
            "past_due": Subscription.all_objects.filter(status=Subscription.Status.PAST_DUE).count(),
            "suspendidas": Subscription.all_objects.filter(status=Subscription.Status.SUSPENDED).count(),
            "canceladas": Subscription.all_objects.filter(status=Subscription.Status.CANCELLED).count(),
        },
        "rows": [
            {
                "tenant": str(s.tenant), "plan": s.plan_version.plan.name, "frecuencia": s.plan_version.get_frequency_display(),
                "estado": s.get_status_display(), "estado_codigo": s.status, "periodo_fin": s.current_period_end,
            }
            for s in Subscription.all_objects.select_related("tenant", "plan_version__plan").order_by("-created_at")
        ],
    }


def get_invoice_aging_report(*, today=None):
    hoy = today or date.today()
    facturas = SaaSInvoice.all_objects.filter(
        status__in=[SaaSInvoice.Status.OPEN, SaaSInvoice.Status.PARTIALLY_PAID],
    ).select_related("tenant")
    # Claves de diccionario SIN guiones (nunca "0-30"/"90+"): la
    # resolución de variables de plantilla de Django solo divide por
    # ".", pero un guion dentro de un bit puede confundirse con el
    # operador de resta en otros contextos de plantilla — más seguro
    # usar identificadores simples.
    cubetas = {"d0_30": [], "d31_60": [], "d61_90": [], "d90_plus": []}
    for factura in facturas:
        dias = (hoy - factura.due_date).days
        if dias <= 30:
            cubetas["d0_30"].append(factura)
        elif dias <= 60:
            cubetas["d31_60"].append(factura)
        elif dias <= 90:
            cubetas["d61_90"].append(factura)
        else:
            cubetas["d90_plus"].append(factura)
    return {
        "summary": {clave: sum((f.total for f in lista), Decimal("0")) for clave, lista in cubetas.items()},
        "rows": [
            {"numero": f.number, "tenant": str(f.tenant), "vencimiento": f.due_date, "total": f.total, "dias_vencido": (hoy - f.due_date).days}
            for lista in cubetas.values() for f in lista
        ],
    }
