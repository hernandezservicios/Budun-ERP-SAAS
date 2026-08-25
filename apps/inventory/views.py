"""
Vistas de Productos e Inventario (FASE 8).

Deliberadamente delgadas: toda la lógica de negocio vive en `services.py`
(consultas y operaciones de stock) y en `forms.py` (validaciones). Las
vistas solo verifican tenant/permiso, arman el formulario/queryset con
`request.tenant`, y traducen el resultado a una respuesta HTTP.

Todas heredan `TenantRequiredMixin` (FASE 3): exige un tenant activo
(403 si no lo hay) y, combinado con `LoginRequiredMixin`, redirige a
login si el usuario ni siquiera está autenticado. El queryset de cada
vista filtra explícitamente por `tenant=self.request.tenant` — nunca por
un `tenant_id` recibido del cliente — como defensa adicional además del
aislamiento automático que ya aplica `TenantManager`.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import (
    CategoryForm,
    InventoryUnitForm,
    InventoryUnitStatusForm,
    ProductForm,
    StockAdjustmentForm,
    StockInForm,
    StockOutForm,
)
from .models import Category, InventoryUnit, Product
from .services import InvalidInventoryOperation


# ---------------------------------------------------------------------
# Categorías
# ---------------------------------------------------------------------


class CategoryListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "inventory/category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        # annotate() en vez de category.products.count() en la plantilla:
        # una sola consulta agregada, no una por fila (evita N+1).
        return (
            Category.objects.filter(tenant=self.request.tenant)
            .annotate(product_count=Count("products", distinct=True))
            .order_by("order", "name")
        )


class CategoryCreateView(LoginRequiredMixin, TenantRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("inventory:category_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        messages.success(self.request, "Categoría creada correctamente.")
        return super().form_valid(form)


class CategoryUpdateView(LoginRequiredMixin, TenantRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("inventory:category_list")

    def get_queryset(self):
        return Category.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Categoría actualizada correctamente.")
        return super().form_valid(form)


class CategoryDeleteView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Solo POST. Si hay productos que referencian la categoría,
    `on_delete=PROTECT` impide el borrado — se informa con un mensaje
    claro en vez de un 500."""

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk, tenant=request.tenant)
        try:
            category.delete()
            messages.success(request, "Categoría eliminada correctamente.")
        except ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar «{category.name}»: tiene productos asociados. "
                "Desactívala en su lugar, o reasigna esos productos a otra categoría primero.",
            )
        return redirect("inventory:category_list")


# ---------------------------------------------------------------------
# Productos
# ---------------------------------------------------------------------


class ProductListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "inventory/product_list.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        return services.list_products_with_stock(
            self.request.tenant,
            search=self.request.GET.get("q", "").strip(),
            category_id=self.request.GET.get("categoria") or None,
            only_active=self.request.GET.get("mostrar_inactivos") != "1",
            only_low_stock=self.request.GET.get("stock_bajo") == "1",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = services.get_active_categories(self.request.tenant)
        context["query"] = self.request.GET.get("q", "")
        context["selected_category"] = self.request.GET.get("categoria", "")
        context["only_low_stock"] = self.request.GET.get("stock_bajo") == "1"
        context["show_inactive"] = self.request.GET.get("mostrar_inactivos") == "1"
        return context


class ProductDetailView(LoginRequiredMixin, TenantRequiredMixin, DetailView):
    template_name = "inventory/product_detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return Product.objects.filter(tenant=self.request.tenant).select_related("category")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_stock"] = services.get_current_stock(self.object)
        context["is_low_stock"] = context["current_stock"] <= self.object.min_stock
        context["is_serialized"] = (
            self.object.inventory_tracking_type == Product.TrackingType.SERIALIZED
        )
        if context["is_serialized"]:
            context["units"] = services.list_units_for_product(self.object)[:50]
            context["unit_status_form"] = InventoryUnitStatusForm()
        else:
            context["movements"] = services.get_product_movements(self.object, limit=15)
        return context


class ProductCreateView(LoginRequiredMixin, TenantRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "inventory/product_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        messages.success(self.request, "Producto creado correctamente.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("inventory:product_detail", args=[self.object.pk])


class ProductUpdateView(LoginRequiredMixin, TenantRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "inventory/product_form.html"

    def get_queryset(self):
        return Product.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Producto actualizado correctamente.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("inventory:product_detail", args=[self.object.pk])


class ProductDeactivateView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Solo POST. "Eliminar" un producto es desactivarlo (`is_active =
    False`), nunca un borrado físico: preserva el historial de
    movimientos, que nunca debe perder su referencia (`on_delete=PROTECT`
    en `StockMovement.product`)."""

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, tenant=request.tenant)
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        messages.success(request, f"«{product.name}» se desactivó correctamente.")
        return redirect("inventory:product_list")


# ---------------------------------------------------------------------
# Movimientos de stock
# ---------------------------------------------------------------------


class _StockMovementView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Base común para entrada/salida/ajuste: solo cambia el formulario y
    qué función de `services` se llama. Solo aplica a productos por
    CANTIDAD — un producto SERIALIZADO se gestiona con unidades
    individuales (ver `UnitCreateView`/`UnitStatusChangeView`)."""

    form_class = None
    template_name = "inventory/stock_movement_form.html"
    titulo = ""

    def get_product(self, request, pk):
        return get_object_or_404(Product, pk=pk, tenant=request.tenant)

    def get(self, request, pk):
        product = self.get_product(request, pk)
        if product.inventory_tracking_type == Product.TrackingType.SERIALIZED:
            messages.error(
                request,
                f"«{product.name}» es un producto serializado: gestiona sus unidades "
                "individuales (IMEI/serie) desde su ficha, no movimientos de cantidad.",
            )
            return redirect("inventory:product_detail", pk=product.pk)
        form = self.form_class()
        return render(
            request,
            self.template_name,
            {"product": product, "form": form, "titulo": self.titulo},
        )

    def post(self, request, pk):
        product = self.get_product(request, pk)
        form = self.form_class(request.POST)
        if form.is_valid():
            try:
                self.registrar(product, form, request)
            except InvalidInventoryOperation as error:
                messages.error(request, "; ".join(error.messages) if hasattr(error, "messages") else str(error))
            else:
                messages.success(request, "Movimiento de inventario registrado correctamente.")
                return redirect("inventory:product_detail", pk=product.pk)
        return render(
            request,
            self.template_name,
            {"product": product, "form": form, "titulo": self.titulo},
        )

    def registrar(self, product, form, request):
        raise NotImplementedError


class StockInView(_StockMovementView):
    form_class = StockInForm
    titulo = "Registrar entrada de stock"

    def registrar(self, product, form, request):
        services.register_stock_in(
            product=product,
            quantity=form.cleaned_data["quantity"],
            user=request.user,
            notes=form.cleaned_data["notes"],
        )


class StockOutView(_StockMovementView):
    form_class = StockOutForm
    titulo = "Registrar salida de stock"

    def registrar(self, product, form, request):
        services.register_stock_out(
            product=product,
            quantity=form.cleaned_data["quantity"],
            user=request.user,
            notes=form.cleaned_data["notes"],
        )


class StockAdjustmentView(_StockMovementView):
    form_class = StockAdjustmentForm
    titulo = "Ajustar stock"

    def registrar(self, product, form, request):
        services.register_stock_adjustment(
            product=product,
            new_stock=form.cleaned_data["new_stock"],
            user=request.user,
            notes=form.cleaned_data["notes"],
        )


# ---------------------------------------------------------------------
# Unidades de inventario (productos SERIALIZADOS)
# ---------------------------------------------------------------------


class UnitCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Alta de una unidad individual nueva (IMEI/serie) para un producto
    SERIALIZADO — equivalente a `StockInView` para productos por
    cantidad. Solo aplica a productos SERIALIZADOS."""

    template_name = "inventory/unit_form.html"

    def get_product(self, request, pk):
        return get_object_or_404(Product, pk=pk, tenant=request.tenant)

    def get(self, request, pk):
        product = self.get_product(request, pk)
        if product.inventory_tracking_type != Product.TrackingType.SERIALIZED:
            messages.error(
                request,
                f"«{product.name}» es un producto por cantidad: registra su stock con "
                "entrada/salida/ajuste, no con unidades individuales.",
            )
            return redirect("inventory:product_detail", pk=product.pk)
        form = InventoryUnitForm()
        return render(request, self.template_name, {"product": product, "form": form})

    def post(self, request, pk):
        product = self.get_product(request, pk)
        form = InventoryUnitForm(request.POST)
        if form.is_valid():
            try:
                services.register_serialized_unit(
                    product=product,
                    user=request.user,
                    serial=form.cleaned_data["serial"],
                    imei_1=form.cleaned_data["imei_1"],
                    imei_2=form.cleaned_data["imei_2"],
                    unit_cost=form.cleaned_data["unit_cost"],
                    entry_date=form.cleaned_data["entry_date"] or None,
                    purchase_origin=form.cleaned_data["purchase_origin"],
                    notes=form.cleaned_data["notes"],
                )
            except InvalidInventoryOperation as error:
                messages.error(request, "; ".join(error.messages) if hasattr(error, "messages") else str(error))
            else:
                messages.success(request, "Unidad registrada correctamente.")
                return redirect("inventory:product_detail", pk=product.pk)
        return render(request, self.template_name, {"product": product, "form": form})


class UnitStatusChangeView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Cambia el estado de una unidad individual (solo POST), validando
    la máquina de estados en `services.transition_unit_status`. La
    unidad se busca siempre filtrando por `tenant=request.tenant` — un
    `pk` de otro tenant nunca es visible ni modificable (404, no 403, para
    no confirmar siquiera que existe)."""

    def post(self, request, product_pk, unit_pk):
        product = get_object_or_404(Product, pk=product_pk, tenant=request.tenant)
        unit = get_object_or_404(InventoryUnit, pk=unit_pk, tenant=request.tenant, product=product)
        form = InventoryUnitStatusForm(request.POST)
        if form.is_valid():
            try:
                services.transition_unit_status(
                    unit=unit,
                    new_status=form.cleaned_data["new_status"],
                    user=request.user,
                    notes=form.cleaned_data["notes"],
                )
            except InvalidInventoryOperation as error:
                messages.error(request, "; ".join(error.messages) if hasattr(error, "messages") else str(error))
            else:
                messages.success(request, "Estado de la unidad actualizado correctamente.")
        else:
            messages.error(request, "Selecciona un estado válido.")
        return redirect("inventory:product_detail", pk=product.pk)
