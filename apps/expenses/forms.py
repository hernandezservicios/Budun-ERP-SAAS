"""Formularios de Gastos (FASE 13). Formularios planos (no `ModelForm`):
el guardado real siempre lo hace `services.py`, nunca `form.save()` —
mismo criterio que `apps.purchases.forms`/`apps.sales.forms`."""

from decimal import Decimal

from django import forms

from apps.customers.file_validation import FORMATOS_PERMITIDOS_LEGIBLE, validar_archivo_adjunto
from apps.customers.models import DocumentCategory, Supplier
from apps.sales.models import PaymentMethod

from .models import ExpenseCategory, ExpenseRecurrence


class ExpenseCategoryForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=100)
    description = forms.CharField(label="Descripción", max_length=255, required=False)


class ExpenseForm(forms.Form):
    category = forms.ModelChoiceField(label="Categoría", queryset=ExpenseCategory.objects.none())
    supplier = forms.ModelChoiceField(label="Proveedor (opcional)", queryset=Supplier.objects.none(), required=False)
    description = forms.CharField(label="Descripción", max_length=255)
    expense_date = forms.DateField(label="Fecha del gasto", widget=forms.DateInput(attrs={"type": "date"}))
    due_date = forms.DateField(label="Fecha de vencimiento", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    currency = forms.CharField(label="Moneda", max_length=3, initial="USD")
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    tax_amount = forms.DecimalField(label="Impuesto", max_digits=12, decimal_places=2, required=False, min_value=Decimal("0"), initial=Decimal("0"))
    discount_amount = forms.DecimalField(label="Descuento", max_digits=12, decimal_places=2, required=False, min_value=Decimal("0"), initial=Decimal("0"))
    preferred_payment_method = forms.ChoiceField(
        label="Método de pago previsto", choices=[("", "—")] + list(PaymentMethod.choices), required=False
    )
    is_exceptional = forms.BooleanField(label="Marcar como excepcional/sensible", required=False)
    exceptional_reason = forms.CharField(label="Motivo de excepcionalidad", max_length=255, required=False)
    notes = forms.CharField(label="Notas", widget=forms.Textarea(attrs={"rows": 2}), required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["category"].queryset = ExpenseCategory.objects.filter(tenant=tenant, is_active=True)
            self.fields["supplier"].queryset = Supplier.objects.filter(tenant=tenant, is_active=True)

    def clean_tax_amount(self):
        return self.cleaned_data.get("tax_amount") or Decimal("0")

    def clean_discount_amount(self):
        return self.cleaned_data.get("discount_amount") or Decimal("0")

    def clean(self):
        datos = super().clean()
        if datos.get("is_exceptional") and not datos.get("exceptional_reason"):
            self.add_error("exceptional_reason", "Indica el motivo si marcas el gasto como excepcional.")
        return datos


class ExpensePaymentForm(forms.Form):
    method = forms.ChoiceField(label="Método", choices=PaymentMethod.choices)
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reference = forms.CharField(label="Referencia", max_length=100, required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)


class RejectExpenseForm(forms.Form):
    reason = forms.CharField(label="Motivo del rechazo", max_length=255, required=False)


class CancelExpenseForm(forms.Form):
    reason = forms.CharField(label="Motivo de la cancelación", max_length=255, required=False)


class ExpenseDocumentForm(forms.Form):
    """Reutiliza literalmente la validación de archivos de FASE 9 —
    mismo patrón que `apps.purchases.forms.PurchaseAttachmentForm`."""

    file = forms.FileField(label="Archivo")
    category = forms.ChoiceField(label="Categoría", choices=DocumentCategory.choices, initial=DocumentCategory.COMPROBANTE)
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].help_text = f"Formatos permitidos: {FORMATOS_PERMITIDOS_LEGIBLE}. Máximo 10 MB."

    def clean_file(self):
        archivo = self.cleaned_data["file"]
        try:
            validar_archivo_adjunto(archivo)
        except forms.ValidationError:
            raise
        except Exception as error:  # noqa: BLE001 — nunca dejar pasar un archivo sin validar
            raise forms.ValidationError(str(error))
        return archivo


class ExpenseRecurrenceForm(forms.Form):
    category = forms.ModelChoiceField(label="Categoría", queryset=ExpenseCategory.objects.none())
    supplier = forms.ModelChoiceField(label="Proveedor (opcional)", queryset=Supplier.objects.none(), required=False)
    description = forms.CharField(label="Descripción", max_length=255)
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    currency = forms.CharField(label="Moneda", max_length=3, initial="USD")
    frequency = forms.ChoiceField(label="Frecuencia", choices=ExpenseRecurrence.Frequency.choices)
    start_date = forms.DateField(label="Fecha de inicio", widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(label="Fecha de fin (opcional)", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["category"].queryset = ExpenseCategory.objects.filter(tenant=tenant, is_active=True)
            self.fields["supplier"].queryset = Supplier.objects.filter(tenant=tenant, is_active=True)
