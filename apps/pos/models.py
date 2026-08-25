"""
Cajas y sesiones de caja (FASE 11, ver `docs/cash-registers.md`). El POS
en sí (carrito, checkout) es una capa de ORQUESTACIÓN sobre
`apps.sales`/`apps.inventory`/`apps.customers`/`apps.approvals` — nunca
un segundo motor de ventas. `CashRegister`/`CashSession`/`CashMovement`
son la única novedad de datos real de esta fase: append-only para los
movimientos (mismo principio que `StockMovement`/`PaymentAllocation`),
nunca un campo de saldo editable.

Un tenant puede crear cualquier cantidad de cajas — sin límite fijo de
diseño. Solo el efectivo (`PaymentMethod.CASH`) genera `CashMovement`
que afecte el efectivo físico esperado; otros métodos quedan
registrados en la sesión a través de `apps.sales.Payment`/
`PaymentAllocation` (ya existentes), nunca duplicados aquí.
"""

from django.conf import settings
from django.db import models

from apps.tenants.models import TenantScopedModel


class CashRegister(TenantScopedModel):
    """Una caja/terminal física. El administrador del tenant puede
    crear cualquier cantidad — nunca un número fijo."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        INACTIVE = "inactive", "Inactiva"

    name = models.CharField("nombre", max_length=100)
    code = models.CharField("código", max_length=20)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.ACTIVE)
    terminal = models.CharField(
        "terminal", max_length=100, blank=True, help_text="Identificador de hardware/estación, opcional."
    )
    authorized_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name="usuarios autorizados",
        blank=True,
        related_name="authorized_cash_registers",
        help_text="Quién puede abrir sesión en esta caja, además del propietario del tenant (siempre autorizado).",
    )
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "caja"
        verbose_name_plural = "cajas"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_register_tenant_codigo"),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


class CashSession(TenantScopedModel):
    """Jornada de caja: apertura → operación → cierre. Reglas de
    exclusividad (ver `docs/cash-registers.md` sección 3), aplicadas
    como `UniqueConstraint` parciales — la base de datos, no solo el
    servicio, garantiza que nunca existan dos sesiones `OPEN`
    simultáneas para la misma caja o el mismo usuario."""

    class Status(models.TextChoices):
        OPEN = "open", "Abierta"
        CLOSED = "closed", "Cerrada"

    cash_register = models.ForeignKey(
        CashRegister, verbose_name="caja", on_delete=models.PROTECT, related_name="sessions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="cajero", on_delete=models.PROTECT, related_name="+"
    )
    opened_at = models.DateTimeField("abierta", auto_now_add=True)
    opening_amount = models.DecimalField("fondo inicial", max_digits=12, decimal_places=2)
    closed_at = models.DateTimeField("cerrada", null=True, blank=True)
    expected_cash = models.DecimalField("efectivo esperado", max_digits=12, decimal_places=2, null=True, blank=True)
    counted_cash = models.DecimalField("efectivo contado", max_digits=12, decimal_places=2, null=True, blank=True)
    difference = models.DecimalField("diferencia", max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.OPEN)
    notes = models.CharField("notas de apertura", max_length=255, blank=True)
    closing_notes = models.CharField("observaciones de cierre", max_length=255, blank=True)

    class Meta:
        verbose_name = "sesión de caja"
        verbose_name_plural = "sesiones de caja"
        ordering = ["-opened_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cash_register"], condition=models.Q(status="open"), name="unique_open_session_per_register"
            ),
            # Deliberadamente GLOBAL (sin tenant en los campos): un
            # usuario no puede tener dos sesiones abiertas ni siquiera
            # en tenants distintos — no puede manejar efectivo en dos
            # cajas físicas a la vez. Ver docs/cash-registers.md.
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(status="open"), name="unique_open_session_per_user"
            ),
            models.CheckConstraint(check=models.Q(opening_amount__gte=0), name="cashsession_fondo_no_negativo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"], name="idx_cashsession_tenant_estado"),
            models.Index(fields=["tenant", "cash_register", "status"], name="idx_cashsession_tenant_caja"),
        ]

    def __str__(self):
        return f"{self.cash_register.code} — {self.user} ({self.get_status_display()})"


class CashMovement(TenantScopedModel):
    """Movimiento de efectivo dentro de una sesión — append-only, mismo
    principio que `StockMovement`/`PaymentAllocation`: el efectivo
    esperado se calcula SIEMPRE sumando estas filas, nunca un campo
    editado a mano. `reference_type`/`reference_id` es una referencia
    genérica opcional al `Payment`/`Refund` de `apps.sales` que originó
    el movimiento (mismo patrón ya usado por `SalesActivityLog`) —
    nunca se duplica el monto de ese `Payment`/`Refund` en una fila
    paralela con vida propia."""

    class MovementType(models.TextChoices):
        OPENING = "opening", "Apertura"
        SALE_CASH = "sale_cash", "Venta en efectivo"
        CASH_IN = "cash_in", "Entrada de efectivo"
        CASH_OUT = "cash_out", "Salida de efectivo"
        CASH_REFUND = "cash_refund", "Devolución en efectivo"
        CUSTOMER_ADVANCE_CASH = "customer_advance_cash", "Anticipo en efectivo"
        WITHDRAWAL = "withdrawal", "Retiro"
        ADJUSTMENT = "adjustment", "Ajuste autorizado"

    cash_session = models.ForeignKey(
        CashSession, verbose_name="sesión de caja", on_delete=models.PROTECT, related_name="movements"
    )
    movement_type = models.CharField("tipo", max_length=25, choices=MovementType.choices)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reason = models.CharField("motivo", max_length=255, blank=True)
    reference_type = models.CharField(
        "tipo de referencia", max_length=30, blank=True,
        help_text="Referencia genérica opcional, p. ej. 'payment'/'refund' de apps.sales.",
    )
    reference_id = models.PositiveBigIntegerField("id de referencia", null=True, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "movimiento de caja"
        verbose_name_plural = "movimientos de caja"
        ordering = ["-created_at", "-id"]
        constraints = [
            # OPENING permite monto 0 (una caja puede abrirse legítimamente
            # sin fondo inicial); cualquier otro tipo de movimiento debe
            # ser estrictamente positivo (un movimiento de $0 no tiene
            # sentido registrarlo).
            models.CheckConstraint(
                check=models.Q(amount__gt=0) | models.Q(movement_type="opening", amount__gte=0),
                name="cashmovement_monto_valido",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "cash_session", "movement_type"], name="idx_cashmov_tenant_sesion"),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.amount}"
