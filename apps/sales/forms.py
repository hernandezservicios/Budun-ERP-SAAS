from decimal import Decimal

from django import forms
from django.db.models import Q

from apps.customers.file_validation import FORMATOS_PERMITIDOS_LEGIBLE, validar_archivo_adjunto
from apps.customers.models import Customer, DocumentCategory
from apps.customers.models import PaymentTerms as CustomerPaymentTerms
from apps.inventory.models import InventoryUnit, Product

from .models import PaymentMethod


class _CommercialDocumentHeaderForm(forms.Form):
    """Base común a la cabecera de Cotización/Proforma/Venta. Un
    formulario plano (no `ModelForm`): el guardado real lo hace
    `services.py` (que también genera el número, ver `generate_document_number`),
    nunca `form.save()`."""

    customer = forms.ModelChoiceField(label="Cliente", queryset=Customer.objects.none(), required=False, empty_label="Consumidor final")
    currency = forms.CharField(label="Moneda", max_length=3, initial="USD")
    payment_terms = forms.ChoiceField(label="Condiciones de pago", choices=CustomerPaymentTerms.choices, initial=CustomerPaymentTerms.CONTADO)
    notes = forms.CharField(label="Notas", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    terms = forms.CharField(label="Términos y condiciones", widget=forms.Textarea(attrs={"rows": 2}), required=False)
    global_discount_percent = forms.DecimalField(label="Descuento global (%)", max_digits=5, decimal_places=2, initial=Decimal("0"), min_value=0, max_value=100, required=False)
    global_discount_amount = forms.DecimalField(label="Descuento global (monto)", max_digits=12, decimal_places=2, initial=Decimal("0"), min_value=0, required=False)

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["customer"].queryset = Customer.objects.filter(tenant=tenant, is_active=True)


class QuotationHeaderForm(_CommercialDocumentHeaderForm):
    issue_date = forms.DateField(label="Fecha de emisión", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    expiry_date = forms.DateField(label="Fecha de vencimiento", required=False, widget=forms.DateInput(attrs={"type": "date"}))


class ProformaHeaderForm(_CommercialDocumentHeaderForm):
    issue_date = forms.DateField(label="Fecha de emisión", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    expiry_date = forms.DateField(label="Fecha de vencimiento", required=False, widget=forms.DateInput(attrs={"type": "date"}))


class SaleHeaderForm(_CommercialDocumentHeaderForm):
    issue_date = forms.DateField(label="Fecha", required=False, widget=forms.DateInput(attrs={"type": "date"}))


class _DocumentItemForm(forms.Form):
    """Formulario para agregar UNA línea a Cotización/Proforma/Venta.
    `inventory_unit` solo aplica a productos SERIALIZED — se identifica
    por su serial/IMEI en texto libre (evita depender de JavaScript para
    filtrar un desplegable por producto; se resuelve server-side)."""

    product = forms.ModelChoiceField(label="Producto", queryset=Product.objects.none())
    quantity = forms.DecimalField(label="Cantidad", max_digits=12, decimal_places=3, initial=Decimal("1"), min_value=Decimal("0.001"))
    unit_identifier = forms.CharField(
        label="IMEI / serie (solo productos serializados)", max_length=100, required=False,
        help_text="Déjalo vacío para productos por cantidad.",
    )
    unit_price = forms.DecimalField(label="Precio unitario (opcional, usa el del producto si se deja vacío)", max_digits=12, decimal_places=2, required=False, min_value=0)
    discount_percent = forms.DecimalField(label="Descuento (%)", max_digits=5, decimal_places=2, required=False, min_value=0, max_value=100, initial=Decimal("0"))
    discount_amount = forms.DecimalField(label="Descuento (monto)", max_digits=12, decimal_places=2, required=False, min_value=0, initial=Decimal("0"))

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["product"].queryset = Product.objects.filter(tenant=tenant, is_active=True)

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        identificador = (cleaned_data.get("unit_identifier") or "").strip()
        if product and product.inventory_tracking_type == Product.TrackingType.SERIALIZED:
            if not identificador:
                raise forms.ValidationError("Indica el IMEI/serie de la unidad para un producto serializado.")
            unidad = InventoryUnit.all_objects.filter(tenant=self.tenant).filter(
                Q(serial=identificador) | Q(imei_1=identificador) | Q(imei_2=identificador)
            ).first()
            if not unidad:
                raise forms.ValidationError("No se encontró ninguna unidad con ese IMEI/serie.")
            cleaned_data["inventory_unit"] = unidad
        else:
            cleaned_data["inventory_unit"] = None
        return cleaned_data


class QuotationItemForm(_DocumentItemForm):
    pass


class ProformaItemForm(_DocumentItemForm):
    pass


class SaleItemForm(_DocumentItemForm):
    pass


class PaymentForm(forms.Form):
    method = forms.ChoiceField(label="Método", choices=PaymentMethod.choices)
    amount = forms.DecimalField(label="Monto", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reference = forms.CharField(label="Referencia", max_length=255, required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)


class ReturnItemSelectionForm(forms.Form):
    """Una fila del formulario de devolución: casilla para incluir la
    línea, cantidad a devolver (productos por cantidad; ignorada para
    serializados, donde la unidad completa se devuelve de una vez)."""

    sale_item_id = forms.IntegerField(widget=forms.HiddenInput)
    include = forms.BooleanField(label="Devolver", required=False)
    quantity_returned = forms.DecimalField(label="Cantidad a devolver", max_digits=12, decimal_places=3, required=False, min_value=Decimal("0.001"))


ReturnItemFormSet = forms.formset_factory(ReturnItemSelectionForm, extra=0)


class ReturnForm(forms.Form):
    reason = forms.CharField(label="Motivo", max_length=255, required=False, widget=forms.Textarea(attrs={"rows": 2}))


class SalesAttachmentForm(forms.Form):
    """Adjunto de Cotización/Proforma/Venta — reutiliza literalmente la
    validación de FASE 9 (`apps.customers.file_validation`), no crea un
    segundo sistema de archivos."""

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
