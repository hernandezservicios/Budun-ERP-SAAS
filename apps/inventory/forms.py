from django import forms

from .models import Category, Product


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "order", "is_active"]
        labels = {
            "name": "Nombre",
            "order": "Orden",
            "is_active": "Activa",
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        existentes = Category.objects.filter(tenant=self.tenant, name__iexact=name)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError("Ya existe una categoría con este nombre.")
        return name


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "sku",
            "barcode",
            "category",
            "description",
            "purchase_price",
            "sale_price",
            "tax_rate",
            "min_stock",
            "is_active",
        ]
        labels = {
            "name": "Nombre",
            "sku": "SKU",
            "barcode": "Código de barras",
            "category": "Categoría",
            "description": "Descripción",
            "purchase_price": "Precio de compra",
            "sale_price": "Precio de venta",
            "tax_rate": "Impuesto (%)",
            "min_stock": "Stock mínimo",
            "is_active": "Activo",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["category"].queryset = Category.objects.filter(tenant=tenant, is_active=True)

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip()
        existentes = Product.objects.filter(tenant=self.tenant, sku__iexact=sku)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError("Ya existe un producto con este SKU.")
        return sku

    def clean_barcode(self):
        barcode = self.cleaned_data["barcode"].strip()
        if not barcode:
            return barcode
        existentes = Product.objects.filter(tenant=self.tenant, barcode=barcode)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError("Ya existe un producto con este código de barras.")
        return barcode

    def clean_purchase_price(self):
        value = self.cleaned_data["purchase_price"]
        if value < 0:
            raise forms.ValidationError("El precio de compra no puede ser negativo.")
        return value

    def clean_sale_price(self):
        value = self.cleaned_data["sale_price"]
        if value < 0:
            raise forms.ValidationError("El precio de venta no puede ser negativo.")
        return value

    def clean_min_stock(self):
        value = self.cleaned_data["min_stock"]
        if value < 0:
            raise forms.ValidationError("El stock mínimo no puede ser negativo.")
        return value


class StockInForm(forms.Form):
    quantity = forms.DecimalField(label="Cantidad", max_digits=12, decimal_places=3, min_value=0.001)
    notes = forms.CharField(label="Motivo / notas", max_length=255, required=False)


class StockOutForm(forms.Form):
    quantity = forms.DecimalField(label="Cantidad", max_digits=12, decimal_places=3, min_value=0.001)
    notes = forms.CharField(label="Motivo / notas", max_length=255, required=False)


class StockAdjustmentForm(forms.Form):
    new_stock = forms.DecimalField(label="Nuevo stock", max_digits=12, decimal_places=3, min_value=0)
    notes = forms.CharField(label="Motivo / notas", max_length=255, required=False)
