"""
Nómina (FASE 13, ver `docs/payroll.md`): dominio de Nómina del ERP,
consumiendo `apps.hr.Employee` como referencia (salario base, moneda,
departamento, cargo) — nunca lo duplica como una segunda fuente de
verdad de "quién es el empleado", pero SÍ toma un snapshot histórico de
esos datos al calcular cada nómina (mismo principio que
`apps.sales.SaleItem` snapshotea el producto: cambiar el salario o el
cargo del empleado después nunca debe alterar una nómina ya calculada).

Reutiliza literalmente, nunca duplica:
- `apps.sales.models.DocumentSequence`/`PaymentMethod` — numeración
  `NOM-000001` (misma tabla de secuencias que Ventas/Compras/Gastos) y
  mismo vocabulario de métodos de pago.
- `apps.pos.services.ensure_open_session_for_checkout`/
  `record_cash_movement` — un pago de nómina en efectivo exige una
  `CashSession` abierta y genera un `CashMovement` propio
  (`PAYROLL_PAYMENT_CASH`), igual que Gastos/Compras/POS.
- `apps.approvals.services` — aprobación de un período de nómina antes
  de pagarlo (`ActionType.PAYROLL_APPROVAL`).

`PayrollLine` es deliberadamente UNA sola tabla con `category`
(ingreso/deducción, determina el signo en el cálculo) + `concept`
(salario base/horas extra/bono/comisión/retención/anticipo/otro) — en
vez de las cuatro tablas casi idénticas mencionadas en la
especificación (`PayrollItem`/`PayrollAdjustment`/`PayrollDeduction`/
`PayrollBonus`). Simplificación deliberada y documentada
(`docs/payroll.md`), consistente con el principio de no-duplicación ya
aplicado en el proyecto (ej. `CustomerCreditLedger` nunca se construyó
como tercera tabla en Cuentas por Cobrar).
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.hr.models import Employee
from apps.sales.models import PaymentMethod
from apps.pos.models import CashSession
from apps.tenants.models import TenantScopedModel


# ---------------------------------------------------------------------
# Período de nómina
# ---------------------------------------------------------------------


class PayrollPeriod(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PROCESSING = "processing", "Procesando"
        APPROVED = "approved", "Aprobado"
        PAID = "paid", "Pagado"
        CLOSED = "closed", "Cerrado"
        CANCELED = "canceled", "Cancelado"

    number = models.CharField("número", max_length=20, db_index=True)
    start_date = models.DateField("fecha de inicio")
    end_date = models.DateField("fecha de fin")
    pay_date = models.DateField("fecha de pago")
    currency = models.CharField("moneda", max_length=3, default="USD")
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="creado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "período de nómina"
        verbose_name_plural = "períodos de nómina"
        ordering = ["-start_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_payrollperiod_tenant_numero"),
            models.CheckConstraint(check=models.Q(end_date__gte=models.F("start_date")), name="payrollperiod_fin_no_antes_de_inicio"),
        ]

    def __str__(self):
        return self.number


# ---------------------------------------------------------------------
# Nómina por empleado (snapshot histórico)
# ---------------------------------------------------------------------


class Payroll(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PARTIALLY_PAID = "partially_paid", "Parcialmente pagada"
        PAID = "paid", "Pagada"
        CANCELED = "canceled", "Cancelada"

    period = models.ForeignKey(PayrollPeriod, verbose_name="período", on_delete=models.PROTECT, related_name="payrolls")
    employee = models.ForeignKey(Employee, verbose_name="empleado", on_delete=models.PROTECT, related_name="payrolls")
    # --- Snapshot histórico: nunca se recalcula si el empleado cambia después ---
    employee_name_snapshot = models.CharField("nombre del empleado", max_length=255)
    department_snapshot = models.CharField("departamento", max_length=100, blank=True)
    position_snapshot = models.CharField("cargo", max_length=100, blank=True)
    base_salary_snapshot = models.DecimalField("salario base", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    gross_total = models.DecimalField("bruto", max_digits=12, decimal_places=2, default=Decimal("0"))
    deductions_total = models.DecimalField("deducciones", max_digits=12, decimal_places=2, default=Decimal("0"))
    net_total = models.DecimalField("neto", max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "nómina de empleado"
        verbose_name_plural = "nóminas de empleado"
        ordering = ["-created_at", "-id"]
        constraints = [
            # Nunca dos filas de nómina para el mismo empleado en el
            # mismo período — mismo principio que "una fila vigente"
            # ya usado en unique_active_contract_per_employee.
            models.UniqueConstraint(fields=["tenant", "period", "employee"], name="unique_payroll_tenant_periodo_empleado"),
        ]
        indexes = [
            models.Index(fields=["tenant", "period"], name="idx_payroll_tenant_periodo"),
        ]

    def __str__(self):
        return f"{self.employee_name_snapshot} — {self.period.number}"


class PayrollLine(TenantScopedModel):
    """Línea de detalle de una nómina — ver nota de diseño arriba sobre
    por qué es una sola tabla con `category`/`concept` en vez de cuatro
    tablas casi idénticas."""

    class Category(models.TextChoices):
        EARNING = "earning", "Ingreso"
        DEDUCTION = "deduction", "Deducción"

    class Concept(models.TextChoices):
        BASE_SALARY = "base_salary", "Salario base"
        OVERTIME = "overtime", "Horas extra"
        BONUS = "bonus", "Bono"
        COMMISSION = "commission", "Comisión"
        TAX_WITHHOLDING = "tax_withholding", "Retención"
        ADVANCE_DEDUCTION = "advance_deduction", "Anticipo"
        ABSENCE_DEDUCTION = "absence_deduction", "Descuento por ausencia"
        ADJUSTMENT = "adjustment", "Ajuste"
        OTHER = "other", "Otro"

    payroll = models.ForeignKey(Payroll, verbose_name="nómina", on_delete=models.CASCADE, related_name="lines")
    category = models.CharField("categoría", max_length=20, choices=Category.choices)
    concept = models.CharField("concepto", max_length=20, choices=Concept.choices)
    description = models.CharField("descripción", max_length=255, blank=True)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "línea de nómina"
        verbose_name_plural = "líneas de nómina"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="payrollline_monto_positivo"),
        ]

    def __str__(self):
        return f"{self.get_concept_display()} — {self.amount}"


# ---------------------------------------------------------------------
# Pago de nómina (ledger append-only, mismo principio que
# apps.expenses.ExpensePayment/apps.sales.Payment)
# ---------------------------------------------------------------------


class PayrollPayment(TenantScopedModel):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmado"
        VOIDED = "voided", "Anulado"

    payroll = models.ForeignKey(Payroll, verbose_name="nómina", on_delete=models.PROTECT, related_name="payments")
    method = models.CharField("método", max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField("monto", max_digits=12, decimal_places=2)
    currency = models.CharField("moneda", max_length=3, default="USD")
    cash_session = models.ForeignKey(
        CashSession, verbose_name="sesión de caja", on_delete=models.PROTECT,
        null=True, blank=True, related_name="payroll_payments",
    )
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    reference = models.CharField("referencia", max_length=100, blank=True)
    notes = models.CharField("notas", max_length=255, blank=True)
    idempotency_key = models.CharField("clave de idempotencia", max_length=100, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="registrado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "pago de nómina"
        verbose_name_plural = "pagos de nómina"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="unique_payrollpayment_tenant_idempotency",
            ),
            models.CheckConstraint(check=models.Q(amount__gt=0), name="payrollpayment_monto_positivo"),
        ]

    def __str__(self):
        return f"{self.get_method_display()} {self.amount} ({self.payroll})"


# ---------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo)
# ---------------------------------------------------------------------


class PayrollActivityLog(TenantScopedModel):
    class Action(models.TextChoices):
        PERIOD_CREATED = "period_created", "Período creado"
        PERIOD_PROCESSED = "period_processed", "Período procesado"
        PERIOD_APPROVED = "period_approved", "Período aprobado"
        PERIOD_CLOSED = "period_closed", "Período cerrado"
        PERIOD_CANCELED = "period_canceled", "Período cancelado"
        PAYROLL_CALCULATED = "payroll_calculated", "Nómina calculada"
        PAYMENT_RECORDED = "payment_recorded", "Pago registrado"
        PAYMENT_VOIDED = "payment_voided", "Pago anulado"

    entity_type = models.CharField("tipo de entidad", max_length=25)
    entity_id = models.PositiveBigIntegerField("id de la entidad")
    entity_label = models.CharField("identificador de la entidad (al momento del evento)", max_length=255, blank=True)
    action = models.CharField("acción", max_length=30, choices=Action.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    details = models.CharField("detalles", max_length=255, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "registro de actividad (nómina)"
        verbose_name_plural = "registros de actividad (nómina)"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "entity_type", "entity_id"], name="idx_payrolllog_tenant_entidad"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.entity_type} #{self.entity_id}"
