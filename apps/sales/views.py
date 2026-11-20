"""
Vistas del motor comercial (FASE 10). Deliberadamente delgadas: toda la
lógica vive en `services.py`. Todas heredan `TenantRequiredMixin` (FASE 3)
+ `LoginRequiredMixin`, y cada queryset/objeto se resuelve filtrando
explícitamente por `tenant=self.request.tenant` — nunca por un
`tenant_id` recibido del cliente.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.customers.file_validation import nombre_original_seguro
from apps.permissions.services import require_permission
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import (
    PaymentForm,
    ProformaHeaderForm,
    ProformaItemForm,
    QuotationHeaderForm,
    QuotationItemForm,
    ReturnForm,
    ReturnItemFormSet,
    SaleHeaderForm,
    SaleItemForm,
    SalesAttachmentForm,
)
from .models import (
    Payment,
    PaymentAllocation,
    ProformaInvoice,
    Quotation,
    QuotationItem,
    ProformaInvoiceItem,
    Reservation,
    Sale,
    SaleItem,
    SalesActivityLog,
    SalesDocumentAttachment,
)


def _item_kwargs_from_form(form):
    data = form.cleaned_data.copy()
    data.pop("unit_identifier", None)
    product = data.pop("product")
    quantity = data.pop("quantity")
    return product, quantity, data


def _mensaje_error(error):
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


# ---------------------------------------------------------------------
# Cotizaciones
# ---------------------------------------------------------------------


class QuotationListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "sales/quotation_list.html"
    context_object_name = "quotations"
    paginate_by = 20

    def get_queryset(self):
        queryset = Quotation.objects.select_related("customer").order_by("-issue_date", "-id")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "")
        if query:
            queryset = queryset.filter(number__icontains=query)
        if estado:
            queryset = queryset.filter(status=estado)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["estado"] = self.request.GET.get("estado", "")
        context["estados"] = Quotation.Status.choices
        return context


class QuotationCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = QuotationHeaderForm(tenant=request.tenant)
        return render(request, "sales/quotation_form.html", {"form": form})

    def post(self, request):
        form = QuotationHeaderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            quotation = services.create_quotation(request.tenant, user=request.user, **form.cleaned_data)
            messages.success(request, f"Cotización «{quotation.number}» creada. Agrega las líneas.")
            return redirect("sales:quotation_detail", pk=quotation.pk)
        return render(request, "sales/quotation_form.html", {"form": form})


class QuotationDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk, tenant=request.tenant)
        context = {
            "quotation": quotation,
            "items": services.get_quotation_items(quotation),
            "item_form": QuotationItemForm(tenant=request.tenant),
            "attachment_form": SalesAttachmentForm(),
            "attachments": SalesDocumentAttachment.objects.filter(document_type="quotation", document_id=quotation.pk),
            "activity_log": services.get_activity_log(request.tenant, entity_type="quotation", entity_id=quotation.pk),
            "converted_proforma": getattr(quotation, "converted_proforma", None),
            "converted_sale": getattr(quotation, "converted_sale_direct", None),
        }
        return render(request, "sales/quotation_detail.html", context)


class QuotationItemAddView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk, tenant=request.tenant)
        form = QuotationItemForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            product, quantity, kwargs = _item_kwargs_from_form(form)
            try:
                services.add_quotation_item(quotation, product=product, quantity=quantity, user=request.user, **kwargs)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
            else:
                messages.success(request, "Línea agregada correctamente.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
        return redirect("sales:quotation_detail", pk=quotation.pk)


class QuotationItemDeleteView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, item_pk):
        quotation = get_object_or_404(Quotation, pk=pk, tenant=request.tenant)
        item = get_object_or_404(QuotationItem, pk=item_pk, tenant=request.tenant, quotation=quotation)
        try:
            services.remove_quotation_item(item)
            messages.success(request, "Línea eliminada correctamente.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("sales:quotation_detail", pk=quotation.pk)


class QuotationStatusView(LoginRequiredMixin, TenantRequiredMixin, View):
    _ACCIONES = {
        "send": (Quotation.Status.SENT, SalesActivityLog.Action.SENT),
        "accept": (Quotation.Status.ACCEPTED, SalesActivityLog.Action.ACCEPTED),
        "reject": (Quotation.Status.REJECTED, SalesActivityLog.Action.REJECTED),
        "cancel": (Quotation.Status.CANCELED, SalesActivityLog.Action.CANCELED),
    }

    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk, tenant=request.tenant)
        accion = request.POST.get("accion")
        datos = self._ACCIONES.get(accion)
        if not datos:
            messages.error(request, "Acción no reconocida.")
        else:
            nuevo_estado, etiqueta = datos
            try:
                services.transition_quotation_status(quotation, nuevo_estado, request.user, action_label=etiqueta)
                messages.success(request, "Estado de la cotización actualizado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        return redirect("sales:quotation_detail", pk=quotation.pk)


class QuotationConvertToProformaView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk, tenant=request.tenant)
        try:
            proforma = services.convert_quotation_to_proforma(quotation, request.user)
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
            return redirect("sales:quotation_detail", pk=quotation.pk)
        messages.success(request, f"Cotización convertida a la proforma «{proforma.number}».")
        return redirect("sales:proforma_detail", pk=proforma.pk)


class QuotationConvertToSaleView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk, tenant=request.tenant)
        try:
            sale = services.convert_quotation_to_sale(quotation, request.user)
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
            return redirect("sales:quotation_detail", pk=quotation.pk)
        messages.success(request, f"Cotización convertida a la venta «{sale.number}».")
        return redirect("sales:sale_detail", pk=sale.pk)


class QuotationDuplicateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk, tenant=request.tenant)
        nueva = services.duplicate_quotation(quotation, request.user)
        messages.success(request, f"Cotización duplicada como «{nueva.number}».")
        return redirect("sales:quotation_detail", pk=nueva.pk)


class QuotationPrintView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk, tenant=request.tenant)
        return render(request, "sales/quotation_print.html", {"quotation": quotation, "items": services.get_quotation_items(quotation)})


# ---------------------------------------------------------------------
# Proformas
# ---------------------------------------------------------------------


class ProformaListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "sales/proforma_list.html"
    context_object_name = "proformas"
    paginate_by = 20

    def get_queryset(self):
        queryset = ProformaInvoice.objects.select_related("customer").order_by("-issue_date", "-id")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "")
        if query:
            queryset = queryset.filter(number__icontains=query)
        if estado:
            queryset = queryset.filter(status=estado)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["estado"] = self.request.GET.get("estado", "")
        context["estados"] = ProformaInvoice.Status.choices
        return context


class ProformaCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = ProformaHeaderForm(tenant=request.tenant)
        return render(request, "sales/proforma_form.html", {"form": form})

    def post(self, request):
        form = ProformaHeaderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            proforma = services.create_proforma(request.tenant, user=request.user, **form.cleaned_data)
            messages.success(request, f"Proforma «{proforma.number}» creada. Agrega las líneas.")
            return redirect("sales:proforma_detail", pk=proforma.pk)
        return render(request, "sales/proforma_form.html", {"form": form})


class ProformaDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        proforma = get_object_or_404(ProformaInvoice, pk=pk, tenant=request.tenant)
        context = {
            "proforma": proforma,
            "items": services.get_proforma_items(proforma),
            "item_form": ProformaItemForm(tenant=request.tenant),
            "attachment_form": SalesAttachmentForm(),
            "attachments": SalesDocumentAttachment.objects.filter(document_type="proforma", document_id=proforma.pk),
            "activity_log": services.get_activity_log(request.tenant, entity_type="proforma", entity_id=proforma.pk),
            "converted_sale": getattr(proforma, "converted_sale", None),
            "reservations": Reservation.objects.filter(source_type=Reservation.SourceType.PROFORMA, source_id=proforma.pk),
        }
        return render(request, "sales/proforma_detail.html", context)


class ProformaItemAddView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        proforma = get_object_or_404(ProformaInvoice, pk=pk, tenant=request.tenant)
        form = ProformaItemForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            product, quantity, kwargs = _item_kwargs_from_form(form)
            try:
                services.add_proforma_item(proforma, product=product, quantity=quantity, user=request.user, **kwargs)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
            else:
                messages.success(request, "Línea agregada correctamente.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
        return redirect("sales:proforma_detail", pk=proforma.pk)


class ProformaItemDeleteView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, item_pk):
        proforma = get_object_or_404(ProformaInvoice, pk=pk, tenant=request.tenant)
        item = get_object_or_404(ProformaInvoiceItem, pk=item_pk, tenant=request.tenant, proforma=proforma)
        try:
            services.remove_proforma_item(item)
            messages.success(request, "Línea eliminada correctamente.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("sales:proforma_detail", pk=proforma.pk)


class ProformaStatusView(LoginRequiredMixin, TenantRequiredMixin, View):
    _ACCIONES = {
        "issue": (ProformaInvoice.Status.ISSUED, SalesActivityLog.Action.ISSUED),
        "cancel": (ProformaInvoice.Status.CANCELED, SalesActivityLog.Action.CANCELED),
    }

    def post(self, request, pk):
        proforma = get_object_or_404(ProformaInvoice, pk=pk, tenant=request.tenant)
        accion = request.POST.get("accion")
        datos = self._ACCIONES.get(accion)
        if not datos:
            messages.error(request, "Acción no reconocida.")
        else:
            nuevo_estado, etiqueta = datos
            try:
                services.transition_proforma_status(proforma, nuevo_estado, request.user, action_label=etiqueta)
                messages.success(request, "Estado de la proforma actualizado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        return redirect("sales:proforma_detail", pk=proforma.pk)


class ProformaReserveStockView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        proforma = get_object_or_404(ProformaInvoice, pk=pk, tenant=request.tenant)
        try:
            reservas = services.reserve_stock_for_proforma(proforma, request.user)
            messages.success(request, f"Se reservó el stock de {len(reservas)} línea(s).")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("sales:proforma_detail", pk=proforma.pk)


class ProformaConvertToSaleView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        proforma = get_object_or_404(ProformaInvoice, pk=pk, tenant=request.tenant)
        try:
            sale = services.convert_proforma_to_sale(proforma, request.user)
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
            return redirect("sales:proforma_detail", pk=proforma.pk)
        messages.success(request, f"Proforma convertida a la venta «{sale.number}».")
        return redirect("sales:sale_detail", pk=sale.pk)


class ProformaPrintView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        proforma = get_object_or_404(ProformaInvoice, pk=pk, tenant=request.tenant)
        return render(request, "sales/proforma_print.html", {"proforma": proforma, "items": services.get_proforma_items(proforma)})


# ---------------------------------------------------------------------
# Ventas / Facturas
# ---------------------------------------------------------------------


class SaleListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "sales/sale_list.html"
    context_object_name = "sales"
    paginate_by = 20

    def get_queryset(self):
        queryset = Sale.objects.select_related("customer").order_by("-issue_date", "-id")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "")
        estado_pago = self.request.GET.get("estado_pago", "")
        if query:
            queryset = queryset.filter(number__icontains=query)
        if estado:
            queryset = queryset.filter(status=estado)
        if estado_pago:
            queryset = queryset.filter(payment_status=estado_pago)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        context["estado"] = self.request.GET.get("estado", "")
        context["estado_pago"] = self.request.GET.get("estado_pago", "")
        context["estados"] = Sale.Status.choices
        context["estados_pago"] = Sale.PaymentStatus.choices
        return context


class SaleCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = SaleHeaderForm(tenant=request.tenant)
        return render(request, "sales/sale_form.html", {"form": form})

    def post(self, request):
        require_permission(request, "sales.create")
        form = SaleHeaderForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            sale = services.create_sale(request.tenant, user=request.user, **form.cleaned_data)
            messages.success(request, f"Venta «{sale.number}» creada. Agrega las líneas y confirma para aplicar el inventario.")
            return redirect("sales:sale_detail", pk=sale.pk)
        return render(request, "sales/sale_form.html", {"form": form})


class SaleDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        context = {
            "sale": sale,
            "items": services.get_sale_items(sale),
            "item_form": SaleItemForm(tenant=request.tenant),
            "payment_form": PaymentForm(),
            "payments": PaymentAllocation.objects.filter(sale=sale).select_related("payment", "user"),
            "paid_amount": services.get_sale_paid_amount(sale),
            "balance_due": services.get_sale_balance_due(sale),
            "returns": sale.returns.select_related("user"),
            "attachment_form": SalesAttachmentForm(),
            "attachments": SalesDocumentAttachment.objects.filter(document_type="sale", document_id=sale.pk),
            "activity_log": services.get_activity_log(request.tenant, entity_type="sale", entity_id=sale.pk),
        }
        return render(request, "sales/sale_detail.html", context)


class SaleItemAddView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        require_permission(request, "sales.update")
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        form = SaleItemForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            product, quantity, kwargs = _item_kwargs_from_form(form)
            try:
                services.add_sale_item(sale, product=product, quantity=quantity, user=request.user, **kwargs)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
            else:
                messages.success(request, "Línea agregada correctamente.")
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
        return redirect("sales:sale_detail", pk=sale.pk)


class SaleItemDeleteView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, item_pk):
        require_permission(request, "sales.update")
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        item = get_object_or_404(SaleItem, pk=item_pk, tenant=request.tenant, sale=sale)
        try:
            services.remove_sale_item(item)
            messages.success(request, "Línea eliminada correctamente.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("sales:sale_detail", pk=sale.pk)


class SaleConfirmView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        require_permission(request, "sales.update")
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        try:
            services.confirm_sale(sale, request.user)
            messages.success(request, f"Venta «{sale.number}» confirmada: se aplicaron los efectos en inventario.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("sales:sale_detail", pk=sale.pk)


class SaleCancelView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        require_permission(request, "sales.cancel")
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        try:
            services.cancel_sale(sale, request.user, reason=request.POST.get("reason", ""))
            messages.success(request, f"Venta «{sale.number}» cancelada.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("sales:sale_detail", pk=sale.pk)


class SalePaymentAddView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        require_permission(request, "payments.create")
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                services.record_payment_for_sale(sale, user=request.user, **form.cleaned_data)
                messages.success(request, "Pago registrado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
        return redirect("sales:sale_detail", pk=sale.pk)


class SalePaymentReverseView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Revierte la APLICACIÓN de un pago a esta venta (no el pago
    completo, que puede estar aplicado también a otras facturas del
    mismo cliente): libera el saldo pendiente de la venta y devuelve
    ese monto al saldo sin aplicar del pago."""

    def post(self, request, pk, allocation_pk):
        require_permission(request, "payments.reverse")
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        allocation = get_object_or_404(PaymentAllocation, pk=allocation_pk, tenant=request.tenant, sale=sale)
        services.reverse_allocation(allocation, request.user)
        messages.success(request, "Pago revertido de esta venta correctamente.")
        return redirect("sales:sale_detail", pk=sale.pk)


class SaleReturnCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        items = list(services.get_sale_items(sale))
        initial = [{"sale_item_id": item.pk, "include": False, "quantity_returned": item.quantity} for item in items]
        formset = ReturnItemFormSet(initial=initial)
        filas = list(zip(items, formset))
        return render(request, "sales/return_form.html", {"sale": sale, "filas": filas, "formset": formset, "reason_form": ReturnForm()})

    def post(self, request, pk):
        require_permission(request, "sales.refund")
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        items_by_id = {item.pk: item for item in services.get_sale_items(sale)}
        formset = ReturnItemFormSet(request.POST)
        reason_form = ReturnForm(request.POST)
        if formset.is_valid() and reason_form.is_valid():
            seleccionadas = []
            for fila in formset.cleaned_data:
                if not fila.get("include"):
                    continue
                sale_item = items_by_id.get(fila["sale_item_id"])
                if sale_item is None:
                    continue
                if sale_item.inventory_unit_id:
                    seleccionadas.append({"sale_item": sale_item})
                else:
                    seleccionadas.append({"sale_item": sale_item, "quantity_returned": fila.get("quantity_returned")})
            try:
                devolucion = services.create_return(sale, items=seleccionadas, user=request.user, reason=reason_form.cleaned_data["reason"])
                messages.success(request, f"Devolución «{devolucion.number}» registrada correctamente.")
                return redirect("sales:sale_detail", pk=sale.pk)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos de la devolución.")
        items = list(services.get_sale_items(sale))
        filas = list(zip(items, formset))
        return render(request, "sales/return_form.html", {"sale": sale, "filas": filas, "formset": formset, "reason_form": reason_form})


class SaleReceiptView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant)
        pagos = PaymentAllocation.objects.filter(
            sale=sale, status=PaymentAllocation.Status.ACTIVE, payment__status=Payment.Status.CONFIRMED
        ).select_related("payment")
        return render(
            request, "sales/sale_receipt.html",
            {
                "sale": sale,
                "items": services.get_sale_items(sale),
                "payments": pagos,
                # FASE 7 — BLOQUE B: columnas Recibido/Cambio solo se
                # muestran cuando algún pago de esta venta realmente
                # tuvo cambio — nunca una sección redundante en cero.
                "hubo_cambio": pagos.filter(payment__change_amount__gt=0).exists(),
            },
        )


# ---------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------


class ReservationListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "sales/reservation_list.html"
    context_object_name = "reservations"
    paginate_by = 20

    def get_queryset(self):
        return Reservation.objects.select_related("product", "customer", "inventory_unit").order_by("-created_at")


class ReservationReleaseView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        reservation = get_object_or_404(Reservation, pk=pk, tenant=request.tenant)
        services.release_reservation(reservation, request.user)
        messages.success(request, "Reserva liberada correctamente.")
        return redirect("sales:reservation_list")


# ---------------------------------------------------------------------
# Documentos adjuntos (Cotización / Proforma / Venta) — mismo patrón de FASE 9
# ---------------------------------------------------------------------

_PARENT_MODELS = {"quotation": Quotation, "proforma": ProformaInvoice, "sale": Sale}
_DETAIL_URL_NAMES = {"quotation": "sales:quotation_detail", "proforma": "sales:proforma_detail", "sale": "sales:sale_detail"}


class _AttachmentUploadView(LoginRequiredMixin, TenantRequiredMixin, View):
    document_type = None

    def post(self, request, pk):
        parent_model = _PARENT_MODELS[self.document_type]
        parent = get_object_or_404(parent_model, pk=pk, tenant=request.tenant)
        form = SalesAttachmentForm(request.POST, request.FILES)
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
        parent_model = _PARENT_MODELS[self.document_type]
        parent = get_object_or_404(parent_model, pk=pk, tenant=request.tenant)
        adjunto = get_object_or_404(
            SalesDocumentAttachment, pk=attachment_pk, tenant=request.tenant, document_type=self.document_type, document_id=parent.pk
        )
        services.delete_attachment(adjunto, request.user)
        messages.success(request, "Documento eliminado correctamente.")
        return redirect(_DETAIL_URL_NAMES[self.document_type], pk=parent.pk)


class _AttachmentDownloadView(LoginRequiredMixin, TenantRequiredMixin, View):
    document_type = None

    def get(self, request, pk, attachment_pk):
        parent_model = _PARENT_MODELS[self.document_type]
        parent = get_object_or_404(parent_model, pk=pk, tenant=request.tenant)
        adjunto = get_object_or_404(
            SalesDocumentAttachment, pk=attachment_pk, tenant=request.tenant, document_type=self.document_type, document_id=parent.pk
        )
        return FileResponse(adjunto.file.open("rb"), as_attachment=True, filename=nombre_original_seguro(adjunto.original_filename))


class QuotationAttachmentUploadView(_AttachmentUploadView):
    document_type = "quotation"


class QuotationAttachmentDeleteView(_AttachmentDeleteView):
    document_type = "quotation"


class QuotationAttachmentDownloadView(_AttachmentDownloadView):
    document_type = "quotation"


class ProformaAttachmentUploadView(_AttachmentUploadView):
    document_type = "proforma"


class ProformaAttachmentDeleteView(_AttachmentDeleteView):
    document_type = "proforma"


class ProformaAttachmentDownloadView(_AttachmentDownloadView):
    document_type = "proforma"


class SaleAttachmentUploadView(_AttachmentUploadView):
    document_type = "sale"


class SaleAttachmentDeleteView(_AttachmentDeleteView):
    document_type = "sale"


class SaleAttachmentDownloadView(_AttachmentDownloadView):
    document_type = "sale"
