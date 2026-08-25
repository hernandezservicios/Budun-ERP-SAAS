"""
Vistas del POS (FASE 11). Deliberadamente delgadas: toda la lógica vive
en `apps.pos.services`, que a su vez consume literalmente
`apps.sales`/`apps.inventory`/`apps.customers`/`apps.approvals` — esta
capa solo arma el request/response. Cada acción sensible (descuento
fuera de límite, crédito excedido) captura la excepción de
`DiscountRequiresApproval`/`CreditOverageRequiresApproval`, genera
automáticamente la `ApprovalRequest` correspondiente y le pide al
cajero reintentar una vez que un supervisor la resuelva — nunca permite
un bypass silencioso.
"""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.approvals.models import ApprovalRequest
from apps.customers.models import Customer
from apps.customers.services import list_customers
from apps.inventory.models import Product
from apps.sales.models import Payment, Sale
from apps.sales import services as sales_services
from apps.tenants.models import Membership
from apps.tenants.permissions import TenantRequiredMixin, require_role

from . import services
from .forms import (
    ApplyCreditForm,
    CashMovementForm,
    CashRegisterForm,
    CheckoutPaymentFormSet,
    CloseSessionForm,
    CollectPaymentForm,
    CustomerAdvanceForm,
    CustomerSelectForm,
    GlobalDiscountForm,
    IssueCreditNoteForm,
    OpenSessionForm,
    PosAddItemForm,
    PosSearchForm,
    RefundForm,
)
from .models import CashMovement, CashRegister, CashSession


def _mensaje_error(error):
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


# ------------------------------------------------------------------
# Cajas
# ------------------------------------------------------------------


class CashRegisterListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_role(request, Membership.Role.OWNER)
        context = {"cajas": services.get_registers(request.tenant), "form": CashRegisterForm()}
        return render(request, "pos/register_list.html", context)

    def post(self, request):
        require_role(request, Membership.Role.OWNER)
        form = CashRegisterForm(request.POST)
        if form.is_valid():
            CashRegister.all_objects.create(
                tenant=request.tenant, name=form.cleaned_data["name"], code=form.cleaned_data["code"],
                terminal=form.cleaned_data["terminal"],
            )
            messages.success(request, "Caja creada correctamente.")
        else:
            messages.error(request, "Revisa los datos de la caja (el código debe ser único).")
        return redirect("pos:register_list")


class CashSessionOpenView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        sesion_activa = services.get_active_session_for_user(request.tenant, request.user)
        if sesion_activa:
            return redirect("pos:terminal_start")
        form = OpenSessionForm(tenant=request.tenant)
        return render(request, "pos/session_open.html", {"form": form})

    def post(self, request):
        form = OpenSessionForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                services.open_cash_session(
                    request.tenant, cash_register=form.cleaned_data["cash_register"], user=request.user,
                    opening_amount=form.cleaned_data["opening_amount"], notes=form.cleaned_data["notes"],
                )
                messages.success(request, "Caja abierta correctamente.")
                return redirect("pos:terminal_start")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        return render(request, "pos/session_open.html", {"form": form})


class CashSessionCloseView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        sesion = services.get_active_session_for_user(request.tenant, request.user)
        if sesion is None:
            messages.error(request, "No tienes una sesión de caja abierta.")
            return redirect("pos:terminal_start")
        context = {
            "sesion": sesion, "form": CloseSessionForm(),
            "esperado": services.get_expected_cash(sesion),
            "movimientos": CashMovement.all_objects.filter(tenant=request.tenant, cash_session=sesion).order_by("created_at"),
        }
        return render(request, "pos/session_close.html", context)

    def post(self, request):
        sesion = services.get_active_session_for_user(request.tenant, request.user)
        if sesion is None:
            messages.error(request, "No tienes una sesión de caja abierta.")
            return redirect("pos:terminal_start")
        form = CloseSessionForm(request.POST)
        if form.is_valid():
            try:
                cerrada = services.close_cash_session(
                    sesion, request.user, counted_cash=form.cleaned_data["counted_cash"],
                    closing_notes=form.cleaned_data["closing_notes"],
                )
                messages.success(
                    request,
                    f"Caja cerrada. Esperado: {cerrada.expected_cash} — Contado: {cerrada.counted_cash} — "
                    f"Diferencia: {cerrada.difference}.",
                )
                return redirect("pos:session_summary", pk=cerrada.pk)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        context = {"sesion": sesion, "form": form, "esperado": services.get_expected_cash(sesion)}
        return render(request, "pos/session_close.html", context)


class CashSessionSummaryView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        sesion = get_object_or_404(CashSession, pk=pk, tenant=request.tenant)
        movimientos = CashMovement.all_objects.filter(tenant=request.tenant, cash_session=sesion).order_by("created_at")
        return render(request, "pos/session_summary.html", {"sesion": sesion, "movimientos": movimientos})


class CashMovementCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        sesion = services.get_active_session_for_user(request.tenant, request.user)
        if sesion is None:
            messages.error(request, "No tienes una sesión de caja abierta.")
            return redirect("pos:terminal_start")
        form = CashMovementForm(request.POST)
        if form.is_valid():
            try:
                services.record_cash_movement(
                    sesion, movement_type=form.cleaned_data["movement_type"], amount=form.cleaned_data["amount"],
                    user=request.user, reason=form.cleaned_data["reason"],
                )
                messages.success(request, "Movimiento de caja registrado.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del movimiento.")
        return redirect("pos:terminal_start")


# ------------------------------------------------------------------
# Terminal (venta)
# ------------------------------------------------------------------


class TerminalStartView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Encuentra o crea el carrito (Sale DRAFT) del usuario actual y
    redirige a su detalle — nunca más de un carrito activo por
    cajero a la vez."""

    def get(self, request):
        carrito = Sale.objects.filter(salesperson=request.user, status=Sale.Status.DRAFT).order_by("-created_at").first()
        if carrito is None:
            carrito = services.start_cart(request.tenant, user=request.user)
        return redirect("pos:terminal_detail", pk=carrito.pk)


class TerminalDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant, status=Sale.Status.DRAFT)
        query = request.GET.get("q", "")
        resultados = services.search(request.tenant, query) if query else []
        sesion = services.get_active_session_for_user(request.tenant, request.user)
        context = {
            "sale": sale,
            "items": services.get_cart_items(sale),
            "search_form": PosSearchForm(initial={"q": query}),
            "resultados": resultados,
            "customer_form": CustomerSelectForm(tenant=request.tenant, initial={"customer": sale.customer_id}),
            "discount_form": GlobalDiscountForm(initial={
                "global_discount_percent": sale.global_discount_percent,
                "global_discount_amount": sale.global_discount_amount,
            }),
            "payment_formset": CheckoutPaymentFormSet(),
            "sesion": sesion,
            "solicitudes_aprobadas": ApprovalRequest.all_objects.filter(
                tenant=request.tenant, document_type="sale", document_id=sale.pk,
                status=ApprovalRequest.Status.APPROVED, consumed_at__isnull=True,
            ) if sesion else [],
        }
        return render(request, "pos/terminal.html", context)


class AddItemView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant, status=Sale.Status.DRAFT)
        form = PosAddItemForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa los datos de la línea.")
            return redirect("pos:terminal_detail", pk=sale.pk)

        product = get_object_or_404(Product, pk=form.cleaned_data["product_id"], tenant=request.tenant)
        identificador = form.cleaned_data["unit_identifier"].strip()
        inventory_unit = None
        if identificador:
            from django.db.models import Q

            from apps.inventory.models import InventoryUnit

            inventory_unit = InventoryUnit.all_objects.filter(tenant=request.tenant).filter(
                Q(serial=identificador) | Q(imei_1=identificador) | Q(imei_2=identificador)
            ).first()
            if inventory_unit is None:
                messages.error(request, "No se encontró ninguna unidad con ese IMEI/serie.")
                return redirect("pos:terminal_detail", pk=sale.pk)

        try:
            services.add_item_to_cart(
                sale, product=product, quantity=form.cleaned_data["quantity"], user=request.user, tenant=request.tenant,
                discount_percent=form.cleaned_data["discount_percent"], discount_amount=form.cleaned_data["discount_amount"],
                inventory_unit=inventory_unit,
            )
            messages.success(request, f"«{product.name}» agregado al carrito.")
        except services.DiscountRequiresApproval as error:
            solicitud = services.request_discount_approval(
                request.tenant, sale, request.user,
                percent_solicitado=error.requested_percent, amount_solicitado=error.requested_amount,
                limite_percent=error.limit_percent, limite_amount=error.limit_amount,
            )
            messages.warning(
                request,
                f"El descuento supera tu límite autorizado — se solicitó autorización (#{solicitud.pk}). "
                "Pide a un supervisor que la apruebe en Autorizaciones y vuelve a agregar el mismo artículo.",
            )
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("pos:terminal_detail", pk=sale.pk)


class RemoveItemView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, item_pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant, status=Sale.Status.DRAFT)
        item = get_object_or_404(sales_services.get_sale_items(sale), pk=item_pk)
        services.remove_cart_item(item)
        messages.success(request, "Línea eliminada.")
        return redirect("pos:terminal_detail", pk=sale.pk)


class SetCustomerView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant, status=Sale.Status.DRAFT)
        form = CustomerSelectForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            services.set_cart_customer(sale, form.cleaned_data["customer"])
            messages.success(request, "Cliente actualizado.")
        else:
            messages.error(request, "Revisa el cliente seleccionado.")
        return redirect("pos:terminal_detail", pk=sale.pk)


class SetGlobalDiscountView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant, status=Sale.Status.DRAFT)
        form = GlobalDiscountForm(request.POST)
        if form.is_valid():
            try:
                services.set_cart_global_discount(
                    sale, user=request.user, tenant=request.tenant,
                    percent=form.cleaned_data["global_discount_percent"], amount=form.cleaned_data["global_discount_amount"],
                )
                messages.success(request, "Descuento global actualizado.")
            except services.DiscountRequiresApproval as error:
                solicitud = services.request_discount_approval(
                    request.tenant, sale, request.user,
                    percent_solicitado=error.requested_percent, amount_solicitado=error.requested_amount,
                    limite_percent=error.limit_percent, limite_amount=error.limit_amount,
                )
                messages.warning(
                    request,
                    f"El descuento global supera tu límite autorizado — se solicitó autorización (#{solicitud.pk}).",
                )
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa el descuento.")
        return redirect("pos:terminal_detail", pk=sale.pk)


class CancelCartView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant, status=Sale.Status.DRAFT)
        sales_services.cancel_sale(sale, request.user, reason="Cancelada desde el POS")
        messages.success(request, "Carrito cancelado.")
        return redirect("pos:terminal_start")


class CheckoutView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk, tenant=request.tenant, status=Sale.Status.DRAFT)
        formset = CheckoutPaymentFormSet(request.POST)
        if not formset.is_valid():
            messages.error(request, "Revisa los métodos de pago.")
            return redirect("pos:terminal_detail", pk=sale.pk)

        pagos = [
            {"method": fila["method"], "amount": fila["amount"]}
            for fila in formset.cleaned_data if fila.get("method") and fila.get("amount")
        ]
        if not pagos:
            messages.error(request, "Indica al menos un método de pago.")
            return redirect("pos:terminal_detail", pk=sale.pk)

        total_recibido = sum((p["amount"] for p in pagos), Decimal("0"))
        # El "cambio" se calcula aquí (nunca en apps.sales): solo se
        # aplica a la venta hasta el total, el resto es cambio a
        # entregar en efectivo.
        exceso = total_recibido - sale.total
        if exceso > 0:
            # Se descuenta el cambio del último método en efectivo indicado.
            for fila in reversed(pagos):
                if fila["method"] == "cash" and fila["amount"] >= exceso:
                    fila["amount"] -= exceso
                    exceso = Decimal("0")
                    break
            if exceso > 0:
                messages.error(request, "El cambio solo puede entregarse en efectivo; ajusta los montos.")
                return redirect("pos:terminal_detail", pk=sale.pk)

        try:
            venta_confirmada, pagos_creados = services.checkout_sale(sale, user=request.user, tenant=request.tenant, payments=pagos)
            cambio = total_recibido - sale.total if total_recibido > sale.total else Decimal("0")
            if cambio > 0:
                messages.success(request, f"Venta {venta_confirmada.number} cobrada. Cambio a entregar: {cambio}.")
            else:
                messages.success(request, f"Venta {venta_confirmada.number} cobrada correctamente.")
            return redirect("sales:sale_receipt", pk=venta_confirmada.pk)
        except services.CreditOverageRequiresApproval as error:
            solicitud = services.request_credit_overage_approval(
                request.tenant, sale, request.user, excedente=error.overage_amount, limite=error.limit,
            )
            messages.warning(
                request,
                f"Esta venta a crédito excede el límite del cliente — se solicitó autorización (#{solicitud.pk}). "
                "Pide a un supervisor que la apruebe y vuelve a cobrar.",
            )
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("pos:terminal_detail", pk=sale.pk)


# ------------------------------------------------------------------
# Cobros de cuentas por cobrar (facturas pendientes, anticipos, saldo a
# favor, notas de crédito, refunds)
# ------------------------------------------------------------------


class CollectionsSearchView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        query = request.GET.get("q", "")
        clientes = list_customers(request.tenant, search=query) if query else []
        return render(request, "pos/collections_search.html", {"query": query, "clientes": clientes})


class CustomerCollectionsView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, customer_pk):
        customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
        resumen = services.get_customer_credit_summary(customer)
        pagos_reembolsables = Payment.all_objects.filter(
            tenant=request.tenant, customer=customer, status=Payment.Status.CONFIRMED
        ).order_by("-created_at")
        saldos = sales_services.get_sale_balance_due_bulk(resumen["pending_sales"])
        context = {
            "customer": customer,
            "resumen": resumen,
            "pending_sales": [
                {"sale": venta, "balance_due": saldos.get(venta.pk)}
                for venta in resumen["pending_sales"]
            ],
            "collect_form": CollectPaymentForm(),
            "advance_form": CustomerAdvanceForm(),
            "credit_form": ApplyCreditForm(),
            "credit_note_form": IssueCreditNoteForm(),
            "refund_form": RefundForm(),
            "pagos": [
                {"payment": pago, "disponible": sales_services.get_unallocated_payment_amount(pago)}
                for pago in pagos_reembolsables
            ],
        }
        return render(request, "pos/customer_collections.html", context)


class CollectPaymentView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, customer_pk):
        customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
        form = CollectPaymentForm(request.POST)
        sale_ids = request.POST.getlist("sale_ids")
        if form.is_valid() and sale_ids:
            ventas = Sale.all_objects.filter(tenant=request.tenant, customer=customer, pk__in=sale_ids)
            allocations = []
            restante = form.cleaned_data["amount"]
            for venta in ventas:
                if restante <= 0:
                    break
                saldo = sales_services.get_sale_balance_due(venta)
                monto = min(saldo, restante)
                if monto > 0:
                    allocations.append({"sale": venta, "amount": monto})
                    restante -= monto
            try:
                services.collect_customer_payment(
                    request.tenant, customer=customer, method=form.cleaned_data["method"],
                    amount=form.cleaned_data["amount"], user=request.user, allocations=allocations,
                    reference=form.cleaned_data["reference"],
                )
                messages.success(request, "Pago aplicado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Selecciona al menos una factura pendiente e indica el monto.")
        return redirect("pos:customer_collections", customer_pk=customer.pk)


class AdvanceView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, customer_pk):
        customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
        form = CustomerAdvanceForm(request.POST)
        if form.is_valid():
            try:
                services.register_customer_advance(
                    request.tenant, customer=customer, method=form.cleaned_data["method"],
                    amount=form.cleaned_data["amount"], user=request.user,
                    reference=form.cleaned_data["reference"], notes=form.cleaned_data["notes"],
                )
                messages.success(request, "Anticipo registrado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del anticipo.")
        return redirect("pos:customer_collections", customer_pk=customer.pk)


class ApplyCreditView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, customer_pk, sale_pk):
        customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
        sale = get_object_or_404(Sale, pk=sale_pk, tenant=request.tenant, customer=customer)
        form = ApplyCreditForm(request.POST)
        if form.is_valid():
            try:
                services.apply_customer_credit_to_sale(customer, sale, form.cleaned_data["amount"], request.user)
                messages.success(request, "Saldo a favor aplicado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa el monto a aplicar.")
        return redirect("pos:customer_collections", customer_pk=customer.pk)


class IssueCreditNoteView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, customer_pk):
        customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
        form = IssueCreditNoteForm(request.POST)
        if form.is_valid():
            try:
                services.issue_customer_credit_note(
                    request.tenant, customer=customer, amount=form.cleaned_data["amount"], user=request.user,
                    reason=form.cleaned_data["reason"],
                )
                messages.success(request, "Nota de crédito emitida correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos de la nota de crédito.")
        return redirect("pos:customer_collections", customer_pk=customer.pk)


class RefundView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, customer_pk, payment_pk):
        customer = get_object_or_404(Customer, pk=customer_pk, tenant=request.tenant)
        payment = get_object_or_404(Payment, pk=payment_pk, tenant=request.tenant, customer=customer)
        form = RefundForm(request.POST)
        if form.is_valid():
            try:
                if form.cleaned_data["mode"] == "cash":
                    services.refund_payment_cash(
                        payment, form.cleaned_data["amount"], request.user, reason=form.cleaned_data["reason"],
                    )
                else:
                    services.refund_payment_to_credit(
                        payment, form.cleaned_data["amount"], request.user, reason=form.cleaned_data["reason"],
                    )
                messages.success(request, "Reembolso procesado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del reembolso.")
        return redirect("pos:customer_collections", customer_pk=customer.pk)
