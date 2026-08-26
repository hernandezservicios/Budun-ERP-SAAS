"""
Vistas de Contabilidad General (FASE 14). Deliberadamente delgadas:
toda la lógica vive en `apps.accounting.services` — esta capa solo
arma el request/response.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import (
    AccountForm,
    AccountingPeriodForm,
    AccountMappingForm,
    JournalEntryHeaderForm,
    JournalEntryLineFormSet,
    ReopenPeriodForm,
    ReverseJournalEntryForm,
)
from .models import Account, AccountingPeriod, JournalEntry


def _mensaje_error(error):
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


# ------------------------------------------------------------------
# Plan de cuentas
# ------------------------------------------------------------------


class AccountListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {"arbol": services.get_account_tree(request.tenant), "form": AccountForm(tenant=request.tenant)}
        return render(request, "accounting/account_list.html", context)

    def post(self, request):
        form = AccountForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                services.create_account(request.tenant, user=request.user, **form.cleaned_data)
                messages.success(request, "Cuenta creada correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos de la cuenta.")
        return redirect("accounting:account_list")


class AccountToggleView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        cuenta = get_object_or_404(Account, pk=pk, tenant=request.tenant)
        services.set_account_active(cuenta, is_active=not cuenta.is_active)
        messages.success(request, "Cuenta actualizada.")
        return redirect("accounting:account_list")


# ------------------------------------------------------------------
# Períodos contables
# ------------------------------------------------------------------


class AccountingPeriodListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {"periodos": services.list_periods(request.tenant), "form": AccountingPeriodForm()}
        return render(request, "accounting/period_list.html", context)

    def post(self, request):
        form = AccountingPeriodForm(request.POST)
        if form.is_valid():
            try:
                periodo = services.open_period(request.tenant, user=request.user, **form.cleaned_data)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
                return redirect("accounting:period_list")
            messages.success(request, f"Período «{periodo.name}» abierto correctamente.")
            return redirect("accounting:period_detail", pk=periodo.pk)
        messages.error(request, "Revisa las fechas del período.")
        return redirect("accounting:period_list")


class AccountingPeriodDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        periodo = get_object_or_404(AccountingPeriod, pk=pk, tenant=request.tenant)
        context = {
            "periodo": periodo,
            "asientos": services.list_journal_entries(request.tenant, period=periodo),
            "reopen_form": ReopenPeriodForm(),
            "activity_log": services.get_activity_log(request.tenant, entity_type="accounting_period", entity_id=periodo.pk),
        }
        return render(request, "accounting/period_detail.html", context)


class AccountingPeriodCloseView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        periodo = get_object_or_404(AccountingPeriod, pk=pk, tenant=request.tenant)
        try:
            services.close_period(periodo, request.user)
            messages.success(request, "Período cerrado correctamente.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("accounting:period_detail", pk=periodo.pk)


class AccountingPeriodReopenView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        periodo = get_object_or_404(AccountingPeriod, pk=pk, tenant=request.tenant)
        form = ReopenPeriodForm(request.POST)
        if form.is_valid():
            try:
                services.reopen_period(periodo, request.user, reason=form.cleaned_data["reason"])
                messages.success(request, "Período reabierto correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Indica el motivo de la reapertura.")
        return redirect("accounting:period_detail", pk=periodo.pk)


# ------------------------------------------------------------------
# Asientos contables
# ------------------------------------------------------------------


class JournalEntryListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {"asientos": services.list_journal_entries(request.tenant)}
        return render(request, "accounting/journal_entry_list.html", context)


class JournalEntryCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {
            "header_form": JournalEntryHeaderForm(),
            "line_formset": JournalEntryLineFormSet(form_kwargs={"tenant": request.tenant}),
        }
        return render(request, "accounting/journal_entry_form.html", context)

    def post(self, request):
        header_form = JournalEntryHeaderForm(request.POST)
        line_formset = JournalEntryLineFormSet(request.POST, form_kwargs={"tenant": request.tenant})
        if header_form.is_valid() and line_formset.is_valid():
            lines = [
                {
                    "account": fila.cleaned_data["account"], "debit": fila.cleaned_data["debit"],
                    "credit": fila.cleaned_data["credit"], "description": fila.cleaned_data.get("description", ""),
                    "customer": fila.cleaned_data.get("customer"), "supplier": fila.cleaned_data.get("supplier"),
                }
                for fila in line_formset if fila.cleaned_data and fila.cleaned_data.get("account")
            ]
            try:
                asiento = services.create_journal_entry(
                    request.tenant, user=request.user, lines=lines, **header_form.cleaned_data,
                )
                asiento = services.post_journal_entry(asiento, request.user)
                messages.success(request, f"Asiento «{asiento.number}» contabilizado correctamente.")
                return redirect("accounting:journal_entry_detail", pk=asiento.pk)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del asiento — las líneas deben cuadrar (débitos = créditos).")
        return render(request, "accounting/journal_entry_form.html", {"header_form": header_form, "line_formset": line_formset})


class JournalEntryDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        asiento = get_object_or_404(JournalEntry, pk=pk, tenant=request.tenant)
        context = {
            "asiento": asiento,
            "lineas": services.get_journal_entry_lines(asiento),
            "reversado": services.is_entry_reversed(asiento),
        }
        return render(request, "accounting/journal_entry_detail.html", context)


class JournalEntryReverseView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        asiento = get_object_or_404(JournalEntry, pk=pk, tenant=request.tenant)
        form = ReverseJournalEntryForm(request.POST)
        reason = form.cleaned_data["reason"] if form.is_valid() else ""
        try:
            reversa = services.reverse_journal_entry(asiento, request.user, reason=reason)
            messages.success(request, f"Asiento reversado — se generó «{reversa.number}».")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("accounting:journal_entry_detail", pk=asiento.pk)


# ------------------------------------------------------------------
# Mapeo de cuentas de control
# ------------------------------------------------------------------


class AccountMappingListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {"mapeos": services.list_account_mappings(request.tenant), "form": AccountMappingForm(tenant=request.tenant)}
        return render(request, "accounting/mapping_list.html", context)

    def post(self, request):
        form = AccountMappingForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            services.set_account_mapping(request.tenant, user=request.user, **form.cleaned_data)
            messages.success(request, "Mapeo de cuenta guardado correctamente.")
        else:
            messages.error(request, "Revisa los datos del mapeo.")
        return redirect("accounting:mapping_list")


# ------------------------------------------------------------------
# Reportes contables
# ------------------------------------------------------------------


class TrialBalanceView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        periodo = _resolver_periodo(request)
        contexto = {"periodos": services.list_periods(request.tenant), "periodo": periodo}
        if periodo:
            contexto["balance"] = services.get_trial_balance(request.tenant, periodo)
        return render(request, "accounting/trial_balance.html", contexto)


class GeneralLedgerView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        cuentas = services.list_accounts(request.tenant, only_active=False).filter(allows_posting=True)
        cuenta = None
        filas = []
        cuenta_id = request.GET.get("cuenta")
        if cuenta_id:
            cuenta = get_object_or_404(Account, pk=cuenta_id, tenant=request.tenant)
            filas = services.get_general_ledger(
                request.tenant, cuenta, date_from=request.GET.get("desde") or None, date_to=request.GET.get("hasta") or None,
            )
        contexto = {"cuentas": cuentas, "cuenta": cuenta, "filas": filas, "desde": request.GET.get("desde", ""), "hasta": request.GET.get("hasta", "")}
        return render(request, "accounting/general_ledger.html", contexto)


class GeneralJournalView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        desde = request.GET.get("desde") or None
        hasta = request.GET.get("hasta") or None
        asientos = services.get_general_journal(request.tenant, date_from=desde, date_to=hasta)
        return render(request, "accounting/general_journal.html", {"asientos": asientos, "desde": desde or "", "hasta": hasta or ""})


class BalanceSheetView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        periodo = _resolver_periodo(request)
        contexto = {"periodos": services.list_periods(request.tenant), "periodo": periodo}
        if periodo:
            contexto["balance"] = services.get_balance_sheet(request.tenant, periodo)
        return render(request, "accounting/balance_sheet.html", contexto)


class IncomeStatementView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        periodo = _resolver_periodo(request)
        contexto = {"periodos": services.list_periods(request.tenant), "periodo": periodo}
        if periodo:
            contexto["estado"] = services.get_income_statement(request.tenant, periodo)
        return render(request, "accounting/income_statement.html", contexto)


def _resolver_periodo(request):
    periodo_id = request.GET.get("periodo")
    if periodo_id:
        return get_object_or_404(AccountingPeriod, pk=periodo_id, tenant=request.tenant)
    return services.list_periods(request.tenant).first()
