"""Formularios de filtro para Reportes (FASE 14) — siempre planos,
nunca `ModelForm`: los reportes son de solo lectura."""

from django import forms

from apps.customers.models import Customer, Supplier
from apps.expenses.models import ExpenseCategory
from apps.payroll.models import PayrollPeriod
from apps.pos.models import CashRegister
from apps.sales.models import Sale


class DateRangeFilterForm(forms.Form):
    date_from = forms.DateField(label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(label="Hasta", required=False, widget=forms.DateInput(attrs={"type": "date"}))


class SalesReportFilterForm(DateRangeFilterForm):
    customer = forms.ModelChoiceField(label="Cliente", queryset=Customer.objects.none(), required=False)
    status = forms.ChoiceField(label="Estado", choices=[("", "Todos")] + list(Sale.Status.choices), required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["customer"].queryset = Customer.objects.filter(tenant=tenant, is_active=True)


class ExpensesReportFilterForm(DateRangeFilterForm):
    category = forms.ModelChoiceField(label="Categoría", queryset=ExpenseCategory.objects.none(), required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["category"].queryset = ExpenseCategory.objects.filter(tenant=tenant, is_active=True)


class PurchasesReportFilterForm(DateRangeFilterForm):
    supplier = forms.ModelChoiceField(label="Proveedor", queryset=Supplier.objects.none(), required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["supplier"].queryset = Supplier.objects.filter(tenant=tenant, is_active=True)


class CashReportFilterForm(DateRangeFilterForm):
    register = forms.ModelChoiceField(label="Caja", queryset=CashRegister.objects.none(), required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["register"].queryset = CashRegister.objects.filter(tenant=tenant)


class PayrollReportFilterForm(forms.Form):
    period = forms.ModelChoiceField(label="Período", queryset=PayrollPeriod.objects.none(), required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["period"].queryset = PayrollPeriod.objects.filter(tenant=tenant).order_by("-start_date")
