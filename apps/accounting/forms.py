"""Formularios de Contabilidad (FASE 14). Formularios planos (no
`ModelForm`): el guardado real siempre lo hace `services.py`, nunca
`form.save()` — mismo criterio que el resto del proyecto."""

from decimal import Decimal

from django import forms

from apps.customers.models import Customer, Supplier

from .models import Account, AccountingPeriod, AccountMapping


class AccountForm(forms.Form):
    code = forms.CharField(label="Código", max_length=20)
    name = forms.CharField(label="Nombre", max_length=150)
    account_type = forms.ChoiceField(label="Tipo", choices=Account.AccountType.choices)
    parent = forms.ModelChoiceField(label="Cuenta padre", queryset=Account.objects.none(), required=False)
    allows_posting = forms.BooleanField(label="Permite movimientos", required=False, initial=True)
    description = forms.CharField(label="Descripción", max_length=255, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["parent"].queryset = Account.objects.filter(tenant=tenant, is_active=True)


class AccountingPeriodForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=50, help_text="Ej. «2025-01».")
    start_date = forms.DateField(label="Fecha de inicio", widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(label="Fecha de fin", widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(label="Notas", max_length=255, required=False)


class ReopenPeriodForm(forms.Form):
    reason = forms.CharField(label="Motivo de la reapertura", max_length=255)


class JournalEntryLineForm(forms.Form):
    account = forms.ModelChoiceField(label="Cuenta", queryset=Account.objects.none())
    # Deliberadamente SIN `initial=Decimal("0")`: un formulario "extra"
    # del formset que llega completamente vacío debe seguir
    # considerándose vacío (`has_changed() == False`) para que Django
    # lo omita de la validación — un `initial` numérico distinto de la
    # cadena vacía enviada rompe esa detección y fuerza la validación
    # de `account` (obligatorio) incluso en filas nunca completadas.
    debit = forms.DecimalField(label="Débito", max_digits=14, decimal_places=2, required=False, min_value=Decimal("0"))
    credit = forms.DecimalField(label="Crédito", max_digits=14, decimal_places=2, required=False, min_value=Decimal("0"))
    description = forms.CharField(label="Descripción", max_length=255, required=False)
    customer = forms.ModelChoiceField(label="Cliente (opcional)", queryset=Customer.objects.none(), required=False)
    supplier = forms.ModelChoiceField(label="Proveedor (opcional)", queryset=Supplier.objects.none(), required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["account"].queryset = Account.objects.filter(tenant=tenant, is_active=True, allows_posting=True)
            self.fields["customer"].queryset = Customer.objects.filter(tenant=tenant, is_active=True)
            self.fields["supplier"].queryset = Supplier.objects.filter(tenant=tenant, is_active=True)

    def clean_debit(self):
        return self.cleaned_data.get("debit") or Decimal("0")

    def clean_credit(self):
        return self.cleaned_data.get("credit") or Decimal("0")


JournalEntryLineFormSet = forms.formset_factory(JournalEntryLineForm, extra=4)


class JournalEntryHeaderForm(forms.Form):
    entry_date = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(label="Descripción", max_length=255)
    reference = forms.CharField(label="Referencia", max_length=100, required=False)


class ReverseJournalEntryForm(forms.Form):
    reason = forms.CharField(label="Motivo del reverso", max_length=255, required=False)


class AccountMappingForm(forms.Form):
    key = forms.ChoiceField(label="Evento de negocio", choices=AccountMapping.Key.choices)
    account = forms.ModelChoiceField(label="Cuenta contable", queryset=Account.objects.none())

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["account"].queryset = Account.objects.filter(tenant=tenant, is_active=True, allows_posting=True)


class ReportPeriodFilterForm(forms.Form):
    period = forms.ModelChoiceField(label="Período", queryset=AccountingPeriod.objects.none())

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["period"].queryset = AccountingPeriod.objects.filter(tenant=tenant).order_by("-start_date")
