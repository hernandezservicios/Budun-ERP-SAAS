"""
Núcleo de Billing SaaS (FASE 17, ver `docs/billing.md`): `SaaSCustomer`,
`Plan`/`PlanVersion`, `Subscription`. Ninguno de estos modelos se
confunde con su homónimo del ERP del tenant (`apps.customers.Customer`
es el cliente COMERCIAL de un tenant; `SaaSCustomer` es quien CONTRATA
el plan para uno o varios `Tenant`) — ejes completamente distintos, ver
`docs/billing.md` sección "Separación obligatoria"."""

from django.conf import settings
from django.db import models

from apps.tenants.models import TenantScopedModel


class SaaSCustomer(models.Model):
    """El comprador de la plataforma — NO hereda `TenantScopedModel`:
    puede estar asociado a uno o varios `Tenant` (un revendedor
    administrando varias empresas clientas), así que la relación es
    `Tenant.saas_customer` (FK, ver abajo), nunca al revés como un campo
    de scoping. Sin país/moneda como catálogos reales (no existen
    todavía en el proyecto, ver `docs/currency.md`) — campos de texto
    libre, suficientes para lo que esta fase necesita."""

    name = models.CharField("nombre", max_length=150)
    email = models.EmailField("correo")
    country = models.CharField("país", max_length=100, blank=True)
    currency = models.CharField("moneda", max_length=3, default="USD")
    tax_id = models.CharField("identificación fiscal", max_length=50, blank=True)
    notes = models.TextField("notas", blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "cliente SaaS"
        verbose_name_plural = "clientes SaaS"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Plan(models.Model):
    """Catálogo de planes — NO hereda `TenantScopedModel` (global,
    compartido por todos los tenants, definido por el Super Admin).
    Reemplaza a `apps.core.pricing.PLANS` (FASE 6, estático) como fuente
    de verdad real; `PLANS` se conserva sin cambios como referencia
    histórica/placeholder pero ya no es lo que se cobra de verdad una
    vez que un `Plan` real con el mismo `slug` existe (ver
    `apps.billing.services.subscriptions._resolver_precio_por_plan_id`)."""

    name = models.CharField("nombre", max_length=100)
    slug = models.SlugField("slug", max_length=100, unique=True)
    description = models.TextField("descripción", blank=True)
    is_active = models.BooleanField("activo", default=True)
    sort_order = models.PositiveIntegerField("orden", default=0)
    max_users = models.PositiveIntegerField("máximo de usuarios", null=True, blank=True)
    max_products = models.PositiveIntegerField("máximo de productos", null=True, blank=True)
    features = models.JSONField("características", default=list, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "plan"
        verbose_name_plural = "planes"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class PlanVersion(models.Model):
    """Versionado de precios (sección 7 de la fase): cambiar el precio de
    un `Plan` NUNCA edita una fila existente — se crea una nueva
    `PlanVersion` y la anterior deja de ser `is_current`. Una
    `Subscription` referencia la versión VIGENTE al momento de
    suscribirse (snapshot histórico, mismo principio que `SaleItem`) —
    cambiar el precio después nunca altera lo que ya paga un tenant
    suscrito ni una factura ya emitida."""

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Mensual"
        ANNUAL = "annual", "Anual"

    plan = models.ForeignKey(Plan, verbose_name="plan", on_delete=models.PROTECT, related_name="versions")
    frequency = models.CharField("frecuencia", max_length=10, choices=Frequency.choices)
    price_amount = models.DecimalField("precio", max_digits=12, decimal_places=2)
    price_currency = models.CharField("moneda", max_length=3, default="USD")
    is_current = models.BooleanField("vigente", default=True)
    # FASE DE CORRECCIÓN 2C (Billing recurrente con PayPal): el mapeo
    # PlanVersion -> Producto/Plan de PayPal es 1:1 y CENTRALIZADO — se
    # crea una única vez la primera vez que algún tenant contrata esta
    # versión con cobro recurrente (`services.recurring.
    # ensure_paypal_billing_plan`), nunca un producto/plan de PayPal por
    # tenant. Vacío hasta que eso ocurra; una vez creado, es inmutable
    # (igual que la propia `PlanVersion`) — un cambio de precio siempre
    # crea una `PlanVersion` NUEVA con sus propios IDs de PayPal.
    paypal_product_id = models.CharField("ID de producto en PayPal", max_length=64, blank=True)
    paypal_plan_id = models.CharField("ID de plan de facturación en PayPal", max_length=64, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "versión de plan"
        verbose_name_plural = "versiones de plan"
        ordering = ["-created_at"]
        constraints = [
            # A lo sumo UNA versión vigente por (plan, frecuencia) — a
            # nivel de base de datos, no solo por convención de servicio
            # (índice único parcial de PostgreSQL).
            models.UniqueConstraint(
                fields=["plan", "frequency"], condition=models.Q(is_current=True),
                name="unique_current_planversion",
            ),
        ]

    def __str__(self):
        return f"{self.plan.name} — {self.get_frequency_display()} — {self.price_amount} {self.price_currency}"


class Subscription(TenantScopedModel):
    """La suscripción de UN tenant al SaaS — hereda `TenantScopedModel`
    (a diferencia de los modelos de FASE 16): el propio TENANT consulta
    su suscripción en el Portal de Billing (`apps.billing.portal_views`)
    dentro de una request normal con `request.tenant` ya resuelto, igual
    que cualquier otro dato operativo del proyecto — el Super Admin usa
    `all_objects` para cruzar tenants, mismo patrón dual ya usado por
    `ApiKey`/`Integration` (FASE 15)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACTIVE = "active", "Activa"
        PAST_DUE = "past_due", "Pago vencido (en gracia)"
        SUSPENDED = "suspended", "Suspendida"
        CANCELLED = "cancelled", "Cancelada"
        EXPIRED = "expired", "Expirada"

    saas_customer = models.ForeignKey(SaaSCustomer, verbose_name="cliente SaaS", on_delete=models.PROTECT, related_name="subscriptions")
    plan_version = models.ForeignKey(PlanVersion, verbose_name="versión de plan", on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDING)
    current_period_start = models.DateField("inicio del período actual", null=True, blank=True)
    current_period_end = models.DateField("fin del período actual", null=True, blank=True)
    coupon = models.ForeignKey(
        "billing.Coupon", verbose_name="cupón", on_delete=models.SET_NULL, null=True, blank=True, related_name="subscriptions",
    )
    # FASE DE CORRECCIÓN 2C (Billing recurrente con PayPal): la
    # referencia externa que autoriza el cobro automático futuro — NUNCA
    # un secreto/token de pago (eso PayPal nunca lo expone vía API,
    # solo internamente); solo el identificador con el que se consulta/
    # cancela la suscripción del lado de PayPal. Vacío mientras el
    # método de pago sea transferencia, o mientras el tenant no haya
    # autorizado todavía un cobro recurrente.
    paypal_subscription_id = models.CharField("ID de suscripción en PayPal", max_length=64, blank=True, db_index=True)
    # Último estado CONOCIDO del lado de PayPal (espejo informativo para
    # el Super Admin, sección 18 — nunca la fuente de verdad: el estado
    # real de negocio sigue siendo `status` de arriba, gobernado
    # exclusivamente por `apps.billing.services.subscriptions`).
    paypal_subscription_status = models.CharField("último estado conocido en PayPal", max_length=20, blank=True)
    started_at = models.DateTimeField("iniciada", null=True, blank=True)
    cancel_at_period_end = models.BooleanField("cancelar al finalizar el período", default=False)
    cancelled_at = models.DateTimeField("cancelada", null=True, blank=True)
    cancel_reason = models.CharField("motivo de cancelación", max_length=255, blank=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)
    updated_at = models.DateTimeField("actualizada", auto_now=True)

    class Meta:
        verbose_name = "suscripción"
        verbose_name_plural = "suscripciones"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_subscription_tenant_estado"),
        ]

    def __str__(self):
        return f"{self.tenant} — {self.plan_version.plan.name} ({self.get_status_display()})"

    @property
    def is_effectively_operational(self):
        return self.status in (self.Status.ACTIVE, self.Status.PAST_DUE)
