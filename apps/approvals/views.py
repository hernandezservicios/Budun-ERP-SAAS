"""
Vistas del servicio de autorizaciones (FASE 11). Deliberadamente
delgadas: toda la lógica vive en `services.py`. Resolver una solicitud
y administrar políticas están restringidos a quien pueda aprobar/al
propietario — nunca solo ocultando el botón en la plantilla.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.tenants.models import Membership
from apps.tenants.permissions import TenantRequiredMixin, require_role

from . import services
from .forms import ResolveApprovalForm, RolePolicyForm
from .models import ApprovalRequest


def _mensaje_error(error):
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


class PendingApprovalsView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "approvals/pending_list.html"
    context_object_name = "solicitudes"

    def get_queryset(self):
        return services.get_pending_requests(self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["puede_resolver"] = services.can_user_approve(self.request.tenant, self.request.user)
        context["historial"] = services.get_request_history(self.request.tenant, limit=20)
        return context


class ApprovalResolveView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        solicitud = get_object_or_404(ApprovalRequest, pk=pk, tenant=request.tenant)
        if not services.can_user_approve(request.tenant, request.user):
            raise PermissionDenied("No tienes permiso para resolver solicitudes de autorización.")
        form = ResolveApprovalForm(request.POST)
        if form.is_valid():
            try:
                services.resolve_approval(
                    solicitud,
                    approved=form.cleaned_data["decision"] == "approve",
                    user=request.user,
                    approved_value=form.cleaned_data["approved_value"] or solicitud.requested_value,
                    decision_reason=form.cleaned_data["decision_reason"],
                )
                messages.success(request, "Solicitud resuelta correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos de la decisión.")
        return redirect("approvals:pending_list")


class ApprovalCancelView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        solicitud = get_object_or_404(ApprovalRequest, pk=pk, tenant=request.tenant)
        services.cancel_approval(solicitud, request.user)
        messages.success(request, "Solicitud cancelada.")
        return redirect("approvals:pending_list")


class PolicyListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_role(request, Membership.Role.OWNER)
        context = {
            "politicas": services.get_policies(request.tenant),
            "role_form": RolePolicyForm(),
        }
        return render(request, "approvals/policy_list.html", context)


class RolePolicySetView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        require_role(request, Membership.Role.OWNER)
        form = RolePolicyForm(request.POST)
        if form.is_valid():
            services.set_role_policy(
                request.tenant,
                role=form.cleaned_data["role"],
                max_discount_percent=form.cleaned_data["max_discount_percent"],
                max_discount_amount=form.cleaned_data["max_discount_amount"],
                max_credit_overage=form.cleaned_data["max_credit_overage"],
                max_purchase_order_amount=form.cleaned_data["max_purchase_order_amount"],
                max_over_receiving_percent=form.cleaned_data["max_over_receiving_percent"],
                max_expense_amount=form.cleaned_data["max_expense_amount"],
                can_approve=form.cleaned_data["can_approve"],
                notes=form.cleaned_data["notes"],
            )
            messages.success(request, "Política de rol guardada correctamente.")
        else:
            messages.error(request, "Revisa los datos de la política.")
        return redirect("approvals:policy_list")
