from decimal import Decimal

from django import forms

from . import services as paypal_services
from .models import BankAccount, PlanVersion
from .services import transfers as transfer_services


class SelectPlanForm(forms.Form):
    plan_version = forms.ModelChoiceField(
        queryset=PlanVersion.objects.filter(is_current=True, plan__is_active=True).select_related("plan"),
        label="Plan",
    )
    payment_method = forms.ChoiceField(label="Método de pago")
    coupon_code = forms.CharField(required=False, max_length=50, label="Cupón (opcional)")

    def __init__(self, *args, **kwargs):
        """FASE DE CORRECCIÓN 2 (Billing del Tenant): las opciones ya
        NUNCA se hardcodean — se calculan en cada instancia a partir de
        la configuración real (`services.is_paypal_available`/
        `services.transfers.is_bank_transfer_available`), nunca de una
        lista fija. Si un método deja de estar disponible entre que se
        renderizó el formulario y que el usuario lo envía, `ChoiceField`
        ya rechaza cualquier valor fuera de `choices` — el mismo
        `create_checkout` además vuelve a rechazar un checkout de
        PayPal deshabilitado como segunda defensa real en el backend.

        FASE DE CORRECCIÓN 2C: "PayPal (cobro automático)" es una
        TERCERA opción, deliberadamente distinta de "PayPal (pago
        único)" — mismo interruptor de disponibilidad
        (`is_paypal_available`, PayPal es PayPal para efectos de
        habilitar/deshabilitar la plataforma), pero autoriza cobros
        FUTUROS en vez de cobrar solo la factura actual (ver
        `docs/billing.md` sección "Billing recurrente con PayPal")."""
        super().__init__(*args, **kwargs)
        opciones = []
        if paypal_services.is_paypal_available():
            opciones.append(("paypal", "PayPal (pago único)"))
            opciones.append(("paypal_recurring", "PayPal (cobro automático mensual/anual)"))
        if transfer_services.is_bank_transfer_available():
            opciones.append(("bank_transfer", "Transferencia bancaria"))
        self.fields["payment_method"].choices = opciones


class ChangePlanForm(forms.Form):
    plan_version = forms.ModelChoiceField(
        queryset=PlanVersion.objects.filter(is_current=True, plan__is_active=True).select_related("plan"),
        label="Nuevo plan",
    )


class UploadProofForm(forms.Form):
    bank_account = forms.ModelChoiceField(queryset=BankAccount.objects.filter(is_active=True), label="Cuenta receptora")
    # FASE DE CORRECCIÓN 2 (Billing del Tenant): `min_value` real — antes
    # aceptaba cero/negativo, un "monto inválido" que ni siquiera el
    # servicio (`transfers.submit_payment_proof`) validaba todavía en
    # ese momento. La consistencia moneda-vs-cuenta se valida en el
    # servicio (necesita `bank_account`, ya resuelto ahí como instancia
    # real, no solo el código de moneda de este campo).
    declared_amount = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"), label="Monto transferido",
    )
    declared_currency = forms.CharField(max_length=3, initial="USD", label="Moneda")
    declared_bank_name = forms.CharField(required=False, max_length=100, label="Tu banco de origen")
    file = forms.FileField(label="Comprobante (PDF/imagen)")


class CancelSubscriptionForm(forms.Form):
    immediate = forms.BooleanField(required=False, label="Cancelar de inmediato (en vez de al finalizar el período)")
    reason = forms.CharField(required=False, max_length=255, label="Motivo")
