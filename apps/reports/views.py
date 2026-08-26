"""
Vistas de Reportes (FASE 14). Deliberadamente delgadas: toda la
agregación vive en `apps.reports.services`, que a su vez reutiliza
literalmente los servicios de cada dominio — esta capa solo arma el
request/response y decide el formato de salida (HTML o CSV).

Exportación: CSV está disponible para los reportes tabulares (barato,
sin dependencias nuevas). PDF/XLSX/reportes programados NO se
construyen en esta fase (ver `docs/reports.md` sección "Qué NO se
construyó") — instalar una librería nueva no está aprobada sin
decisión explícita del usuario, mismo criterio que
`docs/invoice-documents.md` desde FASE 10.
"""

import csv

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View

from apps.hr.services import can_view_sensitive_employee_data
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import (
    CashReportFilterForm,
    DateRangeFilterForm,
    ExpensesReportFilterForm,
    PayrollReportFilterForm,
    PurchasesReportFilterForm,
    SalesReportFilterForm,
)


def _csv_response(filename, header, rows):
    respuesta = HttpResponse(content_type="text/csv")
    respuesta["Content-Disposition"] = f'attachment; filename="{filename}"'
    escritor = csv.writer(respuesta)
    escritor.writerow(header)
    for fila in rows:
        escritor.writerow(fila)
    return respuesta


class ReportsIndexView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        resumen = services.get_executive_summary(request.tenant)
        return render(request, "reports/index.html", {"resumen": resumen})


class SalesReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = SalesReportFilterForm(request.GET or None, tenant=request.tenant)
        filtros = form.cleaned_data if form.is_valid() else {}
        reporte = services.get_sales_report(
            request.tenant, date_from=filtros.get("date_from"), date_to=filtros.get("date_to"),
            customer=filtros.get("customer"), status=filtros.get("status"),
        )
        if request.GET.get("export") == "csv":
            filas = [(v.number, v.issue_date, v.customer.display_name if v.customer else "—", v.status, v.total) for v in reporte["rows"]]
            return _csv_response("ventas.csv", ["Número", "Fecha", "Cliente", "Estado", "Total"], filas)
        return render(request, "reports/sales_report.html", {"form": form, "reporte": reporte})


class InventoryReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        reporte = services.get_inventory_report(request.tenant)
        if request.GET.get("export") == "csv":
            filas = [(p.sku, p.name, getattr(p, "current_stock", ""), p.sale_price) for p in reporte["rows"]]
            return _csv_response("inventario.csv", ["SKU", "Producto", "Stock", "Precio"], filas)
        return render(request, "reports/inventory_report.html", {"reporte": reporte})


class CashReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = CashReportFilterForm(request.GET or None, tenant=request.tenant)
        filtros = form.cleaned_data if form.is_valid() else {}
        reporte = services.get_cash_report(
            request.tenant, date_from=filtros.get("date_from"), date_to=filtros.get("date_to"), register=filtros.get("register"),
        )
        return render(request, "reports/cash_report.html", {"form": form, "reporte": reporte})


class AccountsReceivableReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        reporte = services.get_accounts_receivable_report(request.tenant)
        if request.GET.get("export") == "csv":
            filas = [(f["customer"].display_name, f["sale"].number, f["balance_due"], f["days_overdue"]) for f in reporte["rows"]]
            return _csv_response("cuentas_por_cobrar.csv", ["Cliente", "Factura", "Saldo", "Días vencido"], filas)
        return render(request, "reports/accounts_receivable_report.html", {"reporte": reporte})


class AccountsPayableReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        reporte = services.get_accounts_payable_report(request.tenant)
        if request.GET.get("export") == "csv":
            filas = [(f["supplier"].display_name, f["invoice"].number, f["balance_due"], f["days_overdue"]) for f in reporte["rows"]]
            return _csv_response("cuentas_por_pagar.csv", ["Proveedor", "Factura", "Saldo", "Días vencido"], filas)
        return render(request, "reports/accounts_payable_report.html", {"reporte": reporte})


class PurchasesReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = PurchasesReportFilterForm(request.GET or None, tenant=request.tenant)
        filtros = form.cleaned_data if form.is_valid() else {}
        reporte = services.get_purchases_report(
            request.tenant, date_from=filtros.get("date_from"), date_to=filtros.get("date_to"), supplier=filtros.get("supplier"),
        )
        return render(request, "reports/purchases_report.html", {"form": form, "reporte": reporte})


class ExpensesReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = ExpensesReportFilterForm(request.GET or None, tenant=request.tenant)
        filtros = form.cleaned_data if form.is_valid() else {}
        reporte = services.get_expenses_report(
            request.tenant, date_from=filtros.get("date_from"), date_to=filtros.get("date_to"), category=filtros.get("category"),
        )
        if request.GET.get("export") == "csv":
            filas = [(g.number, g.expense_date, g.category.name, g.status, g.total) for g in reporte["rows"]]
            return _csv_response("gastos.csv", ["Número", "Fecha", "Categoría", "Estado", "Total"], filas)
        return render(request, "reports/expenses_report.html", {"form": form, "reporte": reporte})


class HRReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        reporte = services.get_hr_report(request.tenant)
        return render(request, "reports/hr_report.html", {"reporte": reporte})


class PayrollReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    """La nómina es información sensible — un usuario que no puede ver
    datos sensibles de RRHH (ver `apps.hr.services.
    can_view_sensitive_employee_data`) solo ve los TOTALES agregados,
    nunca el desglose por empleado. Se decide en el SERVIDOR, nunca
    solo ocultando la tabla en la plantilla."""

    def get(self, request):
        form = PayrollReportFilterForm(request.GET or None, tenant=request.tenant)
        periodo = form.cleaned_data.get("period") if form.is_valid() else None
        reporte = services.get_payroll_report(request.tenant, period=periodo)
        puede_ver_sensible = can_view_sensitive_employee_data(request.tenant, request.user)
        if not puede_ver_sensible:
            reporte = {"summary": reporte["summary"], "rows": []}
        return render(request, "reports/payroll_report.html", {
            "form": form, "reporte": reporte, "puede_ver_sensible": puede_ver_sensible,
        })


class CustomersReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = DateRangeFilterForm(request.GET or None)
        filtros = form.cleaned_data if form.is_valid() else {}
        reporte = services.get_customers_report(request.tenant, date_from=filtros.get("date_from"), date_to=filtros.get("date_to"))
        return render(request, "reports/customers_report.html", {"form": form, "reporte": reporte})


class SuppliersReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = DateRangeFilterForm(request.GET or None)
        filtros = form.cleaned_data if form.is_valid() else {}
        reporte = services.get_suppliers_report(request.tenant, date_from=filtros.get("date_from"), date_to=filtros.get("date_to"))
        return render(request, "reports/suppliers_report.html", {"form": form, "reporte": reporte})
