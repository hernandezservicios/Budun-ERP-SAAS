from django.urls import path

from . import platform_views

app_name = "billing_platform"

urlpatterns = [
    path("", platform_views.GatewayStatusView.as_view(), name="status"),
    path("cobrar/", platform_views.CheckoutCreateView.as_view(), name="checkout_create"),
    path("cobrar/retorno/", platform_views.CheckoutReturnView.as_view(), name="checkout_return"),
    path("cobrar/cancelado/", platform_views.CheckoutCancelView.as_view(), name="checkout_cancel"),
    path("transacciones/<int:pk>/", platform_views.TransactionDetailView.as_view(), name="transaction_detail"),
]
