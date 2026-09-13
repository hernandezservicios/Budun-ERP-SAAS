"""
Administración de plataforma de Billing SaaS (FASE 17,
`/plataforma/billing/admin/`) — exclusiva `is_superuser`
(`apps.tenants.permissions.require_superuser`/`SuperuserRequiredMixin`,
mismo criterio ya establecido en FASE 16 para `apps.billing.
platform_views`: este es un recurso de PLATAFORMA, el catálogo
tenant-scoped de `apps.permissions` no aplica). Nunca Django Admin como
UI (CLAUDE.md) — pantallas propias con el Design System del proyecto."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views import View

from apps.accounts import services as account_services
from apps.customers.file_validation import nombre_original_seguro
from apps.tenants.models import Membership, Tenant
from apps.tenants.permissions import SuperuserRequiredMixin

from .admin_forms import BankAccountForm, CreditNoteIssueForm, ManualTenantSaleForm, PlanForm, PlanVersionForm, ProofRejectForm, RefundRequestForm
from .models import (
    BankAccount,
    BillingRefund,
    CreditNote,
    Plan,
    PlanVersion,
    SaaSCustomer,
    SaaSInvoice,
    SaaSPayment,
    Subscription,
)
from .services import credits as credit_services
from .services import invoicing as invoicing_services
from .services import refunds as refund_services
from .services import reports as report_services
from .services import subscriptions as subscription_services
from .services import tenants as tenant_lifecycle_services
from .services import transfers as transfer_services

User = get_user_model()


class DashboardView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/dashboard.html", {"resumen": report_services.get_billing_dashboard_summary()})


# ---------------------------------------------------------------------
# Clientes SaaS
# ---------------------------------------------------------------------

class CustomersListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/customers_list.html", {
            "customers": SaaSCustomer.objects.all().order_by("name"),
        })


class CustomerDetailView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request, pk):
        customer = get_object_or_404(SaaSCustomer, pk=pk)
        return render(request, "billing/admin/customer_detail.html", {
            "customer": customer, "tenants": customer.tenants.all(),
            "subscriptions": Subscription.all_objects.filter(saas_customer=customer).select_related("plan_version__plan"),
        })


# ---------------------------------------------------------------------
# Tenants (estado de Billing)
# ---------------------------------------------------------------------

class TenantsListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/tenants_list.html", {"tenants": Tenant.objects.all().order_by("name")})


class TenantDetailView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk)
        subscription = Subscription.all_objects.filter(tenant=tenant).order_by("-created_at").first()
        return render(request, "billing/admin/tenant_detail.html", {
            "tenant": tenant, "subscription": subscription,
            "invoices": SaaSInvoice.all_objects.filter(tenant=tenant).order_by("-issue_date")[:20],
        })

    def post(self, request, pk):
        tenant = get_object_or_404(Tenant, pk=pk)
        accion = request.POST.get("accion")
        subscription = Subscription.all_objects.filter(tenant=tenant).order_by("-created_at").first()
        try:
            if accion == "activar":
                # ACTIVATE != REACTIVATE (Gate Local, sección 5): acción
                # explícita propia, solo para una Subscription PENDING —
                # nunca reutiliza reactivar (exclusivo SUSPENDED/PAST_DUE).
                if subscription is None:
                    raise ValidationError("Este tenant no tiene ninguna suscripción que activar.")
                subscription_services.activate_pending_subscription(
                    subscription, user=request.user, reference="Activación manual por Super Admin",
                )
            elif accion == "suspender":
                if subscription is not None:
                    subscription_services.suspend_subscription(subscription, user=request.user, reason="Suspendido manualmente por Super Admin")
                else:
                    tenant_lifecycle_services.suspend_tenant(tenant, user=request.user, reason="Suspendido manualmente por Super Admin")
            elif accion == "reactivar":
                if subscription is not None:
                    subscription_services.reactivate_subscription(subscription, user=request.user)
                else:
                    tenant_lifecycle_services.reactivate_tenant(tenant, user=request.user)
            elif accion == "cancelar":
                if subscription is not None:
                    subscription_services.cancel_subscription(subscription, immediate=True, reason="Cancelado manualmente por Super Admin", user=request.user)
                else:
                    tenant_lifecycle_services.cancel_tenant(tenant, user=request.user)
        except ValidationError as error:
            # Antes de este fix, una transición inválida (ej. "Reactivar"
            # sobre una Subscription PENDING) no se atrapaba aquí y
            # producía un error 500 sin manejar — ver KNOWN_ISSUES.md.
            mensaje = error.messages[0] if hasattr(error, "messages") and error.messages else str(error)
            messages.error(request, mensaje)
            return redirect("billing_admin:tenant_detail", pk=pk)

        messages.success(request, "Estado actualizado.")
        return redirect("billing_admin:tenant_detail", pk=pk)


class ManualTenantSaleView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    """Sección 16 de la fase: alta manual completa desde Super Admin —
    SIEMPRE crea una `Subscription` real vía el mismo núcleo de Billing,
    nunca escribe `Tenant.billing_status=ACTIVE` directamente."""

    def get(self, request):
        return render(request, "billing/admin/manual_sale.html", {"form": ManualTenantSaleForm()})

    def post(self, request):
        form = ManualTenantSaleForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa los datos del formulario.")
            return render(request, "billing/admin/manual_sale.html", {"form": form})

        with transaction.atomic():
            base_slug = slugify(form.cleaned_data["tenant_name"]) or "empresa"
            slug, sufijo = base_slug, 1
            while Tenant.objects.filter(slug=slug).exists():
                sufijo += 1
                slug = f"{base_slug}-{sufijo}"

            saas_customer = SaaSCustomer.objects.create(
                name=form.cleaned_data["customer_name"], email=form.cleaned_data["customer_email"], created_by=request.user,
            )
            # billing_status=PENDING_SETUP explícito — mismo motivo que
            # apps.accounts.views.OnboardingView: el default del campo
            # es ACTIVE por compatibilidad con tenants preexistentes,
            # pero todo tenant NUEVO (también los creados manualmente
            # por Super Admin) debe pasar por Billing antes de operar.
            tenant = Tenant.objects.create(
                name=form.cleaned_data["tenant_name"], slug=slug, saas_customer=saas_customer,
                billing_status=Tenant.BillingStatus.PENDING_SETUP,
            )

            owner, _creado = User.objects.get_or_create(
                email=form.cleaned_data["owner_email"], defaults={"is_active": True},
            )
            if _creado:
                owner.set_unusable_password()
                owner.save()
            Membership.objects.create(user=owner, tenant=tenant, role=Membership.Role.OWNER)

            subscription = subscription_services.create_subscription(
                tenant, saas_customer=saas_customer, plan_version=form.cleaned_data["plan_version"], user=request.user,
            )
            # Gate Local (hallazgo real, ver KNOWN_ISSUES.md): la venta
            # manual creaba la Subscription pero nunca generaba su
            # primera SaaSInvoice — el tenant quedaba "pendiente de
            # pago" sin ninguna factura real contra la cual pagar.
            # `generate_invoice_for_subscription` es idempotente
            # (UniqueConstraint(subscription, period_start) real de
            # base de datos), así que llamarla aquí nunca duplica nada
            # si en el futuro se reintenta esta operación.
            invoicing_services.generate_invoice_for_subscription(subscription, user=request.user)
            # PENDING_SETUP → PENDING_PAYMENT: ya existe una factura real
            # esperando pago — un estado más preciso que "configuración
            # pendiente" a secas (sección 3 del Gate Local). Nunca ACTIVE:
            # activar sin pago aprobado es exactamente lo que esta fase
            # prohíbe (ver `activate_pending_subscription`).
            tenant_lifecycle_services.mark_tenant_pending_payment(tenant, user=request.user)

        mensaje = f"Tenant «{tenant.name}» creado con su factura inicial — pendiente de pago/activación."
        if _creado:
            # FASE DE CORRECCIÓN 1 (Acceso del Owner y ciclo de vida del
            # Tenant): el Owner se acaba de crear con contraseña
            # inutilizable — no puede iniciar sesión hasta activar su
            # cuenta. Se envía DESPUÉS de que el `with transaction.
            # atomic()` de arriba ya cerró (Tenant/Owner/Membership/
            # Subscription/Invoice ya están confirmados) para nunca
            # enviar un correo sobre datos que terminaran revertidos por
            # un error posterior dentro de la transacción. Un fallo de
            # envío nunca bloquea la venta — se le muestra el enlace
            # directamente al Super Admin para compartirlo a mano.
            enviado, activation_url = account_services.send_account_activation_email(owner, request=request)
            if enviado:
                mensaje += " Se envió un correo de activación al Owner para que establezca su contraseña."
            else:
                mensaje += (
                    " No se pudo enviar el correo de activación — comparte este enlace "
                    f"manualmente con el Owner: {activation_url}"
                )
        messages.success(request, mensaje)
        return redirect("billing_admin:tenant_detail", pk=tenant.pk)


# ---------------------------------------------------------------------
# Planes
# ---------------------------------------------------------------------

class PlansListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/plans_list.html", {
            "plans": Plan.objects.all(), "plan_form": PlanForm(), "version_form": PlanVersionForm(),
        })

    def post(self, request):
        form = PlanForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Plan creado.")
        else:
            messages.error(request, "Revisa los datos del plan.")
        return redirect("billing_admin:plans_list")


class PlanVersionCreateView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def post(self, request, plan_id):
        plan = get_object_or_404(Plan, pk=plan_id)
        form = PlanVersionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa el precio/frecuencia.")
            return redirect("billing_admin:plans_list")
        with transaction.atomic():
            PlanVersion.objects.filter(plan=plan, frequency=form.cleaned_data["frequency"], is_current=True).update(is_current=False)
            version = form.save(commit=False)
            version.plan = plan
            version.is_current = True
            version.created_by = request.user
            version.save()
        messages.success(request, "Nueva versión de precio creada — la anterior queda como histórica.")
        return redirect("billing_admin:plans_list")


# ---------------------------------------------------------------------
# Suscripciones / Facturas / Pagos (solo lectura + drill-down)
# ---------------------------------------------------------------------

class SubscriptionsListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/subscriptions_list.html", {
            "resumen": report_services.get_subscriptions_report(),
        })


class InvoicesListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/invoices_list.html", {
            "invoices": SaaSInvoice.all_objects.select_related("tenant").order_by("-issue_date")[:100],
        })


class InvoiceDetailView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request, pk):
        from .models import CreditNoteApplication, SaaSInvoiceLine, SaaSPaymentAllocation
        from .services.invoicing import get_invoice_balance_due

        invoice = get_object_or_404(SaaSInvoice.all_objects.select_related("tenant", "subscription"), pk=pk)
        return render(request, "billing/admin/invoice_detail.html", {
            "invoice": invoice, "saldo": get_invoice_balance_due(invoice),
            "lines": SaaSInvoiceLine.all_objects.filter(invoice=invoice),
            "allocations": SaaSPaymentAllocation.all_objects.filter(invoice=invoice).select_related("payment"),
            "credit_applications": CreditNoteApplication.all_objects.filter(invoice=invoice).select_related("credit_note"),
        })


class PaymentsListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/payments_list.html", {
            "payments": SaaSPayment.all_objects.select_related("tenant", "saas_customer").order_by("-created_at")[:100],
        })


# ---------------------------------------------------------------------
# Transferencias / Verificación
# ---------------------------------------------------------------------

class TransfersQueueView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/transfers_queue.html", {"proofs": transfer_services.list_pending_proofs()})


class ProofDetailView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request, pk):
        from .models import PaymentProof

        proof = get_object_or_404(PaymentProof.all_objects.select_related("tenant", "subscription", "invoice", "bank_account"), pk=pk)
        return render(request, "billing/admin/proof_detail.html", {"proof": proof, "reject_form": ProofRejectForm()})

    def post(self, request, pk):
        from .models import PaymentProof

        # `all_objects` explícito: `PaymentProof` hereda `TenantScopedModel`
        # y el Super Admin no tiene ningún tenant activo en el ContextVar
        # — `get_object_or_404(PaymentProof, ...)` usaría el manager
        # tenant-scoped por defecto y siempre devolvería 404 (mismo
        # bug-class que `get_invoice_balance_due`, ver KNOWN_ISSUES.md).
        proof = get_object_or_404(PaymentProof.all_objects, pk=pk)
        accion = request.POST.get("accion")
        try:
            if accion == "aprobar":
                transfer_services.approve_payment_proof(proof, user=request.user)
                messages.success(request, "Comprobante aprobado — pago registrado y aplicado.")
            elif accion == "rechazar":
                form = ProofRejectForm(request.POST)
                if form.is_valid():
                    transfer_services.reject_payment_proof(proof, reason=form.cleaned_data["reason"], user=request.user)
                    messages.success(request, "Comprobante rechazado.")
                else:
                    messages.error(request, "Indica el motivo del rechazo.")
        except ValidationError as error:
            # FASE DE CORRECCIÓN 4 (sección 18): una transición inválida
            # (aprobar uno ya rechazado, rechazar uno ya aprobado — p. ej.
            # dos pestañas del Super Admin operando el mismo comprobante a
            # la vez) nunca debe producir un error 500 sin manejar — mismo
            # criterio ya aplicado en `TenantDetailView.post()`.
            mensaje = error.messages[0] if hasattr(error, "messages") and error.messages else str(error)
            messages.error(request, mensaje)
        return redirect("billing_admin:proof_detail", pk=pk)


class ProofDownloadView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    """FASE DE CORRECCIÓN 4 (sección 5, "consultar comprobante"): antes
    de esta corrección, el Super Admin no tenía NINGUNA forma de ver el
    contenido real del comprobante subido — `proof_detail.html` solo
    mostraba el nombre de archivo como texto plano, sin ningún enlace —
    así que aprobar o rechazar una transferencia se decidía
    completamente A CIEGAS, confiando únicamente en los metadatos
    declarados por el propio tenant. Nunca servido por `MEDIA_URL`
    estático (`PaymentProof.file` vive en `media-private/`) — solo por
    esta vista protegida. `all_objects` explícito (mismo motivo que el
    resto de este archivo: el Super Admin no tiene tenant activo en el
    ContextVar)."""

    def get(self, request, pk):
        from apps.audit.models import AuditLog

        from .models import PaymentProof
        from .services._saas_audit import audit_event

        proof = get_object_or_404(PaymentProof.all_objects, pk=pk)
        audit_event(
            proof.tenant, action=AuditLog.Action.GENERIC, user=request.user, object_type="payment_proof", object_id=proof.pk,
            reason="Comprobante descargado por Super Admin",
        )
        return FileResponse(
            proof.file.open("rb"), as_attachment=True, filename=nombre_original_seguro(proof.original_filename),
        )


# ---------------------------------------------------------------------
# Notas de crédito / Refunds
# ---------------------------------------------------------------------

class CreditNotesListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/credit_notes_list.html", {
            "credit_notes": CreditNote.all_objects.select_related("tenant", "saas_customer").order_by("-created_at")[:100],
        })


class IssueCreditNoteView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def post(self, request, customer_id):
        customer = get_object_or_404(SaaSCustomer, pk=customer_id)
        form = CreditNoteIssueForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa el monto/motivo.")
            return redirect("billing_admin:customer_detail", pk=customer_id)
        tenant = customer.tenants.first()
        credit_services.issue_credit_note(
            tenant=tenant, saas_customer=customer, amount=form.cleaned_data["amount"], currency=form.cleaned_data["currency"],
            reason=form.cleaned_data["reason"], user=request.user,
        )
        messages.success(request, "Nota de crédito emitida.")
        return redirect("billing_admin:customer_detail", pk=customer_id)


class RefundsListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/refunds_list.html", {
            "refunds": BillingRefund.all_objects.select_related("tenant", "payment").order_by("-created_at")[:100],
        })


class RequestRefundView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def post(self, request, payment_id):
        payment = get_object_or_404(SaaSPayment.all_objects, pk=payment_id)
        form = RefundRequestForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Revisa el monto del reembolso.")
        else:
            try:
                refund_services.request_billing_refund(
                    payment, amount=form.cleaned_data.get("amount") or None, reason=form.cleaned_data.get("reason", ""), user=request.user,
                )
                messages.success(request, "Reembolso solicitado.")
            except refund_services.InvalidRefundOperation as error:
                messages.error(request, str(error))
        return redirect("billing_admin:payments_list")


class CompleteManualRefundView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def post(self, request, pk):
        refund = get_object_or_404(BillingRefund.all_objects, pk=pk)
        refund_services.complete_manual_refund(refund, user=request.user)
        messages.success(request, "Reembolso marcado como completado.")
        return redirect("billing_admin:refunds_list")


# ---------------------------------------------------------------------
# Cuentas bancarias
# ---------------------------------------------------------------------

class BankAccountsListView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/bank_accounts_list.html", {
            "bank_accounts": BankAccount.objects.all(), "form": BankAccountForm(),
        })

    def post(self, request):
        form = BankAccountForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Cuenta bancaria creada.")
        else:
            messages.error(request, "Revisa los datos de la cuenta.")
        return redirect("billing_admin:bank_accounts_list")


# ---------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------

class ReportsView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def get(self, request):
        return render(request, "billing/admin/reports.html", {
            "resumen_dashboard": report_services.get_billing_dashboard_summary(),
            "ingresos": report_services.get_revenue_report(),
            "suscripciones": report_services.get_subscriptions_report(),
            "aging": report_services.get_invoice_aging_report(),
        })
