from django.urls import path

from . import admin_views as views

app_name = "billing_admin"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("clientes/", views.CustomersListView.as_view(), name="customers_list"),
    path("clientes/<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("clientes/<int:customer_id>/notas-credito/emitir/", views.IssueCreditNoteView.as_view(), name="issue_credit_note"),
    path("tenants/", views.TenantsListView.as_view(), name="tenants_list"),
    path("tenants/<int:pk>/", views.TenantDetailView.as_view(), name="tenant_detail"),
    path("venta-manual/", views.ManualTenantSaleView.as_view(), name="manual_sale"),
    path("planes/", views.PlansListView.as_view(), name="plans_list"),
    path("planes/<int:plan_id>/versiones/nueva/", views.PlanVersionCreateView.as_view(), name="plan_version_create"),
    path("suscripciones/", views.SubscriptionsListView.as_view(), name="subscriptions_list"),
    path("facturas/", views.InvoicesListView.as_view(), name="invoices_list"),
    path("facturas/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("pagos/", views.PaymentsListView.as_view(), name="payments_list"),
    path("pagos/<int:payment_id>/reembolsar/", views.RequestRefundView.as_view(), name="request_refund"),
    path("transferencias/", views.TransfersQueueView.as_view(), name="transfers_queue"),
    path("transferencias/<int:pk>/", views.ProofDetailView.as_view(), name="proof_detail"),
    path("transferencias/<int:pk>/descargar/", views.ProofDownloadView.as_view(), name="proof_download"),
    path("notas-credito/", views.CreditNotesListView.as_view(), name="credit_notes_list"),
    path("reembolsos/", views.RefundsListView.as_view(), name="refunds_list"),
    path("reembolsos/<int:pk>/completar/", views.CompleteManualRefundView.as_view(), name="complete_refund"),
    path("cuentas-bancarias/", views.BankAccountsListView.as_view(), name="bank_accounts_list"),
    path("cuentas-bancarias/<int:pk>/editar/", views.BankAccountUpdateView.as_view(), name="bank_account_update"),
    path("cuentas-bancarias/<int:pk>/estado/", views.BankAccountToggleActiveView.as_view(), name="bank_account_toggle_active"),
    path("reportes/", views.ReportsView.as_view(), name="reports"),
]
