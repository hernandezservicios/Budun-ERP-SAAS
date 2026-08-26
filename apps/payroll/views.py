"""
Vistas de Nómina (FASE 13). Deliberadamente delgadas: toda la lógica
vive en `apps.payroll.services`, que a su vez consume literalmente
`apps.hr` (Employee), `apps.approvals` (aprobación de período) y
`apps.pos` (caja para pagos en efectivo) — esta capa solo arma el
request/response.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import PayrollCalculateForm, PayrollLineForm, PayrollPaymentForm, PayrollPeriodForm
from .models import Payroll, PayrollPayment, PayrollPeriod


def _mensaje_error(error):
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


class PayrollPeriodListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {"periodos": services.list_payroll_periods(request.tenant), "form": PayrollPeriodForm()}
        return render(request, "payroll/period_list.html", context)

    def post(self, request):
        form = PayrollPeriodForm(request.POST)
        if form.is_valid():
            try:
                periodo = services.create_payroll_period(request.tenant, user=request.user, **form.cleaned_data)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
                return redirect("payroll:period_list")
            messages.success(request, f"Período «{periodo.number}» creado correctamente.")
            return redirect("payroll:period_detail", pk=periodo.pk)
        messages.error(request, "Revisa las fechas del período.")
        return redirect("payroll:period_list")


class PayrollPeriodDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        periodo = get_object_or_404(PayrollPeriod, pk=pk, tenant=request.tenant)
        nominas = services.list_period_payrolls(periodo)
        ya_calculados = [nomina.employee_id for nomina in nominas]
        context = {
            "periodo": periodo,
            "nominas": nominas,
            "calculate_form": PayrollCalculateForm(tenant=request.tenant, exclude_employee_ids=ya_calculados),
            "activity_log": services.get_activity_log(request.tenant, entity_type="payroll_period", entity_id=periodo.pk),
        }
        return render(request, "payroll/period_detail.html", context)


class PayrollPeriodApproveView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        periodo = get_object_or_404(PayrollPeriod, pk=pk, tenant=request.tenant)
        try:
            services.approve_period(periodo, request.user)
            messages.success(request, "Período aprobado correctamente.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("payroll:period_detail", pk=periodo.pk)


class PayrollPeriodCancelView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        periodo = get_object_or_404(PayrollPeriod, pk=pk, tenant=request.tenant)
        try:
            services.cancel_period(periodo, request.user)
            messages.success(request, "Período cancelado.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("payroll:period_detail", pk=periodo.pk)


class PayrollPeriodCloseView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        periodo = get_object_or_404(PayrollPeriod, pk=pk, tenant=request.tenant)
        try:
            services.close_period(periodo, request.user)
            messages.success(request, "Período cerrado.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("payroll:period_detail", pk=periodo.pk)


class PayrollCalculateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        periodo = get_object_or_404(PayrollPeriod, pk=pk, tenant=request.tenant)
        form = PayrollCalculateForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                nomina = services.calculate_payroll_for_employee(
                    request.tenant, periodo, form.cleaned_data["employee"], user=request.user,
                )
                messages.success(request, f"Nómina calculada para {nomina.employee_name_snapshot}.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Selecciona un empleado válido.")
        return redirect("payroll:period_detail", pk=periodo.pk)


class PayrollDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        nomina = get_object_or_404(Payroll, pk=pk, tenant=request.tenant)
        context = {
            "nomina": nomina,
            "lineas": services.get_payroll_lines(nomina),
            "pagos": services.get_payroll_payments(nomina),
            "saldo_pendiente": services.get_payroll_balance_due(nomina),
            "line_form": PayrollLineForm(),
            "payment_form": PayrollPaymentForm(),
        }
        return render(request, "payroll/payroll_detail.html", context)


class PayrollLineAddView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        nomina = get_object_or_404(Payroll, pk=pk, tenant=request.tenant)
        form = PayrollLineForm(request.POST)
        if form.is_valid():
            try:
                services.add_payroll_line(nomina, **form.cleaned_data)
                messages.success(request, "Línea agregada correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos de la línea.")
        return redirect("payroll:payroll_detail", pk=nomina.pk)


class PayrollPaymentAddView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        nomina = get_object_or_404(Payroll, pk=pk, tenant=request.tenant)
        form = PayrollPaymentForm(request.POST)
        if form.is_valid():
            try:
                services.record_payroll_payment(request.tenant, nomina, user=request.user, **form.cleaned_data)
                messages.success(request, "Pago registrado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del pago.")
        return redirect("payroll:payroll_detail", pk=nomina.pk)


class PayrollPaymentVoidView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, payment_pk):
        nomina = get_object_or_404(Payroll, pk=pk, tenant=request.tenant)
        pago = get_object_or_404(PayrollPayment, pk=payment_pk, tenant=request.tenant, payroll=nomina)
        services.void_payroll_payment(pago, request.user)
        messages.success(request, "Pago anulado.")
        return redirect("payroll:payroll_detail", pk=nomina.pk)
