from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportsIndexView.as_view(), name="index"),
    path("ventas/", views.SalesReportView.as_view(), name="sales"),
    path("inventario/", views.InventoryReportView.as_view(), name="inventory"),
    path("caja/", views.CashReportView.as_view(), name="cash"),
    path("cuentas-por-cobrar/", views.AccountsReceivableReportView.as_view(), name="accounts_receivable"),
    path("cuentas-por-pagar/", views.AccountsPayableReportView.as_view(), name="accounts_payable"),
    path("compras/", views.PurchasesReportView.as_view(), name="purchases"),
    path("gastos/", views.ExpensesReportView.as_view(), name="expenses"),
    path("rrhh/", views.HRReportView.as_view(), name="hr"),
    path("nomina/", views.PayrollReportView.as_view(), name="payroll"),
    path("clientes/", views.CustomersReportView.as_view(), name="customers"),
    path("proveedores/", views.SuppliersReportView.as_view(), name="suppliers"),
]
