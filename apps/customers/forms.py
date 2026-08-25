from django import forms

from .file_validation import FORMATOS_PERMITIDOS_LEGIBLE, validar_archivo_adjunto
from .models import Customer, CustomerDocument, Supplier, SupplierDocument

_CAMPOS_COMERCIALES = ["payment_terms", "credit_days", "credit_enabled", "currency"]
_CAMPOS_CONTACTO = [
    "identification_type",
    "identification_number",
    "email",
    "phone",
    "address",
    "city",
    "state_province",
    "country",
    "notes",
]
_ETIQUETAS_COMUNES = {
    "party_type": "Tipo",
    "trade_name": "Nombre comercial",
    "identification_type": "Tipo de identificación",
    "identification_number": "Número de identificación",
    "email": "Correo electrónico",
    "phone": "Teléfono",
    "address": "Dirección",
    "city": "Ciudad",
    "state_province": "Provincia / estado",
    "country": "País",
    "notes": "Notas",
    "is_active": "Activo",
    "payment_terms": "Condiciones de pago",
    "credit_days": "Días de crédito",
    "credit_enabled": "Crédito habilitado",
    "currency": "Moneda",
}
_WIDGETS_COMUNES = {"notes": forms.Textarea(attrs={"rows": 3})}


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = (
            ["party_type", "first_name", "last_name", "company_name", "trade_name"]
            + _CAMPOS_CONTACTO
            + ["secondary_phone", "alternate_email", "postal_code"]
            + _CAMPOS_COMERCIALES
            + ["credit_limit", "commercial_notes", "is_active"]
        )
        labels = {
            **_ETIQUETAS_COMUNES,
            "first_name": "Nombre",
            "last_name": "Apellido",
            "company_name": "Empresa",
            "secondary_phone": "Teléfono secundario",
            "alternate_email": "Correo alternativo",
            "postal_code": "Código postal",
            "credit_limit": "Límite de crédito",
            "commercial_notes": "Notas comerciales",
        }
        widgets = {**_WIDGETS_COMUNES, "commercial_notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if not any(
            [
                cleaned_data.get("first_name", "").strip(),
                cleaned_data.get("last_name", "").strip(),
                cleaned_data.get("company_name", "").strip(),
                cleaned_data.get("trade_name", "").strip(),
            ]
        ):
            raise forms.ValidationError("Indica al menos un nombre, apellido, empresa o nombre comercial.")
        if cleaned_data.get("identification_number", "").strip() and not cleaned_data.get(
            "identification_type"
        ):
            raise forms.ValidationError(
                "Selecciona un tipo de identificación si vas a registrar un número."
            )
        return cleaned_data

    def clean_identification_number(self):
        numero = self.cleaned_data["identification_number"].strip()
        if not numero:
            return numero
        # `all_objects` + filtro explícito por tenant (no `objects`/TenantManager):
        # esta validación debe dar el mismo resultado se llame desde una
        # request HTTP real o desde cualquier otro contexto, igual que en
        # `apps.inventory.services` (ver su docstring).
        existentes = Customer.all_objects.filter(tenant=self.tenant, identification_number=numero)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError("Ya existe un cliente con este número de identificación.")
        return numero

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if not email:
            return email
        existentes = Customer.all_objects.filter(tenant=self.tenant, email__iexact=email)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError("Ya existe un cliente con este correo electrónico.")
        return email

    def clean_credit_limit(self):
        valor = self.cleaned_data["credit_limit"]
        if valor < 0:
            raise forms.ValidationError("El límite de crédito no puede ser negativo.")
        return valor


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = (
            ["party_type", "legal_name", "trade_name"]
            + _CAMPOS_CONTACTO
            + _CAMPOS_COMERCIALES
            + ["is_active"]
        )
        labels = {**_ETIQUETAS_COMUNES, "legal_name": "Razón social"}
        widgets = _WIDGETS_COMUNES

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if not any(
            [
                cleaned_data.get("legal_name", "").strip(),
                cleaned_data.get("trade_name", "").strip(),
            ]
        ):
            raise forms.ValidationError("Indica al menos una razón social o un nombre comercial.")
        if cleaned_data.get("identification_number", "").strip() and not cleaned_data.get(
            "identification_type"
        ):
            raise forms.ValidationError(
                "Selecciona un tipo de identificación si vas a registrar un número."
            )
        return cleaned_data

    def clean_identification_number(self):
        numero = self.cleaned_data["identification_number"].strip()
        if not numero:
            return numero
        existentes = Supplier.all_objects.filter(tenant=self.tenant, identification_number=numero)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError("Ya existe un proveedor con este número de identificación.")
        return numero

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if not email:
            return email
        existentes = Supplier.all_objects.filter(tenant=self.tenant, email__iexact=email)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError("Ya existe un proveedor con este correo electrónico.")
        return email


class _DocumentFormBase(forms.Form):
    """Base común a la subida de documentos de Cliente/Proveedor. La
    validación real de contenido (extensión + firma binaria + tamaño)
    vive en `file_validation.validar_archivo_adjunto` y se ejecuta aquí
    Y de nuevo en `services.py` antes de guardar (defensa en
    profundidad: el formulario nunca es la única barrera)."""

    file = forms.FileField(label="Archivo")
    category = forms.ChoiceField(label="Categoría")
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = self._document_model.category.field.choices
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


class CustomerDocumentForm(_DocumentFormBase):
    _document_model = CustomerDocument


class SupplierDocumentForm(_DocumentFormBase):
    _document_model = SupplierDocument
