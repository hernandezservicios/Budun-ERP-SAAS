"""
Portal de Billing del propio tenant (FASE 17, `/facturacion/`, ver
`docs/billing.md` sección 49). El tenant ve/gestiona SU suscripción —
nunca la de otro (siempre filtrado por `request.tenant`, nunca por un
id enviado por el cliente). Nunca acciones administrativas de
plataforma (aprobar transferencias, reembolsar, etc. — eso es
`apps.billing.admin_views`, exclusivo `is_superuser`)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.permissions.services import require_permission
from apps.tenants.permissions import TenantRequiredMixin

from . import services as paypal_services
from .models import BankAccount, PayPalTransaction, SaaSCustomer, SaaSInvoice, Subscription
from .portal_forms import CancelSubscriptionForm, ChangePlanForm, SelectPlanForm, UploadProofForm
from .services import coupons as coupon_services
from .services import credits as credit_services
from .services import invoicing as invoicing_services
from .services import subscriptions as subscription_services
from .services import transfers as transfer_services


def _current_subscription(tenant):
    return Subscription.all_objects.filter(tenant=tenant).select_related("plan_version__plan").order_by("-created_at").first()


def _ensure_saas_customer(tenant, user):
    if tenant.saas_customer is not None:
        return tenant.saas_customer
    saas_customer = SaaSCustomer.objects.create(name=str(tenant), email=user.email, created_by=user)
    tenant.saas_customer = saas_customer
    tenant.save(update_fields=["saas_customer"])
    return saas_customer


class BillingPortalStatusView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_permission(request, "billing.saas.view")
        subscription = _current_subscription(request.tenant)
        contexto = {"subscription": subscription, "tenant": request.tenant}
        if subscription is not None:
            contexto["invoices"] = SaaSInvoice.all_objects.filter(tenant=request.tenant).order_by("-issue_date")[:10]
            contexto["credit_balance"] = credit_services.get_subscription_credit_balance(tenant=request.tenant, subscription=subscription)
        return render(request, "billing/portal_status.html", contexto)


class SelectPlanView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_permission(request, "billing.saas.manage")
        return render(request, "billing/portal_select_plan.html", {"form": SelectPlanForm()})

    def post(self, request):
        require_permission(request, "billing.saas.manage")
        form = SelectPlanForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa el plan y método de pago seleccionados.")
            return render(request, "billing/portal_select_plan.html", {"form": form})

        plan_version = form.cleaned_data["plan_version"]
        metodo = form.cleaned_data["payment_method"]
        codigo_cupon = (form.cleaned_data.get("coupon_code") or "").strip()

        cupon = None
        if codigo_cupon:
            try:
                cupon = coupon_services.validate_coupon(codigo_cupon)
            except coupon_services.InvalidCouponOperation as error:
                messages.error(request, str(error))
                return render(request, "billing/portal_select_plan.html", {"form": form})

        saas_customer = _ensure_saas_customer(request.tenant, request.user)
        subscription = _current_subscription(request.tenant)
        if subscription is not None and subscription.status == Subscription.Status.PENDING:
            subscription.plan_version = plan_version
            subscription.coupon = cupon
            subscription.save(update_fields=["plan_version", "coupon"])
        else:
            try:
                subscription = subscription_services.create_subscription(
                    request.tenant, saas_customer=saas_customer, plan_version=plan_version, coupon=cupon, user=request.user,
                )
            except subscription_services.InvalidSubscriptionOperation as error:
                messages.error(request, str(error))
                return redirect("billing_portal:status")

        invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription, user=request.user)

        if metodo == "paypal":
            return redirect("billing_portal:checkout_paypal_initiate", invoice_id=invoice.pk)
        return redirect("billing_portal:transfer_instructions", invoice_id=invoice.pk)


class CheckoutPayPalInitiateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, invoice_id):
        require_permission(request, "billing.saas.manage")
        invoice = get_object_or_404(SaaSInvoice, pk=invoice_id, tenant=request.tenant)
        from .services import payments as payment_services

        pago = payment_services.record_payment(
            tenant=request.tenant, saas_customer=invoice.subscription.saas_customer, subscription=invoice.subscription,
            method="paypal", amount=invoice.total, currency=invoice.currency, user=request.user,
        )
        try:
            txn, approve_url = paypal_services.create_checkout(
                tenant=request.tenant, plan_id=invoice.subscription.plan_version.plan.slug,
                purpose=(PayPalTransaction.Purpose.RENEWAL if invoice.subscription.started_at else PayPalTransaction.Purpose.SIGNUP),
                user=request.user, description=f"Factura {invoice.number}",
                return_url=request.build_absolute_uri(reverse("billing_portal:checkout_paypal_return", args=[invoice.pk])),
                cancel_url=request.build_absolute_uri(reverse("billing_portal:checkout_paypal_cancel", args=[invoice.pk])),
            )
        except paypal_services.InvalidBillingOperation as error:
            messages.error(request, str(error))
            return redirect("billing_portal:status")
        pago.paypal_transaction = txn
        pago.save(update_fields=["paypal_transaction"])
        return redirect(approve_url)


class CheckoutPayPalReturnView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, invoice_id):
        order_id = request.GET.get("token", "")
        txn = get_object_or_404(PayPalTransaction, external_order_id=order_id, tenant=request.tenant)
        paypal_services.capture_checkout(txn, user=request.user)
        messages.info(request, "Procesando tu pago — si ya fue aprobado, se reflejará en unos segundos.")
        return redirect("billing_portal:status")


class CheckoutPayPalCancelView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, invoice_id):
        order_id = request.GET.get("token", "")
        txn = get_object_or_404(PayPalTransaction, external_order_id=order_id, tenant=request.tenant)
        paypal_services.cancel_checkout(txn, user=request.user)
        messages.warning(request, "Pago cancelado.")
        return redirect("billing_portal:status")


class TransferInstructionsView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, invoice_id):
        require_permission(request, "billing.saas.view")
        invoice = get_object_or_404(SaaSInvoice, pk=invoice_id, tenant=request.tenant)
        return render(request, "billing/portal_transfer_instructions.html", {
            "invoice": invoice, "bank_accounts": BankAccount.objects.filter(is_active=True), "form": UploadProofForm(),
        })

    def post(self, request, invoice_id):
        require_permission(request, "billing.saas.manage")
        invoice = get_object_or_404(SaaSInvoice, pk=invoice_id, tenant=request.tenant)
        form = UploadProofForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Revisa los datos del comprobante.")
            return render(request, "billing/portal_transfer_instructions.html", {
                "invoice": invoice, "bank_accounts": BankAccount.objects.filter(is_active=True), "form": form,
            })
        try:
            transfer_services.submit_payment_proof(
                subscription=invoice.subscription, invoice=invoice, bank_account=form.cleaned_data["bank_account"],
                declared_amount=form.cleaned_data["declared_amount"], declared_currency=form.cleaned_data["declared_currency"],
                declared_bank_name=form.cleaned_data.get("declared_bank_name", ""), file=form.cleaned_data["file"], user=request.user,
            )
        except Exception as error:  # noqa: BLE001 — validación de archivo puede lanzar ValidationError u otros.
            messages.error(request, str(error))
            return render(request, "billing/portal_transfer_instructions.html", {
                "invoice": invoice, "bank_accounts": BankAccount.objects.filter(is_active=True), "form": form,
            })
        messages.success(request, "Comprobante enviado — tu pago quedará en revisión.")
        return redirect("billing_portal:status")


class ChangePlanView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_permission(request, "billing.saas.manage")
        subscription = _current_subscription(request.tenant)
        if subscription is None or not subscription.is_effectively_operational:
            messages.error(request, "No tienes una suscripción activa para cambiar de plan.")
            return redirect("billing_portal:status")
        return render(request, "billing/portal_change_plan.html", {"form": ChangePlanForm(), "subscription": subscription})

    def post(self, request):
        require_permission(request, "billing.saas.manage")
        subscription = _current_subscription(request.tenant)
        form = ChangePlanForm(request.POST)
        if subscription is None or not form.is_valid():
            messages.error(request, "Revisa el plan seleccionado.")
            return redirect("billing_portal:change_plan")
        subscription, desglose, nota = subscription_services.change_plan(
            subscription, new_plan_version=form.cleaned_data["plan_version"], user=request.user,
        )
        if nota is not None:
            messages.success(request, f"Cambio realizado — se emitió una nota de crédito de {nota.amount} {nota.currency}.")
        else:
            messages.success(request, "Cambio de plan realizado.")
        return redirect("billing_portal:status")


class CancelSubscriptionView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        require_permission(request, "billing.saas.manage")
        subscription = _current_subscription(request.tenant)
        form = CancelSubscriptionForm(request.POST)
        if subscription is None or not form.is_valid():
            messages.error(request, "No se pudo procesar la cancelación.")
            return redirect("billing_portal:status")
        subscription_services.cancel_subscription(
            subscription, immediate=form.cleaned_data.get("immediate", False),
            reason=form.cleaned_data.get("reason", ""), user=request.user,
        )
        messages.success(request, "Solicitud de cancelación procesada.")
        return redirect("billing_portal:status")
