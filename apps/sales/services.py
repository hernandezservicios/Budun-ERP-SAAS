"""
Capa de servicios del motor comercial (FASE 10): la única vía sancionada
para crear/editar/transicionar Cotizaciones, Proformas, Ventas, Pagos,
Reservas, Devoluciones y Reembolsos. Ninguna vista debe escribir estos
modelos directamente.

Principios heredados de FASES 8/9, aplicados aquí sin excepción:
- `transaction.atomic()` + `select_for_update()` en toda operación que
  lea-y-luego-escriba un valor que pueda cambiar por concurrencia
  (numeración, confirmación de venta, reservas, pagos).
- `all_objects` (nunca `objects`/TenantManager) en todas las consultas de
  este módulo, filtrando siempre `tenant` de forma explícita — mismo
  razonamiento documentado en `apps.inventory.services`.
- Operaciones inválidas se rechazan ANTES de escribir nada
  (`InvalidSalesOperation`, subclase de `ValidationError`).
- NUNCA se duplica lógica de inventario: todo lo que toca stock/unidades
  llama a `apps.inventory.services` (`register_stock_in`,
  `register_stock_out`, `transition_unit_status`,
  `ensure_unit_available_for_sale`, `get_current_stock`) — este módulo
  solo orquesta CUÁNDO llamarlas.

Ver `docs/sales.md` para el diseño completo (cálculo de totales,
máquinas de estado, snapshot histórico, concurrencia).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.customers.file_validation import nombre_original_seguro, validar_archivo_adjunto
from apps.inventory.models import InventoryUnit, Product
from apps.inventory.services import (
    InvalidInventoryOperation,
    get_current_stock,
    register_stock_in,
    register_stock_out,
    transition_unit_status,
)

from .models import (
    CreditNote,
    CreditNoteApplication,
    DocumentSequence,
    Payment,
    PaymentAllocation,
    PaymentMethod,
    ProformaInvoice,
    ProformaInvoiceItem,
    Quotation,
    QuotationItem,
    Refund,
    Reservation,
    Return,
    ReturnItem,
    Sale,
    SaleItem,
    SalesActivityLog,
    SalesDocumentAttachment,
)


class InvalidSalesOperation(ValidationError):
    """Se lanza cuando una operación del motor comercial no es válida:
    transición de estado no permitida, datos insuficientes, intento de
    sobre-reservar, pago/reembolso inválido, etc."""


# ------------------------------------------------------------------
# Numeración de documentos
# ------------------------------------------------------------------

_PREFIJOS_POR_DEFECTO = {
    DocumentSequence.DocumentType.QUOTATION: "COT",
    DocumentSequence.DocumentType.PROFORMA: "PRO",
    DocumentSequence.DocumentType.SALE: "FAC",
    DocumentSequence.DocumentType.RETURN: "DEV",
    DocumentSequence.DocumentType.CREDIT_NOTE: "NC",
    # FASE 12 (Compras) — apps.purchases.services llama a
    # generate_document_number(tenant, DocumentSequence.DocumentType.PURCHASE_ORDER)
    # literalmente, nunca reimplementa su propia numeración.
    DocumentSequence.DocumentType.PURCHASE_ORDER: "OC",
    DocumentSequence.DocumentType.PURCHASE_RECEIPT: "REC",
    DocumentSequence.DocumentType.SUPPLIER_RETURN: "DEVP",
    # FASE 13 (Gastos + RRHH + Nómina) — apps.expenses.services/
    # apps.payroll.services llaman a generate_document_number
    # literalmente, nunca reimplementan su propia numeración.
    DocumentSequence.DocumentType.EXPENSE: "GAS",
    DocumentSequence.DocumentType.PAYROLL_PERIOD: "NOM",
    # FASE 14 (Contabilidad General) — apps.accounting.services llama a
    # generate_document_number literalmente, nunca reimplementa su
    # propia numeración.
    DocumentSequence.DocumentType.JOURNAL_ENTRY: "AST",
}


@transaction.atomic
def generate_document_number(tenant, document_type):
    """Número comercial único por tenant y tipo de documento — nunca el
    ID de base de datos. `select_for_update()` (implícito en
    `get_or_create` sobre una fila ya bloqueada, y en el `save`
    subsiguiente dentro de la misma transacción) evita que dos
    documentos creados al mismo tiempo reciban el mismo número."""
    secuencia, creada = DocumentSequence.all_objects.select_for_update().get_or_create(
        tenant=tenant,
        document_type=document_type,
        defaults={"prefix": _PREFIJOS_POR_DEFECTO[document_type]},
    )
    if not creada:
        # Re-obtener con el lock ya aplicado (get_or_create no relockea
        # si la fila ya existía antes de esta llamada a select_for_update
        # en algunas versiones; esta segunda lectura explícita es barata
        # y garantiza que el valor que incrementamos es el más reciente).
        secuencia = DocumentSequence.all_objects.select_for_update().get(pk=secuencia.pk)
    numero_actual = secuencia.next_number
    secuencia.next_number = numero_actual + 1
    secuencia.save(update_fields=["next_number"])
    return f"{secuencia.prefix}-{str(numero_actual).zfill(secuencia.padding)}"


# ------------------------------------------------------------------
# Cálculo de líneas y totales (genérico: Quotation/ProformaInvoice/Sale)
# ------------------------------------------------------------------


def _snapshot_item_fields(product, quantity, *, unit_price=None, discount_percent=None, discount_amount=None, tax_rate=None, inventory_unit=None):
    return dict(
        product=product,
        inventory_unit=inventory_unit,
        description=product.name,
        sku_snapshot=product.sku,
        quantity=quantity,
        unit_price=unit_price if unit_price is not None else product.sale_price,
        discount_percent=discount_percent or Decimal("0"),
        discount_amount=discount_amount or Decimal("0"),
        tax_rate=tax_rate if tax_rate is not None else product.tax_rate,
    )


def _recalculate_item(item):
    """Recalcula los campos derivados de una línea (subtotal, monto de
    descuento efectivo, impuesto, total). El descuento por PORCENTAJE
    tiene prioridad sobre el descuento por MONTO FIJO si ambos llegaran
    a estar presentes — nunca se suman los dos."""
    line_subtotal = (item.quantity * item.unit_price).quantize(Decimal("0.01"))
    if item.discount_percent and item.discount_percent > 0:
        descuento = (line_subtotal * item.discount_percent / Decimal("100")).quantize(Decimal("0.01"))
    else:
        descuento = item.discount_amount or Decimal("0")
    base_imponible = line_subtotal - descuento
    impuesto = (base_imponible * item.tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    item.subtotal = line_subtotal
    item.discount_amount = descuento  # normalizado: siempre el monto EFECTIVO usado
    item.tax_amount = impuesto
    item.total = base_imponible + impuesto
    return item


def get_quotation_items(quotation):
    return (
        QuotationItem.all_objects.filter(tenant=quotation.tenant, quotation=quotation)
        .select_related("product", "inventory_unit")
        .order_by("line_order", "id")
    )


def get_proforma_items(proforma):
    return (
        ProformaInvoiceItem.all_objects.filter(tenant=proforma.tenant, proforma=proforma)
        .select_related("product", "inventory_unit")
        .order_by("line_order", "id")
    )


def get_sale_items(sale):
    return (
        SaleItem.all_objects.filter(tenant=sale.tenant, sale=sale)
        .select_related("product", "inventory_unit")
        .order_by("line_order", "id")
    )


def _items_queryset_for(document):
    """Consulta explícita (`all_objects` + filtro por tenant/FK) de las
    líneas de un documento — NUNCA la relación inversa por defecto
    (`document.items`), que usa `TenantManager` y depende del
    `ContextVar` de una request HTTP real (mismo principio ya
    documentado en `apps.inventory.services`): este módulo debe dar el
    mismo resultado se llame desde una vista o desde un script/tarea sin
    request activa."""
    if isinstance(document, Quotation):
        return get_quotation_items(document)
    if isinstance(document, ProformaInvoice):
        return get_proforma_items(document)
    if isinstance(document, Sale):
        return get_sale_items(document)
    raise TypeError(f"Tipo de documento comercial no soportado: {type(document)!r}")


def recalculate_document_totals(document):
    """Recalcula la cabecera (subtotal/descuento/impuesto/total) a
    partir de sus líneas — nunca al revés. El descuento GLOBAL del
    documento se aplica como una rebaja FINAL sobre la suma de los
    totales de línea (simplificación deliberada y documentada, ver
    `docs/sales.md`): no se redistribuye proporcionalmente en la base
    imponible de cada línea."""
    items = list(_items_queryset_for(document))
    subtotal = sum((i.quantity * i.unit_price for i in items), Decimal("0")).quantize(Decimal("0.01"))
    descuento_lineas = sum((i.discount_amount for i in items), Decimal("0"))
    impuesto_total = sum((i.tax_amount for i in items), Decimal("0"))
    total_antes_de_global = sum((i.total for i in items), Decimal("0"))

    if document.global_discount_percent and document.global_discount_percent > 0:
        descuento_global = (total_antes_de_global * document.global_discount_percent / Decimal("100")).quantize(
            Decimal("0.01")
        )
    else:
        descuento_global = document.global_discount_amount or Decimal("0")
    descuento_global = min(descuento_global, total_antes_de_global)  # nunca más que el total

    document.subtotal = subtotal
    document.discount_total = descuento_lineas + descuento_global
    document.tax_total = impuesto_total
    document.total = total_antes_de_global - descuento_global
    document.save(update_fields=["subtotal", "discount_total", "tax_total", "total", "updated_at"])
    return document


# ------------------------------------------------------------------
# Auditoría (bitácora mínima, ver models.SalesActivityLog)
# ------------------------------------------------------------------


def log_activity(tenant, *, entity_type, entity_id, action, user, entity_label="", details=""):
    return SalesActivityLog.all_objects.create(
        tenant=tenant,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        action=action,
        user=user,
        details=details,
    )


def get_activity_log(tenant, *, entity_type, entity_id, limit=20):
    return SalesActivityLog.all_objects.filter(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id
    ).select_related("user")[:limit]


# ------------------------------------------------------------------
# Cotizaciones
# ------------------------------------------------------------------

QUOTATION_TRANSITIONS = {
    Quotation.Status.DRAFT: {Quotation.Status.SENT, Quotation.Status.CANCELED, Quotation.Status.CONVERTED},
    Quotation.Status.SENT: {
        Quotation.Status.ACCEPTED,
        Quotation.Status.REJECTED,
        Quotation.Status.EXPIRED,
        Quotation.Status.CANCELED,
        Quotation.Status.CONVERTED,
    },
    Quotation.Status.ACCEPTED: {Quotation.Status.CONVERTED, Quotation.Status.CANCELED},
    Quotation.Status.REJECTED: set(),
    Quotation.Status.EXPIRED: set(),
    Quotation.Status.CANCELED: set(),
    Quotation.Status.CONVERTED: set(),
}
_QUOTATION_EDITABLE_STATUSES = {Quotation.Status.DRAFT}


def _require_editable_quotation(quotation):
    if quotation.status not in _QUOTATION_EDITABLE_STATUSES:
        raise InvalidSalesOperation(
            f"La cotización «{quotation.number}» no se puede editar en estado {quotation.get_status_display()}."
        )


@transaction.atomic
def create_quotation(tenant, *, user, customer=None, currency="USD", payment_terms="contado", notes="", terms="", issue_date=None, expiry_date=None, global_discount_percent=None, global_discount_amount=None):
    numero = generate_document_number(tenant, DocumentSequence.DocumentType.QUOTATION)
    quotation = Quotation.all_objects.create(
        tenant=tenant,
        number=numero,
        customer=customer,
        salesperson=user,
        currency=currency,
        payment_terms=payment_terms,
        notes=notes,
        terms=terms,
        issue_date=issue_date or timezone.localdate(),
        expiry_date=expiry_date,
        global_discount_percent=global_discount_percent or Decimal("0"),
        global_discount_amount=global_discount_amount or Decimal("0"),
    )
    log_activity(tenant, entity_type="quotation", entity_id=quotation.pk, entity_label=numero, action=SalesActivityLog.Action.CREATED, user=user)
    return quotation


@transaction.atomic
def add_quotation_item(quotation, *, product, quantity, user=None, **kwargs):
    _require_editable_quotation(quotation)
    orden = get_quotation_items(quotation).count() + 1
    item = QuotationItem.all_objects.create(
        tenant=quotation.tenant, quotation=quotation, line_order=orden,
        **_snapshot_item_fields(product, quantity, **kwargs),
    )
    _recalculate_item(item)
    item.save()
    recalculate_document_totals(quotation)
    return item


@transaction.atomic
def remove_quotation_item(item):
    quotation = item.quotation
    _require_editable_quotation(quotation)
    item.delete()
    recalculate_document_totals(quotation)


@transaction.atomic
def transition_quotation_status(quotation, new_status, user, action_label=None):
    locked = Quotation.all_objects.select_for_update().get(pk=quotation.pk, tenant=quotation.tenant)
    permitidos = QUOTATION_TRANSITIONS.get(locked.status, set())
    if new_status not in permitidos:
        raise InvalidSalesOperation(
            f"No se puede pasar la cotización «{locked.number}» de "
            f"{locked.get_status_display()} a {Quotation.Status(new_status).label}."
        )
    locked.status = new_status
    locked.save(update_fields=["status", "updated_at"])
    log_activity(
        locked.tenant, entity_type="quotation", entity_id=locked.pk, entity_label=locked.number,
        action=action_label or new_status, user=user,
    )
    return locked


@transaction.atomic
def duplicate_quotation(quotation, user):
    nueva = create_quotation(
        quotation.tenant, user=user, customer=quotation.customer, currency=quotation.currency,
        payment_terms=quotation.payment_terms, notes=quotation.notes, terms=quotation.terms,
    )
    for item in get_quotation_items(quotation):
        QuotationItem.all_objects.create(
            tenant=nueva.tenant, quotation=nueva, product=item.product, inventory_unit=None,
            description=item.description, sku_snapshot=item.sku_snapshot, quantity=item.quantity,
            unit_price=item.unit_price, discount_percent=item.discount_percent, discount_amount=item.discount_amount,
            tax_rate=item.tax_rate, line_order=item.line_order,
        )
    for i in get_quotation_items(nueva):
        _recalculate_item(i)
        i.save()
    recalculate_document_totals(nueva)
    return nueva


def _copy_items_into(source_items, *, item_model, parent_field, parent, tenant):
    for item in source_items:
        kwargs = {
            parent_field: parent,
            "tenant": tenant,
            "product": item.product,
            "inventory_unit": item.inventory_unit,
            "description": item.description,
            "sku_snapshot": item.sku_snapshot,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "discount_percent": item.discount_percent,
            "discount_amount": item.discount_amount,
            "tax_rate": item.tax_rate,
            "tax_amount": item.tax_amount,
            "subtotal": item.subtotal,
            "total": item.total,
            "line_order": item.line_order,
        }
        item_model.all_objects.create(**kwargs)


@transaction.atomic
def convert_quotation_to_proforma(quotation, user):
    locked = Quotation.all_objects.select_for_update().get(pk=quotation.pk, tenant=quotation.tenant)
    if Quotation.Status.CONVERTED not in QUOTATION_TRANSITIONS.get(locked.status, set()):
        raise InvalidSalesOperation(
            f"La cotización «{locked.number}» no se puede convertir desde {locked.get_status_display()}."
        )
    if hasattr(locked, "converted_proforma"):
        raise InvalidSalesOperation(f"La cotización «{locked.number}» ya fue convertida a una proforma.")

    numero = generate_document_number(locked.tenant, DocumentSequence.DocumentType.PROFORMA)
    proforma = ProformaInvoice.all_objects.create(
        tenant=locked.tenant, number=numero, customer=locked.customer, salesperson=locked.salesperson,
        currency=locked.currency, payment_terms=locked.payment_terms, notes=locked.notes, terms=locked.terms,
        global_discount_percent=locked.global_discount_percent, global_discount_amount=locked.global_discount_amount,
        source_quotation=locked,
    )
    _copy_items_into(_items_queryset_for(locked), item_model=ProformaInvoiceItem, parent_field="proforma", parent=proforma, tenant=locked.tenant)
    recalculate_document_totals(proforma)

    locked.status = Quotation.Status.CONVERTED
    locked.converted_at = timezone.now()
    locked.converted_by = user
    locked.save(update_fields=["status", "converted_at", "converted_by", "updated_at"])
    log_activity(locked.tenant, entity_type="quotation", entity_id=locked.pk, entity_label=locked.number, action=SalesActivityLog.Action.CONVERTED, user=user, details=f"→ proforma {numero}")
    return proforma


@transaction.atomic
def convert_quotation_to_sale(quotation, user):
    locked = Quotation.all_objects.select_for_update().get(pk=quotation.pk, tenant=quotation.tenant)
    if Quotation.Status.CONVERTED not in QUOTATION_TRANSITIONS.get(locked.status, set()):
        raise InvalidSalesOperation(
            f"La cotización «{locked.number}» no se puede convertir desde {locked.get_status_display()}."
        )
    if hasattr(locked, "converted_sale_direct"):
        raise InvalidSalesOperation(f"La cotización «{locked.number}» ya fue convertida a una venta.")

    numero = generate_document_number(locked.tenant, DocumentSequence.DocumentType.SALE)
    sale = Sale.all_objects.create(
        tenant=locked.tenant, number=numero, customer=locked.customer, salesperson=locked.salesperson,
        currency=locked.currency, payment_terms=locked.payment_terms, notes=locked.notes, terms=locked.terms,
        global_discount_percent=locked.global_discount_percent, global_discount_amount=locked.global_discount_amount,
        source_quotation=locked,
    )
    _copy_items_into(_items_queryset_for(locked), item_model=SaleItem, parent_field="sale", parent=sale, tenant=locked.tenant)
    recalculate_document_totals(sale)

    locked.status = Quotation.Status.CONVERTED
    locked.converted_at = timezone.now()
    locked.converted_by = user
    locked.save(update_fields=["status", "converted_at", "converted_by", "updated_at"])
    log_activity(locked.tenant, entity_type="quotation", entity_id=locked.pk, entity_label=locked.number, action=SalesActivityLog.Action.CONVERTED, user=user, details=f"→ venta {numero}")
    return sale


def get_expired_quotation_candidates(tenant=None):
    queryset = Quotation.all_objects.filter(
        status__in=[Quotation.Status.DRAFT, Quotation.Status.SENT], expiry_date__lt=timezone.localdate()
    )
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    return queryset


def expire_due_quotations(tenant=None):
    """Marca como vencidas las cotizaciones con `expiry_date` pasada.
    Pensada para ejecutarse sin request activa (comando de
    administración / tarea programada futura) — usa `all_objects` con
    filtro explícito, mismo principio que `apps.inventory.services`."""
    vencidas = []
    for quotation in get_expired_quotation_candidates(tenant):
        vencidas.append(transition_quotation_status(quotation, Quotation.Status.EXPIRED, user=None, action_label=SalesActivityLog.Action.EXPIRED))
    return vencidas


# ------------------------------------------------------------------
# Proforma / Prefactura
# ------------------------------------------------------------------

PROFORMA_TRANSITIONS = {
    ProformaInvoice.Status.DRAFT: {ProformaInvoice.Status.ISSUED, ProformaInvoice.Status.CANCELED},
    ProformaInvoice.Status.ISSUED: {
        ProformaInvoice.Status.EXPIRED,
        ProformaInvoice.Status.CANCELED,
        ProformaInvoice.Status.CONVERTED,
    },
    ProformaInvoice.Status.EXPIRED: set(),
    ProformaInvoice.Status.CANCELED: set(),
    ProformaInvoice.Status.CONVERTED: set(),
}
_PROFORMA_EDITABLE_STATUSES = {ProformaInvoice.Status.DRAFT}


def _require_editable_proforma(proforma):
    if proforma.status not in _PROFORMA_EDITABLE_STATUSES:
        raise InvalidSalesOperation(
            f"La proforma «{proforma.number}» no se puede editar en estado {proforma.get_status_display()}."
        )


@transaction.atomic
def create_proforma(tenant, *, user, customer=None, currency="USD", payment_terms="contado", notes="", terms="", issue_date=None, expiry_date=None, global_discount_percent=None, global_discount_amount=None):
    numero = generate_document_number(tenant, DocumentSequence.DocumentType.PROFORMA)
    proforma = ProformaInvoice.all_objects.create(
        tenant=tenant, number=numero, customer=customer, salesperson=user, currency=currency,
        payment_terms=payment_terms, notes=notes, terms=terms,
        issue_date=issue_date or timezone.localdate(), expiry_date=expiry_date,
        global_discount_percent=global_discount_percent or Decimal("0"),
        global_discount_amount=global_discount_amount or Decimal("0"),
    )
    log_activity(tenant, entity_type="proforma", entity_id=proforma.pk, entity_label=numero, action=SalesActivityLog.Action.CREATED, user=user)
    return proforma


@transaction.atomic
def add_proforma_item(proforma, *, product, quantity, user=None, **kwargs):
    _require_editable_proforma(proforma)
    orden = get_proforma_items(proforma).count() + 1
    item = ProformaInvoiceItem.all_objects.create(
        tenant=proforma.tenant, proforma=proforma, line_order=orden,
        **_snapshot_item_fields(product, quantity, **kwargs),
    )
    _recalculate_item(item)
    item.save()
    recalculate_document_totals(proforma)
    return item


@transaction.atomic
def remove_proforma_item(item):
    proforma = item.proforma
    _require_editable_proforma(proforma)
    item.delete()
    recalculate_document_totals(proforma)


@transaction.atomic
def transition_proforma_status(proforma, new_status, user, action_label=None):
    locked = ProformaInvoice.all_objects.select_for_update().get(pk=proforma.pk, tenant=proforma.tenant)
    permitidos = PROFORMA_TRANSITIONS.get(locked.status, set())
    if new_status not in permitidos:
        raise InvalidSalesOperation(
            f"No se puede pasar la proforma «{locked.number}» de "
            f"{locked.get_status_display()} a {ProformaInvoice.Status(new_status).label}."
        )
    locked.status = new_status
    locked.save(update_fields=["status", "updated_at"])
    log_activity(locked.tenant, entity_type="proforma", entity_id=locked.pk, entity_label=locked.number, action=action_label or new_status, user=user)

    if new_status in (ProformaInvoice.Status.CANCELED, ProformaInvoice.Status.EXPIRED):
        _release_reservations_for_source(Reservation.SourceType.PROFORMA, locked.pk, user=user)
    return locked


@transaction.atomic
def convert_proforma_to_sale(proforma, user):
    locked = ProformaInvoice.all_objects.select_for_update().get(pk=proforma.pk, tenant=proforma.tenant)
    if ProformaInvoice.Status.CONVERTED not in PROFORMA_TRANSITIONS.get(locked.status, set()):
        raise InvalidSalesOperation(
            f"La proforma «{locked.number}» no se puede convertir desde {locked.get_status_display()}."
        )
    if hasattr(locked, "converted_sale"):
        raise InvalidSalesOperation(f"La proforma «{locked.number}» ya fue convertida a una venta.")

    numero = generate_document_number(locked.tenant, DocumentSequence.DocumentType.SALE)
    sale = Sale.all_objects.create(
        tenant=locked.tenant, number=numero, customer=locked.customer, salesperson=locked.salesperson,
        currency=locked.currency, payment_terms=locked.payment_terms, notes=locked.notes, terms=locked.terms,
        global_discount_percent=locked.global_discount_percent, global_discount_amount=locked.global_discount_amount,
        source_proforma=locked, source_quotation=locked.source_quotation,
    )
    _copy_items_into(_items_queryset_for(locked), item_model=SaleItem, parent_field="sale", parent=sale, tenant=locked.tenant)
    recalculate_document_totals(sale)

    locked.status = ProformaInvoice.Status.CONVERTED
    locked.converted_at = timezone.now()
    locked.converted_by = user
    locked.save(update_fields=["status", "converted_at", "converted_by", "updated_at"])
    log_activity(locked.tenant, entity_type="proforma", entity_id=locked.pk, entity_label=locked.number, action=SalesActivityLog.Action.CONVERTED, user=user, details=f"→ venta {numero}")
    return sale


def get_expired_proforma_candidates(tenant=None):
    queryset = ProformaInvoice.all_objects.filter(
        status=ProformaInvoice.Status.ISSUED, expiry_date__lt=timezone.localdate()
    )
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    return queryset


def expire_due_proformas(tenant=None):
    vencidas = []
    for proforma in get_expired_proforma_candidates(tenant):
        vencidas.append(
            transition_proforma_status(proforma, ProformaInvoice.Status.EXPIRED, user=None, action_label=SalesActivityLog.Action.EXPIRED)
        )
    return vencidas


# ------------------------------------------------------------------
# Reservas
# ------------------------------------------------------------------

RESERVATION_TRANSITIONS = {
    Reservation.Status.ACTIVE: {Reservation.Status.RELEASED, Reservation.Status.CONVERTED, Reservation.Status.EXPIRED},
    Reservation.Status.RELEASED: set(),
    Reservation.Status.CONVERTED: set(),
    Reservation.Status.EXPIRED: set(),
}


def get_reserved_quantity(product):
    total = Reservation.all_objects.filter(
        tenant=product.tenant, product=product, status=Reservation.Status.ACTIVE, quantity__isnull=False
    ).aggregate(total=Sum("quantity"))["total"]
    return total or Decimal("0")


def get_available_to_promise(product):
    """Disponibilidad real para prometer en una nueva cotización/venta.
    Para SERIALIZED, `get_current_stock` (FASE 8) ya cuenta solo
    unidades EN_STOCK (una unidad RESERVADO no cuenta), así que no hace
    falta restar nada más. Para QUANTITY, se resta la cantidad
    actualmente reservada (una capa que `StockMovement` no conoce)."""
    stock_actual = get_current_stock(product)
    if product.inventory_tracking_type == Product.TrackingType.SERIALIZED:
        return stock_actual
    return stock_actual - get_reserved_quantity(product)


@transaction.atomic
def create_reservation(tenant, *, product, user, customer=None, quantity=None, inventory_unit=None, source_type=Reservation.SourceType.MANUAL, source_id=None, expires_at=None, notes=""):
    if bool(quantity) == bool(inventory_unit):
        raise InvalidSalesOperation(
            "Indica cantidad a reservar (producto por cantidad) o una unidad concreta (producto serializado), no ambos ni ninguno."
        )

    if inventory_unit is not None:
        unit = InventoryUnit.all_objects.select_for_update().get(pk=inventory_unit.pk, tenant=tenant)
        try:
            transition_unit_status(unit=unit, new_status=InventoryUnit.Status.RESERVADO, user=user)
        except InvalidInventoryOperation as error:
            raise InvalidSalesOperation(str(error)) from error
        reservation = Reservation.all_objects.create(
            tenant=tenant, product=product, inventory_unit=unit, customer=customer,
            source_type=source_type, source_id=source_id, user=user, expires_at=expires_at, notes=notes,
        )
    else:
        locked_product = Product.all_objects.select_for_update().get(pk=product.pk, tenant=tenant)
        disponible = get_available_to_promise(locked_product)
        if quantity <= 0:
            raise InvalidSalesOperation("La cantidad a reservar debe ser mayor que cero.")
        if quantity > disponible:
            raise InvalidSalesOperation(
                f"No hay suficiente disponibilidad de «{locked_product.sku}» para reservar "
                f"(disponible: {disponible}, solicitado: {quantity})."
            )
        reservation = Reservation.all_objects.create(
            tenant=tenant, product=locked_product, quantity=quantity, customer=customer,
            source_type=source_type, source_id=source_id, user=user, expires_at=expires_at, notes=notes,
        )
    log_activity(tenant, entity_type="reservation", entity_id=reservation.pk, action=SalesActivityLog.Action.RESERVED, user=user, details=notes)
    return reservation


@transaction.atomic
def release_reservation(reservation, user):
    locked = Reservation.all_objects.select_for_update().get(pk=reservation.pk, tenant=reservation.tenant)
    if locked.status != Reservation.Status.ACTIVE:
        return locked  # ya liberada/convertida/vencida: operación idempotente, no-op
    if locked.inventory_unit_id:
        unit = InventoryUnit.all_objects.select_for_update().get(pk=locked.inventory_unit_id, tenant=locked.tenant)
        if unit.status == InventoryUnit.Status.RESERVADO:
            transition_unit_status(unit=unit, new_status=InventoryUnit.Status.EN_STOCK, user=user)
    locked.status = Reservation.Status.RELEASED
    locked.released_at = timezone.now()
    locked.save(update_fields=["status", "released_at"])
    log_activity(locked.tenant, entity_type="reservation", entity_id=locked.pk, action=SalesActivityLog.Action.RELEASED, user=user)
    return locked


def _release_reservations_for_source(source_type, source_id, *, user):
    activas = Reservation.all_objects.filter(source_type=source_type, source_id=source_id, status=Reservation.Status.ACTIVE)
    for reservation in activas:
        release_reservation(reservation, user)


def _convert_reservations_for_source(source_type, source_id):
    Reservation.all_objects.filter(source_type=source_type, source_id=source_id, status=Reservation.Status.ACTIVE).update(
        status=Reservation.Status.CONVERTED
    )


@transaction.atomic
def reserve_stock_for_proforma(proforma, user):
    """Inicia una reserva explícita para cada línea de una proforma
    EMITIDA — nunca automática (requisito explícito: la proforma no
    reserva por sí sola, alguien debe pedirlo)."""
    locked = ProformaInvoice.all_objects.select_for_update().get(pk=proforma.pk, tenant=proforma.tenant)
    if locked.status != ProformaInvoice.Status.ISSUED:
        raise InvalidSalesOperation(f"Solo se puede reservar stock de una proforma emitida (estado actual: {locked.get_status_display()}).")

    reservas = []
    for item in get_proforma_items(locked):
        if item.product.inventory_tracking_type == Product.TrackingType.SERIALIZED:
            reservas.append(
                create_reservation(
                    locked.tenant, product=item.product, user=user, customer=locked.customer,
                    inventory_unit=item.inventory_unit, source_type=Reservation.SourceType.PROFORMA, source_id=locked.pk,
                )
            )
        else:
            reservas.append(
                create_reservation(
                    locked.tenant, product=item.product, user=user, customer=locked.customer,
                    quantity=item.quantity, source_type=Reservation.SourceType.PROFORMA, source_id=locked.pk,
                )
            )
    return reservas


def expire_due_reservations(tenant=None):
    queryset = Reservation.all_objects.filter(status=Reservation.Status.ACTIVE, expires_at__lt=timezone.now())
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    vencidas = []
    for reservation in queryset:
        locked = Reservation.all_objects.select_for_update().get(pk=reservation.pk)
        if locked.inventory_unit_id:
            unit = InventoryUnit.all_objects.get(pk=locked.inventory_unit_id)
            if unit.status == InventoryUnit.Status.RESERVADO:
                transition_unit_status(unit=unit, new_status=InventoryUnit.Status.EN_STOCK, user=None)
        locked.status = Reservation.Status.EXPIRED
        locked.save(update_fields=["status"])
        vencidas.append(locked)
    return vencidas


# ------------------------------------------------------------------
# Venta / Factura
# ------------------------------------------------------------------

SALE_TRANSITIONS = {
    Sale.Status.DRAFT: {Sale.Status.CONFIRMED, Sale.Status.CANCELED},
    Sale.Status.CONFIRMED: {Sale.Status.RETURNED, Sale.Status.PARTIALLY_RETURNED},
    Sale.Status.CANCELED: set(),
    Sale.Status.RETURNED: set(),
    Sale.Status.PARTIALLY_RETURNED: {Sale.Status.RETURNED},
}
_SALE_EDITABLE_STATUSES = {Sale.Status.DRAFT}


def _require_editable_sale(sale):
    if sale.status not in _SALE_EDITABLE_STATUSES:
        raise InvalidSalesOperation(f"La venta «{sale.number}» no se puede editar en estado {sale.get_status_display()}.")


@transaction.atomic
def create_sale(tenant, *, user, customer=None, currency="USD", payment_terms="contado", notes="", terms="", issue_date=None, source_quotation=None, source_proforma=None, global_discount_percent=None, global_discount_amount=None):
    numero = generate_document_number(tenant, DocumentSequence.DocumentType.SALE)
    sale = Sale.all_objects.create(
        tenant=tenant, number=numero, customer=customer, salesperson=user, currency=currency,
        payment_terms=payment_terms, notes=notes, terms=terms, issue_date=issue_date or timezone.localdate(),
        source_quotation=source_quotation, source_proforma=source_proforma,
        global_discount_percent=global_discount_percent or Decimal("0"),
        global_discount_amount=global_discount_amount or Decimal("0"),
    )
    log_activity(tenant, entity_type="sale", entity_id=sale.pk, entity_label=numero, action=SalesActivityLog.Action.CREATED, user=user)
    return sale


@transaction.atomic
def add_sale_item(sale, *, product, quantity, user=None, **kwargs):
    _require_editable_sale(sale)
    orden = get_sale_items(sale).count() + 1
    item = SaleItem.all_objects.create(
        tenant=sale.tenant, sale=sale, line_order=orden,
        **_snapshot_item_fields(product, quantity, **kwargs),
    )
    _recalculate_item(item)
    item.save()
    recalculate_document_totals(sale)
    return item


@transaction.atomic
def remove_sale_item(item):
    sale = item.sale
    _require_editable_sale(sale)
    item.delete()
    recalculate_document_totals(sale)


@transaction.atomic
def set_sale_global_discount(sale, *, percent=None, amount=None):
    """Actualiza el descuento GLOBAL de una venta en `DRAFT` (usado por
    FASE 11/POS, donde el descuento puede decidirse en cualquier
    momento del armado del carrito, no solo al crear la venta).
    Porcentaje tiene prioridad sobre monto fijo — mismo criterio que el
    descuento por línea, ver `recalculate_document_totals`."""
    _require_editable_sale(sale)
    sale.global_discount_percent = percent or Decimal("0")
    sale.global_discount_amount = amount or Decimal("0")
    sale.save(update_fields=["global_discount_percent", "global_discount_amount", "updated_at"])
    recalculate_document_totals(sale)
    return sale


@transaction.atomic
def confirm_sale(sale, user):
    """Confirma la venta: aplica los efectos reales en inventario
    (QUANTITY → `register_stock_out`; SERIALIZED →
    `transition_unit_status(..., VENDIDO, ...)`, reutilizando
    literalmente las validaciones de FASE 8 — nunca se duplica esa
    lógica aquí). Idempotente: confirmar una venta ya CONFIRMADA es un
    no-op que devuelve la misma venta, para que un reintento de red
    nunca produzca una venta duplicada ni una doble salida de
    inventario."""
    locked = Sale.all_objects.select_for_update().get(pk=sale.pk, tenant=sale.tenant)
    if locked.status == Sale.Status.CONFIRMED:
        return locked
    if locked.status != Sale.Status.DRAFT:
        raise InvalidSalesOperation(f"La venta «{locked.number}» no se puede confirmar desde {locked.get_status_display()}.")
    if not get_sale_items(locked).exists():
        raise InvalidSalesOperation(f"La venta «{locked.number}» no tiene líneas que confirmar.")

    for item in get_sale_items(locked):
        if item.product.inventory_tracking_type == Product.TrackingType.SERIALIZED:
            if not item.inventory_unit_id:
                raise InvalidSalesOperation(f"La línea «{item.description}» es un producto serializado sin unidad asignada.")
            unit = InventoryUnit.all_objects.select_for_update().get(pk=item.inventory_unit_id, tenant=locked.tenant)
            try:
                transition_unit_status(unit=unit, new_status=InventoryUnit.Status.VENDIDO, user=user)
            except InvalidInventoryOperation as error:
                raise InvalidSalesOperation(str(error)) from error
            # COGS (ampliación de cierre de FASE 14): costo específico de
            # ESTA unidad física, congelado desde que se recibió.
            costo_linea = unit.unit_cost
        else:
            try:
                movimiento = register_stock_out(product=item.product, quantity=item.quantity, user=user, notes=f"Venta {locked.number}")
            except InvalidInventoryOperation as error:
                raise InvalidSalesOperation(str(error)) from error
            # COGS (ampliación de cierre de FASE 14): costo promedio
            # ponderado vigente en el instante de la salida (snapshot
            # guardado en el propio movimiento, ver
            # apps.inventory.services._register_movement).
            costo_linea = (movimiento.unit_cost or Decimal("0")) * item.quantity
        SaleItem.all_objects.filter(pk=item.pk, tenant=locked.tenant).update(cost_amount=costo_linea)

    if locked.source_proforma_id:
        _convert_reservations_for_source(Reservation.SourceType.PROFORMA, locked.source_proforma_id)

    locked.status = Sale.Status.CONFIRMED
    locked.confirmed_at = timezone.now()
    locked.confirmed_by = user
    locked.save(update_fields=["status", "confirmed_at", "confirmed_by", "updated_at"])
    log_activity(locked.tenant, entity_type="sale", entity_id=locked.pk, entity_label=locked.number, action=SalesActivityLog.Action.CONFIRMED, user=user)

    # FASE 14 (Contabilidad General): contabilización automática,
    # deliberadamente resiliente — nunca debe poder romper la venta.
    # Import diferido (no al nivel de módulo) para evitar un ciclo de
    # importación: apps.accounting.services ya importa
    # apps.sales.services (generate_document_number).
    from apps.accounting.services import try_record_sale_confirmed, try_record_sale_cogs

    try_record_sale_confirmed(locked, user)
    try_record_sale_cogs(locked, user)
    return locked


@transaction.atomic
def cancel_sale(sale, user, reason=""):
    """Solo puede cancelarse una venta en BORRADOR — nunca tocó
    inventario todavía, así que cancelarla es una operación trivial (sin
    reversión de stock/reservas que hacer). Cancelar una venta ya
    CONFIRMADA se hace mediante una devolución total
    (`create_return` con todas las líneas) — nunca con esta función; ver
    `docs/sales.md` para la justificación de esta decisión de diseño."""
    locked = Sale.all_objects.select_for_update().get(pk=sale.pk, tenant=sale.tenant)
    if Sale.Status.CANCELED not in SALE_TRANSITIONS.get(locked.status, set()):
        raise InvalidSalesOperation(f"La venta «{locked.number}» no se puede cancelar desde {locked.get_status_display()}.")
    locked.status = Sale.Status.CANCELED
    locked.canceled_at = timezone.now()
    locked.canceled_by = user
    locked.cancel_reason = reason
    locked.save(update_fields=["status", "canceled_at", "canceled_by", "cancel_reason", "updated_at"])
    log_activity(locked.tenant, entity_type="sale", entity_id=locked.pk, entity_label=locked.number, action=SalesActivityLog.Action.CANCELED, user=user, details=reason)
    return locked


# ------------------------------------------------------------------
# Pagos y cuentas por cobrar (Payment + PaymentAllocation)
#
# Extensión obligatoria pedida explícitamente por el usuario tras el
# cierre de FASE 10: un `Payment` ya NO pertenece a una única venta.
# Representa dinero recibido de un cliente; `PaymentAllocation` es el
# ledger append-only que registra contra qué venta(s) se aplicó ese
# dinero y cuánto de cada una — nunca redistribuido implícitamente,
# siempre una fila explícita y auditable por aplicación. El saldo de
# una factura y el saldo sin aplicar de un pago se CALCULAN siempre
# desde este ledger (nunca un campo desnormalizado), mismo principio
# que `get_current_stock` en `apps.inventory.services`.
# ------------------------------------------------------------------


def get_sale_paid_amount(sale):
    """Suma de asignaciones ACTIVAS de pagos CONFIRMADOS Y de notas de
    crédito aplicadas a esta venta — única fuente de verdad de "cuánto
    se ha cubierto" (dinero + crédito juntos, nunca dos totales
    separados: ver docs/accounts-receivable.md)."""
    pagado = PaymentAllocation.all_objects.filter(
        tenant=sale.tenant, sale=sale, status=PaymentAllocation.Status.ACTIVE, payment__status=Payment.Status.CONFIRMED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    acreditado = CreditNoteApplication.all_objects.filter(
        tenant=sale.tenant, sale=sale, status=CreditNoteApplication.Status.ACTIVE
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return pagado + acreditado


def get_sale_balance_due(sale):
    """Saldo pendiente de la factura: total menos lo efectivamente
    aplicado (asignaciones activas de pagos confirmados)."""
    return sale.total - get_sale_paid_amount(sale)


def recompute_payment_status(sale):
    """Deriva el estado de pago de la venta ÚNICAMENTE de lo realmente
    aplicado (`get_sale_paid_amount`). `REFUNDED`/`PARTIALLY_REFUNDED`
    siguen existiendo como valores del enum, pero ya no se derivan
    automáticamente aquí: bajo la nueva regla, un reembolso solo puede
    salir del saldo SIN APLICAR de un pago (`get_unallocated_payment_amount`)
    — para "des-pagar" una factura primero hay que reversar su
    asignación (`reverse_allocation`), lo que ya la devuelve a
    UNPAID/PARTIALLY_PAID de forma natural. Ver docs/payments.md."""
    pagado = get_sale_paid_amount(sale)
    if pagado <= 0:
        estado = Sale.PaymentStatus.UNPAID
    elif pagado < sale.total:
        estado = Sale.PaymentStatus.PARTIALLY_PAID
    else:
        estado = Sale.PaymentStatus.PAID
    Sale.all_objects.filter(pk=sale.pk).update(payment_status=estado)
    return estado


def get_unallocated_payment_amount(payment):
    """Saldo del pago sin aplicar a ninguna factura — monto total menos
    lo asignado (activo), menos lo ya reembolsado, menos lo ya
    convertido en crédito (`convert_refund_to_credit`, que mueve
    permanentemente ese monto al ledger de la `CreditNote` generada, a
    menos que esa nota se cancele). Es el "saldo a favor" de ese pago
    concreto si nunca se aplica a nada."""
    asignado = PaymentAllocation.all_objects.filter(
        tenant=payment.tenant, payment=payment, status=PaymentAllocation.Status.ACTIVE
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    reembolsado = Refund.all_objects.filter(
        tenant=payment.tenant, payment=payment, status=Refund.Status.COMPLETED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    convertido_a_credito = (
        CreditNote.all_objects.filter(tenant=payment.tenant, source_payment=payment)
        .exclude(status=CreditNote.Status.CANCELED)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    return payment.amount - asignado - reembolsado - convertido_a_credito


def get_credit_note_remaining(credit_note):
    """Saldo de la nota de crédito sin aplicar todavía a ninguna
    factura — mismo principio que `get_unallocated_payment_amount`,
    calculado siempre desde `CreditNoteApplication` (nunca un campo
    desnormalizado)."""
    aplicado = CreditNoteApplication.all_objects.filter(
        tenant=credit_note.tenant, credit_note=credit_note, status=CreditNoteApplication.Status.ACTIVE
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return credit_note.amount - aplicado


def get_customer_credit_balance(customer):
    """Saldo a favor TOTAL de un cliente, EN LA MONEDA DEL CLIENTE
    (`customer.currency`): suma del saldo sin aplicar de sus pagos
    confirmados MÁS el saldo sin aplicar de sus notas de crédito
    emitidas — un ÚNICO saldo (nunca dos balances paralelos, ver
    docs/accounts-receivable.md), siempre una agregación de lectura
    sobre `Payment`/`PaymentAllocation`/`CreditNote`/
    `CreditNoteApplication` ya existentes, nunca un campo ni tabla
    nueva de saldo.

    Sin un motor de tipos de cambio (ver docs/currency.md), un pago o
    nota de crédito en una moneda DISTINTA a `customer.currency` nunca
    se suma aquí — mezclar DOP+USD (o cualquier otro par) como si
    fueran la misma unidad sería un error aritmético real, no una
    simplificación aceptable. Ese pago/nota en otra moneda simplemente
    no participa en ESTE saldo (necesitaría su propia conversión
    explícita/auditada/con tasa cuando exista FX real)."""
    total = Decimal("0")
    pagos = Payment.all_objects.filter(
        tenant=customer.tenant, customer=customer, status=Payment.Status.CONFIRMED, currency=customer.currency,
    )
    for pago in pagos:
        total += get_unallocated_payment_amount(pago)
    notas = CreditNote.all_objects.filter(
        tenant=customer.tenant, customer=customer, currency=customer.currency,
        status__in=[CreditNote.Status.ISSUED, CreditNote.Status.PARTIALLY_APPLIED],
    )
    for nota in notas:
        total += get_credit_note_remaining(nota)
    return total


def get_sale_balance_due_bulk(sales):
    """Saldo pendiente de VARIAS ventas en una sola pasada (3 consultas
    en total, nunca 2×N) — usado por listados como "facturas
    pendientes de un cliente" para evitar N+1 (FASE 11, requisito
    explícito de revisión de performance). Devuelve `{sale.pk: saldo}`;
    el resultado es idéntico a llamar `get_sale_balance_due` por cada
    venta, una por una."""
    sales = list(sales)
    if not sales:
        return {}
    ids_ventas = [venta.pk for venta in sales]
    tenant = sales[0].tenant

    pagos_por_venta = dict(
        PaymentAllocation.all_objects.filter(
            tenant=tenant, sale_id__in=ids_ventas, status=PaymentAllocation.Status.ACTIVE,
            payment__status=Payment.Status.CONFIRMED,
        ).values("sale_id").annotate(total=Sum("amount")).values_list("sale_id", "total")
    )
    creditos_por_venta = dict(
        CreditNoteApplication.all_objects.filter(
            tenant=tenant, sale_id__in=ids_ventas, status=CreditNoteApplication.Status.ACTIVE,
        ).values("sale_id").annotate(total=Sum("amount")).values_list("sale_id", "total")
    )
    return {
        venta.pk: venta.total
        - (pagos_por_venta.get(venta.pk) or Decimal("0"))
        - (creditos_por_venta.get(venta.pk) or Decimal("0"))
        for venta in sales
    }


def get_customer_pending_sales(customer):
    """Ventas confirmadas (o parcialmente devueltas) del cliente con
    saldo pendiente > 0 — las "facturas pendientes" que FASE 11 (POS)
    debe poder cobrar. Consulta reutilizable, no un reporte (FASE 14).
    Usa `get_sale_balance_due_bulk` internamente — nunca N+1 sin
    importar cuántas ventas tenga el cliente."""
    ventas = list(Sale.all_objects.filter(
        tenant=customer.tenant, customer=customer, status__in=[Sale.Status.CONFIRMED, Sale.Status.PARTIALLY_RETURNED]
    ).order_by("issue_date", "id"))
    saldos = get_sale_balance_due_bulk(ventas)
    return [venta for venta in ventas if saldos.get(venta.pk, Decimal("0")) > 0]


@transaction.atomic
def create_payment(tenant, *, customer=None, method, amount, user, currency=None, reference="", idempotency_key="", notes=""):
    """Registra dinero recibido de un cliente SIN aplicarlo todavía a
    ninguna factura — queda disponible como saldo sin aplicar
    (`get_unallocated_payment_amount`) hasta llamar a
    `allocate_payment`/`apply_payment_to_sales`/`record_payment_for_sale`.
    Idempotente por `idempotency_key`: un reintento con la misma clave
    devuelve el pago ya existente en vez de crear uno duplicado."""
    if idempotency_key:
        existente = Payment.all_objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
        if existente:
            return existente
    if amount is None or amount <= 0:
        raise InvalidSalesOperation("El monto del pago debe ser mayor que cero.")

    payment = Payment.all_objects.create(
        tenant=tenant, customer=customer, method=method, amount=amount,
        currency=currency or (customer.currency if customer else "USD"),
        reference=reference, idempotency_key=idempotency_key, user=user, notes=notes,
    )
    log_activity(
        tenant, entity_type="payment", entity_id=payment.pk,
        entity_label=f"{payment.get_method_display()} {payment.amount}",
        action=SalesActivityLog.Action.PAYMENT_RECORDED, user=user,
        details=(customer.display_name if customer else ""),
    )

    # FASE 14 (Contabilidad General): contabilización automática,
    # deliberadamente resiliente — nunca debe poder romper el registro
    # del pago. Import diferido, ver nota en confirm_sale.
    from apps.accounting.services import try_record_customer_payment

    try_record_customer_payment(payment, user)
    return payment


@transaction.atomic
def allocate_payment(payment, sale, amount, user):
    """Aplica `amount` de un pago a una factura concreta. Bloquea AMBAS
    filas (`Payment` y `Sale`) antes de validar para que dos
    asignaciones concurrentes del mismo pago (o de la misma factura)
    nunca sobre-apliquen — mismo patrón de concurrencia que el resto
    del módulo (`select_for_update`)."""
    locked_payment = Payment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    locked_sale = Sale.all_objects.select_for_update().get(pk=sale.pk, tenant=sale.tenant)

    if locked_payment.tenant_id != locked_sale.tenant_id:
        raise InvalidSalesOperation("El pago y la venta deben pertenecer al mismo tenant.")
    if locked_payment.customer_id != locked_sale.customer_id:
        raise InvalidSalesOperation("Un pago solo puede aplicarse a facturas del mismo cliente.")
    if locked_payment.currency != locked_sale.currency:
        # Sin un motor de tipos de cambio (ver docs/currency.md): nunca
        # mezclar monedas distintas en una misma asignación — se
        # rechaza con un error de negocio claro en vez de sumar montos
        # de monedas diferentes como si fueran la misma unidad. Una
        # conversión explícita/auditada/con tasa queda para cuando
        # exista FX real (fase futura).
        raise InvalidSalesOperation(
            f"El pago está en {locked_payment.currency} y la venta «{locked_sale.number}» está en "
            f"{locked_sale.currency} — no se puede aplicar un pago en una moneda distinta a la de la factura."
        )
    if locked_payment.status != Payment.Status.CONFIRMED:
        raise InvalidSalesOperation("Solo un pago confirmado puede aplicarse a una factura.")
    if locked_sale.status not in (Sale.Status.CONFIRMED, Sale.Status.PARTIALLY_RETURNED):
        raise InvalidSalesOperation(
            f"Solo se puede aplicar un pago a una venta confirmada (estado actual: {locked_sale.get_status_display()})."
        )
    if amount is None or amount <= 0:
        raise InvalidSalesOperation("El monto a aplicar debe ser mayor que cero.")

    disponible_pago = get_unallocated_payment_amount(locked_payment)
    if amount > disponible_pago:
        raise InvalidSalesOperation(f"El pago solo tiene {disponible_pago} disponible sin aplicar.")
    saldo_factura = get_sale_balance_due(locked_sale)
    if amount > saldo_factura:
        raise InvalidSalesOperation(f"La venta «{locked_sale.number}» solo tiene {saldo_factura} pendiente.")

    asignacion = PaymentAllocation.all_objects.create(
        tenant=locked_payment.tenant, payment=locked_payment, sale=locked_sale, amount=amount, user=user,
    )
    recompute_payment_status(locked_sale)
    log_activity(
        locked_sale.tenant, entity_type="sale", entity_id=locked_sale.pk, entity_label=locked_sale.number,
        action=SalesActivityLog.Action.PAYMENT_ALLOCATED, user=user,
        details=f"{amount} del pago #{locked_payment.pk} ({locked_payment.get_method_display()})",
    )
    return asignacion


@transaction.atomic
def apply_payment_to_sales(payment, allocations, user):
    """Aplica un mismo pago a VARIAS facturas en una sola operación —
    `allocations`: lista de `{"sale": Sale, "amount": Decimal}`. Valida
    que la suma total solicitada no exceda el saldo disponible del pago
    ANTES de aplicar ninguna (todo o nada); cada asignación individual
    se valida además contra el saldo de su propia factura dentro de
    `allocate_payment`. Es el mecanismo pedido explícitamente para
    "aplicar un solo pago a varias facturas" desde FASE 11 (POS)."""
    if not allocations:
        raise InvalidSalesOperation("Debes indicar al menos una factura a la que aplicar el pago.")
    locked_payment = Payment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    total_solicitado = sum((entrada["amount"] for entrada in allocations), Decimal("0"))
    disponible = get_unallocated_payment_amount(locked_payment)
    if total_solicitado > disponible:
        raise InvalidSalesOperation(
            f"El total a aplicar ({total_solicitado}) excede el saldo disponible del pago ({disponible})."
        )
    return [allocate_payment(locked_payment, entrada["sale"], entrada["amount"], user) for entrada in allocations]


@transaction.atomic
def record_payment_for_sale(sale, *, method, amount, user, currency=None, reference="", idempotency_key="", notes=""):
    """Atajo para el caso más común: un pago que se cobra y se aplica de
    inmediato a una sola venta (usado por la vista de "registrar pago"
    de FASE 10). Crea el `Payment` (con el cliente de la venta) y lo
    aplica en su totalidad en un solo paso atómico, para que las vistas
    que solo cobran una venta no necesiten conocer el ledger de
    asignaciones. Idempotente: un reintento con la misma
    `idempotency_key` reutiliza el `Payment` ya creado y, si ya fue
    aplicado, no vuelve a aplicarlo (nunca duplica ni la creación ni la
    aplicación)."""
    locked_sale = Sale.all_objects.select_for_update().get(pk=sale.pk, tenant=sale.tenant)
    payment = create_payment(
        locked_sale.tenant, customer=locked_sale.customer, method=method, amount=amount, user=user,
        currency=currency or locked_sale.currency, reference=reference, idempotency_key=idempotency_key, notes=notes,
    )
    disponible = get_unallocated_payment_amount(payment)
    if disponible > 0:
        allocate_payment(payment, locked_sale, min(amount, disponible), user)
    return payment


@transaction.atomic
def reverse_allocation(allocation, user):
    """Deshace una asignación de pago a una factura: libera tanto el
    saldo pendiente de la factura como el saldo sin aplicar del pago.
    Es la acción de "reversa" pedida explícitamente, distinta de
    `refund` (reversar mueve el dinero de vuelta al saldo sin aplicar
    del pago; reembolsar lo devuelve fuera del sistema). Idempotente:
    reversar una asignación ya reversada es un no-op."""
    locked = PaymentAllocation.all_objects.select_for_update().get(pk=allocation.pk, tenant=allocation.tenant)
    if locked.status == PaymentAllocation.Status.REVERSED:
        return locked
    locked.status = PaymentAllocation.Status.REVERSED
    locked.reversed_at = timezone.now()
    locked.reversed_by = user
    locked.save(update_fields=["status", "reversed_at", "reversed_by"])
    recompute_payment_status(locked.sale)
    log_activity(
        locked.tenant, entity_type="sale", entity_id=locked.sale_id, entity_label=locked.sale.number,
        action=SalesActivityLog.Action.PAYMENT_ALLOCATION_REVERSED, user=user,
        details=f"{locked.amount} del pago #{locked.payment_id}",
    )
    return locked


@transaction.atomic
def void_payment(payment, user):
    """Anula un pago completo: reversa todas sus asignaciones ACTIVAS
    (liberando el saldo de cada factura que respaldaban) y lo marca
    `VOIDED`. Idempotente."""
    locked = Payment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    if locked.status == Payment.Status.VOIDED:
        return locked
    asignaciones_activas = PaymentAllocation.all_objects.filter(
        tenant=locked.tenant, payment=locked, status=PaymentAllocation.Status.ACTIVE
    )
    for asignacion in asignaciones_activas:
        reverse_allocation(asignacion, user)
    locked.status = Payment.Status.VOIDED
    locked.save(update_fields=["status"])
    log_activity(
        locked.tenant, entity_type="payment", entity_id=locked.pk,
        entity_label=f"{locked.get_method_display()} {locked.amount}",
        action=SalesActivityLog.Action.PAYMENT_VOIDED, user=user,
    )
    return locked


# ------------------------------------------------------------------
# Devoluciones (mercancía) y Reembolsos (dinero)
# ------------------------------------------------------------------


def _is_full_return(sale):
    for item in get_sale_items(sale):
        if item.inventory_unit_id:
            if not ReturnItem.all_objects.filter(tenant=sale.tenant, sale_item=item).exists():
                return False
        else:
            devuelto = ReturnItem.all_objects.filter(tenant=sale.tenant, sale_item=item).aggregate(t=Sum("quantity_returned"))["t"] or Decimal("0")
            if devuelto < item.quantity:
                return False
    return True


@transaction.atomic
def create_return(sale, *, items, user, reason=""):
    """`items`: lista de dicts `{"sale_item": SaleItem, "quantity_returned": Decimal}`
    (productos por cantidad) o `{"sale_item": SaleItem}` (productos
    serializados — la unidad se toma de `sale_item.inventory_unit`).

    Para SERIALIZED: `InventoryUnit` VENDIDO → DEVUELTO (transición ya
    válida en la máquina de estados de FASE 8). Deliberadamente NO
    reingresa la unidad a EN_STOCK automáticamente — eso requiere una
    revisión y transición manual posterior (reparación/garantía/stock),
    tal como pidió el usuario explícitamente."""
    if not items:
        raise InvalidSalesOperation("Debes indicar al menos una línea a devolver.")

    locked_sale = Sale.all_objects.select_for_update().get(pk=sale.pk, tenant=sale.tenant)
    if locked_sale.status not in (Sale.Status.CONFIRMED, Sale.Status.PARTIALLY_RETURNED):
        raise InvalidSalesOperation(f"Solo se puede devolver una venta confirmada (estado actual: {locked_sale.get_status_display()}).")

    numero = generate_document_number(locked_sale.tenant, DocumentSequence.DocumentType.RETURN)
    devolucion = Return.all_objects.create(tenant=locked_sale.tenant, sale=locked_sale, number=numero, reason=reason, user=user)

    for entrada in items:
        sale_item = entrada["sale_item"]
        if sale_item.inventory_unit_id:
            unit = InventoryUnit.all_objects.select_for_update().get(pk=sale_item.inventory_unit_id, tenant=locked_sale.tenant)
            try:
                transition_unit_status(unit=unit, new_status=InventoryUnit.Status.DEVUELTO, user=user)
            except InvalidInventoryOperation as error:
                raise InvalidSalesOperation(str(error)) from error
            ReturnItem.all_objects.create(tenant=locked_sale.tenant, return_document=devolucion, sale_item=sale_item, inventory_unit=unit)
        else:
            cantidad = entrada["quantity_returned"]
            if cantidad is None or cantidad <= 0:
                raise InvalidSalesOperation("La cantidad devuelta debe ser mayor que cero.")
            # COGS (ampliación de cierre de FASE 14): la mercancía devuelta
            # reingresa al promedio ponderado a SU costo original (el que
            # se consumió al vender), nunca al costo de mercado actual —
            # ver docs/accounting.md.
            costo_unitario_restaurado = (
                (sale_item.cost_amount / sale_item.quantity) if sale_item.quantity else Decimal("0")
            )
            try:
                register_stock_in(
                    product=sale_item.product, quantity=cantidad, user=user, notes=f"Devolución {numero}",
                    unit_cost=costo_unitario_restaurado,
                )
            except InvalidInventoryOperation as error:
                raise InvalidSalesOperation(str(error)) from error
            ReturnItem.all_objects.create(tenant=locked_sale.tenant, return_document=devolucion, sale_item=sale_item, quantity_returned=cantidad)

    locked_sale.status = Sale.Status.RETURNED if _is_full_return(locked_sale) else Sale.Status.PARTIALLY_RETURNED
    locked_sale.save(update_fields=["status", "updated_at"])
    log_activity(locked_sale.tenant, entity_type="sale", entity_id=locked_sale.pk, entity_label=locked_sale.number, action=SalesActivityLog.Action.RETURNED, user=user, details=numero)

    # FASE 14 (Contabilidad General, ampliación de cierre): reversa el
    # COGS de lo REALMENTE devuelto — nunca toca un Refund monetario
    # (modelo separado, jamás referenciado desde aquí).
    from apps.accounting.services import try_record_return_cogs_reversal

    try_record_return_cogs_reversal(devolucion, user)
    return devolucion


def get_sale_gross_margin(sale):
    """Margen bruto de una venta ya confirmada: subtotal menos descuentos
    menos el costo (COGS) de todas sus líneas — agregación de solo
    lectura sobre `SaleItem.cost_amount`, nunca un cálculo paralelo."""
    costo_total = get_sale_items(sale).aggregate(total=Sum("cost_amount"))["total"] or Decimal("0")
    return sale.subtotal - sale.discount_total - costo_total


@transaction.atomic
def record_refund(payment, *, amount, user, reason="", return_document=None):
    """Devuelve dinero de un pago HACIA AFUERA del sistema. Solo puede
    salir del saldo SIN APLICAR del pago (`get_unallocated_payment_amount`):
    si el dinero ya está aplicado a una o más facturas, primero hay que
    liberarlo con `reverse_allocation` (eso ya recalcula el estado de
    pago de cada factura afectada) — un reembolso nunca "des-aplica"
    una asignación en silencio. Esta es una separación deliberada entre
    "reversa" (mueve el dinero de vuelta al saldo sin aplicar del pago,
    sigue dentro del sistema) y "reembolso" (el dinero sale del
    sistema)."""
    locked_payment = Payment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    if amount is None or amount <= 0:
        raise InvalidSalesOperation("El monto del reembolso debe ser mayor que cero.")
    disponible = get_unallocated_payment_amount(locked_payment)
    if amount > disponible:
        raise InvalidSalesOperation(
            f"El reembolso no puede superar el saldo sin aplicar del pago ({disponible}). "
            "Si el dinero ya está aplicado a una factura, revierte esa asignación primero."
        )

    refund = Refund.all_objects.create(
        tenant=locked_payment.tenant, payment=locked_payment, return_document=return_document,
        amount=amount, reason=reason, user=user,
    )
    log_activity(
        locked_payment.tenant, entity_type="payment", entity_id=locked_payment.pk,
        entity_label=f"{locked_payment.get_method_display()} {locked_payment.amount}",
        action=SalesActivityLog.Action.REFUNDED, user=user, details=f"{refund.amount}",
    )
    return refund


# ------------------------------------------------------------------
# Notas de crédito (FASE 11 — ver docs/accounts-receivable.md)
#
# Estructuralmente análoga a Payment/PaymentAllocation: misma
# disciplina de validación (select_for_update() sobre ambas filas,
# nunca sobre-aplica, nunca cruza tenant/cliente, corrige con reversa
# nunca con edición). El saldo a favor de un cliente y el saldo
# pendiente de una factura ya suman esto automáticamente (ver
# `get_customer_credit_balance`/`get_sale_paid_amount` arriba).
# ------------------------------------------------------------------


@transaction.atomic
def create_credit_note(tenant, *, customer, amount, user, reason="", source_type=CreditNote.SourceType.MANUAL, source_return=None, source_payment=None, issue_date=None, currency=None):
    """Crea una nota de crédito en DRAFT — todavía no genera saldo a
    favor (mismo principio que `Quotation` DRAFT: existe pero no
    compromete nada). Emitirla (`issue_credit_note`) es el paso que la
    activa. `currency` es un snapshot al momento de crearse (por
    defecto, la moneda actual del cliente) — nunca se recalcula si el
    cliente cambia de moneda después, ver `docs/currency.md`."""
    if customer is None:
        raise InvalidSalesOperation("Una nota de crédito siempre debe tener un cliente.")
    if amount is None or amount <= 0:
        raise InvalidSalesOperation("El monto de la nota de crédito debe ser mayor que cero.")
    numero = generate_document_number(tenant, DocumentSequence.DocumentType.CREDIT_NOTE)
    nota = CreditNote.all_objects.create(
        tenant=tenant, customer=customer, number=numero, amount=amount, reason=reason,
        currency=currency or customer.currency,
        source_type=source_type, source_return=source_return, source_payment=source_payment,
        issue_date=issue_date or timezone.localdate(), user=user,
    )
    log_activity(
        tenant, entity_type="credit_note", entity_id=nota.pk, entity_label=numero,
        action=SalesActivityLog.Action.CREATED, user=user, details=reason,
    )
    return nota


@transaction.atomic
def issue_credit_note(credit_note, user):
    """DRAFT → ISSUED: a partir de aquí la nota genera saldo a favor
    real (`get_customer_credit_balance` ya la cuenta). Idempotente:
    emitir una nota ya emitida es un no-op."""
    locked = CreditNote.all_objects.select_for_update().get(pk=credit_note.pk, tenant=credit_note.tenant)
    if locked.status == CreditNote.Status.ISSUED:
        return locked
    if locked.status != CreditNote.Status.DRAFT:
        raise InvalidSalesOperation(
            f"La nota de crédito «{locked.number}» no se puede emitir desde {locked.get_status_display()}."
        )
    locked.status = CreditNote.Status.ISSUED
    locked.save(update_fields=["status"])
    log_activity(
        locked.tenant, entity_type="credit_note", entity_id=locked.pk, entity_label=locked.number,
        action=SalesActivityLog.Action.CREDIT_NOTE_ISSUED, user=user,
    )
    return locked


def _recompute_credit_note_status(nota):
    """Deriva el estado de la nota ÚNICAMENTE de su saldo restante
    (`get_credit_note_remaining`) — nunca asumido. `CANCELED` es
    terminal y nunca se recalcula desde aquí."""
    if nota.status == CreditNote.Status.CANCELED:
        return nota.status
    restante = get_credit_note_remaining(nota)
    if restante <= 0:
        estado = CreditNote.Status.FULLY_APPLIED
    elif restante < nota.amount:
        estado = CreditNote.Status.PARTIALLY_APPLIED
    else:
        estado = CreditNote.Status.ISSUED
    CreditNote.all_objects.filter(pk=nota.pk).update(status=estado)
    return estado


@transaction.atomic
def apply_credit_note(credit_note, sale, amount, user):
    """Aplica `amount` de una nota de crédito a una factura concreta —
    mismas reglas que `allocate_payment`: bloquea ambas filas antes de
    validar, nunca excede el saldo de la nota ni el saldo pendiente de
    la factura, nunca cruza tenant ni cliente."""
    locked_note = CreditNote.all_objects.select_for_update().get(pk=credit_note.pk, tenant=credit_note.tenant)
    locked_sale = Sale.all_objects.select_for_update().get(pk=sale.pk, tenant=sale.tenant)

    if locked_note.tenant_id != locked_sale.tenant_id:
        raise InvalidSalesOperation("La nota de crédito y la venta deben pertenecer al mismo tenant.")
    if locked_note.customer_id != locked_sale.customer_id:
        raise InvalidSalesOperation("Una nota de crédito solo puede aplicarse a facturas del mismo cliente.")
    if locked_note.currency != locked_sale.currency:
        # Mismo principio que `allocate_payment` — sin motor de FX (ver
        # docs/currency.md), nunca mezclar monedas distintas.
        raise InvalidSalesOperation(
            f"La nota de crédito está en {locked_note.currency} y la venta «{locked_sale.number}» está en "
            f"{locked_sale.currency} — no se puede aplicar una nota de crédito en una moneda distinta a la de la factura."
        )
    if locked_note.status not in (CreditNote.Status.ISSUED, CreditNote.Status.PARTIALLY_APPLIED):
        raise InvalidSalesOperation(
            f"Solo una nota de crédito emitida puede aplicarse (estado actual: {locked_note.get_status_display()})."
        )
    if locked_sale.status not in (Sale.Status.CONFIRMED, Sale.Status.PARTIALLY_RETURNED):
        raise InvalidSalesOperation(
            f"Solo se puede aplicar una nota de crédito a una venta confirmada (estado actual: {locked_sale.get_status_display()})."
        )
    if amount is None or amount <= 0:
        raise InvalidSalesOperation("El monto a aplicar debe ser mayor que cero.")

    disponible_nota = get_credit_note_remaining(locked_note)
    if amount > disponible_nota:
        raise InvalidSalesOperation(f"La nota de crédito solo tiene {disponible_nota} disponible sin aplicar.")
    saldo_factura = get_sale_balance_due(locked_sale)
    if amount > saldo_factura:
        raise InvalidSalesOperation(f"La venta «{locked_sale.number}» solo tiene {saldo_factura} pendiente.")

    aplicacion = CreditNoteApplication.all_objects.create(
        tenant=locked_note.tenant, credit_note=locked_note, sale=locked_sale, amount=amount, user=user,
    )
    _recompute_credit_note_status(locked_note)
    recompute_payment_status(locked_sale)
    log_activity(
        locked_sale.tenant, entity_type="sale", entity_id=locked_sale.pk, entity_label=locked_sale.number,
        action=SalesActivityLog.Action.CREDIT_NOTE_APPLIED, user=user,
        details=f"{amount} de la nota {locked_note.number}",
    )
    return aplicacion


@transaction.atomic
def reverse_credit_note_application(application, user):
    """Deshace una aplicación de nota de crédito: libera el saldo
    pendiente de la factura y devuelve el monto al saldo sin aplicar de
    la nota. Idempotente."""
    locked = CreditNoteApplication.all_objects.select_for_update().get(pk=application.pk, tenant=application.tenant)
    if locked.status == CreditNoteApplication.Status.REVERSED:
        return locked
    locked.status = CreditNoteApplication.Status.REVERSED
    locked.reversed_at = timezone.now()
    locked.reversed_by = user
    locked.save(update_fields=["status", "reversed_at", "reversed_by"])

    nota = CreditNote.all_objects.select_for_update().get(pk=locked.credit_note_id, tenant=locked.tenant)
    _recompute_credit_note_status(nota)
    recompute_payment_status(locked.sale)
    log_activity(
        locked.tenant, entity_type="sale", entity_id=locked.sale_id, entity_label=locked.sale.number,
        action=SalesActivityLog.Action.CREDIT_NOTE_APP_REVERSED, user=user,
        details=f"{locked.amount} de la nota {nota.number}",
    )
    return locked


@transaction.atomic
def cancel_credit_note(credit_note, user, reason=""):
    """Solo se puede cancelar una nota `DRAFT` o `ISSUED` SIN
    aplicaciones activas — mismo principio que `Return`: nunca dos
    caminos de reversión que puedan divergir. Si ya tiene aplicaciones,
    hay que revertirlas primero con `reverse_credit_note_application`.
    Idempotente."""
    locked = CreditNote.all_objects.select_for_update().get(pk=credit_note.pk, tenant=credit_note.tenant)
    if locked.status == CreditNote.Status.CANCELED:
        return locked
    if locked.status not in (CreditNote.Status.DRAFT, CreditNote.Status.ISSUED):
        raise InvalidSalesOperation(
            f"La nota de crédito «{locked.number}» no se puede cancelar desde {locked.get_status_display()}."
        )
    if CreditNoteApplication.all_objects.filter(
        tenant=locked.tenant, credit_note=locked, status=CreditNoteApplication.Status.ACTIVE
    ).exists():
        raise InvalidSalesOperation(
            "No se puede cancelar una nota de crédito con aplicaciones activas: revierte las aplicaciones primero."
        )
    locked.status = CreditNote.Status.CANCELED
    locked.canceled_at = timezone.now()
    locked.canceled_by = user
    locked.save(update_fields=["status", "canceled_at", "canceled_by"])
    log_activity(
        locked.tenant, entity_type="credit_note", entity_id=locked.pk, entity_label=locked.number,
        action=SalesActivityLog.Action.CREDIT_NOTE_CANCELED, user=user, details=reason,
    )
    return locked


@transaction.atomic
def convert_refund_to_credit(payment, amount, user, reason=""):
    """Alternativa a `record_refund`: en vez de sacar dinero del
    sistema, emite una `CreditNote` a favor del cliente del pago por el
    monto indicado — el dinero nunca sale del negocio. Misma validación
    que un reembolso real: solo puede salir del saldo SIN APLICAR del
    pago (`get_unallocated_payment_amount`, que ya excluye lo
    previamente convertido). Preserva intacto el contrato de
    `record_refund` — ver docs/accounts-receivable.md sección 5."""
    locked_payment = Payment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    if locked_payment.customer_id is None:
        raise InvalidSalesOperation("Un pago sin cliente no puede convertirse en crédito: no hay a quién atribuírselo.")
    if amount is None or amount <= 0:
        raise InvalidSalesOperation("El monto a convertir en crédito debe ser mayor que cero.")
    disponible = get_unallocated_payment_amount(locked_payment)
    if amount > disponible:
        raise InvalidSalesOperation(f"Solo hay {disponible} sin aplicar en este pago para convertir en crédito.")

    nota = create_credit_note(
        locked_payment.tenant, customer=locked_payment.customer, amount=amount, user=user, reason=reason,
        source_type=CreditNote.SourceType.REFUND, source_payment=locked_payment,
        currency=locked_payment.currency,
    )
    nota = issue_credit_note(nota, user)
    log_activity(
        locked_payment.tenant, entity_type="payment", entity_id=locked_payment.pk,
        entity_label=f"{locked_payment.get_method_display()} {locked_payment.amount}",
        action=SalesActivityLog.Action.REFUND_CONVERTED_TO_CREDIT, user=user,
        details=f"{amount} → {nota.number}",
    )
    return nota


# ------------------------------------------------------------------
# Documentos adjuntos (reutiliza FASE 9 — no se crea un segundo sistema de archivos)
# ------------------------------------------------------------------


def register_attachment(*, tenant, document_type, document_id, archivo, category, user, notes=""):
    extension, content_type = validar_archivo_adjunto(archivo)
    adjunto = SalesDocumentAttachment.all_objects.create(
        tenant=tenant, document_type=document_type, document_id=document_id, category=category, file=archivo,
        original_filename=nombre_original_seguro(archivo.name), content_type=content_type, size_bytes=archivo.size,
        uploaded_by=user, notes=notes,
    )
    log_activity(tenant, entity_type=document_type, entity_id=document_id, action=SalesActivityLog.Action.ATTACHMENT_UPLOADED, user=user, details=adjunto.original_filename)
    return adjunto


def delete_attachment(adjunto, user):
    tenant, document_type, document_id, nombre = adjunto.tenant, adjunto.document_type, adjunto.document_id, adjunto.original_filename
    adjunto.delete()
    log_activity(tenant, entity_type=document_type, entity_id=document_id, action=SalesActivityLog.Action.ATTACHMENT_DELETED, user=user, details=nombre)
