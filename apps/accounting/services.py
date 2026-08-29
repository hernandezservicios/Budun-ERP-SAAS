"""
Única vía sancionada para operar sobre Contabilidad General (ver
`docs/accounting.md`). Ninguna vista ni otro módulo debe escribir
`Account`/`JournalEntry`/`JournalEntryLine` directamente.

Mismos principios que el resto del proyecto:
- `all_objects` (nunca `objects`/TenantManager) en toda consulta,
  filtrando siempre `tenant` explícitamente.
- `transaction.atomic()` + `select_for_update()` en toda operación que
  lea-y-luego-escriba.
- Un asiento `POSTED` nunca se edita — una corrección es un reverso
  (`reverse_journal_entry`), nunca una edición del histórico.
- La integración automática (`record_business_event`, y los
  `record_*` de más abajo) es DELIBERADAMENTE resiliente: si la
  contabilización falla o no está configurada (`AccountMapping`
  faltante), la operación de negocio que la originó (venta, pago,
  gasto, nómina) NUNCA se ve afectada — se registra el fallo en
  `AccountingActivityLog` y se continúa. Ver `docs/accounting.md`
  sección 8.
"""

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.utils import timezone

from apps.purchases.models import SupplierInvoice, SupplierInvoiceItem, SupplierReturnItem
from apps.sales.models import DocumentSequence, ReturnItem, SaleItem
from apps.sales.services import generate_document_number

from .models import (
    Account,
    AccountingActivityLog,
    AccountingPeriod,
    AccountMapping,
    JournalEntry,
    JournalEntryLine,
    SaleItemTax,
    TaxCode,
)

logger = logging.getLogger("apps.accounting.auto_posting")


class InvalidAccountingOperation(ValidationError):
    """Operación contable inválida: asiento descuadrado, cuenta que no
    admite movimientos, período cerrado, reverso de un asiento ya
    reversado, etc."""


# ------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo)
# ------------------------------------------------------------------


def log_activity(tenant, *, entity_type, entity_id, action, user=None, entity_label="", details=""):
    return AccountingActivityLog.all_objects.create(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id, entity_label=entity_label,
        action=action, user=user, details=details,
    )


def get_activity_log(tenant, *, entity_type, entity_id, limit=20):
    return AccountingActivityLog.all_objects.filter(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id
    ).select_related("user")[:limit]


# ------------------------------------------------------------------
# Plan de cuentas
# ------------------------------------------------------------------


def list_accounts(tenant, *, only_active=True):
    queryset = Account.all_objects.filter(tenant=tenant).select_related("parent")
    if only_active:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("code")


def get_account_tree(tenant):
    """Estructura anidada para la UI — una sola consulta, sin N+1:
    agrupa las cuentas ya cargadas por `parent_id` en memoria."""
    cuentas = list(list_accounts(tenant, only_active=False))
    por_padre = {}
    for cuenta in cuentas:
        por_padre.setdefault(cuenta.parent_id, []).append(cuenta)

    def construir(parent_id):
        return [
            {"cuenta": cuenta, "hijos": construir(cuenta.pk)}
            for cuenta in por_padre.get(parent_id, [])
        ]

    return construir(None)


@transaction.atomic
def create_account(tenant, *, code, name, account_type, user=None, parent=None, allows_posting=True, normal_balance=None, description=""):
    codigo = (code or "").strip()
    if not codigo:
        raise InvalidAccountingOperation("El código de la cuenta es obligatorio.")
    if Account.all_objects.filter(tenant=tenant, code=codigo).exists():
        raise InvalidAccountingOperation(f"Ya existe una cuenta con el código «{codigo}».")
    if parent is not None:
        if parent.tenant_id != tenant.id:
            raise InvalidAccountingOperation("La cuenta padre no pertenece a este tenant.")
        nivel = parent.level + 1
    else:
        nivel = 1

    cuenta = Account.all_objects.create(
        tenant=tenant, code=codigo, name=name, account_type=account_type,
        normal_balance=normal_balance or Account.DEFAULT_NORMAL_BALANCE[account_type],
        parent=parent, level=nivel, allows_posting=allows_posting, description=description,
    )
    log_activity(
        tenant, entity_type="account", entity_id=cuenta.pk, entity_label=cuenta.code,
        action=AccountingActivityLog.Action.ACCOUNT_CREATED, user=user, details=name,
    )
    return cuenta


def set_account_active(account, *, is_active):
    account.is_active = is_active
    account.save(update_fields=["is_active"])
    return account


# ------------------------------------------------------------------
# Período contable
# ------------------------------------------------------------------


def list_periods(tenant):
    return AccountingPeriod.all_objects.filter(tenant=tenant).order_by("-start_date")


@transaction.atomic
def open_period(tenant, *, name, start_date, end_date, user, notes=""):
    if end_date < start_date:
        raise InvalidAccountingOperation("La fecha de fin no puede ser anterior a la fecha de inicio.")
    solapado = AccountingPeriod.all_objects.filter(
        tenant=tenant, start_date__lte=end_date, end_date__gte=start_date,
    ).exclude(status=AccountingPeriod.Status.CLOSED).exists()
    if solapado:
        raise InvalidAccountingOperation("Ya existe un período abierto que se solapa con este rango de fechas.")
    periodo = AccountingPeriod.all_objects.create(
        tenant=tenant, name=name, start_date=start_date, end_date=end_date, opened_by=user, notes=notes,
    )
    log_activity(
        tenant, entity_type="accounting_period", entity_id=periodo.pk, entity_label=periodo.name,
        action=AccountingActivityLog.Action.PERIOD_OPENED, user=user,
    )
    return periodo


def get_period_for_date(tenant, fecha):
    return AccountingPeriod.all_objects.filter(
        tenant=tenant, start_date__lte=fecha, end_date__gte=fecha,
        status__in=[AccountingPeriod.Status.OPEN, AccountingPeriod.Status.REOPENED],
    ).first()


@transaction.atomic
def close_period(period, user):
    locked = AccountingPeriod.all_objects.select_for_update().get(pk=period.pk, tenant=period.tenant)
    if locked.status not in (AccountingPeriod.Status.OPEN, AccountingPeriod.Status.REOPENED):
        raise InvalidAccountingOperation(f"Un período en estado «{locked.get_status_display()}» no puede cerrarse.")
    # Validar que no haya descuadres reales antes de cerrar (red de
    # seguridad — un sistema de partida doble correcto siempre cuadra
    # si cada asiento individual cuadró al contabilizarse, ver
    # `post_journal_entry`, pero esta verificación agregada detecta
    # cualquier inconsistencia real antes de bloquear el período).
    totales = JournalEntryLine.all_objects.filter(
        tenant=locked.tenant, journal_entry__period=locked, journal_entry__status=JournalEntry.Status.POSTED,
    ).aggregate(debitos=Sum("debit"), creditos=Sum("credit"))
    debitos = totales["debitos"] or Decimal("0")
    creditos = totales["creditos"] or Decimal("0")
    if debitos != creditos:
        raise InvalidAccountingOperation(
            f"El período no cuadra (débitos {debitos} ≠ créditos {creditos}) — no puede cerrarse hasta corregirlo."
        )
    locked.status = AccountingPeriod.Status.CLOSED
    locked.closed_by = user
    locked.closed_at = timezone.now()
    locked.save(update_fields=["status", "closed_by", "closed_at"])
    log_activity(
        locked.tenant, entity_type="accounting_period", entity_id=locked.pk, entity_label=locked.name,
        action=AccountingActivityLog.Action.PERIOD_CLOSED, user=user,
    )
    return locked


@transaction.atomic
def reopen_period(period, user, *, reason):
    if not (reason or "").strip():
        raise InvalidAccountingOperation("Reabrir un período cerrado exige indicar un motivo.")
    locked = AccountingPeriod.all_objects.select_for_update().get(pk=period.pk, tenant=period.tenant)
    if locked.status != AccountingPeriod.Status.CLOSED:
        raise InvalidAccountingOperation(f"Un período en estado «{locked.get_status_display()}» no puede reabrirse.")
    locked.status = AccountingPeriod.Status.REOPENED
    locked.save(update_fields=["status"])
    log_activity(
        locked.tenant, entity_type="accounting_period", entity_id=locked.pk, entity_label=locked.name,
        action=AccountingActivityLog.Action.PERIOD_REOPENED, user=user, details=reason,
    )
    return locked


# ------------------------------------------------------------------
# Asientos contables (partida doble)
# ------------------------------------------------------------------


@transaction.atomic
def create_journal_entry(
    tenant, *, entry_date, description, user, lines, period=None, reference="",
    source_type="manual", source_id=None, source_event_key="", metadata=None,
):
    """Crea un asiento en `DRAFT` con sus líneas — `post_journal_entry`
    es quien valida que cuadre y lo contabiliza. `lines`: lista de
    `{"account":, "debit":, "credit":, "description": "", "currency": "USD",
    "customer":, "supplier":}`."""
    if not lines:
        raise InvalidAccountingOperation("Un asiento contable necesita al menos una línea.")
    periodo = period or get_period_for_date(tenant, entry_date)
    if periodo is None:
        raise InvalidAccountingOperation(f"No hay un período contable abierto para la fecha {entry_date}.")
    if periodo.tenant_id != tenant.id:
        raise InvalidAccountingOperation("El período no pertenece a este tenant.")

    numero = generate_document_number(tenant, DocumentSequence.DocumentType.JOURNAL_ENTRY)
    asiento = JournalEntry.all_objects.create(
        tenant=tenant, number=numero, entry_date=entry_date, period=periodo, description=description,
        reference=reference, source_type=source_type, source_id=source_id, source_event_key=source_event_key,
        user=user, metadata=metadata or {},
    )
    for orden, linea in enumerate(lines, start=1):
        cuenta = linea["account"]
        if cuenta.tenant_id != tenant.id:
            raise InvalidAccountingOperation(f"La cuenta «{cuenta.code}» no pertenece a este tenant.")
        JournalEntryLine.all_objects.create(
            tenant=tenant, journal_entry=asiento, account=cuenta,
            debit=linea.get("debit") or Decimal("0"), credit=linea.get("credit") or Decimal("0"),
            description=linea.get("description", ""), currency=linea.get("currency") or "USD",
            customer=linea.get("customer"), supplier=linea.get("supplier"), line_order=orden,
        )
    log_activity(
        tenant, entity_type="journal_entry", entity_id=asiento.pk, entity_label=numero,
        action=AccountingActivityLog.Action.ENTRY_CREATED, user=user, details=description,
    )
    return asiento


@transaction.atomic
def post_journal_entry(entry, user):
    locked = JournalEntry.all_objects.select_for_update().get(pk=entry.pk, tenant=entry.tenant)
    if locked.status != JournalEntry.Status.DRAFT:
        raise InvalidAccountingOperation(f"Un asiento en estado «{locked.get_status_display()}» no puede contabilizarse de nuevo.")
    periodo = AccountingPeriod.all_objects.get(pk=locked.period_id, tenant=locked.tenant)
    if periodo.status not in (AccountingPeriod.Status.OPEN, AccountingPeriod.Status.REOPENED):
        raise InvalidAccountingOperation(f"El período «{periodo.name}» está «{periodo.get_status_display()}» — no admite nuevos asientos.")

    lineas = list(JournalEntryLine.all_objects.filter(tenant=locked.tenant, journal_entry=locked).select_related("account"))
    if not lineas:
        raise InvalidAccountingOperation("El asiento no tiene líneas.")
    monedas = {linea.currency for linea in lineas}
    if len(monedas) > 1:
        raise InvalidAccountingOperation(
            f"El asiento mezcla monedas distintas ({', '.join(sorted(monedas))}) — sin motor de FX "
            "completo, todas las líneas de un mismo asiento deben compartir moneda (ver docs/currency.md)."
        )
    for linea in lineas:
        if not linea.account.allows_posting:
            raise InvalidAccountingOperation(f"La cuenta «{linea.account.code}» es de agrupación — no admite movimientos.")
        if not linea.account.is_active:
            raise InvalidAccountingOperation(f"La cuenta «{linea.account.code}» está inactiva.")

    total_debito = sum((linea.debit for linea in lineas), Decimal("0"))
    total_credito = sum((linea.credit for linea in lineas), Decimal("0"))
    if total_debito != total_credito:
        raise InvalidAccountingOperation(
            f"El asiento no cuadra: débitos {total_debito} ≠ créditos {total_credito}."
        )

    locked.status = JournalEntry.Status.POSTED
    locked.save(update_fields=["status"])
    log_activity(
        locked.tenant, entity_type="journal_entry", entity_id=locked.pk, entity_label=locked.number,
        action=AccountingActivityLog.Action.ENTRY_POSTED, user=user,
    )
    return locked


@transaction.atomic
def reverse_journal_entry(entry, user, *, reason=""):
    """Nunca edita ni borra el asiento original — crea uno NUEVO con
    los montos invertidos, enlazado vía `reversal_of`, y lo contabiliza
    de inmediato (si el período de la fecha de reverso sigue abierto).
    Idempotente: reversar un asiento ya reversado es un no-op que
    devuelve la reversa existente."""
    locked = JournalEntry.all_objects.select_for_update().get(pk=entry.pk, tenant=entry.tenant)
    if locked.status != JournalEntry.Status.POSTED:
        raise InvalidAccountingOperation("Solo un asiento contabilizado puede reversarse.")
    existente = JournalEntry.all_objects.filter(tenant=locked.tenant, reversal_of=locked).first()
    if existente is not None:
        return existente

    lineas = JournalEntryLine.all_objects.filter(tenant=locked.tenant, journal_entry=locked).order_by("line_order")
    fecha_reverso = timezone.localdate()
    lineas_reversa = [
        {
            "account": linea.account, "debit": linea.credit, "credit": linea.debit,
            "description": f"Reverso: {linea.description}" if linea.description else "Reverso",
            "currency": linea.currency, "customer": linea.customer, "supplier": linea.supplier,
        }
        for linea in lineas
    ]
    reversa = create_journal_entry(
        locked.tenant, entry_date=fecha_reverso, description=f"Reverso de {locked.number}" + (f" — {reason}" if reason else ""),
        user=user, lines=lineas_reversa, reference=locked.number, source_type=locked.source_type,
        source_id=locked.source_id, source_event_key=f"reversal-of-{locked.pk}",
    )
    reversa.reversal_of = locked
    reversa.save(update_fields=["reversal_of"])
    reversa = post_journal_entry(reversa, user)
    log_activity(
        locked.tenant, entity_type="journal_entry", entity_id=locked.pk, entity_label=locked.number,
        action=AccountingActivityLog.Action.ENTRY_REVERSED, user=user, details=reason,
    )
    return reversa


def is_entry_reversed(entry):
    return JournalEntry.all_objects.filter(tenant=entry.tenant, reversal_of=entry).exists()


def get_journal_entry_lines(entry):
    return JournalEntryLine.all_objects.filter(tenant=entry.tenant, journal_entry=entry).select_related("account", "customer", "supplier").order_by("line_order")


def list_journal_entries(tenant, *, period=None, status=None):
    queryset = JournalEntry.all_objects.filter(tenant=tenant).select_related("period")
    if period:
        queryset = queryset.filter(period=period)
    if status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("-entry_date", "-id")


# ------------------------------------------------------------------
# Mapeo de cuentas de control
# ------------------------------------------------------------------


def get_mapped_account(tenant, key):
    mapeo = AccountMapping.all_objects.filter(tenant=tenant, key=key).select_related("account").first()
    return mapeo.account if mapeo else None


@transaction.atomic
def set_account_mapping(tenant, *, key, account, user=None):
    if account.tenant_id != tenant.id:
        raise InvalidAccountingOperation("La cuenta no pertenece a este tenant.")
    mapeo, _creado = AccountMapping.all_objects.update_or_create(tenant=tenant, key=key, defaults={"account": account})
    log_activity(
        tenant, entity_type="account_mapping", entity_id=mapeo.pk, entity_label=key,
        action=AccountingActivityLog.Action.MAPPING_SET, user=user, details=account.code,
    )
    return mapeo


def list_account_mappings(tenant):
    return AccountMapping.all_objects.filter(tenant=tenant).select_related("account").order_by("key")


# ------------------------------------------------------------------
# Impuestos multi-código (ampliación de cierre de FASE 14, tenant-
# configurable — mismo patrón que create_account/create_expense_category)
# ------------------------------------------------------------------


def list_tax_codes(tenant, *, only_active=True):
    queryset = TaxCode.all_objects.filter(tenant=tenant).select_related("account")
    if only_active:
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("code")


@transaction.atomic
def create_tax_code(tenant, *, code, name, rate, account, user=None):
    codigo = (code or "").strip()
    if not codigo:
        raise InvalidAccountingOperation("El código de impuesto es obligatorio.")
    if TaxCode.all_objects.filter(tenant=tenant, code=codigo).exists():
        raise InvalidAccountingOperation(f"Ya existe un código de impuesto «{codigo}».")
    if account.tenant_id != tenant.id:
        raise InvalidAccountingOperation("La cuenta de control no pertenece a este tenant.")
    return TaxCode.all_objects.create(tenant=tenant, code=codigo, name=name, rate=rate, account=account)


def apply_tax_code_to_sale_item(sale_item, tax_code, *, base_amount=None):
    """Aplica un `TaxCode` a una línea de venta ya guardada — congela
    `rate_snapshot`/`base_amount`/`tax_amount` al momento de aplicarse
    (cambiar `TaxCode.rate` después nunca altera una línea ya emitida,
    mismo principio que el resto de los snapshots de línea). `base_amount`
    por defecto es `sale_item.subtotal` (la base imponible usual)."""
    if tax_code.tenant_id != sale_item.tenant_id:
        raise InvalidAccountingOperation("El código de impuesto no pertenece a este tenant.")
    base = base_amount if base_amount is not None else sale_item.subtotal
    monto = (base * tax_code.rate / Decimal("100")).quantize(Decimal("0.01"))
    return SaleItemTax.all_objects.create(
        tenant=sale_item.tenant, sale_item=sale_item, tax_code=tax_code,
        rate_snapshot=tax_code.rate, base_amount=base, tax_amount=monto,
    )


# ------------------------------------------------------------------
# Contabilización automática (Business Event → Accounting Service →
# Journal Entry) — ver docs/accounting.md sección 8.
# ------------------------------------------------------------------


def record_business_event(
    tenant, *, source_type, source_id, source_event_key, entry_date, description, lines, user, reference="", metadata=None,
):
    """Punto de entrada genérico para CUALQUIER integración automática.
    Idempotente: si ya existe un asiento para (tenant, source_type,
    source_event_key), lo devuelve tal cual en vez de crear uno nuevo
    — un reintento de la operación de negocio que lo originó nunca
    contabiliza dos veces."""
    existente = JournalEntry.all_objects.filter(
        tenant=tenant, source_type=source_type, source_event_key=source_event_key,
    ).first() if source_event_key else None
    if existente is not None:
        return existente
    asiento = create_journal_entry(
        tenant, entry_date=entry_date, description=description, user=user, lines=lines, reference=reference,
        source_type=source_type, source_id=source_id, source_event_key=source_event_key, metadata=metadata,
    )
    return post_journal_entry(asiento, user)


def _registrar_fallo_contabilizacion(tenant, *, source_type, source_id, error):
    logger.warning("Contabilización automática falló (%s #%s): %s", source_type, source_id, error)
    try:
        log_activity(
            tenant, entity_type=source_type, entity_id=source_id or 0,
            action=AccountingActivityLog.Action.AUTO_POSTING_FAILED, details=str(error)[:255],
        )
    except Exception:  # noqa: BLE001 — ni siquiera dejar que el log de auditoría rompa el llamador.
        logger.exception("No se pudo registrar el fallo de contabilización automática.")


def record_sale_confirmed(sale, user):
    """Venta confirmada → Dr Cuentas por Cobrar (total), Cr Ingresos
    por ventas (subtotal − descuento), Cr Impuestos por pagar (si
    aplica). Nunca bloquea `confirm_sale` — ver el try/except en el
    llamador (`apps.sales.services.confirm_sale`)."""
    cuenta_ar = get_mapped_account(sale.tenant, AccountMapping.Key.ACCOUNTS_RECEIVABLE)
    cuenta_ingresos = get_mapped_account(sale.tenant, AccountMapping.Key.SALES_REVENUE)
    if cuenta_ar is None or cuenta_ingresos is None:
        return None  # Sin configurar todavía — no contabiliza, no bloquea la venta.

    ingreso_neto = sale.subtotal - sale.discount_total
    lines = [
        {"account": cuenta_ar, "debit": sale.total, "customer": sale.customer, "description": f"Venta {sale.number}"},
        {"account": cuenta_ingresos, "credit": ingreso_neto, "description": f"Venta {sale.number}"},
    ]
    # Impuestos multi-código (ampliación de cierre de FASE 14): se
    # comprueban las filas `SaleItemTax` PRIMERO, independientemente de
    # `sale.tax_total` — un tenant que solo usa `TaxCode` en una línea
    # (`SaleItem.tax_rate` en 0) igual debe contabilizarse. Si hay filas,
    # una línea Cr por cada cuenta de `TaxCode` distinta usada; si no
    # hay ninguna, se usa exactamente el camino simple existente
    # (`SALES_TAX_PAYABLE`) cuando `sale.tax_total` es positivo — sin
    # ningún cambio de comportamiento para tenants que nunca adoptan
    # `TaxCode`. Nota de uso esperado: cuando se usan ambos a la vez,
    # el `TaxCode` debe reflejar la MISMA tasa que ya está en
    # `SaleItem.tax_rate` (`sale.total` — lo que paga el cliente — se
    # calcula siempre desde el campo plano, `apps.sales`, nunca desde
    # `SaleItemTax`); `TaxCode` solo decide a qué cuenta va cada
    # porción, documentado en `docs/accounting.md` sección 15.
    agregados_por_cuenta = list(
        SaleItemTax.all_objects.filter(tenant=sale.tenant, sale_item__sale=sale)
        .values("tax_code__account_id").annotate(total=Sum("tax_amount"))
    )
    if agregados_por_cuenta:
        cuentas = {
            c.pk: c for c in Account.all_objects.filter(
                pk__in=[fila["tax_code__account_id"] for fila in agregados_por_cuenta]
            )
        }
        for fila in agregados_por_cuenta:
            cuenta = cuentas[fila["tax_code__account_id"]]
            lines.append({
                "account": cuenta, "credit": fila["total"],
                "description": f"Impuesto ({cuenta.code}) venta {sale.number}",
            })
    elif sale.tax_total:
        cuenta_impuesto = get_mapped_account(sale.tenant, AccountMapping.Key.SALES_TAX_PAYABLE)
        if cuenta_impuesto is None:
            return None
        lines.append({"account": cuenta_impuesto, "credit": sale.tax_total, "description": f"Impuesto venta {sale.number}"})

    for linea in lines:
        linea["currency"] = sale.currency
    return record_business_event(
        sale.tenant, source_type="sale", source_id=sale.pk, source_event_key=f"sale-confirmed-{sale.pk}",
        entry_date=sale.issue_date, description=f"Venta confirmada {sale.number}", lines=lines, user=user,
        reference=sale.number,
    )


def record_sale_cogs(sale, user):
    """Costo de ventas (COGS) de una venta confirmada → Dr Costo de
    Ventas / Cr Inventario, por `SUM(SaleItem.cost_amount)`. Asiento
    SEPARADO del de ingresos (`record_sale_confirmed`) — si falta el
    mapeo de COGS/Inventario, esta entrada específica no se postea (la
    de ingresos sigue intacta, misma resiliencia). Ampliación de cierre
    de FASE 14 — ver docs/accounting.md."""
    cuenta_cogs = get_mapped_account(sale.tenant, AccountMapping.Key.COST_OF_GOODS_SOLD)
    cuenta_inventario = get_mapped_account(sale.tenant, AccountMapping.Key.INVENTORY_ASSET)
    if cuenta_cogs is None or cuenta_inventario is None:
        return None

    # `sale.items` (related_name) usa el manager tenant-scoped por
    # defecto de SaleItem, que depende del ContextVar de TenantMiddleware
    # -- solo fijado durante una request HTTP real. `record_sale_cogs` se
    # invoca desde `confirm_sale`, que también corre en tests/scripts sin
    # ese contexto, así que se usa `all_objects` con tenant explícito,
    # mismo patrón que el resto de este archivo.
    costo_total = sum(
        (item.cost_amount for item in SaleItem.all_objects.filter(tenant=sale.tenant, sale=sale)), Decimal("0"),
    )
    if costo_total <= 0:
        return None  # Sin costo conocido (p. ej. venta confirmada antes de esta ampliación) — nada que contabilizar.

    lines = [
        {"account": cuenta_cogs, "debit": costo_total, "customer": sale.customer, "currency": sale.currency,
         "description": f"Costo de ventas {sale.number}"},
        {"account": cuenta_inventario, "credit": costo_total, "currency": sale.currency,
         "description": f"Costo de ventas {sale.number}"},
    ]
    return record_business_event(
        sale.tenant, source_type="sale", source_id=sale.pk, source_event_key=f"sale-cogs-{sale.pk}",
        entry_date=sale.issue_date, description=f"Costo de ventas — {sale.number}", lines=lines, user=user,
        reference=sale.number,
    )


def record_return_cogs_reversal(return_document, user):
    """Reverso de COGS por una devolución de mercancía → Dr Inventario /
    Cr Costo de Ventas, por el costo de LO REALMENTE devuelto
    (proporcional en devoluciones parciales por cantidad; el costo
    específico de la unidad en devoluciones serializadas). Solo si la
    venta original ya tiene un asiento de COGS contabilizado — si no,
    no hay nada que reversar (no-op). Un `Refund` monetario (modelo
    separado) nunca dispara esta función."""
    sale = return_document.sale
    existe_cogs_original = JournalEntry.all_objects.filter(
        tenant=return_document.tenant, source_type="sale", source_event_key=f"sale-cogs-{sale.pk}",
        status=JournalEntry.Status.POSTED,
    ).exists()
    if not existe_cogs_original:
        return None

    costo_total = Decimal("0")
    for item in ReturnItem.all_objects.filter(tenant=return_document.tenant, return_document=return_document).select_related("sale_item"):
        sale_item = item.sale_item
        if item.inventory_unit_id:
            costo_total += sale_item.cost_amount
        elif item.quantity_returned and sale_item.quantity:
            costo_total += (sale_item.cost_amount / sale_item.quantity) * item.quantity_returned
    if costo_total <= 0:
        return None

    cuenta_cogs = get_mapped_account(return_document.tenant, AccountMapping.Key.COST_OF_GOODS_SOLD)
    cuenta_inventario = get_mapped_account(return_document.tenant, AccountMapping.Key.INVENTORY_ASSET)
    if cuenta_cogs is None or cuenta_inventario is None:
        return None

    lines = [
        {"account": cuenta_inventario, "debit": costo_total, "currency": sale.currency,
         "description": f"Reverso de costo de ventas — {return_document.number}"},
        {"account": cuenta_cogs, "credit": costo_total, "customer": sale.customer, "currency": sale.currency,
         "description": f"Reverso de costo de ventas — {return_document.number}"},
    ]
    return record_business_event(
        return_document.tenant, source_type="return", source_id=return_document.pk,
        source_event_key=f"return-cogs-{return_document.pk}", entry_date=timezone.localdate(),
        description=f"Reverso de costo de ventas — {return_document.number}", lines=lines, user=user,
        reference=return_document.number,
    )


def record_cash_session_closing(session, user):
    """Cierre de sesión de caja con sobrante/faltante → reconoce la
    DIFERENCIA descubierta al contar (nunca el efectivo esperado, que
    ya se contabilizó vía los eventos de venta/pago/gasto/nómina). Sin
    diferencia, no hay nada que reconocer (no-op). Ampliación de cierre
    de FASE 14 — convención contable "Cash Over and Short". Ver
    docs/accounting.md."""
    if not session.difference:
        return None

    cuenta_caja = get_mapped_account(session.tenant, AccountMapping.Key.CASH_AND_EQUIVALENTS)
    if cuenta_caja is None:
        return None

    monto = abs(session.difference)
    if session.difference > 0:
        cuenta_contraparte = get_mapped_account(session.tenant, AccountMapping.Key.CASH_OVER)
        if cuenta_contraparte is None:
            return None
        lines = [
            {"account": cuenta_caja, "debit": monto, "description": f"Sobrante de caja — sesión #{session.pk}"},
            {"account": cuenta_contraparte, "credit": monto, "description": f"Sobrante de caja — sesión #{session.pk}"},
        ]
    else:
        cuenta_contraparte = get_mapped_account(session.tenant, AccountMapping.Key.CASH_SHORT)
        if cuenta_contraparte is None:
            return None
        lines = [
            {"account": cuenta_contraparte, "debit": monto, "description": f"Faltante de caja — sesión #{session.pk}"},
            {"account": cuenta_caja, "credit": monto, "description": f"Faltante de caja — sesión #{session.pk}"},
        ]

    return record_business_event(
        session.tenant, source_type="cash_session", source_id=session.pk,
        source_event_key=f"cash-session-closed-{session.pk}", entry_date=timezone.localdate(),
        description=f"Cierre de sesión de caja #{session.pk} ({'sobrante' if session.difference > 0 else 'faltante'})",
        lines=lines, user=user,
    )


def record_customer_payment(payment, user):
    """Pago de cliente registrado → Dr Efectivo y equivalentes, Cr
    Cuentas por Cobrar (el pago libera saldo de AR, se aplique o no
    todavía a una factura específica — la aplicación en sí, ver
    `apps.sales.PaymentAllocation`, es un movimiento dentro de AR, no
    un evento contable nuevo)."""
    cuenta_caja = get_mapped_account(payment.tenant, AccountMapping.Key.CASH_AND_EQUIVALENTS)
    cuenta_ar = get_mapped_account(payment.tenant, AccountMapping.Key.ACCOUNTS_RECEIVABLE)
    if cuenta_caja is None or cuenta_ar is None:
        return None

    lines = [
        {"account": cuenta_caja, "debit": payment.amount, "customer": payment.customer, "currency": payment.currency,
         "description": f"Pago recibido ({payment.get_method_display()})"},
        {"account": cuenta_ar, "credit": payment.amount, "customer": payment.customer, "currency": payment.currency,
         "description": f"Pago recibido ({payment.get_method_display()})"},
    ]
    return record_business_event(
        payment.tenant, source_type="payment", source_id=payment.pk, source_event_key=f"payment-recorded-{payment.pk}",
        entry_date=timezone.localdate(), description=f"Pago recibido de cliente #{payment.pk}", lines=lines, user=user,
    )


def record_expense_payment_event(expense_payment, user):
    """Pago de gasto → Dr Gastos operativos, Cr Efectivo y
    equivalentes."""
    cuenta_gasto = get_mapped_account(expense_payment.tenant, AccountMapping.Key.OPERATING_EXPENSE)
    cuenta_caja = get_mapped_account(expense_payment.tenant, AccountMapping.Key.CASH_AND_EQUIVALENTS)
    if cuenta_gasto is None or cuenta_caja is None:
        return None

    expense = expense_payment.expense
    lines = [
        {"account": cuenta_gasto, "debit": expense_payment.amount, "supplier": expense.supplier, "currency": expense_payment.currency,
         "description": f"Pago de gasto {expense.number}"},
        {"account": cuenta_caja, "credit": expense_payment.amount, "supplier": expense.supplier, "currency": expense_payment.currency,
         "description": f"Pago de gasto {expense.number}"},
    ]
    return record_business_event(
        expense_payment.tenant, source_type="expense_payment", source_id=expense_payment.pk,
        source_event_key=f"expense-payment-{expense_payment.pk}", entry_date=timezone.localdate(),
        description=f"Pago de gasto {expense.number}", lines=lines, user=user, reference=expense.number,
    )


def record_payroll_payment_event(payroll_payment, user):
    """Pago de nómina → Dr Gasto de nómina, Cr Efectivo y
    equivalentes."""
    cuenta_gasto = get_mapped_account(payroll_payment.tenant, AccountMapping.Key.PAYROLL_EXPENSE)
    cuenta_caja = get_mapped_account(payroll_payment.tenant, AccountMapping.Key.CASH_AND_EQUIVALENTS)
    if cuenta_gasto is None or cuenta_caja is None:
        return None

    nomina = payroll_payment.payroll
    lines = [
        {"account": cuenta_gasto, "debit": payroll_payment.amount, "currency": payroll_payment.currency,
         "description": f"Pago de nómina {nomina.employee_name_snapshot} ({nomina.period.number})"},
        {"account": cuenta_caja, "credit": payroll_payment.amount, "currency": payroll_payment.currency,
         "description": f"Pago de nómina {nomina.employee_name_snapshot} ({nomina.period.number})"},
    ]
    return record_business_event(
        payroll_payment.tenant, source_type="payroll_payment", source_id=payroll_payment.pk,
        source_event_key=f"payroll-payment-{payroll_payment.pk}", entry_date=timezone.localdate(),
        description=f"Pago de nómina {nomina.employee_name_snapshot}", lines=lines, user=user, reference=nomina.period.number,
    )


def record_supplier_invoice_confirmed(invoice, user):
    """Factura de proveedor confirmada → Dr Inventario (líneas ligadas a
    una orden de compra real) y/o Dr Gasto Operativo (líneas sin orden
    — servicio o costo no ligado a inventario) y/o Dr Impuesto por
    Recuperar (si hay impuesto), Cr Cuentas por Pagar por el total.
    Ampliación de cierre de FASE 14 — ver docs/accounting.md."""
    cuenta_ap = get_mapped_account(invoice.tenant, AccountMapping.Key.ACCOUNTS_PAYABLE)
    if cuenta_ap is None:
        return None

    items = list(SupplierInvoiceItem.all_objects.filter(tenant=invoice.tenant, invoice=invoice))
    inventario_subtotal = sum((i.subtotal for i in items if i.purchase_order_item_id), Decimal("0"))
    gasto_subtotal = sum((i.subtotal for i in items if not i.purchase_order_item_id), Decimal("0"))

    lines = []
    if inventario_subtotal > 0:
        cuenta_inventario = get_mapped_account(invoice.tenant, AccountMapping.Key.INVENTORY_ASSET)
        if cuenta_inventario is None:
            return None
        lines.append({
            "account": cuenta_inventario, "debit": inventario_subtotal, "supplier": invoice.supplier,
            "description": f"Compra de inventario — factura {invoice.supplier_invoice_number}",
        })
    if gasto_subtotal > 0:
        cuenta_gasto = get_mapped_account(invoice.tenant, AccountMapping.Key.OPERATING_EXPENSE)
        if cuenta_gasto is None:
            return None
        lines.append({
            "account": cuenta_gasto, "debit": gasto_subtotal, "supplier": invoice.supplier,
            "description": f"Gasto operativo — factura {invoice.supplier_invoice_number}",
        })
    if invoice.tax_total:
        cuenta_impuesto = get_mapped_account(invoice.tenant, AccountMapping.Key.PURCHASE_TAX_RECEIVABLE)
        if cuenta_impuesto is None:
            return None
        lines.append({
            "account": cuenta_impuesto, "debit": invoice.tax_total, "supplier": invoice.supplier,
            "description": f"Impuesto por recuperar — factura {invoice.supplier_invoice_number}",
        })
    if not lines:
        return None  # Factura sin importe reconocible (caso degenerado) — nada que contabilizar.

    lines.append({
        "account": cuenta_ap, "credit": invoice.total, "supplier": invoice.supplier,
        "description": f"Factura de proveedor {invoice.supplier_invoice_number}",
    })
    for linea in lines:
        linea["currency"] = invoice.currency
    return record_business_event(
        invoice.tenant, source_type="supplier_invoice", source_id=invoice.pk,
        source_event_key=f"supplier-invoice-confirmed-{invoice.pk}", entry_date=invoice.issue_date,
        description=f"Factura de proveedor confirmada {invoice.supplier_invoice_number}", lines=lines, user=user,
        reference=invoice.supplier_invoice_number,
    )


def record_supplier_payment(payment, user):
    """Pago a proveedor registrado → Dr Cuentas por Pagar, Cr Efectivo y
    equivalentes — espejo exacto de `record_customer_payment`."""
    cuenta_ap = get_mapped_account(payment.tenant, AccountMapping.Key.ACCOUNTS_PAYABLE)
    cuenta_caja = get_mapped_account(payment.tenant, AccountMapping.Key.CASH_AND_EQUIVALENTS)
    if cuenta_ap is None or cuenta_caja is None:
        return None

    lines = [
        {"account": cuenta_ap, "debit": payment.amount, "supplier": payment.supplier, "currency": payment.currency,
         "description": f"Pago a proveedor ({payment.get_method_display()})"},
        {"account": cuenta_caja, "credit": payment.amount, "supplier": payment.supplier, "currency": payment.currency,
         "description": f"Pago a proveedor ({payment.get_method_display()})"},
    ]
    return record_business_event(
        payment.tenant, source_type="supplier_payment", source_id=payment.pk,
        source_event_key=f"supplier-payment-recorded-{payment.pk}", entry_date=timezone.localdate(),
        description=f"Pago registrado a proveedor #{payment.pk}", lines=lines, user=user,
    )


def record_supplier_return(return_document, user):
    """Devolución a proveedor → Dr Cuentas por Pagar / Cr Inventario, por
    el costo de lo devuelto — SOLO si ya existe alguna factura de este
    proveedor/orden contabilizada (si la devolución ocurre antes de
    facturar, no hay nada contabilizado todavía que revertir)."""
    existe_factura_contabilizada = JournalEntry.all_objects.filter(
        tenant=return_document.tenant, source_type="supplier_invoice", status=JournalEntry.Status.POSTED,
        source_id__in=SupplierInvoice.all_objects.filter(
            tenant=return_document.tenant, purchase_order=return_document.purchase_order,
        ).values_list("pk", flat=True),
    ).exists()
    if not existe_factura_contabilizada:
        return None

    costo_total = Decimal("0")
    for item in SupplierReturnItem.all_objects.filter(tenant=return_document.tenant, return_document=return_document).select_related("receipt_item"):
        if item.inventory_unit_id:
            costo_total += item.receipt_item.unit_cost
        elif item.quantity_returned:
            costo_total += item.receipt_item.unit_cost * item.quantity_returned
    if costo_total <= 0:
        return None

    cuenta_ap = get_mapped_account(return_document.tenant, AccountMapping.Key.ACCOUNTS_PAYABLE)
    cuenta_inventario = get_mapped_account(return_document.tenant, AccountMapping.Key.INVENTORY_ASSET)
    if cuenta_ap is None or cuenta_inventario is None:
        return None

    supplier = return_document.purchase_order.supplier
    lines = [
        {"account": cuenta_ap, "debit": costo_total, "supplier": supplier,
         "description": f"Devolución a proveedor {return_document.number}"},
        {"account": cuenta_inventario, "credit": costo_total,
         "description": f"Devolución a proveedor {return_document.number}"},
    ]
    return record_business_event(
        return_document.tenant, source_type="supplier_return", source_id=return_document.pk,
        source_event_key=f"supplier-return-{return_document.pk}", entry_date=timezone.localdate(),
        description=f"Devolución a proveedor {return_document.number}", lines=lines, user=user,
        reference=return_document.number,
    )


def try_record_sale_confirmed(sale, user):
    try:
        record_sale_confirmed(sale, user)
    except Exception as error:  # noqa: BLE001 — la contabilización automática nunca debe romper la venta.
        _registrar_fallo_contabilizacion(sale.tenant, source_type="sale", source_id=sale.pk, error=error)


def try_record_customer_payment(payment, user):
    try:
        record_customer_payment(payment, user)
    except Exception as error:  # noqa: BLE001
        _registrar_fallo_contabilizacion(payment.tenant, source_type="payment", source_id=payment.pk, error=error)


def try_record_expense_payment(expense_payment, user):
    try:
        record_expense_payment_event(expense_payment, user)
    except Exception as error:  # noqa: BLE001
        _registrar_fallo_contabilizacion(expense_payment.tenant, source_type="expense_payment", source_id=expense_payment.pk, error=error)


def try_record_payroll_payment(payroll_payment, user):
    try:
        record_payroll_payment_event(payroll_payment, user)
    except Exception as error:  # noqa: BLE001
        _registrar_fallo_contabilizacion(payroll_payment.tenant, source_type="payroll_payment", source_id=payroll_payment.pk, error=error)


def try_record_sale_cogs(sale, user):
    try:
        record_sale_cogs(sale, user)
    except Exception as error:  # noqa: BLE001 — la contabilización automática nunca debe romper la venta.
        _registrar_fallo_contabilizacion(sale.tenant, source_type="sale", source_id=sale.pk, error=error)


def try_record_return_cogs_reversal(return_document, user):
    try:
        record_return_cogs_reversal(return_document, user)
    except Exception as error:  # noqa: BLE001 — nunca debe romper la devolución.
        _registrar_fallo_contabilizacion(return_document.tenant, source_type="return", source_id=return_document.pk, error=error)


def try_record_supplier_invoice_confirmed(invoice, user):
    try:
        record_supplier_invoice_confirmed(invoice, user)
    except Exception as error:  # noqa: BLE001 — nunca debe romper la confirmación de la factura.
        _registrar_fallo_contabilizacion(invoice.tenant, source_type="supplier_invoice", source_id=invoice.pk, error=error)


def try_record_supplier_payment(payment, user):
    try:
        record_supplier_payment(payment, user)
    except Exception as error:  # noqa: BLE001 — nunca debe romper el pago al proveedor.
        _registrar_fallo_contabilizacion(payment.tenant, source_type="supplier_payment", source_id=payment.pk, error=error)


def try_record_supplier_return(return_document, user):
    try:
        record_supplier_return(return_document, user)
    except Exception as error:  # noqa: BLE001 — nunca debe romper la devolución al proveedor.
        _registrar_fallo_contabilizacion(return_document.tenant, source_type="supplier_return", source_id=return_document.pk, error=error)


def try_record_cash_session_closing(session, user):
    try:
        record_cash_session_closing(session, user)
    except Exception as error:  # noqa: BLE001 — nunca debe romper el cierre de la sesión de caja.
        _registrar_fallo_contabilizacion(session.tenant, source_type="cash_session", source_id=session.pk, error=error)


# ------------------------------------------------------------------
# Reportes contables (ver docs/accounting.md secciones 21-26)
# ------------------------------------------------------------------


def get_trial_balance(tenant, period):
    """Balance de comprobación: por cuenta, total débito/crédito/saldo
    de todas las líneas POSTED del período."""
    lineas = JournalEntryLine.all_objects.filter(
        tenant=tenant, journal_entry__period=period, journal_entry__status=JournalEntry.Status.POSTED,
    ).values("account_id", "account__code", "account__name", "account__normal_balance").annotate(
        total_debito=Sum("debit"), total_credito=Sum("credit"),
    ).order_by("account__code")

    filas = []
    total_debito = Decimal("0")
    total_credito = Decimal("0")
    for fila in lineas:
        debito = fila["total_debito"] or Decimal("0")
        credito = fila["total_credito"] or Decimal("0")
        saldo = (debito - credito) if fila["account__normal_balance"] == Account.NormalBalance.DEBIT else (credito - debito)
        filas.append({
            "account_id": fila["account_id"], "code": fila["account__code"], "name": fila["account__name"],
            "debit": debito, "credit": credito, "balance": saldo,
        })
        total_debito += debito
        total_credito += credito
    return {"rows": filas, "total_debit": total_debito, "total_credit": total_credito}


def get_general_ledger(tenant, account, *, date_from=None, date_to=None):
    """Movimientos cronológicos de UNA cuenta, con saldo acumulado —
    permite drill-down hasta el asiento origen (`journal_entry`)."""
    queryset = JournalEntryLine.all_objects.filter(
        tenant=tenant, account=account, journal_entry__status=JournalEntry.Status.POSTED,
    ).select_related("journal_entry").order_by("journal_entry__entry_date", "journal_entry__id", "line_order")
    if date_from:
        queryset = queryset.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(journal_entry__entry_date__lte=date_to)

    saldo = Decimal("0")
    filas = []
    for linea in queryset:
        if account.normal_balance == Account.NormalBalance.DEBIT:
            saldo += linea.debit - linea.credit
        else:
            saldo += linea.credit - linea.debit
        filas.append({"line": linea, "running_balance": saldo})
    return filas


def get_general_journal(tenant, *, date_from=None, date_to=None):
    """Libro diario: asientos POSTED en orden cronológico con sus
    líneas — nunca recalculado desde otra fuente que no sea
    `JournalEntry`/`JournalEntryLine`.

    FASE 19 (Performance): hasta esta fase llamaba a
    `get_journal_entry_lines` una vez POR ASIENTO dentro del `for`
    -- N+1 real, medido con un reporte de 300 asientos (301 queries,
    18.7x más lento que con 10 asientos — ver `docs/performance.md`).
    Corregido con `Prefetch` explícito sobre `all_objects` (mismo
    criterio ya establecido para toda relación inversa sobre un
    modelo `TenantScopedModel`, ver `KNOWN_ISSUES.md`
    #90/#95/#97/#108): una sola consulta adicional trae TODAS las
    líneas de TODOS los asientos de la página, agrupadas en Python
    por Django — nunca N consultas."""
    queryset = JournalEntry.all_objects.filter(tenant=tenant, status=JournalEntry.Status.POSTED).order_by("entry_date", "id")
    if date_from:
        queryset = queryset.filter(entry_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(entry_date__lte=date_to)
    queryset = queryset.prefetch_related(
        Prefetch(
            "lines",
            queryset=JournalEntryLine.all_objects.select_related("account", "customer", "supplier").order_by("line_order"),
        )
    )
    return [{"entry": entry, "lines": list(entry.lines.all())} for entry in queryset]


def get_balance_sheet(tenant, period):
    """Estado de situación financiera: ACUMULADO desde siempre hasta
    `period.end_date` (activo/pasivo/patrimonio son saldos, no flujos
    del período — a diferencia del estado de resultados)."""
    lineas = JournalEntryLine.all_objects.filter(
        tenant=tenant, journal_entry__status=JournalEntry.Status.POSTED,
        journal_entry__entry_date__lte=period.end_date,
        account__account_type__in=[Account.AccountType.ASSET, Account.AccountType.LIABILITY, Account.AccountType.EQUITY],
    ).values("account_id", "account__code", "account__name", "account__account_type", "account__normal_balance").annotate(
        total_debito=Sum("debit"), total_credito=Sum("credit"),
    ).order_by("account__account_type", "account__code")

    grupos = {Account.AccountType.ASSET: [], Account.AccountType.LIABILITY: [], Account.AccountType.EQUITY: []}
    totales = {tipo: Decimal("0") for tipo in grupos}
    for fila in lineas:
        debito = fila["total_debito"] or Decimal("0")
        credito = fila["total_credito"] or Decimal("0")
        saldo = (debito - credito) if fila["account__normal_balance"] == Account.NormalBalance.DEBIT else (credito - debito)
        tipo = fila["account__account_type"]
        grupos[tipo].append({"code": fila["account__code"], "name": fila["account__name"], "balance": saldo})
        totales[tipo] += saldo
    return {"assets": grupos[Account.AccountType.ASSET], "liabilities": grupos[Account.AccountType.LIABILITY],
            "equity": grupos[Account.AccountType.EQUITY], "total_assets": totales[Account.AccountType.ASSET],
            "total_liabilities": totales[Account.AccountType.LIABILITY], "total_equity": totales[Account.AccountType.EQUITY]}


def get_income_statement(tenant, period):
    """Estado de resultados: SOLO el flujo DENTRO del rango del
    período (ingresos/costos/gastos se reinician cada período, a
    diferencia del balance general)."""
    lineas = JournalEntryLine.all_objects.filter(
        tenant=tenant, journal_entry__status=JournalEntry.Status.POSTED,
        journal_entry__entry_date__gte=period.start_date, journal_entry__entry_date__lte=period.end_date,
        account__account_type__in=[Account.AccountType.REVENUE, Account.AccountType.COST, Account.AccountType.EXPENSE],
    ).values("account_id", "account__code", "account__name", "account__account_type", "account__normal_balance").annotate(
        total_debito=Sum("debit"), total_credito=Sum("credit"),
    ).order_by("account__account_type", "account__code")

    grupos = {Account.AccountType.REVENUE: [], Account.AccountType.COST: [], Account.AccountType.EXPENSE: []}
    totales = {tipo: Decimal("0") for tipo in grupos}
    for fila in lineas:
        debito = fila["total_debito"] or Decimal("0")
        credito = fila["total_credito"] or Decimal("0")
        saldo = (debito - credito) if fila["account__normal_balance"] == Account.NormalBalance.DEBIT else (credito - debito)
        tipo = fila["account__account_type"]
        grupos[tipo].append({"code": fila["account__code"], "name": fila["account__name"], "balance": saldo})
        totales[tipo] += saldo

    ingresos = totales[Account.AccountType.REVENUE]
    costos = totales[Account.AccountType.COST]
    gastos = totales[Account.AccountType.EXPENSE]
    utilidad_bruta = ingresos - costos
    utilidad_neta = utilidad_bruta - gastos
    return {
        "revenue": grupos[Account.AccountType.REVENUE], "cost": grupos[Account.AccountType.COST],
        "expense": grupos[Account.AccountType.EXPENSE], "total_revenue": ingresos, "total_cost": costos,
        "total_expense": gastos, "gross_profit": utilidad_bruta, "net_income": utilidad_neta,
    }


def get_inventory_gl_reconciliation(tenant):
    """Reporte de integridad (ampliación de cierre de FASE 14): compara
    el valor de inventario calculado por `apps.inventory` (fuente real
    de cantidades/costos) contra el saldo de la cuenta mapeada
    `INVENTORY_ASSET` en el Libro Mayor — nunca una tercera cifra, solo
    una comparación de las dos que ya existen. Si no hay cuenta mapeada,
    devuelve `None` (nada que reconciliar todavía)."""
    from apps.inventory.services import get_inventory_valuation

    cuenta_inventario = get_mapped_account(tenant, AccountMapping.Key.INVENTORY_ASSET)
    if cuenta_inventario is None:
        return None

    valorizacion = get_inventory_valuation(tenant)
    lineas_mayor = get_general_ledger(tenant, cuenta_inventario)
    saldo_contable = lineas_mayor[-1]["running_balance"] if lineas_mayor else Decimal("0")
    valor_inventario = valorizacion["total_value"]
    return {
        "inventory_value": valor_inventario, "gl_balance": saldo_contable,
        "difference": valor_inventario - saldo_contable, "rows": valorizacion["rows"],
    }
