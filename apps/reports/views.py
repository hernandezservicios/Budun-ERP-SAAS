"""
Vistas de Reportes (FASE 14). Deliberadamente delgadas: toda la
agregación vive en `apps.reports.services`, que a su vez reutiliza
literalmente los servicios de cada dominio — esta capa solo arma el
request/response y decide el formato de salida (HTML, CSV, PDF o
XLSX).

Exportación (ampliación de cierre de FASE 14, ver `docs/reports.md`):
CSV/PDF/XLSX disponibles en los reportes tabulares principales
(Ventas/Gastos/Cuentas por Cobrar/Cuentas por Pagar) y en los dos
Estados de Cuenta — el resto mantiene solo pantalla, documentado como
brecha conocida ("no todos los reportes necesitan todos los
formatos"). `reportlab`/`openpyxl` (ver `apps.reports.exports`) son
puro-Python, sin dependencias nativas, aprobadas explícitamente por el
usuario para esta ampliación.
"""

import csv

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from apps.core.utils import sanitize_cell_value
from apps.customers.models import Customer, Supplier
from apps.hr.services import can_view_sensitive_employee_data
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .exports import pdf_response, xlsx_response
from .forms import (
    CashReportFilterForm,
    DateRangeFilterForm,
    ExpensesReportFilterForm,
    PayrollReportFilterForm,
    PurchasesReportFilterForm,
    SalesReportFilterForm,
)


def _audit_export(request, *, reporte, formato):
    """Audita una exportación de reporte en la auditoría transversal
    (`apps.audit`) — import diferido + resiliente, mismo criterio que
    el resto de integraciones automáticas del proyecto (nunca bloquea
    ni rompe la exportación que está auditando)."""
    try:
        from apps.audit.services import get_client_ip, log_event
        from apps.audit.models import AuditLog

        log_event(
            request.tenant, user=request.user, action=AuditLog.Action.EXPORT_PERFORMED, domain="reports",
            object_type="report", object_id=reporte, metadata={"formato": formato},
            ip_address=get_client_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except Exception:  # noqa: BLE001
        pass


def _csv_response(filename, header, rows):
    respuesta = HttpResponse(content_type="text/csv")
    respuesta["Content-Disposition"] = f'attachment; filename="{filename}"'
    escritor = csv.writer(respuesta)
    # `sanitize_cell_value` (FASE 18 — Security Hardening): nunca
    # escribir una celda controlada por el usuario que Excel/Sheets
    # pueda interpretar como fórmula (CSV Formula Injection).
    escritor.writerow([sanitize_cell_value(valor) for valor in header])
    for fila in rows:
        escritor.writerow([sanitize_cell_value(valor) for valor in fila])
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
        exportar = request.GET.get("export")
        if exportar in ("csv", "pdf", "xlsx"):
            _audit_export(request, reporte="ventas", formato=exportar)
            header = ["Número", "Fecha", "Cliente", "Estado", "Total"]
            filas = [(v.number, v.issue_date, v.customer.display_name if v.customer else "—", v.status, v.total) for v in reporte["rows"]]
            if exportar == "csv":
                return _csv_response("ventas.csv", header, filas)
            if exportar == "pdf":
                return pdf_response(filename="ventas.pdf", title="Reporte de Ventas", tenant=request.tenant, generated_by=request.user.get_full_name() or request.user.email, header=header, rows=filas)
            return xlsx_response(filename="ventas.xlsx", sheet_title="Ventas", header=header, rows=filas)
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
        exportar = request.GET.get("export")
        if exportar in ("csv", "pdf", "xlsx"):
            _audit_export(request, reporte="cuentas_por_cobrar", formato=exportar)
            header = ["Cliente", "Factura", "Saldo", "Días vencido"]
            filas = [(f["customer"].display_name, f["sale"].number, f["balance_due"], f["days_overdue"]) for f in reporte["rows"]]
            if exportar == "csv":
                return _csv_response("cuentas_por_cobrar.csv", header, filas)
            if exportar == "pdf":
                return pdf_response(filename="cuentas_por_cobrar.pdf", title="Cuentas por Cobrar", tenant=request.tenant, generated_by=request.user.get_full_name() or request.user.email, header=header, rows=filas)
            return xlsx_response(filename="cuentas_por_cobrar.xlsx", sheet_title="CxC", header=header, rows=filas)
        return render(request, "reports/accounts_receivable_report.html", {"reporte": reporte})


class AccountsPayableReportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        reporte = services.get_accounts_payable_report(request.tenant)
        exportar = request.GET.get("export")
        if exportar in ("csv", "pdf", "xlsx"):
            _audit_export(request, reporte="cuentas_por_pagar", formato=exportar)
            header = ["Proveedor", "Factura", "Saldo", "Días vencido"]
            filas = [(f["supplier"].display_name, f["invoice"].number, f["balance_due"], f["days_overdue"]) for f in reporte["rows"]]
            if exportar == "csv":
                return _csv_response("cuentas_por_pagar.csv", header, filas)
            if exportar == "pdf":
                return pdf_response(filename="cuentas_por_pagar.pdf", title="Cuentas por Pagar", tenant=request.tenant, generated_by=request.user.get_full_name() or request.user.email, header=header, rows=filas)
            return xlsx_response(filename="cuentas_por_pagar.xlsx", sheet_title="CxP", header=header, rows=filas)
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
        exportar = request.GET.get("export")
        if exportar in ("csv", "pdf", "xlsx"):
            _audit_export(request, reporte="gastos", formato=exportar)
            header = ["Número", "Fecha", "Categoría", "Estado", "Total"]
            filas = [(g.number, g.expense_date, g.category.name, g.status, g.total) for g in reporte["rows"]]
            if exportar == "csv":
                return _csv_response("gastos.csv", header, filas)
            if exportar == "pdf":
                return pdf_response(filename="gastos.pdf", title="Reporte de Gastos", tenant=request.tenant, generated_by=request.user.get_full_name() or request.user.email, header=header, rows=filas)
            return xlsx_response(filename="gastos.xlsx", sheet_title="Gastos", header=header, rows=filas)
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


class CustomerStatementView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Estado de cuenta de un cliente (ampliación de cierre de FASE 14) —
    resumen + detalle cronológico, nunca una copia de los datos ya
    existentes en apps.sales."""

    def get(self, request, pk):
        cliente = get_object_or_404(Customer, pk=pk, tenant=request.tenant)
        reporte = services.get_customer_statement(request.tenant, cliente)
        exportar = request.GET.get("export")
        if exportar in ("csv", "pdf", "xlsx"):
            _audit_export(request, reporte=f"estado_cuenta_cliente_{cliente.pk}", formato=exportar)
            header = ["Fecha", "Tipo", "Documento", "Monto"]
            filas = [(m["date"], m["type"], getattr(m["document"], "number", str(m["document"].pk)), m["amount"]) for m in reporte["rows"]]
            nombre = f"estado_cuenta_{cliente.pk}"
            if exportar == "csv":
                return _csv_response(f"{nombre}.csv", header, filas)
            if exportar == "pdf":
                return pdf_response(filename=f"{nombre}.pdf", title=f"Estado de Cuenta — {cliente.display_name}", tenant=request.tenant, generated_by=request.user.get_full_name() or request.user.email, header=header, rows=filas)
            return xlsx_response(filename=f"{nombre}.xlsx", sheet_title="Estado de Cuenta", header=header, rows=filas)
        return render(request, "reports/customer_statement.html", {"cliente": cliente, "reporte": reporte})


class SupplierStatementView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Estado de cuenta de un proveedor — mismo patrón espejo."""

    def get(self, request, pk):
        proveedor = get_object_or_404(Supplier, pk=pk, tenant=request.tenant)
        reporte = services.get_supplier_statement(request.tenant, proveedor)
        exportar = request.GET.get("export")
        if exportar in ("csv", "pdf", "xlsx"):
            _audit_export(request, reporte=f"estado_cuenta_proveedor_{proveedor.pk}", formato=exportar)
            header = ["Fecha", "Tipo", "Documento", "Monto"]
            filas = [(m["date"], m["type"], getattr(m["document"], "supplier_invoice_number", None) or getattr(m["document"], "pk"), m["amount"]) for m in reporte["rows"]]
            nombre = f"estado_cuenta_proveedor_{proveedor.pk}"
            if exportar == "csv":
                return _csv_response(f"{nombre}.csv", header, filas)
            if exportar == "pdf":
                return pdf_response(filename=f"{nombre}.pdf", title=f"Estado de Cuenta — {proveedor.display_name}", tenant=request.tenant, generated_by=request.user.get_full_name() or request.user.email, header=header, rows=filas)
            return xlsx_response(filename=f"{nombre}.xlsx", sheet_title="Estado de Cuenta", header=header, rows=filas)
        return render(request, "reports/supplier_statement.html", {"proveedor": proveedor, "reporte": reporte})
