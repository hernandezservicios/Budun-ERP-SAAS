"""
Contabilidad General (FASE 14, ver `docs/accounting.md`): fuente
financiera central del ERP. Plan de cuentas jerárquico, períodos
contables, asientos de partida doble (`JournalEntry`/`JournalEntryLine`,
SUM(debit) == SUM(credit) siempre) y el "mapeo" de cuentas de control
(`AccountMapping`) que usa la capa de contabilización automática
(`services.record_business_event`) para traducir eventos de negocio
(venta confirmada, pago recibido, pago de gasto, pago de nómina) en
asientos reales — ver `docs/accounting.md` sección 8 para el diseño
completo de esa integración y qué eventos están conectados hoy.

Un asiento CONTABILIZADO (`status=POSTED`) nunca se edita ni se borra
— una corrección es un reverso (`reversal_of`), un nuevo asiento con
los montos invertidos, nunca una edición del histórico (mismo
principio que `Return`/`PaymentAllocation` revertida desde FASE 10).
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.customers.models import Customer, Supplier
from apps.tenants.models import TenantScopedModel


# ---------------------------------------------------------------------
# Plan de cuentas
# ---------------------------------------------------------------------


class Account(TenantScopedModel):
    """Una cuenta del plan de cuentas. Jerárquica vía `parent` (self,
    profundidad no limitada arbitrariamente) — `level` se calcula una
    vez al crearse (`parent.level + 1`, raíz = 1) y no cambia después
    (mover una cuenta de padre no está soportado hoy, evita
    inconsistencias de `level` en cascada sin un caso de uso real que
    lo exija)."""

    class AccountType(models.TextChoices):
        ASSET = "asset", "Activo"
        LIABILITY = "liability", "Pasivo"
        EQUITY = "equity", "Patrimonio"
        REVENUE = "revenue", "Ingreso"
        COST = "cost", "Costo"
        EXPENSE = "expense", "Gasto"

    class NormalBalance(models.TextChoices):
        DEBIT = "debit", "Débito"
        CREDIT = "credit", "Crédito"

    # Naturaleza contable estándar por tipo — ver `services.py` para el
    # único lugar donde se deriva (nunca hardcodeado dos veces).
    DEFAULT_NORMAL_BALANCE = {
        AccountType.ASSET: NormalBalance.DEBIT,
        AccountType.LIABILITY: NormalBalance.CREDIT,
        AccountType.EQUITY: NormalBalance.CREDIT,
        AccountType.REVENUE: NormalBalance.CREDIT,
        AccountType.COST: NormalBalance.DEBIT,
        AccountType.EXPENSE: NormalBalance.DEBIT,
    }

    code = models.CharField("código", max_length=20)
    name = models.CharField("nombre", max_length=150)
    account_type = models.CharField("tipo", max_length=20, choices=AccountType.choices)
    normal_balance = models.CharField("naturaleza", max_length=10, choices=NormalBalance.choices)
    parent = models.ForeignKey(
        "self", verbose_name="cuenta padre", on_delete=models.PROTECT, null=True, blank=True, related_name="children",
    )
    level = models.PositiveSmallIntegerField("nivel", default=1)
    allows_posting = models.BooleanField(
        "permite movimientos", default=True,
        help_text="Falso para cuentas de agrupación (ej. «1000 Activos») — nunca reciben líneas de asiento directamente.",
    )
    is_active = models.BooleanField("activa", default=True)
    description = models.CharField("descripción", max_length=255, blank=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "cuenta contable"
        verbose_name_plural = "cuentas contables"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_account_tenant_codigo"),
        ]
        indexes = [
            models.Index(fields=["tenant", "account_type"], name="idx_account_tenant_tipo"),
            models.Index(fields=["tenant", "parent"], name="idx_account_tenant_padre"),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


# ---------------------------------------------------------------------
# Período contable
# ---------------------------------------------------------------------


class AccountingPeriod(TenantScopedModel):
    """Un período no tiene "número comercial" vía `DocumentSequence`
    (decisión deliberada, ver `docs/accounting.md` sección 4): un
    período se identifica por su rango de fechas (`name`, ej.
    «2025-01»), no por un consecutivo — no es un documento que se
    emite, es un contenedor de tiempo."""

    class Status(models.TextChoices):
        OPEN = "open", "Abierto"
        CLOSING = "closing", "Cerrando"
        CLOSED = "closed", "Cerrado"
        REOPENED = "reopened", "Reabierto"

    name = models.CharField("nombre", max_length=50)
    start_date = models.DateField("fecha de inicio")
    end_date = models.DateField("fecha de fin")
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.OPEN)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="abierto por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    opened_at = models.DateTimeField("fecha de apertura", auto_now_add=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="cerrado por", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    closed_at = models.DateTimeField("fecha de cierre", null=True, blank=True)
    notes = models.CharField("notas", max_length=255, blank=True)

    class Meta:
        verbose_name = "período contable"
        verbose_name_plural = "períodos contables"
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_accountingperiod_tenant_nombre"),
            models.CheckConstraint(check=models.Q(end_date__gte=models.F("start_date")), name="accountingperiod_fin_no_antes_de_inicio"),
        ]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------
# Asiento contable (partida doble)
# ---------------------------------------------------------------------


class JournalEntry(TenantScopedModel):
    """Numerado vía la misma `DocumentSequence` de Ventas/Compras/
    Gastos/Nómina (`DocumentType.JOURNAL_ENTRY`, prefijo «AST-»).
    `source_type`/`source_id`/`source_event_key` son la trazabilidad
    hacia el documento origen (`docs/accounting.md` sección 8) — la
    combinación (tenant, source_type, source_event_key) es única
    cuando `source_event_key` no está vacío: la idempotencia
    obligatoria de un reintento (`services.record_business_event`)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        POSTED = "posted", "Contabilizado"

    number = models.CharField("número", max_length=20, db_index=True)
    entry_date = models.DateField("fecha")
    period = models.ForeignKey(AccountingPeriod, verbose_name="período", on_delete=models.PROTECT, related_name="entries")
    description = models.CharField("descripción", max_length=255)
    reference = models.CharField("referencia", max_length=100, blank=True)
    source_type = models.CharField(
        "tipo de origen", max_length=30, blank=True,
        help_text="ej. «sale», «expense_payment», «payroll_payment», «manual».",
    )
    source_id = models.PositiveBigIntegerField("id del origen", null=True, blank=True)
    source_event_key = models.CharField("clave de evento", max_length=100, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.DRAFT)
    reversal_of = models.ForeignKey(
        "self", verbose_name="reversa de", on_delete=models.PROTECT, null=True, blank=True, related_name="reversals",
    )
    metadata = models.JSONField("metadata", default=dict, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "asiento contable"
        verbose_name_plural = "asientos contables"
        ordering = ["-entry_date", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_journalentry_tenant_numero"),
            models.UniqueConstraint(
                fields=["tenant", "source_type", "source_event_key"],
                condition=models.Q(source_event_key__gt=""),
                name="unique_journalentry_tenant_evento",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "period", "status"], name="idx_jentry_tenant_periodo"),
            models.Index(fields=["tenant", "source_type", "source_id"], name="idx_jentry_tenant_origen"),
        ]

    def __str__(self):
        return self.number


class JournalEntryLine(TenantScopedModel):
    """Una línea es débito O crédito, nunca ambos ni ninguno (ver
    constraint). `customer`/`supplier` son el "partner" opcional de la
    línea (ej. la cuenta por cobrar de un cliente específico) — nunca
    una segunda fuente de saldo por cliente, solo trazabilidad; el
    saldo real sigue viviendo en `apps.sales`/`apps.purchases`."""

    journal_entry = models.ForeignKey(JournalEntry, verbose_name="asiento", on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, verbose_name="cuenta", on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField("débito", max_digits=14, decimal_places=2, default=Decimal("0"))
    credit = models.DecimalField("crédito", max_digits=14, decimal_places=2, default=Decimal("0"))
    description = models.CharField("descripción", max_length=255, blank=True)
    currency = models.CharField("moneda", max_length=3, default="USD")
    customer = models.ForeignKey(
        Customer, verbose_name="cliente", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    supplier = models.ForeignKey(
        Supplier, verbose_name="proveedor", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    # --- Preparación FX (ver docs/currency.md) — nunca un motor completo hoy ---
    original_amount = models.DecimalField("monto original", max_digits=14, decimal_places=2, null=True, blank=True)
    original_currency = models.CharField("moneda original", max_length=3, blank=True)
    exchange_rate = models.DecimalField("tipo de cambio", max_digits=14, decimal_places=6, null=True, blank=True)
    line_order = models.PositiveSmallIntegerField("orden", default=1)

    class Meta:
        verbose_name = "línea de asiento"
        verbose_name_plural = "líneas de asiento"
        ordering = ["journal_entry", "line_order"]
        constraints = [
            models.CheckConstraint(check=models.Q(debit__gte=0) & models.Q(credit__gte=0), name="journalentryline_montos_no_negativos"),
            models.CheckConstraint(
                check=(
                    (models.Q(debit__gt=0) & models.Q(credit=0)) | (models.Q(credit__gt=0) & models.Q(debit=0))
                ),
                name="journalentryline_debito_xor_credito",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "account"], name="idx_jeline_tenant_cuenta"),
        ]

    def __str__(self):
        monto = self.debit if self.debit else self.credit
        lado = "Db" if self.debit else "Cr"
        return f"{lado} {self.account.code} {monto}"


# ---------------------------------------------------------------------
# Mapeo de cuentas de control (contabilización automática)
# ---------------------------------------------------------------------


class AccountMapping(TenantScopedModel):
    """Traduce una CLAVE de evento de negocio a una `Account` real —
    la única forma en que `services.record_business_event` sabe en qué
    cuenta contabilizar cada lado de un asiento automático. Sin una
    clave configurada, ese evento simplemente NO se contabiliza
    (nunca bloquea la operación de negocio que lo originó — ver
    `docs/accounting.md` sección 8, "resiliencia obligatoria")."""

    class Key(models.TextChoices):
        ACCOUNTS_RECEIVABLE = "accounts_receivable", "Cuentas por cobrar"
        SALES_REVENUE = "sales_revenue", "Ingresos por ventas"
        SALES_TAX_PAYABLE = "sales_tax_payable", "Impuestos por pagar (ventas)"
        CASH_AND_EQUIVALENTS = "cash_and_equivalents", "Efectivo y equivalentes"
        OPERATING_EXPENSE = "operating_expense", "Gastos operativos"
        PAYROLL_EXPENSE = "payroll_expense", "Gasto de nómina"

    key = models.CharField("clave", max_length=30, choices=Key.choices)
    account = models.ForeignKey(Account, verbose_name="cuenta", on_delete=models.PROTECT, related_name="mappings")

    class Meta:
        verbose_name = "mapeo de cuenta contable"
        verbose_name_plural = "mapeos de cuentas contables"
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="unique_accountmapping_tenant_clave"),
        ]

    def __str__(self):
        return f"{self.get_key_display()} → {self.account.code}"


# ---------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo)
# ---------------------------------------------------------------------


class AccountingActivityLog(TenantScopedModel):
    class Action(models.TextChoices):
        ACCOUNT_CREATED = "account_created", "Cuenta creada"
        PERIOD_OPENED = "period_opened", "Período abierto"
        PERIOD_CLOSED = "period_closed", "Período cerrado"
        PERIOD_REOPENED = "period_reopened", "Período reabierto"
        ENTRY_CREATED = "entry_created", "Asiento creado"
        ENTRY_POSTED = "entry_posted", "Asiento contabilizado"
        ENTRY_REVERSED = "entry_reversed", "Asiento reversado"
        MAPPING_SET = "mapping_set", "Mapeo de cuenta configurado"
        AUTO_POSTING_FAILED = "auto_posting_failed", "Contabilización automática falló"

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
        verbose_name = "registro de actividad (contabilidad)"
        verbose_name_plural = "registros de actividad (contabilidad)"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "entity_type", "entity_id"], name="idx_acctglog_tenant_entidad"),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.entity_type} #{self.entity_id}"
