from django import forms

from .models import BankAccount, PlanVersion


class SelectPlanForm(forms.Form):
    plan_version = forms.ModelChoiceField(
        queryset=PlanVersion.objects.filter(is_current=True, plan__is_active=True).select_related("plan"),
        label="Plan",
    )
    payment_method = forms.ChoiceField(choices=[("paypal", "PayPal"), ("bank_transfer", "Transferencia bancaria")], label="Método de pago")
    coupon_code = forms.CharField(required=False, max_length=50, label="Cupón (opcional)")


class ChangePlanForm(forms.Form):
    plan_version = forms.ModelChoiceField(
        queryset=PlanVersion.objects.filter(is_current=True, plan__is_active=True).select_related("plan"),
        label="Nuevo plan",
    )


class UploadProofForm(forms.Form):
    bank_account = forms.ModelChoiceField(queryset=BankAccount.objects.filter(is_active=True), label="Cuenta receptora")
    declared_amount = forms.DecimalField(max_digits=12, decimal_places=2, label="Monto transferido")
    declared_currency = forms.CharField(max_length=3, initial="USD", label="Moneda")
    declared_bank_name = forms.CharField(required=False, max_length=100, label="Tu banco de origen")
    file = forms.FileField(label="Comprobante (PDF/imagen)")


class CancelSubscriptionForm(forms.Form):
    immediate = forms.BooleanField(required=False, label="Cancelar de inmediato (en vez de al finalizar el período)")
    reason = forms.CharField(required=False, max_length=255, label="Motivo")
