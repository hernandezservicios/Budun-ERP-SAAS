"""
Política comercial configurable de Billing SaaS (FASE 17, ver
`docs/billing.md`). Fila única (singleton, `pk=1`, mismo patrón que
`PayPalGatewayStatus` de FASE 16) — los tiempos de gracia/vencimiento
NUNCA se hardcodean en el código (sección 31 de la fase: "no hardcodear
una política comercial no definida"), se leen siempre de aquí, con
valores por defecto razonables y documentados que el Super Admin puede
ajustar sin un despliegue de código."""

from django.db import models


class BillingPolicy(models.Model):
    grace_period_days = models.PositiveIntegerField(
        "días de gracia tras vencimiento", default=5,
        help_text="Días entre la fecha de vencimiento de una factura y que la suscripción pase a PAST_DUE.",
    )
    past_due_to_suspend_days = models.PositiveIntegerField(
        "días en PAST_DUE antes de suspender", default=15,
        help_text="Días adicionales en PAST_DUE antes de suspender automáticamente la suscripción/tenant.",
    )
    invoice_advance_days = models.PositiveIntegerField(
        "días de anticipación para generar factura", default=0,
        help_text="Días antes del inicio del período en que se genera la factura recurrente (0 = el mismo día).",
    )
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "política de Billing"
        verbose_name_plural = "política de Billing"

    def __str__(self):
        return "Política de Billing SaaS"
