from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
    verbose_name = "Billing SaaS (PayPal)"

    def ready(self):
        # FASE 17: conecta las señales de PayPal (FASE 16) con el
        # núcleo de Billing SaaS — patrón estándar de Django para
        # registrar receptores de señales al arrancar la app.
        from .services import paypal_integration

        paypal_integration.connect()
