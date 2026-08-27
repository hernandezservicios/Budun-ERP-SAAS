from django import forms

from apps.core.pricing import PLANS
from apps.tenants.models import Tenant

from .models import PayPalTransaction

_PLANES_COBRABLES = [(plan["id"], plan["nombre"]) for plan in PLANS if plan.get("price_amount") is not None]


class CheckoutCreateForm(forms.Form):
    """Iniciar un cobro de PayPal (herramienta de plataforma para el
    Super Admin, ver `docs/paypal.md`) — NO es el flujo de autoservicio
    Landing → Pricing → Plan del tenant (eso es FASE 17). Sirve para
    probar/operar el mecanismo real de PayPal end-to-end: elegir un
    tenant existente, un plan con precio de autoservicio, y el
    propósito del cobro (alta/renovación)."""

    tenant = forms.ModelChoiceField(queryset=Tenant.objects.all().order_by("name"), label="Tenant")
    plan_id = forms.ChoiceField(choices=_PLANES_COBRABLES, label="Plan")
    purpose = forms.ChoiceField(choices=PayPalTransaction.Purpose.choices, label="Propósito")


class RefundForm(forms.Form):
    amount = forms.DecimalField(required=False, min_value=0, max_digits=12, decimal_places=2, label="Monto (vacío = reembolso total)")
    reason = forms.CharField(required=False, max_length=255, label="Motivo")
