"""Formularios de Compras (FASE 12). Formularios planos (no `ModelForm`):
el guardado real siempre lo hace `services.py`, nunca `form.save()` —
mismo criterio que `apps.sales.forms`/`apps.pos.forms`."""

from decimal import Decimal

from django import forms

from apps.customers.file_validation import FORMATOS_PERMITIDOS_LEGIBLE, validar_archivo_adjunto
from apps.customers.models import DocumentCategory, Supplier
from apps.inventory.models import Product

from .models import PurchaseDocumentAttachment


class PurchaseOrderHeaderForm(forms.Form):
    supplier = forms.ModelChoiceField(label="Proveedor", queryset=Supplier.objects.none())
    expected_date = forms.DateField(label="Fecha esperada de entrega", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    currency = forms.CharField(label="Moneda", max_length=3, initial="USD", required=False)
    notes = forms.CharField(label="Notas", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    terms = forms.CharField(label="Términos y condiciones", widget=forms.Textarea(attrs={"rows": 2}), required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["supplier"].queryset = Supplier.objects.filter(tenant=tenant, is_active=True)


class PurchaseOrderHeaderEditForm(forms.Form):
    """Edición de cabecera de una orden en BORRADOR (el proveedor no se
    puede cambiar una vez creada — crea una orden nueva en su lugar)."""

    expected_date = forms.DateField(label="Fecha esperada de entrega", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    currency = forms.CharField(label="Moneda", max_length=3, required=False)
    notes = forms.CharField(label="Notas", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    terms = forms.CharField(label="Términos y condiciones", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    global_discount_percent = forms.DecimalField(label="Descuento global (%)", max_digits=5, decimal_places=2, required=False, min_value=0, max_value=100)
    global_discount_amount = forms.DecimalField(label="Descuento global (monto)", max_digits=12, decimal_places=2, required=False, min_value=0)
    freight_cost = forms.DecimalField(label="Costo de flete", max_digits=12, decimal_places=2, required=False, min_value=0)
    insurance_cost = forms.DecimalField(label="Costo de seguro", max_digits=12, decimal_places=2, required=False, min_value=0)
    other_costs = forms.DecimalField(label="Otros costos atribuibles", max_digits=12, decimal_places=2, required=False, min_value=0)


class PurchaseOrderItemForm(forms.Form):
    product = forms.ModelChoiceField(label="Producto", queryset=Product.objects.none())
    quantity = forms.DecimalField(label="Cantidad", max_digits=12, decimal_places=3, initial=Decimal("1"), min_value=Decimal("0.001"))
    unit_cost = forms.DecimalField(
        label="Costo unitario (opcional, usa el costo de compra del producto si se deja vacío)",
        max_digits=12, decimal_places=2, required=False, min_value=0,
    )
    discount_percent = forms.DecimalField(label="Descuento (%)", max_digits=5, decimal_places=2, required=False, min_value=0, max_value=100, initial=Decimal("0"))
    discount_amount = forms.DecimalField(label="Descuento (monto)", max_digits=12, decimal_places=2, required=False, min_value=0, initial=Decimal("0"))
    tax_rate = forms.DecimalField(label="Tasa de impuesto (%)", max_digits=5, decimal_places=2, required=False, min_value=0)

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["product"].queryset = Product.objects.filter(tenant=tenant, is_active=True)


class ReceiveQuantityForm(forms.Form):
    quantity_received = forms.DecimalField(label="Cantidad a recibir", max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit_cost = forms.DecimalField(label="Costo unitario real (opcional)", max_digits=12, decimal_places=2, required=False, min_value=0)
    receipt_date = forms.DateField(label="Fecha de recepción", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(label="Notas", max_length=255, required=False)


class ReceiveSerializedUnitForm(forms.Form):
    serial = forms.CharField(label="Número de serie", max_length=100, required=False)
    imei_1 = forms.CharField(label="IMEI 1", max_length=100, required=False)
    imei_2 = forms.CharField(label="IMEI 2", max_length=100, required=False)
    unit_cost = forms.DecimalField(label="Costo unitario", max_digits=12, decimal_places=2, required=False, min_value=0)

    def has_any_identifier(self):
        return bool((self.cleaned_data.get("serial") or "").strip() or (self.cleaned_data.get("imei_1") or "").strip() or (self.cleaned_data.get("imei_2") or "").strip())


ReceiveSerializedFormSet = forms.formset_factory(ReceiveSerializedUnitForm, extra=10)


class SupplierInvoiceHeaderForm(forms.Form):
    supplier_invoice_number = forms.CharField(label="Número de factura del proveedor", max_length=50)
    issue_date = forms.DateField(label="Fecha de emisión", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    due_date = forms.DateField(label="Fecha de vencimiento", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    currency = forms.CharField(label="Moneda", max_length=3, required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)


class SupplierInvoiceItemForm(forms.Form):
    description = forms.CharField(label="Descripción", max_length=255)
    quantity = forms.DecimalField(label="Cantidad", max_digits=12, decimal_places=3, initial=Decimal("1"), min_value=Decimal("0.001"))
    unit_cost = forms.DecimalField(label="Costo unitario", max_digits=12, decimal_places=2, min_value=0)
    discount_percent = forms.DecimalField(label="Descuento (%)", max_digits=5, decimal_places=2, required=False, min_value=0, max_value=100)
    discount_amount = forms.DecimalField(label="Descuento (monto)", max_digits=12, decimal_places=2, required=False, min_value=0)
    tax_rate = forms.DecimalField(label="Tasa de impuesto (%)", max_digits=5, decimal_places=2, required=False, min_value=0)


class SupplierPaymentForm(forms.Form):
    method = forms.ChoiceField(label="Método")
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reference = forms.CharField(label="Referencia", max_length=255, required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.sales.models import PaymentMethod
        self.fields["method"].choices = PaymentMethod.choices


class SupplierAdvanceForm(SupplierPaymentForm):
    pass


class ApplySupplierAdvanceForm(forms.Form):
    amount = forms.DecimalField(label="Monto a aplicar", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class SupplierReturnItemSelectionForm(forms.Form):
    """Una fila del formulario de devolución a proveedor: casilla para
    incluir la línea de recepción, cantidad a devolver (recepciones por
    cantidad; ignorada para serializadas, donde la unidad completa se
    devuelve de una vez)."""

    receipt_item_id = forms.IntegerField(widget=forms.HiddenInput)
    include = forms.BooleanField(label="Devolver", required=False)
    quantity_returned = forms.DecimalField(label="Cantidad a devolver", max_digits=12, decimal_places=3, required=False, min_value=Decimal("0.001"))


SupplierReturnItemFormSet = forms.formset_factory(SupplierReturnItemSelectionForm, extra=0)


class SupplierReturnForm(forms.Form):
    reason = forms.CharField(label="Motivo", max_length=255, required=False)


class PurchaseAttachmentForm(forms.Form):
    """Adjunto de Orden de Compra/Recepción/Factura de Proveedor/
    Devolución a proveedor — reutiliza literalmente la validación de
    FASE 9, nunca crea un segundo sistema de archivos."""

    file = forms.FileField(label="Archivo")
    category = forms.ChoiceField(label="Categoría", choices=DocumentCategory.choices)
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
