"""
UI de plataforma para PayPal/Billing SaaS (FASE 16) — exclusiva del
Super Admin (`SuperuserRequiredMixin`, ver `apps.tenants.permissions`),
NUNCA parte del hub «Configuración» del tenant (`apps.core`): esto no
es configuración de un tenant, es configuración del operador del SaaS.

Esta pantalla es deliberadamente una herramienta de operación/prueba
del mecanismo de PayPal (Test Connection, iniciar un cobro real de
Sandbox, ver transacciones/webhooks, reembolsar) — no el flujo de venta
de autoservicio (Landing → Pricing → Plan) ni la administración
completa de Billing (planes, suscripciones, transferencias), que son
FASE 17 (ver `docs/billing.md`)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.tenants.permissions import SuperuserRequiredMixin

from . import services
from .forms import CheckoutCreateForm, RefundForm
from .models import PayPalTransaction, SaaSPayment


class GatewayStatusView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/gateway_status.html", {
            "status": services.get_gateway_status(),
            "transacciones": PayPalTransaction.objects.select_related("tenant")[:20],
        })

    def post(self, request):
        accion = request.POST.get("accion")
        if accion == "probar_conexion":
            ok, error = services.test_paypal_connection(user=request.user)
            if ok:
                messages.success(request, "Conectado — las credenciales de PayPal son válidas.")
            else:
                messages.error(request, f"No conectado: {error}")
        elif accion == "alternar_habilitado":
            status = services.get_gateway_status()
            services.set_gateway_enabled(is_enabled=not status.is_enabled, user=request.user)
            messages.success(request, "Estado del checkout actualizado.")
        return redirect("billing_platform:status")


class CheckoutCreateView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/checkout_create.html", {"form": CheckoutCreateForm()})

    def post(self, request):
        form = CheckoutCreateForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa el tenant, plan y propósito seleccionados.")
            return render(request, "billing/checkout_create.html", {"form": form})
        try:
            txn, approve_url = services.create_checkout(
                tenant=form.cleaned_data["tenant"], plan_id=form.cleaned_data["plan_id"],
                purpose=form.cleaned_data["purpose"], user=request.user,
                return_url=request.build_absolute_uri(reverse("billing_platform:checkout_return")),
                cancel_url=request.build_absolute_uri(reverse("billing_platform:checkout_cancel")),
            )
        except services.InvalidBillingOperation as error:
            messages.error(request, str(error))
            return render(request, "billing/checkout_create.html", {"form": form})
        return redirect(approve_url)


class CheckoutReturnView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    """PayPal redirige aquí tras la aprobación del pagador (`?token=
    <order id>`, mismo `external_order_id` que guardamos al crear la
    orden) — la captura real ocurre aquí, síncronamente, nunca
    confiando solo en el redirect del navegador (ver `docs/paypal.md`
    sección 6): si el webhook llega después, `capture_checkout`/la
    aplicación del webhook son idempotentes."""

    def get(self, request):
        order_id = request.GET.get("token", "")
        txn = get_object_or_404(PayPalTransaction, external_order_id=order_id)
        txn = services.capture_checkout(txn, user=request.user)
        return render(request, "billing/checkout_result.html", {"transaccion": txn})


class CheckoutCancelView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        order_id = request.GET.get("token", "")
        txn = get_object_or_404(PayPalTransaction, external_order_id=order_id)
        txn = services.cancel_checkout(txn, user=request.user)
        return render(request, "billing/checkout_result.html", {"transaccion": txn})


class TransactionDetailView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request, pk):
        txn = get_object_or_404(PayPalTransaction, pk=pk)
        return render(request, "billing/transaction_detail.html", {
            "transaccion": txn, "refund_form": RefundForm(),
            "eventos": txn.webhook_events.all()[:20],
            # Gate Local (ver KNOWN_ISSUES.md): esta transacción solo
            # activa algo de Billing si un SaaSPayment real la referencia
            # (ver apps.billing.services.paypal_integration) — nunca por
            # el solo hecho de tener Order/Capture ID, aunque esté
            # `confirmed` (sección 13 del Gate Local: "no permitir
            # activación solo porque exista PayPalTransaction/Order ID/
            # Capture ID").
            "tiene_saas_payment": SaaSPayment.all_objects.filter(paypal_transaction=txn).exists(),
        })

    def post(self, request, pk):
        txn = get_object_or_404(PayPalTransaction, pk=pk)
        form = RefundForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa el monto del reembolso.")
            return redirect("billing_platform:transaction_detail", pk=pk)
        try:
            services.request_refund(
                txn, user=request.user,
                amount=form.cleaned_data.get("amount") or None, reason=form.cleaned_data.get("reason", ""),
            )
        except services.InvalidBillingOperation as error:
            messages.error(request, str(error))
            return redirect("billing_platform:transaction_detail", pk=pk)
        messages.success(request, "Reembolso solicitado.")
        return redirect("billing_platform:transaction_detail", pk=pk)
