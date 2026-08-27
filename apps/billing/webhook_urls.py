from django.urls import path

from . import webhook_views

app_name = "billing_webhooks"

urlpatterns = [
    path("paypal/", webhook_views.PayPalWebhookView.as_view(), name="paypal"),
]
