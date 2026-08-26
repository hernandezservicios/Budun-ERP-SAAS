"""Formularios de Nómina (FASE 13). Formularios planos (no `ModelForm`):
el guardado real siempre lo hace `services.py`, nunca `form.save()` —
mismo criterio que `apps.expenses.forms`/`apps.hr.forms`."""

from decimal import Decimal

from django import forms

from apps.hr.models import Employee
from apps.sales.models import PaymentMethod

from .models import PayrollLine


class PayrollPeriodForm(forms.Form):
    start_date = forms.DateField(label="Fecha de inicio", widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(label="Fecha de fin", widget=forms.DateInput(attrs={"type": "date"}))
    pay_date = forms.DateField(label="Fecha de pago", widget=forms.DateInput(attrs={"type": "date"}))
    currency = forms.CharField(label="Moneda", max_length=3, initial="USD", required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)


class PayrollCalculateForm(forms.Form):
    employee = forms.ModelChoiceField(label="Empleado", queryset=Employee.objects.none())

    def __init__(self, *args, tenant=None, exclude_employee_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            queryset = Employee.objects.filter(tenant=tenant, status=Employee.Status.ACTIVE)
            if exclude_employee_ids:
                queryset = queryset.exclude(pk__in=exclude_employee_ids)
            self.fields["employee"].queryset = queryset


class PayrollLineForm(forms.Form):
    category = forms.ChoiceField(label="Categoría", choices=PayrollLine.Category.choices)
    concept = forms.ChoiceField(label="Concepto", choices=PayrollLine.Concept.choices)
    description = forms.CharField(label="Descripción", max_length=255, required=False)
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class PayrollPaymentForm(forms.Form):
    method = forms.ChoiceField(label="Método", choices=PaymentMethod.choices)
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reference = forms.CharField(label="Referencia", max_length=100, required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)
