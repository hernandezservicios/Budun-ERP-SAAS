from django.conf import settings
from django.db import models

from .managers import TenantManager


class Tenant(models.Model):
    """Una empresa/cliente del SaaS. Toda entidad de negocio futura
    (productos, ventas, POS, etc.) pertenecerá a exactamente un Tenant."""

    class BillingStatus(models.TextChoices):
        """Ciclo de vida de la SUSCRIPCIÓN de este tenant al SaaS (FASE 17,
        ver `docs/billing.md`) — deliberadamente separado de `is_active`
        (que conserva su significado histórico desde FASE 3, sin relación
        con Billing). `default=ACTIVE` es intencional: preserva el
        comportamiento de TODO tenant creado antes de FASE 17 (fixtures de
        tests incluidos) sin ningún cambio — solo los tenants nuevos
        creados a través del flujo de alta de Billing (`apps.billing`)
        arrancan explícitamente en `PENDING_SETUP`. Este campo NUNCA se
        expone en un formulario editable directamente: solo
        `apps.billing.services` lo cambia, siempre como consecuencia de
        un evento de negocio real (pago confirmado, factura vencida,
        política de suspensión) — nunca a mano."""

        PENDING_SETUP = "pending_setup", "Configuración pendiente"
        PENDING_PAYMENT = "pending_payment", "Pago pendiente"
        ACTIVE = "active", "Activo"
        PAST_DUE = "past_due", "Pago vencido (en gracia)"
        SUSPENDED = "suspended", "Suspendido"
        CANCELLED = "cancelled", "Cancelado"
        EXPIRED = "expired", "Expirado"

    name = models.CharField("nombre", max_length=150)
    slug = models.SlugField("slug", max_length=150, unique=True)
    is_active = models.BooleanField("activo", default=True)
    # Referencia perezosa por "app_label.ModelName" (FASE 17,
    # `apps.billing.models.SaaSCustomer`) — evita un import circular
    # (`apps.tenants` es la app más fundacional del proyecto; `apps.billing`
    # es mucho más tardía). Quién CONTRATÓ el plan para este tenant — un
    # SaaSCustomer puede tener varios Tenants, nunca al revés. Nulo para
    # todo tenant creado antes de FASE 17.
    saas_customer = models.ForeignKey(
        "billing.SaaSCustomer", verbose_name="cliente SaaS", on_delete=models.PROTECT,
        null=True, blank=True, related_name="tenants",
    )
    billing_status = models.CharField(
        "estado de facturación", max_length=20, choices=BillingStatus.choices, default=BillingStatus.ACTIVE,
    )
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "tenant"
        verbose_name_plural = "tenants"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def billing_status_blocks_operation(self):
        """`True` cuando el estado de facturación no permite operación
        completa del ERP (ver `apps.billing.middleware.BillingStatusMiddleware`)
        — `ACTIVE`/`PAST_DUE` (en gracia) sí permiten operar con normalidad."""
        return self.billing_status not in (self.BillingStatus.ACTIVE, self.BillingStatus.PAST_DUE)


class Membership(models.Model):
    """Relación User ↔ Tenant: a qué tenant(s) pertenece un usuario y con
    qué rol. Un usuario puede pertenecer a más de un tenant (p. ej. un
    contador que da servicio a varias empresas), pero cada request solo
    tiene UN tenant activo (ver `tenants.middleware.TenantMiddleware`).

    Nota deliberada: Membership usa el manager por defecto de Django (no
    `TenantManager`), porque es precisamente el modelo que se consulta
    para *determinar* el tenant activo de una request; si estuviera
    filtrado por tenant activo no se podría resolver nada la primera vez.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Propietario"
        # Roles granulares (FASE 15, ver docs/roles-permissions.md).
        # "MEMBER" se conserva sin cambios (todas las membresías
        # existentes creadas antes de FASE 15 siguen siendo válidas
        # exactamente como estaban) — los cuatro roles nuevos son
        # opciones ADICIONALES, nunca un reemplazo. "SUPER_ADMIN" de la
        # especificación de FASE 15 no se modela aquí: no tiene sentido
        # como rol POR TENANT (un "super admin" es un concepto de
        # PLATAFORMA, no de una empresa cliente) — se adapta a
        # `User.is_superuser` (ya existe en `AbstractUser`, sin campo
        # nuevo), documentado en `docs/roles-permissions.md`.
        ADMIN = "admin", "Administrador"
        MANAGER = "manager", "Gerente"
        CASHIER = "cashier", "Cajero"
        EMPLOYEE = "employee", "Empleado"
        MEMBER = "member", "Miembro"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField("rol", max_length=20, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "membresía"
        verbose_name_plural = "membresías"
        constraints = [
            models.UniqueConstraint(fields=["user", "tenant"], name="unique_membership_user_tenant"),
        ]
        indexes = [
            # Cubre las consultas del Panel (FASE 7): contar/():listar
            # membresías activas de un tenant ordenadas por fecha.
            models.Index(fields=["tenant", "is_active", "created_at"], name="idx_membership_tenant_activo"),
        ]

    def __str__(self):
        return f"{self.user} @ {self.tenant} ({self.role})"

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER


class TenantScopedModel(models.Model):
    """Base abstracta para cualquier modelo cuyos datos pertenecen a un
    único tenant.

    A partir de FASE 8 (Products + Inventory), los modelos de negocio
    reales heredarán de esta clase para obtener aislamiento automático:

        class Product(TenantScopedModel):
            name = models.CharField(...)
            ...

    - `objects` (manager por defecto) SOLO ve el tenant activo del
      contexto actual (ver `tenants.scoping`).
    - `all_objects` es una vía de escape EXPLÍCITA y consciente, pensada
      para tareas internas (migraciones de datos, comandos de
      administración, auditoría). Nunca debe usarse en vistas, serializers
      o servicios que atienden una request de un tenant.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+")

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True


class IsolationSample(TenantScopedModel):
    """Modelo de referencia MÍNIMO, usado únicamente por las pruebas
    automatizadas de aislamiento de FASE 3 (ver `tests.py`).

    No se expone en ninguna vista, URL ni funcionalidad de negocio: existe
    solo para demostrar y verificar, con datos reales en PostgreSQL, que
    `TenantScopedModel`/`TenantManager` aíslan correctamente un tenant de
    otro. Las apps de negocio reales (desde FASE 8) heredarán del mismo
    patrón (`TenantScopedModel`), no de este modelo.
    """

    label = models.CharField("etiqueta", max_length=100)

    class Meta:
        verbose_name = "registro de aislamiento (interno)"
        verbose_name_plural = "registros de aislamiento (interno)"

    def __str__(self):
        return f"{self.label} [{self.tenant_id}]"
