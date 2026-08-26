"""
Vistas de Clientes y Proveedores (FASE 9).

Deliberadamente delgadas, mismo patrón que `apps.inventory.views`: la
lógica de negocio (consultas reutilizables, documentos, auditoría) vive
en `services.py`, la validación en `forms.py`. Todas heredan
`TenantRequiredMixin` (FASE 3) + `LoginRequiredMixin`, y cada queryset
filtra explícitamente por `tenant=self.request.tenant` — nunca por un
`tenant_id` recibido del cliente — como defensa adicional además del
aislamiento automático que ya aplica `TenantManager`.

`Customer` y `Supplier` comparten exactamente el mismo patrón de CRUD/
desactivación/documentos, así que las vistas base (`_ContactListView`,
`_ContactCreateView`, etc.) están parametrizadas por modelo/formulario/
servicio y cada subclase concreta solo fija esos atributos — evita
duplicar la misma lógica dos veces. La descarga de documentos NUNCA se
sirve como archivo estático público (ver `MEDIA_URL` en settings): esta
vista es la única forma de obtener el contenido, y verifica tenant +
pertenencia al cliente/proveedor antes de servir un solo byte.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.permissions.services import PermissionRequiredMixin
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .file_validation import nombre_original_seguro
from .forms import CustomerDocumentForm, CustomerForm, SupplierDocumentForm, SupplierForm
from .models import ActivityLog, Customer, CustomerDocument, Supplier, SupplierDocument

ORDENAMIENTOS_VALIDOS = {"nombre", "-nombre", "reciente", "antiguo"}


def _parametros_listado(request):
    return {
        "search": request.GET.get("q", "").strip(),
        "only_active": request.GET.get("mostrar_inactivos") != "1",
        "order": request.GET.get("orden") if request.GET.get("orden") in ORDENAMIENTOS_VALIDOS else "nombre",
    }


# ---------------------------------------------------------------------
# Base compartida (Cliente y Proveedor comparten el mismo patrón CRUD)
# ---------------------------------------------------------------------


class _ContactListView(LoginRequiredMixin, TenantRequiredMixin, PermissionRequiredMixin, ListView):
    paginate_by = 20
    list_service = None  # fijado por subclase
    permission_code = None  # "customers.view" | "suppliers.view", fijado por subclase

    def get_queryset(self):
        parametros = _parametros_listado(self.request)
        return self.list_service(self.request.tenant, **parametros)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        parametros = _parametros_listado(self.request)
        context["query"] = parametros["search"]
        context["show_inactive"] = not parametros["only_active"]
        context["orden"] = parametros["order"]
        return context


class _ContactDetailView(LoginRequiredMixin, TenantRequiredMixin, PermissionRequiredMixin, DetailView):
    model = None  # fijado por subclase
    entity_type = ""  # "customer" | "supplier"
    document_model = None
    document_form_class = None
    permission_code = None  # "customers.view" | "suppliers.view", fijado por subclase

    def get_queryset(self):
        return self.model.objects.filter(tenant=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["documents"] = self.document_model.objects.filter(
            **{self.entity_type: self.object}
        ).select_related("uploaded_by")
        context["document_form"] = self.document_form_class()
        context["activity_log"] = services.get_activity_log(
            self.request.tenant, entity_type=self.entity_type, entity_id=self.object.pk
        )
        return context


class _ContactCreateView(LoginRequiredMixin, TenantRequiredMixin, PermissionRequiredMixin, CreateView):
    model = None
    form_class = None
    entity_type = ""
    entity_label_singular = ""
    url_namespace_detail = ""
    permission_code = None  # "customers.create" | "suppliers.create", fijado por subclase

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        form.instance.tenant = self.request.tenant
        respuesta = super().form_valid(form)
        services.log_activity(
            self.request.tenant,
            entity_type=self.entity_type,
            entity_id=self.object.pk,
            entity_label=self.object.display_name,
            action=ActivityLog.Action.CREATED,
            user=self.request.user,
        )
        messages.success(self.request, f"{self.entity_label_singular} creado correctamente.")
        return respuesta

    def get_success_url(self):
        return reverse(self.url_namespace_detail, args=[self.object.pk])


class _ContactUpdateView(LoginRequiredMixin, TenantRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = None
    form_class = None
    entity_type = ""
    entity_label_singular = ""
    url_namespace_detail = ""
    permission_code = None  # "customers.update" | "suppliers.update", fijado por subclase

    def get_queryset(self):
        return self.model.objects.filter(tenant=self.request.tenant)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        services.log_activity(
            self.request.tenant,
            entity_type=self.entity_type,
            entity_id=self.object.pk,
            entity_label=self.object.display_name,
            action=ActivityLog.Action.UPDATED,
            user=self.request.user,
        )
        messages.success(self.request, f"{self.entity_label_singular} actualizado correctamente.")
        return respuesta

    def get_success_url(self):
        return reverse(self.url_namespace_detail, args=[self.object.pk])


class _ContactStatusView(LoginRequiredMixin, TenantRequiredMixin, PermissionRequiredMixin, View):
    """Solo POST: desactiva o reactiva (`?accion=reactivar`), nunca un
    borrado físico — preserva el historial/documentos/auditoría."""

    model = None
    entity_type = ""
    url_namespace_detail = ""
    permission_code = None  # "customers.delete" | "suppliers.delete", fijado por subclase

    def post(self, request, pk):
        instance = get_object_or_404(self.model, pk=pk, tenant=request.tenant)
        reactivar = request.POST.get("accion") == "reactivar"
        instance.is_active = reactivar
        instance.save(update_fields=["is_active", "updated_at"])
        services.log_activity(
            request.tenant,
            entity_type=self.entity_type,
            entity_id=instance.pk,
            entity_label=instance.display_name,
            action=ActivityLog.Action.REACTIVATED if reactivar else ActivityLog.Action.DEACTIVATED,
            user=request.user,
        )
        verbo = "reactivó" if reactivar else "desactivó"
        messages.success(request, f"«{instance.display_name}» se {verbo} correctamente.")
        return redirect(self.url_namespace_detail, pk=instance.pk)


class _ContactDocumentUploadView(LoginRequiredMixin, TenantRequiredMixin, PermissionRequiredMixin, View):
    """Solo POST desde el detalle del cliente/proveedor. La validación
    real de contenido ocurre dos veces por diseño (formulario Y
    servicio): nunca depende de una sola barrera."""

    parent_model = None
    form_class = None
    entity_type = ""
    register_service = None  # staticmethod, fijado por subclase
    url_namespace_detail = ""
    # Subir/eliminar un documento es parte de "editar" el cliente/
    # proveedor (no hay un código de catálogo dedicado a documentos):
    # mismo permiso que `_ContactUpdateView`.
    permission_code = None  # "customers.update" | "suppliers.update", fijado por subclase

    def post(self, request, pk):
        parent = get_object_or_404(self.parent_model, pk=pk, tenant=request.tenant)
        form = self.form_class(request.POST, request.FILES)
        if form.is_valid():
            try:
                self.register_service(
                    **{self.entity_type: parent},
                    archivo=form.cleaned_data["file"],
                    category=form.cleaned_data["category"],
                    user=request.user,
                    notes=form.cleaned_data["notes"],
                )
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages) if hasattr(error, "messages") else str(error))
            else:
                messages.success(request, "Documento subido correctamente.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
        return redirect(self.url_namespace_detail, pk=parent.pk)


class _ContactDocumentDeleteView(LoginRequiredMixin, TenantRequiredMixin, PermissionRequiredMixin, View):
    parent_model = None
    document_model = None
    entity_type = ""
    delete_service = None
    url_namespace_detail = ""
    permission_code = None  # "customers.update" | "suppliers.update", fijado por subclase

    def post(self, request, pk, document_pk):
        parent = get_object_or_404(self.parent_model, pk=pk, tenant=request.tenant)
        documento = get_object_or_404(
            self.document_model, pk=document_pk, tenant=request.tenant, **{self.entity_type: parent}
        )
        self.delete_service(documento=documento, user=request.user)
        messages.success(request, "Documento eliminado correctamente.")
        return redirect(self.url_namespace_detail, pk=parent.pk)


class _ContactDocumentDownloadView(LoginRequiredMixin, TenantRequiredMixin, PermissionRequiredMixin, View):
    """Única vía de descarga: verifica tenant + pertenencia al cliente/
    proveedor antes de abrir el archivo (un ID de otro tenant o de otro
    cliente/proveedor da 404, nunca el contenido)."""

    parent_model = None
    document_model = None
    entity_type = ""
    permission_code = None  # "customers.view" | "suppliers.view", fijado por subclase

    def get(self, request, pk, document_pk):
        parent = get_object_or_404(self.parent_model, pk=pk, tenant=request.tenant)
        documento = get_object_or_404(
            self.document_model, pk=document_pk, tenant=request.tenant, **{self.entity_type: parent}
        )
        services.log_activity(
            request.tenant,
            entity_type=self.entity_type,
            entity_id=parent.pk,
            entity_label=parent.display_name,
            action=ActivityLog.Action.DOCUMENT_DOWNLOADED,
            user=request.user,
            details=documento.original_filename,
        )
        return FileResponse(
            documento.file.open("rb"),
            as_attachment=True,
            filename=nombre_original_seguro(documento.original_filename),
        )


# ---------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------


class CustomerListView(_ContactListView):
    template_name = "customers/customer_list.html"
    context_object_name = "customers"
    list_service = staticmethod(services.list_customers)
    permission_code = "customers.view"


class CustomerDetailView(_ContactDetailView):
    model = Customer
    template_name = "customers/customer_detail.html"
    context_object_name = "customer"
    entity_type = "customer"
    document_model = CustomerDocument
    document_form_class = CustomerDocumentForm
    permission_code = "customers.view"


class CustomerCreateView(_ContactCreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    entity_type = "customer"
    entity_label_singular = "Cliente"
    url_namespace_detail = "customers:customer_detail"
    permission_code = "customers.create"


class CustomerUpdateView(_ContactUpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    entity_type = "customer"
    entity_label_singular = "Cliente"
    url_namespace_detail = "customers:customer_detail"
    permission_code = "customers.update"


class CustomerStatusView(_ContactStatusView):
    model = Customer
    entity_type = "customer"
    url_namespace_detail = "customers:customer_detail"
    permission_code = "customers.delete"


class CustomerDocumentUploadView(_ContactDocumentUploadView):
    parent_model = Customer
    form_class = CustomerDocumentForm
    entity_type = "customer"
    register_service = staticmethod(services.register_customer_document)
    url_namespace_detail = "customers:customer_detail"
    permission_code = "customers.update"


class CustomerDocumentDeleteView(_ContactDocumentDeleteView):
    parent_model = Customer
    document_model = CustomerDocument
    entity_type = "customer"
    delete_service = staticmethod(services.delete_customer_document)
    url_namespace_detail = "customers:customer_detail"
    permission_code = "customers.update"


class CustomerDocumentDownloadView(_ContactDocumentDownloadView):
    parent_model = Customer
    document_model = CustomerDocument
    entity_type = "customer"
    permission_code = "customers.view"


# ---------------------------------------------------------------------
# Proveedores
# ---------------------------------------------------------------------


class SupplierListView(_ContactListView):
    template_name = "customers/supplier_list.html"
    context_object_name = "suppliers"
    list_service = staticmethod(services.list_suppliers)
    permission_code = "suppliers.view"


class SupplierDetailView(_ContactDetailView):
    model = Supplier
    template_name = "customers/supplier_detail.html"
    context_object_name = "supplier"
    entity_type = "supplier"
    document_model = SupplierDocument
    document_form_class = SupplierDocumentForm
    permission_code = "suppliers.view"


class SupplierCreateView(_ContactCreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "customers/supplier_form.html"
    entity_type = "supplier"
    entity_label_singular = "Proveedor"
    url_namespace_detail = "customers:supplier_detail"
    permission_code = "suppliers.create"


class SupplierUpdateView(_ContactUpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "customers/supplier_form.html"
    entity_type = "supplier"
    entity_label_singular = "Proveedor"
    url_namespace_detail = "customers:supplier_detail"
    permission_code = "suppliers.update"


class SupplierStatusView(_ContactStatusView):
    model = Supplier
    entity_type = "supplier"
    url_namespace_detail = "customers:supplier_detail"
    permission_code = "suppliers.delete"


class SupplierDocumentUploadView(_ContactDocumentUploadView):
    parent_model = Supplier
    form_class = SupplierDocumentForm
    entity_type = "supplier"
    register_service = staticmethod(services.register_supplier_document)
    url_namespace_detail = "customers:supplier_detail"
    permission_code = "suppliers.update"


class SupplierDocumentDeleteView(_ContactDocumentDeleteView):
    parent_model = Supplier
    document_model = SupplierDocument
    entity_type = "supplier"
    delete_service = staticmethod(services.delete_supplier_document)
    url_namespace_detail = "customers:supplier_detail"
    permission_code = "suppliers.update"


class SupplierDocumentDownloadView(_ContactDocumentDownloadView):
    parent_model = Supplier
    document_model = SupplierDocument
    entity_type = "supplier"
    permission_code = "suppliers.view"
