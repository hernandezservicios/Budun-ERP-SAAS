"""
Servicio de autorizaciones centralizado y reutilizable (FASE 11, ver
docs/approvals.md). `ApprovalPolicy` define límites configurables por
usuario, por rol o por tenant (nunca hardcodeados en código);
`ApprovalRequest` es la solicitud/decisión, con auditoría inmutable.

Ningún módulo (POS, y en el futuro Compras/Gastos/ajustes de
inventario) debe implementar su propia lógica de aprobación — todos
consumen `apps.approvals.services`, nunca estos modelos directamente
desde una vista.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.tenants.models import Membership, TenantScopedModel


class ApprovalPolicy(TenantScopedModel):
    """Límites de autorización. Jerarquía de resolución (ver
    `docs/approvals.md` sección 3, contrato oficial): usuario → rol →
    tenant → negar. Como máximo una fila por (tenant, rol), una por
    (tenant, usuario) y una fila `TENANT` (predeterminada) por tenant."""

    class Scope(models.TextChoices):
        USER = "user", "Usuario específico"
        ROLE = "role", "Rol"
        TENANT = "tenant", "Tenant (predeterminada)"

    scope = models.CharField("alcance", max_length=10, choices=Scope.choices)
    role = models.CharField(
        "rol", max_length=20, choices=Membership.Role.choices, blank=True,
        help_text="Solo cuando alcance = Rol.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="approval_policies",
        help_text="Solo cuando alcance = Usuario específico.",
    )
    max_discount_percent = models.DecimalField(
        "descuento máximo (%)", max_digits=5, decimal_places=2, default=Decimal("0")
    )
    max_discount_amount = models.DecimalField(
        "descuento máximo (monto)", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    max_credit_overage = models.DecimalField(
        "exceso de crédito autorizable sin aprobación", max_digits=12, decimal_places=2, default=Decimal("0")
    )
    max_purchase_order_amount = models.DecimalField(
        "total de orden de compra autorizable sin aprobación",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="FASE 12 (Compras): una orden de compra con total mayor a este límite "
        "requiere autorización antes de poder enviarse. Mismo patrón que max_credit_overage.",
    )
    max_over_receiving_percent = models.DecimalField(
        "sobre-recepción autorizable sin aprobación (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text="FASE 12 (Compras): porcentaje por encima de la cantidad pendiente de una "
        "línea de orden de compra que puede recibirse sin autorización adicional "
        "(0 = ninguna sobre-recepción permitida sin aprobación explícita).",
    )
    max_expense_amount = models.DecimalField(
        "total de gasto autorizable sin aprobación",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="FASE 13 (Gastos): un gasto con total mayor a este límite requiere "
        "autorización antes de aprobarse. Mismo patrón que max_purchase_order_amount.",
    )
    can_approve = models.BooleanField("puede resolver solicitudes de autorización", default=False)
    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)
    updated_at = models.DateTimeField("actualizada", auto_now=True)

    class Meta:
        verbose_name = "política de autorización"
        verbose_name_plural = "políticas de autorización"
        ordering = ["scope", "role", "user_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "role"], condition=models.Q(scope="role"), name="unique_policy_tenant_rol"
            ),
            models.UniqueConstraint(
                fields=["tenant", "user"], condition=models.Q(scope="user"), name="unique_policy_tenant_usuario"
            ),
            models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(scope="tenant"), name="unique_policy_tenant_default"
            ),
            models.CheckConstraint(
                check=(
                    (models.Q(scope="role") & ~models.Q(role="") & models.Q(user__isnull=True))
                    | (models.Q(scope="user") & models.Q(role="") & models.Q(user__isnull=False))
                    | (models.Q(scope="tenant") & models.Q(role="") & models.Q(user__isnull=True))
                ),
                name="approvalpolicy_alcance_consistente",
            ),
            models.CheckConstraint(
                check=models.Q(max_discount_percent__gte=0)
                & models.Q(max_discount_amount__gte=0)
                & models.Q(max_credit_overage__gte=0)
                & models.Q(max_purchase_order_amount__gte=0)
                & models.Q(max_over_receiving_percent__gte=0)
                & models.Q(max_expense_amount__gte=0),
                name="approvalpolicy_limites_no_negativos",
            ),
        ]

    def __str__(self):
        if self.scope == self.Scope.USER:
            return f"Política de {self.user}"
        if self.scope == self.Scope.ROLE:
            return f"Política de rol: {self.get_role_display()}"
        return "Política predeterminada del tenant"


class ApprovalRequest(TenantScopedModel):
    """Solicitud de autorización — nunca se borra, una decisión
    equivocada se corrige con una nueva solicitud, nunca editando el
    historial (ver `docs/approvals.md` sección 6)."""

    class ActionType(models.TextChoices):
        DISCOUNT = "discount", "Descuento"
        CREDIT_OVERAGE = "credit_overage", "Crédito excedido"
        REFUND = "refund", "Reembolso especial"
        CANCELLATION = "cancellation", "Anulación sensible"
        INVENTORY_ADJUSTMENT = "inventory_adjustment", "Ajuste de inventario"
        CASH_MOVEMENT = "cash_movement", "Movimiento de caja especial"
        # FASE 12 (Compras): mismas primitivas reutilizables
        # (request_approval/resolve_approval/mark_consumed/
        # get_usable_approved_request), solo dos tipos de acción nuevos.
        PURCHASE_OVER_THRESHOLD = "purchase_over_threshold", "Compra sobre el límite"
        OVER_RECEIVING = "over_receiving", "Sobre-recepción de compra"
        # FASE 13 (Gastos + RRHH + Nómina): mismas primitivas reutilizables.
        EXPENSE_OVER_THRESHOLD = "expense_over_threshold", "Gasto sobre el límite"
        EXPENSE_EXCEPTIONAL = "expense_exceptional", "Gasto excepcional"
        LEAVE_REQUEST = "leave_request", "Solicitud de ausencia/vacaciones"
        PAYROLL_APPROVAL = "payroll_approval", "Aprobación de nómina"
        OTHER = "other", "Otro"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        CANCELED = "canceled", "Cancelada"
        EXPIRED = "expired", "Vencida"

    action_type = models.CharField("tipo", max_length=30, choices=ActionType.choices)
    document_type = models.CharField(
        "tipo de documento", max_length=30, blank=True, help_text="Referencia genérica, p. ej. 'sale'."
    )
    document_id = models.PositiveBigIntegerField("id del documento", null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="solicitado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="resuelto por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reason = models.CharField("motivo de la solicitud", max_length=255, blank=True)
    decision_reason = models.CharField("motivo de la decisión", max_length=255, blank=True)
    requested_value = models.DecimalField("valor solicitado", max_digits=12, decimal_places=2, null=True, blank=True)
    allowed_limit = models.DecimalField("límite permitido", max_digits=12, decimal_places=2, null=True, blank=True)
    approved_value = models.DecimalField("valor aprobado", max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.PENDING)
    metadata = models.JSONField("metadata", default=dict, blank=True)
    requested_at = models.DateTimeField("solicitada", auto_now_add=True)
    decided_at = models.DateTimeField("decidida", null=True, blank=True)
    consumed_at = models.DateTimeField(
        "consumida", null=True, blank=True,
        help_text="Momento en que una solicitud APROBADA se usó para ejecutar la operación — evita reutilizarla dos veces.",
    )
    consumed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="consumida por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "solicitud de autorización"
        verbose_name_plural = "solicitudes de autorización"
        ordering = ["-requested_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "status", "requested_at"], name="idx_approval_tenant_estado"),
            models.Index(fields=["tenant", "document_type", "document_id"], name="idx_approval_tenant_doc"),
        ]

    def __str__(self):
        return f"{self.get_action_type_display()} #{self.pk} ({self.get_status_display()})"
