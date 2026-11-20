from decimal import Decimal

from django import forms

from apps.customers.models import Customer
from apps.sales.models import PaymentMethod

from .models import CashRegister


class PosSearchForm(forms.Form):
    q = forms.CharField(
        label="Buscar", max_length=100, required=False,
        widget=forms.TextInput(attrs={"placeholder": "Nombre, SKU, código de barras, IMEI o serie", "autofocus": True}),
    )


class PosAddItemForm(forms.Form):
    """Agregar UNA línea al carrito. `unit_identifier` llega ya
    resuelto desde la búsqueda (`pos_services.search`) cuando el
    resultado fue una unidad concreta — el cajero también puede
    escribirlo/escanearlo directamente sin pasar por la búsqueda de
    texto (item 12 de la autorización de FASE 11)."""

    product_id = forms.IntegerField(widget=forms.HiddenInput)
    quantity = forms.DecimalField(
        label="Cantidad", max_digits=12, decimal_places=3, min_value=Decimal("0.001"), initial=Decimal("1")
    )
    unit_identifier = forms.CharField(label="IMEI / serie", max_length=100, required=False)
    discount_percent = forms.DecimalField(
        label="Descuento (%)", max_digits=5, decimal_places=2, required=False, min_value=0, max_value=100
    )
    discount_amount = forms.DecimalField(
        label="Descuento (monto)", max_digits=12, decimal_places=2, required=False, min_value=0
    )


class UpdateQuantityForm(forms.Form):
    """Editar la cantidad de UNA línea ya existente del carrito (FASE 7
    — Bloque A). Mismo campo `quantity` que `PosAddItemForm` — nunca
    permite 0 ni negativos."""

    quantity = forms.DecimalField(
        label="Cantidad", max_digits=12, decimal_places=3, min_value=Decimal("0.001")
    )


class CustomerSelectForm(forms.Form):
    customer = forms.ModelChoiceField(
        label="Cliente", queryset=Customer.objects.none(), required=False, empty_label="Consumidor final",
    )
    customer_search = forms.CharField(label="Buscar cliente", max_length=100, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["customer"].queryset = Customer.objects.filter(tenant=tenant, is_active=True)


class GlobalDiscountForm(forms.Form):
    global_discount_percent = forms.DecimalField(
        label="Descuento global (%)", max_digits=5, decimal_places=2, required=False, min_value=0, max_value=100
    )
    global_discount_amount = forms.DecimalField(
        label="Descuento global (monto)", max_digits=12, decimal_places=2, required=False, min_value=0
    )


class CheckoutPaymentForm(forms.Form):
    method = forms.ChoiceField(label="Método", choices=PaymentMethod.choices, required=False)
    amount = forms.DecimalField(label="Monto recibido", max_digits=12, decimal_places=2, required=False, min_value=Decimal("0.01"))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("method") and cleaned.get("amount") is None:
            raise forms.ValidationError("Indica el monto para este método de pago.")
        if cleaned.get("amount") is not None and not cleaned.get("method"):
            raise forms.ValidationError("Indica el método de pago.")
        return cleaned


CheckoutPaymentFormSet = forms.formset_factory(CheckoutPaymentForm, extra=2)


class OpenSessionForm(forms.Form):
    cash_register = forms.ModelChoiceField(label="Caja", queryset=CashRegister.objects.none())
    opening_amount = forms.DecimalField(label="Fondo inicial", max_digits=12, decimal_places=2, min_value=Decimal("0"))
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["cash_register"].queryset = CashRegister.objects.filter(
                tenant=tenant, status=CashRegister.Status.ACTIVE
            )


class CloseSessionForm(forms.Form):
    counted_cash = forms.DecimalField(label="Efectivo contado", max_digits=12, decimal_places=2, min_value=Decimal("0"))
    closing_notes = forms.CharField(label="Observaciones", max_length=255, required=False, widget=forms.Textarea(attrs={"rows": 2}))


class CashMovementForm(forms.Form):
    movement_type = forms.ChoiceField(label="Tipo", choices=[
        ("cash_in", "Entrada de efectivo"), ("cash_out", "Salida de efectivo"), ("withdrawal", "Retiro"),
    ])
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reason = forms.CharField(label="Motivo", max_length=255, required=False)


class CashRegisterForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=100)
    code = forms.CharField(label="Código", max_length=20)
    terminal = forms.CharField(label="Terminal", max_length=100, required=False)


class CustomerAdvanceForm(forms.Form):
    method = forms.ChoiceField(label="Método", choices=PaymentMethod.choices)
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reference = forms.CharField(label="Referencia", max_length=255, required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)


class CollectPaymentForm(forms.Form):
    method = forms.ChoiceField(label="Método", choices=PaymentMethod.choices)
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reference = forms.CharField(label="Referencia", max_length=255, required=False)


class ApplyCreditForm(forms.Form):
    amount = forms.DecimalField(label="Monto a aplicar", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class IssueCreditNoteForm(forms.Form):
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reason = forms.CharField(label="Motivo", max_length=255, required=False, widget=forms.Textarea(attrs={"rows": 2}))


class RefundForm(forms.Form):
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reason = forms.CharField(label="Motivo", max_length=255, required=False)
    mode = forms.ChoiceField(label="Modo", choices=[("cash", "Efectivo (sale de caja)"), ("credit", "Convertir en saldo a favor")])
