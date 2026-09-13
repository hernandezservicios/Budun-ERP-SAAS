from django.urls import path

from . import portal_views as views

app_name = "billing_portal"

urlpatterns = [
    path("", views.BillingPortalStatusView.as_view(), name="status"),
    path("elegir-plan/", views.SelectPlanView.as_view(), name="select_plan"),
    path("cambiar-plan/", views.ChangePlanView.as_view(), name="change_plan"),
    path("cancelar/", views.CancelSubscriptionView.as_view(), name="cancel"),
    path("cobrar/<int:invoice_id>/paypal/", views.CheckoutPayPalInitiateView.as_view(), name="checkout_paypal_initiate"),
    path("cobrar/<int:invoice_id>/paypal/retorno/", views.CheckoutPayPalReturnView.as_view(), name="checkout_paypal_return"),
    path("cobrar/<int:invoice_id>/paypal/cancelado/", views.CheckoutPayPalCancelView.as_view(), name="checkout_paypal_cancel"),
    path(
        "cobrar/<int:invoice_id>/paypal-recurrente/",
        views.RecurringCheckoutInitiateView.as_view(), name="checkout_paypal_recurring_initiate",
    ),
    path(
        "cobrar/<int:invoice_id>/paypal-recurrente/retorno/",
        views.RecurringCheckoutReturnView.as_view(), name="checkout_paypal_recurring_return",
    ),
    path(
        "cobrar/<int:invoice_id>/paypal-recurrente/cancelado/",
        views.RecurringCheckoutCancelView.as_view(), name="checkout_paypal_recurring_cancel",
    ),
    path("transferencia/<int:invoice_id>/", views.TransferInstructionsView.as_view(), name="transfer_instructions"),
    path("comprobantes/<int:pk>/descargar/", views.PaymentProofDownloadView.as_view(), name="proof_download"),
]
