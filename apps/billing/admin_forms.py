from django import forms

from .models import BankAccount, Plan, PlanVersion


class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        fields = ["name", "slug", "description", "is_active", "sort_order", "max_users", "max_products", "features"]


class PlanVersionForm(forms.ModelForm):
    class Meta:
        model = PlanVersion
        fields = ["frequency", "price_amount", "price_currency"]


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ["bank_name", "country", "currency", "account_holder", "account_number", "account_type", "is_active", "priority", "notes"]


class CreditNoteIssueForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, label="Monto")
    currency = forms.CharField(max_length=3, initial="USD", label="Moneda")
    reason = forms.CharField(max_length=255, label="Motivo")


class RefundRequestForm(forms.Form):
    amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Monto (vacío = total disponible)")
    reason = forms.CharField(required=False, max_length=255, label="Motivo")


class ProofRejectForm(forms.Form):
    reason = forms.CharField(max_length=255, label="Motivo del rechazo")


class ManualTenantSaleForm(forms.Form):
    """Venta manual desde Super Admin (sección 16 de la fase) — SIEMPRE
    pasa por el mismo núcleo de Billing (crea `Subscription` real),
    nunca escribe `Tenant.billing_status=ACTIVE` directamente."""

    customer_name = forms.CharField(max_length=150, label="Nombre del cliente SaaS")
    customer_email = forms.EmailField(label="Correo del cliente SaaS")
    tenant_name = forms.CharField(max_length=150, label="Nombre de la empresa (tenant)")
    plan_version = forms.ModelChoiceField(
        queryset=PlanVersion.objects.filter(is_current=True, plan__is_active=True).select_related("plan"), label="Plan",
    )
    owner_email = forms.EmailField(label="Correo del usuario propietario (OWNER)")
