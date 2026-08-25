"""
Vistas de Compras (FASE 12). Deliberadamente delgadas: toda la lógica
vive en `apps.purchases.services`, que a su vez consume literalmente
`apps.inventory`/`apps.customers`/`apps.approvals`/`apps.pos`/
`apps.sales` — esta capa solo arma el request/response. Cada acción
sensible (compra sobre el límite, sobre-recepción) captura la
excepción `PurchaseOverThresholdRequiresApproval`/
`OverReceivingRequiresApproval`, genera automáticamente la
`ApprovalRequest` correspondiente y le pide al usuario reintentar una
vez que un supervisor la resuelva — mismo patrón que `apps.pos.views`,
nunca un bypass silencioso.
"""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.customers.file_validation import nombre_original_seguro
from apps.customers.models import Supplier
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import (
    ApplySupplierAdvanceForm,
    PurchaseAttachmentForm,
    PurchaseOrderHeaderEditForm,
    PurchaseOrderHeaderForm,
    PurchaseOrderItemForm,
    ReceiveQuantityForm,
    ReceiveSerializedFormSet,
    SupplierAdvanceForm,
    SupplierInvoiceHeaderForm,
    SupplierInvoiceItemForm,
    SupplierPaymentForm,
    SupplierReturnForm,
    SupplierReturnItemFormSet,
)
from .models import (
    PurchaseDocumentAttachment,
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierInvoice,
)


def _mensaje_error(error):
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


# ------------------------------------------------------------------
# Órdenes de Compra
# ------------------------------------------------------------------


class PurchaseOrderListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "purchases/purchase_order_list.html"
    context_object_name = "ordenes"
    paginate_by = 20

    def get_queryset(self):
        queryset = PurchaseOrder.objects.select_related("supplier").order_by("-issue_date", "-id")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "")
        if query:
            queryset = queryset.filter(number__icontains=query)
        if estado:
            queryset = queryset.filter(status=estado)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["estados"] = PurchaseOrder.Status.choices
        context["q"] = self.request.GET.get("q", "")
        context["estado"] = self.request.GET.get("estado", "")
        return context


class PurchaseOrderCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = PurchaseOrderHeaderForm(tenant=request.tenant)
        return render(request, "purchases/purchase_order_form.html", {"form": form})

    def post(self, request):
        form = PurchaseOrderHeaderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                orden = services.create_purchase_order(request.tenant, user=request.user, **form.cleaned_data)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
                return render(request, "purchases/purchase_order_form.html", {"form": form})
            messages.success(request, f"Orden de compra «{orden.number}» creada. Agrega las líneas y envíala al proveedor.")
            return redirect("purchases:purchase_order_detail", pk=orden.pk)
        return render(request, "purchases/purchase_order_form.html", {"form": form})


class PurchaseOrderDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        items = list(services.get_purchase_order_items(orden))
        recibido_por_item = services.get_purchase_order_items_received_bulk(items)
        for item in items:
            item.recibido = recibido_por_item.get(item.pk, Decimal("0"))
            item.pendiente = item.quantity - item.recibido
        context = {
            "orden": orden,
            "items": items,
            "item_form": PurchaseOrderItemForm(tenant=request.tenant),
            "header_form": PurchaseOrderHeaderEditForm(),
            "receipts": services.get_purchase_receipts(orden),
            "invoices": SupplierInvoice.objects.filter(purchase_order=orden).order_by("-issue_date"),
            "returns": services.get_supplier_returns(orden),
            "attachment_form": PurchaseAttachmentForm(),
            "attachments": PurchaseDocumentAttachment.objects.filter(document_type="purchase_order", document_id=orden.pk),
            "activity_log": services.get_activity_log(request.tenant, entity_type="purchase_order", entity_id=orden.pk),
        }
        return render(request, "purchases/purchase_order_detail.html", context)


class PurchaseOrderItemAddView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        form = PurchaseOrderItemForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                services.add_purchase_order_item(orden, user=request.user, **form.cleaned_data)
                messages.success(request, "Línea agregada correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
        return redirect("purchases:purchase_order_detail", pk=orden.pk)


class PurchaseOrderItemRemoveView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, item_pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        item = get_object_or_404(PurchaseOrderItem, pk=item_pk, tenant=request.tenant, purchase_order=orden)
        try:
            services.remove_purchase_order_item(item)
            messages.success(request, "Línea eliminada.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("purchases:purchase_order_detail", pk=orden.pk)


class PurchaseOrderHeaderEditView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        form = PurchaseOrderHeaderEditForm(request.POST)
        if form.is_valid():
            try:
                services.update_purchase_order_header(orden, user=request.user, **form.cleaned_data)
                messages.success(request, "Orden de compra actualizada.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos de la orden.")
        return redirect("purchases:purchase_order_detail", pk=orden.pk)


class PurchaseOrderSendView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        try:
            services.send_purchase_order(orden, request.user, tenant=request.tenant)
            messages.success(request, f"Orden «{orden.number}» enviada al proveedor.")
        except services.PurchaseOverThresholdRequiresApproval as error:
            solicitud = services.request_purchase_approval(request.tenant, orden, request.user, limite=error.limit)
            messages.warning(
                request,
                f"Esta orden supera tu límite autorizado — se solicitó autorización (#{solicitud.pk}). "
                "Pide a un supervisor que la apruebe en Autorizaciones y vuelve a enviarla.",
            )
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("purchases:purchase_order_detail", pk=orden.pk)


class PurchaseOrderCancelView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        try:
            services.cancel_purchase_order(orden, request.user, reason=request.POST.get("reason", ""))
            messages.success(request, "Orden de compra cancelada.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("purchases:purchase_order_detail", pk=orden.pk)


class PurchaseOrderCloseView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        try:
            services.close_purchase_order(orden, request.user)
            messages.success(request, "Orden de compra cerrada.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("purchases:purchase_order_detail", pk=orden.pk)


# ------------------------------------------------------------------
# Recepción
# ------------------------------------------------------------------


class ReceivePurchaseOrderItemView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Recibe UNA línea de la orden por vez — cantidad o serializado
    según el tipo de seguimiento del producto (ver `docs/receiving.md`)."""

    def get(self, request, pk, item_pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        item = get_object_or_404(PurchaseOrderItem, pk=item_pk, tenant=request.tenant, purchase_order=orden)
        es_serializado = item.product.inventory_tracking_type == item.product.TrackingType.SERIALIZED
        context = {
            "orden": orden, "item": item, "es_serializado": es_serializado,
            "pendiente": services.get_purchase_order_item_pending_quantity(item),
            "quantity_form": ReceiveQuantityForm(),
            "serialized_formset": ReceiveSerializedFormSet(),
        }
        return render(request, "purchases/receive_item.html", context)

    def post(self, request, pk, item_pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        item = get_object_or_404(PurchaseOrderItem, pk=item_pk, tenant=request.tenant, purchase_order=orden)
        es_serializado = item.product.inventory_tracking_type == item.product.TrackingType.SERIALIZED

        if es_serializado:
            formset = ReceiveSerializedFormSet(request.POST)
            quantity_form = ReceiveQuantityForm()
            if not formset.is_valid():
                messages.error(request, "Revisa los datos de las unidades.")
                return self._reload(request, orden, item, es_serializado, quantity_form, formset)
            unidades = [
                {"serial": f.cleaned_data.get("serial", ""), "imei_1": f.cleaned_data.get("imei_1", ""),
                 "imei_2": f.cleaned_data.get("imei_2", ""), "unit_cost": f.cleaned_data.get("unit_cost")}
                for f in formset if f.cleaned_data and f.has_any_identifier()
            ]
            lineas = [{"purchase_order_item": item, "units": unidades}]
        else:
            quantity_form = ReceiveQuantityForm(request.POST)
            formset = ReceiveSerializedFormSet()
            if not quantity_form.is_valid():
                messages.error(request, "Revisa la cantidad a recibir.")
                return self._reload(request, orden, item, es_serializado, quantity_form, formset)
            lineas = [{
                "purchase_order_item": item,
                "quantity_received": quantity_form.cleaned_data["quantity_received"],
                "unit_cost": quantity_form.cleaned_data.get("unit_cost"),
            }]

        try:
            recepcion = services.receive_purchase_order(
                orden, lines=lineas, user=request.user, tenant=request.tenant,
                receipt_date=quantity_form.cleaned_data.get("receipt_date") if not es_serializado else None,
                notes=quantity_form.cleaned_data.get("notes", "") if not es_serializado else "",
            )
            messages.success(request, f"Recepción «{recepcion.number}» registrada correctamente.")
        except services.OverReceivingRequiresApproval as error:
            solicitud = services.request_over_receiving_approval(
                request.tenant, orden, request.user,
                limite_percent=error.limit_percent, exceso_percent=error.requested_percent,
            )
            messages.warning(
                request,
                f"Esto excede la cantidad pendiente — se solicitó autorización de sobre-recepción "
                f"(#{solicitud.pk}). Pide a un supervisor que la apruebe en Autorizaciones y vuelve a intentarlo.",
            )
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("purchases:purchase_order_detail", pk=orden.pk)

    def _reload(self, request, orden, item, es_serializado, quantity_form, formset):
        context = {
            "orden": orden, "item": item, "es_serializado": es_serializado,
            "pendiente": services.get_purchase_order_item_pending_quantity(item),
            "quantity_form": quantity_form, "serialized_formset": formset,
        }
        return render(request, "purchases/receive_item.html", context)


# ------------------------------------------------------------------
# Devolución a proveedor
# ------------------------------------------------------------------


class SupplierReturnCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        receipt_items = _receipt_items_for_order(request.tenant, orden)
        formset = SupplierReturnItemFormSet(initial=[{"receipt_item_id": ri.pk} for ri in receipt_items])
        return render(request, "purchases/supplier_return_form.html", {
            "orden": orden, "receipt_items": receipt_items,
            "formset": list(zip(receipt_items, formset)), "management_form": formset.management_form,
            "reason_form": SupplierReturnForm(),
        })

    def post(self, request, pk):
        orden = get_object_or_404(PurchaseOrder, pk=pk, tenant=request.tenant)
        receipt_items = _receipt_items_for_order(request.tenant, orden)
        formset = SupplierReturnItemFormSet(request.POST)
        reason_form = SupplierReturnForm(request.POST)
        if not (formset.is_valid() and reason_form.is_valid()):
            messages.error(request, "Revisa los datos de la devolución.")
            return redirect("purchases:purchase_order_detail", pk=orden.pk)

        receipt_items_by_id = {ri.pk: ri for ri in receipt_items}
        items = []
        for fila in formset.cleaned_data:
            if not fila or not fila.get("include"):
                continue
            receipt_item = receipt_items_by_id.get(fila["receipt_item_id"])
            if receipt_item is None:
                continue
            entrada = {"receipt_item": receipt_item}
            if receipt_item.inventory_unit_id is None:
                entrada["quantity_returned"] = fila.get("quantity_returned")
            items.append(entrada)

        if not items:
            messages.error(request, "Selecciona al menos una línea a devolver.")
            return redirect("purchases:purchase_order_detail", pk=orden.pk)

        try:
            devolucion = services.create_supplier_return(
                orden, items=items, user=request.user, reason=reason_form.cleaned_data["reason"],
            )
            messages.success(request, f"Devolución a proveedor «{devolucion.number}» registrada correctamente.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("purchases:purchase_order_detail", pk=orden.pk)


def _receipt_items_for_order(tenant, orden):
    receipt_items = []
    for recepcion in services.get_purchase_receipts(orden):
        receipt_items.extend(services.get_receipt_items(recepcion))
    return receipt_items


# ------------------------------------------------------------------
# Facturas de proveedor / Cuentas por Pagar
# ------------------------------------------------------------------


class SupplierInvoiceListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "purchases/supplier_invoice_list.html"
    context_object_name = "facturas"
    paginate_by = 20

    def get_queryset(self):
        queryset = SupplierInvoice.objects.select_related("supplier").order_by("-issue_date", "-id")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(supplier_invoice_number__icontains=query)
        return queryset


class SupplierInvoiceCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        purchase_order_pk = request.GET.get("orden")
        orden = None
        if purchase_order_pk:
            orden = get_object_or_404(PurchaseOrder, pk=purchase_order_pk, tenant=request.tenant)
        context = {
            "form": SupplierInvoiceHeaderForm(),
            "proveedores": Supplier.objects.filter(tenant=request.tenant, is_active=True),
            "orden": orden,
        }
        return render(request, "purchases/supplier_invoice_form.html", context)

    def post(self, request):
        form = SupplierInvoiceHeaderForm(request.POST)
        supplier_pk = request.POST.get("supplier")
        purchase_order_pk = request.POST.get("purchase_order")
        supplier = get_object_or_404(Supplier, pk=supplier_pk, tenant=request.tenant) if supplier_pk else None
        orden = get_object_or_404(PurchaseOrder, pk=purchase_order_pk, tenant=request.tenant) if purchase_order_pk else None
        if form.is_valid() and supplier is not None:
            try:
                factura = services.create_supplier_invoice(
                    request.tenant, supplier=supplier, user=request.user, purchase_order=orden, **form.cleaned_data,
                )
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
                return redirect(request.path)
            messages.success(request, f"Factura de proveedor «{factura.supplier_invoice_number}» registrada.")
            return redirect("purchases:supplier_invoice_detail", pk=factura.pk)
        messages.error(request, "Revisa los datos de la factura (proveedor y número son obligatorios).")
        return redirect("purchases:supplier_invoice_list")


class SupplierInvoiceDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        factura = get_object_or_404(SupplierInvoice, pk=pk, tenant=request.tenant)
        context = {
            "factura": factura,
            "items": services.get_supplier_invoice_items(factura),
            "item_form": SupplierInvoiceItemForm(),
            "paid_amount": services.get_invoice_paid_amount(factura),
            "balance_due": services.get_invoice_balance_due(factura),
            "allocations": services.get_invoice_allocations(factura),
            "payment_form": SupplierPaymentForm(),
            "advance_balance": services.get_supplier_advance_balance(factura.supplier),
            "apply_advance_form": ApplySupplierAdvanceForm(),
            "attachment_form": PurchaseAttachmentForm(),
            "attachments": PurchaseDocumentAttachment.objects.filter(document_type="supplier_invoice", document_id=factura.pk),
            "activity_log": services.get_activity_log(request.tenant, entity_type="supplier_invoice", entity_id=factura.pk),
        }
        return render(request, "purchases/supplier_invoice_detail.html", context)


class SupplierInvoiceItemAddView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        factura = get_object_or_404(SupplierInvoice, pk=pk, tenant=request.tenant)
        form = SupplierInvoiceItemForm(request.POST)
        if form.is_valid():
            try:
                services.add_supplier_invoice_item(factura, user=request.user, **form.cleaned_data)
                messages.success(request, "Línea agregada correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos de la línea.")
        return redirect("purchases:supplier_invoice_detail", pk=factura.pk)


class SupplierInvoiceConfirmView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        factura = get_object_or_404(SupplierInvoice, pk=pk, tenant=request.tenant)
        try:
            services.confirm_supplier_invoice(factura, request.user)
            messages.success(request, "Factura de proveedor confirmada.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("purchases:supplier_invoice_detail", pk=factura.pk)


class SupplierInvoiceCancelView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        factura = get_object_or_404(SupplierInvoice, pk=pk, tenant=request.tenant)
        try:
            services.cancel_supplier_invoice(factura, request.user, reason=request.POST.get("reason", ""))
            messages.success(request, "Factura de proveedor cancelada.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("purchases:supplier_invoice_detail", pk=factura.pk)


class SupplierInvoicePaymentView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        factura = get_object_or_404(SupplierInvoice, pk=pk, tenant=request.tenant)
        form = SupplierPaymentForm(request.POST)
        if form.is_valid():
            try:
                services.record_supplier_payment_for_invoice(factura, user=request.user, **form.cleaned_data)
                messages.success(request, "Pago registrado y aplicado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del pago.")
        return redirect("purchases:supplier_invoice_detail", pk=factura.pk)


class SupplierInvoiceApplyAdvanceView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        factura = get_object_or_404(SupplierInvoice, pk=pk, tenant=request.tenant)
        form = ApplySupplierAdvanceForm(request.POST)
        if form.is_valid():
            try:
                services.apply_supplier_advance_to_invoice(factura.supplier, factura, form.cleaned_data["amount"], request.user)
                messages.success(request, "Anticipo aplicado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Indica un monto válido.")
        return redirect("purchases:supplier_invoice_detail", pk=factura.pk)


class SupplierPaymentAllocationReverseView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, allocation_pk):
        factura = get_object_or_404(SupplierInvoice, pk=pk, tenant=request.tenant)
        asignacion = get_object_or_404(
            services.SupplierPaymentAllocation, pk=allocation_pk, tenant=request.tenant, supplier_invoice=factura,
        )
        services.reverse_supplier_allocation(asignacion, request.user)
        messages.success(request, "Aplicación de pago reversada.")
        return redirect("purchases:supplier_invoice_detail", pk=factura.pk)


# ------------------------------------------------------------------
# Anticipos a proveedor (independientes de una factura)
# ------------------------------------------------------------------


class SupplierAdvanceCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, supplier_pk):
        supplier = get_object_or_404(Supplier, pk=supplier_pk, tenant=request.tenant)
        context = {
            "supplier": supplier, "form": SupplierAdvanceForm(),
            "advance_balance": services.get_supplier_advance_balance(supplier),
            "pending_invoices": services.get_supplier_pending_invoices(supplier),
        }
        return render(request, "purchases/supplier_advance_form.html", context)

    def post(self, request, supplier_pk):
        supplier = get_object_or_404(Supplier, pk=supplier_pk, tenant=request.tenant)
        form = SupplierAdvanceForm(request.POST)
        if form.is_valid():
            try:
                services.register_supplier_advance(request.tenant, supplier=supplier, user=request.user, **form.cleaned_data)
                messages.success(request, "Anticipo registrado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del anticipo.")
        return redirect("purchases:supplier_advance_create", supplier_pk=supplier.pk)


# ------------------------------------------------------------------
# Documentos adjuntos (reutiliza FASE 9 — un solo sistema de archivos)
# ------------------------------------------------------------------


_PARENT_MODELS = {
    "purchase_order": PurchaseOrder,
    "supplier_invoice": SupplierInvoice,
}
_DETAIL_URL_NAMES = {
    "purchase_order": "purchases:purchase_order_detail",
    "supplier_invoice": "purchases:supplier_invoice_detail",
}


class _AttachmentUploadView(LoginRequiredMixin, TenantRequiredMixin, View):
    document_type = None

    def post(self, request, pk):
        parent = get_object_or_404(_PARENT_MODELS[self.document_type], pk=pk, tenant=request.tenant)
        form = PurchaseAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                services.register_attachment(
                    tenant=request.tenant, document_type=self.document_type, document_id=parent.pk,
                    archivo=form.cleaned_data["file"], category=form.cleaned_data["category"],
                    user=request.user, notes=form.cleaned_data["notes"],
                )
                messages.success(request, "Documento subido correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
        return redirect(_DETAIL_URL_NAMES[self.document_type], pk=parent.pk)


class _AttachmentDeleteView(LoginRequiredMixin, TenantRequiredMixin, View):
    document_type = None

    def post(self, request, pk, attachment_pk):
        parent = get_object_or_404(_PARENT_MODELS[self.document_type], pk=pk, tenant=request.tenant)
        adjunto = get_object_or_404(
            PurchaseDocumentAttachment, pk=attachment_pk, tenant=request.tenant,
            document_type=self.document_type, document_id=parent.pk,
        )
        services.delete_attachment(adjunto, request.user)
        messages.success(request, "Documento eliminado correctamente.")
        return redirect(_DETAIL_URL_NAMES[self.document_type], pk=parent.pk)


class _AttachmentDownloadView(LoginRequiredMixin, TenantRequiredMixin, View):
    document_type = None

    def get(self, request, pk, attachment_pk):
        parent = get_object_or_404(_PARENT_MODELS[self.document_type], pk=pk, tenant=request.tenant)
        adjunto = get_object_or_404(
            PurchaseDocumentAttachment, pk=attachment_pk, tenant=request.tenant,
            document_type=self.document_type, document_id=parent.pk,
        )
        return FileResponse(adjunto.file.open("rb"), as_attachment=True, filename=nombre_original_seguro(adjunto.original_filename))


class PurchaseOrderAttachmentUploadView(_AttachmentUploadView):
    document_type = "purchase_order"


class PurchaseOrderAttachmentDeleteView(_AttachmentDeleteView):
    document_type = "purchase_order"


class PurchaseOrderAttachmentDownloadView(_AttachmentDownloadView):
    document_type = "purchase_order"


class SupplierInvoiceAttachmentUploadView(_AttachmentUploadView):
    document_type = "supplier_invoice"


class SupplierInvoiceAttachmentDeleteView(_AttachmentDeleteView):
    document_type = "supplier_invoice"


class SupplierInvoiceAttachmentDownloadView(_AttachmentDownloadView):
    document_type = "supplier_invoice"
