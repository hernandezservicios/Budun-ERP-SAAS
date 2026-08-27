"""
Payment Provider Interface de Billing SaaS (FASE 16, ver `docs/paypal.md`).

`Billing SaaS -> Payment Provider Interface -> PayPal Provider`: ningún
módulo de Billing debe hablar HTTP con PayPal directamente — siempre a
través de la interfaz `PaymentProvider` (`.base`). Hoy solo existe
`PayPalProvider` (`.paypal`) porque es el único proveedor con soporte
real; el diseño deja espacio explícito para Transferencia Bancaria
(FASE 17) u otro proveedor futuro sin rehacer `apps.billing.services`.

`get_default_provider()` es el único punto de construcción — nunca
instanciar `PayPalProvider` directamente desde `services.py`/vistas,
para poder sustituirlo en tests (`unittest.mock.patch`) o en el futuro
por una fábrica que elija el proveedor activo.
"""

from django.conf import settings

from .base import PaymentProvider, PaymentProviderError  # noqa: F401
from .paypal import PayPalProvider


def get_default_provider() -> PaymentProvider:
    return PayPalProvider(
        client_id=settings.PAYPAL_CLIENT_ID,
        client_secret=settings.PAYPAL_CLIENT_SECRET,
        environment=settings.PAYPAL_ENVIRONMENT,
        webhook_id=settings.PAYPAL_WEBHOOK_ID,
    )
