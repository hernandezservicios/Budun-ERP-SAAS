from django import forms

from .models import Category, InventoryUnit, Product, StockMovement


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
            "inventory_tracking_type",
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
            "inventory_tracking_type": "Tipo de seguimiento de inventario",
            "purchase_price": "Precio de compra",
            "sale_price": "Precio de venta",
            "tax_rate": "Impuesto (%)",
            "min_stock": "Stock mínimo",
            "is_active": "Activo",
        }
        help_texts = {
            "inventory_tracking_type": (
                "Por cantidad: el stock se controla con entradas/salidas/ajustes. "
                "Serializado: cada unidad física se registra con su propio IMEI/número "
                "de serie (no aplica «stock mínimo» de la misma forma; puedes dejarlo en 0)."
            ),
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields["category"].queryset = Category.objects.filter(tenant=tenant, is_active=True)
        # El campo es opcional a nivel de modelo (`blank=True`, tiene un
        # default sensato) pero en el formulario debe verse como una
        # elección real, sin la opción en blanco "---------" que Django
        # agrega automáticamente para un campo no requerido.
        self.fields["inventory_tracking_type"].choices = Product.TrackingType.choices
        if not self.instance.pk:
            self.fields["inventory_tracking_type"].initial = Product.TrackingType.QUANTITY

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

    def clean_inventory_tracking_type(self):
        # Se usa `all_objects` (no la relación inversa por defecto, que
        # pasaría por `TenantManager`/ContextVar): esta validación debe
        # dar el mismo resultado se llame desde una request HTTP real o
        # desde cualquier otro contexto (p. ej. un test o una tarea en
        # segundo plano), igual que el resto de `services.py`.
        # El campo es opcional en el formulario (`blank=True` en el modelo,
        # ver models.py): si se omite, se conserva el tipo actual (al
        # editar) o se usa el default del modelo, `QUANTITY` (al crear) —
        # nunca se guarda una cadena vacía.
        nuevo_tipo = self.cleaned_data.get("inventory_tracking_type") or (
            self.instance.inventory_tracking_type if self.instance.pk else Product.TrackingType.QUANTITY
        )
        if self.instance.pk and self.instance.inventory_tracking_type != nuevo_tipo:
            tiene_historial = (
                StockMovement.all_objects.filter(product=self.instance).exists()
                or InventoryUnit.all_objects.filter(product=self.instance).exists()
            )
            if tiene_historial:
                raise forms.ValidationError(
                    "No se puede cambiar el tipo de seguimiento de un producto que ya tiene "
                    "movimientos de stock o unidades registradas: crearía dos fuentes de "
                    "verdad inconsistentes. Crea un producto nuevo con el otro tipo si lo necesitas."
                )
        return nuevo_tipo


class StockInForm(forms.Form):
    quantity = forms.DecimalField(label="Cantidad", max_digits=12, decimal_places=3, min_value=0.001)
    notes = forms.CharField(label="Motivo / notas", max_length=255, required=False)


class StockOutForm(forms.Form):
    quantity = forms.DecimalField(label="Cantidad", max_digits=12, decimal_places=3, min_value=0.001)
    notes = forms.CharField(label="Motivo / notas", max_length=255, required=False)


class StockAdjustmentForm(forms.Form):
    new_stock = forms.DecimalField(label="Nuevo stock", max_digits=12, decimal_places=3, min_value=0)
    notes = forms.CharField(label="Motivo / notas", max_length=255, required=False)


class InventoryUnitForm(forms.Form):
    """Alta de una unidad individual nueva para un producto SERIALIZADO
    (equivalente a una «entrada de stock» para productos por cantidad).
    La validación de unicidad real (serial/IMEI únicos por tenant, IMEI 1
    != IMEI 2, al menos un identificador) la hace `services.register_serialized_unit`
    contra la base de datos — aquí solo se homogeniza el texto de entrada."""

    serial = forms.CharField(label="Número de serie", max_length=100, required=False)
    imei_1 = forms.CharField(label="IMEI 1", max_length=20, required=False)
    imei_2 = forms.CharField(label="IMEI 2", max_length=20, required=False)
    unit_cost = forms.DecimalField(label="Costo unitario", max_digits=12, decimal_places=2, min_value=0)
    entry_date = forms.DateField(
        label="Fecha de ingreso", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    purchase_origin = forms.CharField(label="Origen de compra", max_length=255, required=False)
    notes = forms.CharField(label="Notas", max_length=255, required=False)

    def clean(self):
        cleaned_data = super().clean()
        serial = cleaned_data.get("serial", "").strip()
        imei_1 = cleaned_data.get("imei_1", "").strip()
        imei_2 = cleaned_data.get("imei_2", "").strip()
        if not (serial or imei_1 or imei_2):
            raise forms.ValidationError(
                "Debes indicar al menos un identificador: número de serie, IMEI 1 o IMEI 2."
            )
        if imei_1 and imei_2 and imei_1 == imei_2:
            raise forms.ValidationError("IMEI 1 e IMEI 2 no pueden ser iguales.")
        cleaned_data["serial"] = serial
        cleaned_data["imei_1"] = imei_1
        cleaned_data["imei_2"] = imei_2
        return cleaned_data


class InventoryUnitStatusForm(forms.Form):
    """Cambio de estado de una unidad. Las opciones válidas dependen del
    estado actual de la unidad (ver `services.ALLOWED_UNIT_TRANSITIONS`);
    el formulario ofrece todos los estados y deja que `services.transition_unit_status`
    rechace la transición si no está permitida (nunca confía únicamente
    en la validación del cliente)."""

    new_status = forms.ChoiceField(label="Nuevo estado", choices=InventoryUnit.Status.choices)
    notes = forms.CharField(label="Notas", max_length=255, required=False)
