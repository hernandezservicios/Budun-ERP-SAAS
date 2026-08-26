"""
Capa de servicios de Compras (FASE 12): la única vía sancionada para
crear/editar/transicionar Órdenes de Compra, Recepciones, Facturas de
Proveedor, Pagos a Proveedor (Cuentas por Pagar) y Devoluciones a
Proveedor. Ninguna vista debe escribir estos modelos directamente.

Principios heredados de FASES 8/9/10/11, aplicados aquí sin excepción:
- `transaction.atomic()` + `select_for_update()` en toda operación que
  lea-y-luego-escriba un valor que pueda cambiar por concurrencia
  (numeración, recepción, pagos/asignaciones).
- `all_objects` (nunca `objects`/TenantManager) en todas las consultas,
  filtrando siempre `tenant` de forma explícita.
- Operaciones inválidas se rechazan ANTES de escribir nada
  (`InvalidPurchaseOperation`, subclase de `ValidationError`).
- NUNCA se duplica lógica de otro dominio ya construido:
  - Inventario (`apps.inventory.services`): `register_stock_in`/
    `register_stock_out` (QUANTITY), `register_serialized_unit`/
    `transition_unit_status` (SERIALIZED) — este módulo solo orquesta
    CUÁNDO llamarlas.
  - Numeración (`apps.sales.services.generate_document_number` sobre la
    misma `DocumentSequence`) — nunca un segundo sistema de numeración.
  - Autorizaciones (`apps.approvals.services`) — compra sobre el límite
    y sobre-recepción reutilizan las mismas primitivas
    (`request_approval`/`resolve_approval`/`mark_consumed`/
    `get_usable_approved_request`) que ya usa `apps.pos`.
  - Caja (`apps.pos.services.ensure_open_session_for_checkout`/
    `record_cash_movement`) — un pago a proveedor en efectivo exige una
    `CashSession` abierta, igual que un cobro en efectivo del POS.
  - Archivos (`apps.customers.file_validation`) — mismo sistema seguro
    de adjuntos que ya usa `apps.sales`.

Ver `docs/purchases.md`, `docs/purchase-orders.md`, `docs/receiving.md`,
`docs/supplier-invoices.md`, `docs/supplier-returns.md` y
`docs/accounts-payable.md` para el diseño completo.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.approvals import services as approvals_services
from apps.approvals.models import ApprovalRequest
from apps.customers.file_validation import nombre_original_seguro, validar_archivo_adjunto
from apps.customers.models import Supplier
from apps.inventory.models import InventoryUnit, Product
from apps.inventory.services import (
    InvalidInventoryOperation,
    register_serialized_unit,
    register_stock_in,
    register_stock_out,
    transition_unit_status,
)
from apps.pos.models import CashMovement
from apps.pos.services import ensure_open_session_for_checkout, record_cash_movement
from apps.sales.models import DocumentSequence, PaymentMethod
from apps.sales.services import generate_document_number

from .models import (
    PurchaseDocumentAttachment,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
    PurchasesActivityLog,
    SupplierInvoice,
    SupplierInvoiceItem,
    SupplierPayment,
    SupplierPaymentAllocation,
    SupplierReturn,
    SupplierReturnItem,
)


class InvalidPurchaseOperation(ValidationError):
    """Se lanza cuando una operación de Compras no es válida: transición
    de estado no permitida, sobre-recepción sin autorización, pago/
    asignación inválidos, devolución imposible, etc."""


class PurchaseOverThresholdRequiresApproval(InvalidPurchaseOperation):
    """El total de la orden supera el límite autorizado del usuario y no
    se aportó una `ApprovalRequest` aprobada que lo cubra."""

    def __init__(self, *, limit, total):
        self.limit = limit
        self.total = total
        super().__init__(
            f"Esta orden de compra por {total} supera el límite autorizado sin aprobación "
            f"({limit}) — se requiere autorización."
        )


class OverReceivingRequiresApproval(InvalidPurchaseOperation):
    """Se intenta recibir más de lo pendiente de una línea y no se
    aportó una `ApprovalRequest` aprobada que lo cubra."""

    def __init__(self, *, limit_percent, requested_percent, purchase_order_item):
        self.limit_percent = limit_percent
        self.requested_percent = requested_percent
        self.purchase_order_item = purchase_order_item
        super().__init__(
            f"Recibir «{purchase_order_item.description}» excede la cantidad pendiente en "
            f"{requested_percent}% (autorizable sin aprobación: {limit_percent}%) — se requiere autorización."
        )


# ------------------------------------------------------------------
# Auditoría (mínima, acotada a este módulo)
# ------------------------------------------------------------------


def log_activity(tenant, *, entity_type, entity_id, action, user, entity_label="", details=""):
    return PurchasesActivityLog.all_objects.create(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id, entity_label=entity_label,
        action=action, user=user, details=details,
    )


def get_activity_log(tenant, *, entity_type, entity_id, limit=20):
    return PurchasesActivityLog.all_objects.filter(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id
    ).select_related("user")[:limit]


# ------------------------------------------------------------------
# Cálculo de líneas y totales — misma matemática que
# apps.sales.services._recalculate_item/recalculate_document_totals
# (descuento % con prioridad sobre monto fijo, impuesto sobre la base
# ya descontada), reimplementada aquí porque `PurchaseOrderItem`/
# `SupplierInvoiceItem` no comparten el mixin de apps.sales (su
# proveedor no es un Customer) — no es una duplicación de LEDGER ni de
# lógica de inventario/pagos, solo de una fórmula aritmética genérica.
# ------------------------------------------------------------------


def _recalculate_cost_item(item):
    """Válido tanto para `PurchaseOrderItem` como para
    `SupplierInvoiceItem` — ambos comparten exactamente los mismos
    campos derivados (quantity/unit_cost/discount_*/tax_*/subtotal/total)."""
    line_subtotal = (item.quantity * item.unit_cost).quantize(Decimal("0.01"))
    if item.discount_percent and item.discount_percent > 0:
        descuento = (line_subtotal * item.discount_percent / Decimal("100")).quantize(Decimal("0.01"))
    else:
        descuento = item.discount_amount or Decimal("0")
    base_imponible = line_subtotal - descuento
    impuesto = (base_imponible * item.tax_rate / Decimal("100")).quantize(Decimal("0.01"))

    item.subtotal = line_subtotal
    item.discount_amount = descuento
    item.tax_amount = impuesto
    item.total = base_imponible + impuesto
    return item


def get_purchase_order_items(purchase_order):
    return (
        PurchaseOrderItem.all_objects.filter(tenant=purchase_order.tenant, purchase_order=purchase_order)
        .select_related("product")
        .order_by("line_order", "id")
    )


def recalculate_purchase_order_totals(purchase_order):
    """Recalcula la cabecera a partir de sus líneas — nunca al revés.
    El total final suma flete/seguro/otros costos atribuibles (landed
    cost preparado a nivel de cabecera, ver docstring de
    `PurchaseOrder`)."""
    items = list(get_purchase_order_items(purchase_order))
    subtotal = sum((i.quantity * i.unit_cost for i in items), Decimal("0")).quantize(Decimal("0.01"))
    descuento_lineas = sum((i.discount_amount for i in items), Decimal("0"))
    impuesto_total = sum((i.tax_amount for i in items), Decimal("0"))
    total_antes_de_global = sum((i.total for i in items), Decimal("0"))

    if purchase_order.global_discount_percent and purchase_order.global_discount_percent > 0:
        descuento_global = (
            total_antes_de_global * purchase_order.global_discount_percent / Decimal("100")
        ).quantize(Decimal("0.01"))
    else:
        descuento_global = purchase_order.global_discount_amount or Decimal("0")
    descuento_global = min(descuento_global, total_antes_de_global)

    purchase_order.subtotal = subtotal
    purchase_order.discount_total = descuento_lineas + descuento_global
    purchase_order.tax_total = impuesto_total
    purchase_order.total = (
        (total_antes_de_global - descuento_global)
        + purchase_order.freight_cost
        + purchase_order.insurance_cost
        + purchase_order.other_costs
    )
    purchase_order.save(
        update_fields=["subtotal", "discount_total", "tax_total", "total", "updated_at"]
    )


def get_supplier_invoice_items(invoice):
    return (
        SupplierInvoiceItem.all_objects.filter(tenant=invoice.tenant, invoice=invoice)
        .select_related("purchase_order_item")
        .order_by("line_order", "id")
    )


def recalculate_supplier_invoice_totals(invoice):
    items = list(get_supplier_invoice_items(invoice))
    subtotal = sum((i.quantity * i.unit_cost for i in items), Decimal("0")).quantize(Decimal("0.01"))
    descuento = sum((i.discount_amount for i in items), Decimal("0"))
    impuesto = sum((i.tax_amount for i in items), Decimal("0"))
    total = sum((i.total for i in items), Decimal("0"))
    invoice.subtotal = subtotal
    invoice.discount_total = descuento
    invoice.tax_total = impuesto
    invoice.total = total
    invoice.save(update_fields=["subtotal", "discount_total", "tax_total", "total"])


# ------------------------------------------------------------------
# Orden de Compra
# ------------------------------------------------------------------


@transaction.atomic
def create_purchase_order(
    tenant, *, supplier, user, issue_date=None, expected_date=None, currency=None,
    payment_terms=None, notes="", terms="",
):
    if supplier.tenant_id != tenant.id:
        raise InvalidPurchaseOperation("El proveedor no pertenece a este tenant.")
    numero = generate_document_number(tenant, DocumentSequence.DocumentType.PURCHASE_ORDER)
    orden = PurchaseOrder.all_objects.create(
        tenant=tenant, supplier=supplier, number=numero,
        issue_date=issue_date or timezone.localdate(), expected_date=expected_date,
        currency=currency or supplier.currency, payment_terms=payment_terms or supplier.payment_terms,
        notes=notes, terms=terms, created_by=user,
    )
    log_activity(
        tenant, entity_type="purchase_order", entity_id=orden.pk, entity_label=orden.number,
        action=PurchasesActivityLog.Action.CREATED, user=user, details=supplier.display_name,
    )
    return orden


@transaction.atomic
def update_purchase_order_header(
    purchase_order, *, user, expected_date=None, currency=None, payment_terms=None, notes=None,
    terms=None, global_discount_percent=None, global_discount_amount=None,
    freight_cost=None, insurance_cost=None, other_costs=None,
):
    locked = PurchaseOrder.all_objects.select_for_update().get(pk=purchase_order.pk, tenant=purchase_order.tenant)
    if locked.status != PurchaseOrder.Status.DRAFT:
        raise InvalidPurchaseOperation("Solo se puede editar una orden de compra en borrador.")
    campos = []
    for campo, valor in (
        ("expected_date", expected_date), ("currency", currency), ("payment_terms", payment_terms),
        ("notes", notes), ("terms", terms),
        ("global_discount_percent", global_discount_percent), ("global_discount_amount", global_discount_amount),
        ("freight_cost", freight_cost), ("insurance_cost", insurance_cost), ("other_costs", other_costs),
    ):
        if valor is not None:
            setattr(locked, campo, valor)
            campos.append(campo)
    if campos:
        locked.save(update_fields=campos + ["updated_at"])
    recalculate_purchase_order_totals(locked)
    log_activity(
        locked.tenant, entity_type="purchase_order", entity_id=locked.pk, entity_label=locked.number,
        action=PurchasesActivityLog.Action.UPDATED, user=user,
    )
    return locked


@transaction.atomic
def add_purchase_order_item(
    purchase_order, *, product, quantity, user, unit_cost=None,
    discount_percent=None, discount_amount=None, tax_rate=None,
):
    locked_po = PurchaseOrder.all_objects.select_for_update().get(pk=purchase_order.pk, tenant=purchase_order.tenant)
    if locked_po.status != PurchaseOrder.Status.DRAFT:
        raise InvalidPurchaseOperation("Solo se pueden agregar líneas a una orden de compra en borrador.")
    if product.tenant_id != locked_po.tenant_id:
        raise InvalidPurchaseOperation("El producto no pertenece a este tenant.")
    if quantity is None or quantity <= 0:
        raise InvalidPurchaseOperation("La cantidad debe ser mayor que cero.")

    orden_linea = PurchaseOrderItem.all_objects.filter(tenant=locked_po.tenant, purchase_order=locked_po).count() + 1
    item = PurchaseOrderItem.all_objects.create(
        tenant=locked_po.tenant, purchase_order=locked_po, product=product,
        description=product.name, sku_snapshot=product.sku, quantity=quantity,
        unit_cost=unit_cost if unit_cost is not None else product.purchase_price,
        discount_percent=discount_percent or Decimal("0"), discount_amount=discount_amount or Decimal("0"),
        tax_rate=tax_rate if tax_rate is not None else product.tax_rate, line_order=orden_linea,
    )
    _recalculate_cost_item(item)
    item.save()
    recalculate_purchase_order_totals(locked_po)
    return item


@transaction.atomic
def remove_purchase_order_item(item):
    locked_po = PurchaseOrder.all_objects.select_for_update().get(pk=item.purchase_order_id, tenant=item.tenant)
    if locked_po.status != PurchaseOrder.Status.DRAFT:
        raise InvalidPurchaseOperation("Solo se pueden quitar líneas de una orden en borrador.")
    item.delete()
    recalculate_purchase_order_totals(locked_po)


def _find_usable_purchase_approval(tenant, purchase_order, user):
    return approvals_services.get_usable_approved_request(
        tenant, action_type=ApprovalRequest.ActionType.PURCHASE_OVER_THRESHOLD,
        document_type="purchase_order", document_id=purchase_order.pk,
    )


@transaction.atomic
def send_purchase_order(purchase_order, user, *, tenant, use_approval=None):
    """Envía la orden al proveedor. Si el total excede el límite
    autorizable del usuario, exige una `ApprovalRequest` aprobada y no
    consumida (`use_approval`), o lanza `PurchaseOverThresholdRequiresApproval`
    — mismo patrón que `apps.pos.services.add_item_to_cart` con
    descuentos."""
    locked = PurchaseOrder.all_objects.select_for_update().get(pk=purchase_order.pk, tenant=purchase_order.tenant)
    if locked.status != PurchaseOrder.Status.DRAFT:
        raise InvalidPurchaseOperation(
            f"Solo una orden en borrador puede enviarse (estado actual: {locked.get_status_display()})."
        )
    if not PurchaseOrderItem.all_objects.filter(tenant=locked.tenant, purchase_order=locked).exists():
        raise InvalidPurchaseOperation("La orden de compra no tiene líneas.")

    autorizado, limite = approvals_services.check_purchase_authorization(tenant, user, amount=locked.total)
    if not autorizado:
        aprobacion = use_approval or _find_usable_purchase_approval(tenant, locked, user)
        cubierto = (
            aprobacion is not None
            and aprobacion.status == ApprovalRequest.Status.APPROVED
            and aprobacion.consumed_at is None
            and (aprobacion.approved_value or Decimal("0")) >= locked.total
        )
        if not cubierto:
            raise PurchaseOverThresholdRequiresApproval(limit=limite, total=locked.total)
        approvals_services.mark_consumed(aprobacion, user)

    locked.status = PurchaseOrder.Status.SENT
    locked.sent_at = timezone.now()
    locked.sent_by = user
    locked.save(update_fields=["status", "sent_at", "sent_by"])
    log_activity(
        locked.tenant, entity_type="purchase_order", entity_id=locked.pk, entity_label=locked.number,
        action=PurchasesActivityLog.Action.SENT, user=user, details=str(locked.total),
    )
    return locked


def request_purchase_approval(tenant, purchase_order, user, *, limite):
    return approvals_services.request_approval(
        tenant, action_type=ApprovalRequest.ActionType.PURCHASE_OVER_THRESHOLD, requested_by=user,
        requested_value=purchase_order.total, allowed_limit=limite,
        reason=f"Orden de compra {purchase_order.number} por {purchase_order.total}",
        document_type="purchase_order", document_id=purchase_order.pk,
    )


@transaction.atomic
def cancel_purchase_order(purchase_order, user, *, reason=""):
    locked = PurchaseOrder.all_objects.select_for_update().get(pk=purchase_order.pk, tenant=purchase_order.tenant)
    if locked.status in (PurchaseOrder.Status.CANCELED, PurchaseOrder.Status.CLOSED):
        raise InvalidPurchaseOperation(f"Esta orden ya está {locked.get_status_display()}.")
    if PurchaseReceipt.all_objects.filter(tenant=locked.tenant, purchase_order=locked).exists():
        raise InvalidPurchaseOperation(
            "No se puede cancelar una orden que ya tiene recepciones registradas — ciérrala en su lugar."
        )
    locked.status = PurchaseOrder.Status.CANCELED
    locked.canceled_at = timezone.now()
    locked.canceled_by = user
    locked.cancel_reason = reason
    locked.save(update_fields=["status", "canceled_at", "canceled_by", "cancel_reason"])
    log_activity(
        locked.tenant, entity_type="purchase_order", entity_id=locked.pk, entity_label=locked.number,
        action=PurchasesActivityLog.Action.CANCELED, user=user, details=reason,
    )
    return locked


@transaction.atomic
def close_purchase_order(purchase_order, user):
    """Cierra manualmente una orden que no recibirá más mercancía
    (p. ej. quedó parcialmente recibida y el resto ya no llegará) —
    distinto de `RECEIVED`, que se deriva automáticamente al recibir
    por completo."""
    locked = PurchaseOrder.all_objects.select_for_update().get(pk=purchase_order.pk, tenant=purchase_order.tenant)
    if locked.status not in (
        PurchaseOrder.Status.SENT, PurchaseOrder.Status.PARTIALLY_RECEIVED, PurchaseOrder.Status.RECEIVED,
    ):
        raise InvalidPurchaseOperation(f"No se puede cerrar una orden en estado {locked.get_status_display()}.")
    locked.status = PurchaseOrder.Status.CLOSED
    locked.closed_at = timezone.now()
    locked.closed_by = user
    locked.save(update_fields=["status", "closed_at", "closed_by"])
    log_activity(
        locked.tenant, entity_type="purchase_order", entity_id=locked.pk, entity_label=locked.number,
        action=PurchasesActivityLog.Action.CLOSED, user=user,
    )
    return locked


# ------------------------------------------------------------------
# Recepción — parcial o completa, QUANTITY (register_stock_in) y
# SERIALIZED (register_serialized_unit, una llamada por unidad física).
# `PurchaseOrderItem` NUNCA guarda "recibido"/"pendiente": se calculan
# siempre agregando sobre `PurchaseReceiptItem` (ver docstring del
# módulo de modelos).
# ------------------------------------------------------------------


def get_purchase_order_item_received_quantity(item):
    agregado = PurchaseReceiptItem.all_objects.filter(
        tenant=item.tenant, purchase_order_item=item
    ).aggregate(cantidad=Sum("quantity_received"), unidades=Count("inventory_unit"))
    return (agregado["cantidad"] or Decimal("0")) + Decimal(agregado["unidades"] or 0)


def get_purchase_order_item_pending_quantity(item):
    return item.quantity - get_purchase_order_item_received_quantity(item)


def get_purchase_order_items_received_bulk(items):
    """Mismo principio que `apps.sales.services.get_sale_balance_due_bulk`
    (FASE 11): evita N+1 al listar la recepción pendiente de todas las
    líneas de una orden en una sola pasada."""
    items = list(items)
    if not items:
        return {}
    ids = [i.pk for i in items]
    tenant = items[0].tenant
    filas = (
        PurchaseReceiptItem.all_objects.filter(tenant=tenant, purchase_order_item_id__in=ids)
        .values("purchase_order_item_id")
        .annotate(cantidad=Sum("quantity_received"), unidades=Count("inventory_unit"))
    )
    recibido_por_item = {
        fila["purchase_order_item_id"]: (fila["cantidad"] or Decimal("0")) + Decimal(fila["unidades"] or 0)
        for fila in filas
    }
    return {item.pk: recibido_por_item.get(item.pk, Decimal("0")) for item in items}


def get_purchase_receipts(purchase_order):
    return (
        PurchaseReceipt.all_objects.filter(tenant=purchase_order.tenant, purchase_order=purchase_order)
        .select_related("user")
        .order_by("-created_at", "-id")
    )


def get_receipt_items(receipt):
    return (
        PurchaseReceiptItem.all_objects.filter(tenant=receipt.tenant, receipt=receipt)
        .select_related("purchase_order_item", "inventory_unit")
        .order_by("id")
    )


def _recompute_purchase_order_status(purchase_order):
    items = list(PurchaseOrderItem.all_objects.filter(tenant=purchase_order.tenant, purchase_order=purchase_order))
    recibido = get_purchase_order_items_received_bulk(items)
    todo_completo = bool(items) and all(recibido.get(i.pk, Decimal("0")) >= i.quantity for i in items)
    algo_recibido = any(recibido.get(i.pk, Decimal("0")) > 0 for i in items)
    if todo_completo:
        estado = PurchaseOrder.Status.RECEIVED
    elif algo_recibido:
        estado = PurchaseOrder.Status.PARTIALLY_RECEIVED
    else:
        estado = purchase_order.status
    PurchaseOrder.all_objects.filter(pk=purchase_order.pk).update(status=estado)
    purchase_order.status = estado
    return estado


@transaction.atomic
def receive_purchase_order(purchase_order, *, lines, user, tenant, receipt_date=None, notes="", use_approval=None):
    """Registra una recepción (parcial o completa) contra una orden ya
    enviada. `lines`: lista de dicts, uno por línea de la orden que se
    recibe en esta operación:
    - QUANTITY: `{"purchase_order_item":, "quantity_received": Decimal, "unit_cost": Decimal opcional}`
    - SERIALIZED: `{"purchase_order_item":, "units": [{"serial":, "imei_1":, "imei_2":, "unit_cost":, "notes":}, ...]}`

    Por defecto rechaza recibir más de lo pendiente de cada línea
    (sobre-recepción): exige una `ApprovalRequest` APROBADA
    (`ActionType.OVER_RECEIVING`) para esta orden, o lanza
    `OverReceivingRequiresApproval`. El `select_for_update()` sobre la
    orden serializa dos recepciones concurrentes de la misma orden —
    la segunda ve siempre el "pendiente" ya actualizado por la primera."""
    locked_po = PurchaseOrder.all_objects.select_for_update().get(pk=purchase_order.pk, tenant=purchase_order.tenant)
    if locked_po.status not in (PurchaseOrder.Status.SENT, PurchaseOrder.Status.PARTIALLY_RECEIVED):
        raise InvalidPurchaseOperation(
            f"Solo se puede recibir contra una orden enviada o parcialmente recibida "
            f"(estado actual: {locked_po.get_status_display()})."
        )
    if not lines:
        raise InvalidPurchaseOperation("Debes indicar al menos una línea a recibir.")

    numero = generate_document_number(locked_po.tenant, DocumentSequence.DocumentType.PURCHASE_RECEIPT)
    recepcion = PurchaseReceipt.all_objects.create(
        tenant=locked_po.tenant, purchase_order=locked_po, number=numero,
        receipt_date=receipt_date or timezone.localdate(), notes=notes, user=user,
    )

    for linea in lines:
        item = linea["purchase_order_item"]
        if item.purchase_order_id != locked_po.pk or item.tenant_id != locked_po.tenant_id:
            raise InvalidPurchaseOperation("Una línea de recepción debe pertenecer a esta orden de compra.")

        es_serializado = item.product.inventory_tracking_type == Product.TrackingType.SERIALIZED
        if es_serializado:
            unidades = linea.get("units") or []
            if not unidades:
                raise InvalidPurchaseOperation(f"«{item.description}» es serializado: indica al menos una unidad.")
            solicitado = Decimal(len(unidades))
        else:
            solicitado = linea.get("quantity_received")
            if solicitado is None or solicitado <= 0:
                raise InvalidPurchaseOperation(f"La cantidad recibida de «{item.description}» debe ser mayor que cero.")

        pendiente = get_purchase_order_item_pending_quantity(item)
        if solicitado > pendiente:
            exceso = solicitado - pendiente
            base = pendiente if pendiente > 0 else item.quantity
            exceso_percent = (exceso / base * Decimal("100")).quantize(Decimal("0.01")) if base else Decimal("100")
            autorizado, limite_percent = approvals_services.check_over_receiving_authorization(
                tenant, user, excess_percent=exceso_percent
            )
            if not autorizado:
                aprobacion = use_approval or approvals_services.get_usable_approved_request(
                    tenant, action_type=ApprovalRequest.ActionType.OVER_RECEIVING,
                    document_type="purchase_order", document_id=locked_po.pk,
                )
                cubierto = (
                    aprobacion is not None
                    and aprobacion.status == ApprovalRequest.Status.APPROVED
                    and aprobacion.consumed_at is None
                )
                if not cubierto:
                    raise OverReceivingRequiresApproval(
                        limit_percent=limite_percent, requested_percent=exceso_percent, purchase_order_item=item,
                    )
                approvals_services.mark_consumed(aprobacion, user)

        if es_serializado:
            for unidad in unidades:
                # `dict.get(key, default)` solo usa `default` si la CLAVE
                # falta, nunca si está presente con valor `None` (el caso
                # normal cuando el formulario deja el costo en blanco) —
                # de ahí la comprobación explícita en vez de `.get(..., x)`.
                costo_unidad = unidad.get("unit_cost")
                if costo_unidad is None:
                    costo_unidad = item.unit_cost
                try:
                    with transaction.atomic():
                        inventory_unit = register_serialized_unit(
                            product=item.product, user=user,
                            serial=unidad.get("serial", ""), imei_1=unidad.get("imei_1", ""),
                            imei_2=unidad.get("imei_2", ""), unit_cost=costo_unidad,
                            entry_date=recepcion.receipt_date,
                            purchase_origin=f"{locked_po.number} / {recepcion.number}",
                            notes=unidad.get("notes", ""),
                        )
                except InvalidInventoryOperation as error:
                    raise InvalidPurchaseOperation(str(error)) from error
                except IntegrityError as error:
                    # Sin una única fila que bloquear con select_for_update()
                    # (la unicidad de serial/IMEI es por tenant, no por una
                    # fila concreta) — mismo caso ya resuelto en FASE 11
                    # para la exclusividad de CashSession por usuario:
                    # se traduce el IntegrityError de la constraint de
                    # PostgreSQL a un error de negocio claro, nunca se deja
                    # escapar sin traducir.
                    raise InvalidPurchaseOperation(
                        "Ese número de serie o IMEI ya está registrado en otra unidad de este tenant."
                    ) from error
                PurchaseReceiptItem.all_objects.create(
                    tenant=locked_po.tenant, receipt=recepcion, purchase_order_item=item,
                    inventory_unit=inventory_unit, unit_cost=costo_unidad,
                )
        else:
            costo_linea = linea.get("unit_cost")
            if costo_linea is None:
                costo_linea = item.unit_cost
            try:
                # Costeo por promedio ponderado (ampliación de cierre de
                # FASE 14): el costo real de esta recepción alimenta el
                # promedio del producto — nunca una entrada "ciega" sin
                # costo, ver apps.inventory.services._register_movement.
                register_stock_in(
                    product=item.product, quantity=solicitado, user=user,
                    notes=f"Recepción {recepcion.number} (OC {locked_po.number})", unit_cost=costo_linea,
                )
            except InvalidInventoryOperation as error:
                raise InvalidPurchaseOperation(str(error)) from error
            PurchaseReceiptItem.all_objects.create(
                tenant=locked_po.tenant, receipt=recepcion, purchase_order_item=item,
                quantity_received=solicitado, unit_cost=costo_linea,
            )

    estado_final = _recompute_purchase_order_status(locked_po)
    log_activity(
        locked_po.tenant, entity_type="purchase_receipt", entity_id=recepcion.pk, entity_label=recepcion.number,
        action=(
            PurchasesActivityLog.Action.RECEIVED_FULL
            if estado_final == PurchaseOrder.Status.RECEIVED
            else PurchasesActivityLog.Action.RECEIVED_PARTIAL
        ),
        user=user, details=f"OC {locked_po.number}",
    )
    return recepcion


def request_over_receiving_approval(tenant, purchase_order, user, *, limite_percent, exceso_percent):
    return approvals_services.request_approval(
        tenant, action_type=ApprovalRequest.ActionType.OVER_RECEIVING, requested_by=user,
        requested_value=exceso_percent, allowed_limit=limite_percent,
        reason=f"Sobre-recepción en orden de compra {purchase_order.number}",
        document_type="purchase_order", document_id=purchase_order.pk,
    )


# ------------------------------------------------------------------
# Factura de proveedor
# ------------------------------------------------------------------


@transaction.atomic
def create_supplier_invoice(
    tenant, *, supplier, supplier_invoice_number, user, purchase_order=None,
    issue_date=None, due_date=None, currency=None, notes="",
):
    if not supplier_invoice_number:
        raise InvalidPurchaseOperation("El número de factura del proveedor es obligatorio.")
    if purchase_order is not None and purchase_order.supplier_id != supplier.pk:
        raise InvalidPurchaseOperation("La orden de compra indicada no pertenece a este proveedor.")
    factura = SupplierInvoice.all_objects.create(
        tenant=tenant, supplier=supplier, purchase_order=purchase_order,
        supplier_invoice_number=supplier_invoice_number, issue_date=issue_date or timezone.localdate(),
        due_date=due_date, currency=currency or supplier.currency, notes=notes, created_by=user,
    )
    log_activity(
        tenant, entity_type="supplier_invoice", entity_id=factura.pk, entity_label=factura.supplier_invoice_number,
        action=PurchasesActivityLog.Action.INVOICE_REGISTERED, user=user, details=supplier.display_name,
    )
    return factura


@transaction.atomic
def add_supplier_invoice_item(
    invoice, *, description, quantity, unit_cost, user, purchase_order_item=None,
    discount_percent=None, discount_amount=None, tax_rate=None,
):
    locked = SupplierInvoice.all_objects.select_for_update().get(pk=invoice.pk, tenant=invoice.tenant)
    if locked.status != SupplierInvoice.Status.DRAFT:
        raise InvalidPurchaseOperation("Solo se pueden agregar líneas a una factura en borrador.")
    if quantity is None or quantity <= 0:
        raise InvalidPurchaseOperation("La cantidad debe ser mayor que cero.")

    orden_linea = SupplierInvoiceItem.all_objects.filter(tenant=locked.tenant, invoice=locked).count() + 1
    item = SupplierInvoiceItem.all_objects.create(
        tenant=locked.tenant, invoice=locked, purchase_order_item=purchase_order_item,
        description=description, quantity=quantity, unit_cost=unit_cost,
        discount_percent=discount_percent or Decimal("0"), discount_amount=discount_amount or Decimal("0"),
        tax_rate=tax_rate or Decimal("0"), line_order=orden_linea,
    )
    _recalculate_cost_item(item)
    item.save()
    recalculate_supplier_invoice_totals(locked)
    return item


@transaction.atomic
def confirm_supplier_invoice(invoice, user):
    locked = SupplierInvoice.all_objects.select_for_update().get(pk=invoice.pk, tenant=invoice.tenant)
    if locked.status != SupplierInvoice.Status.DRAFT:
        raise InvalidPurchaseOperation(
            f"Solo una factura en borrador puede confirmarse (estado actual: {locked.get_status_display()})."
        )
    if not SupplierInvoiceItem.all_objects.filter(tenant=locked.tenant, invoice=locked).exists():
        raise InvalidPurchaseOperation("La factura no tiene líneas.")
    locked.status = SupplierInvoice.Status.CONFIRMED
    locked.confirmed_at = timezone.now()
    locked.confirmed_by = user
    locked.save(update_fields=["status", "confirmed_at", "confirmed_by"])
    log_activity(
        locked.tenant, entity_type="supplier_invoice", entity_id=locked.pk, entity_label=locked.supplier_invoice_number,
        action=PurchasesActivityLog.Action.INVOICE_CONFIRMED, user=user, details=str(locked.total),
    )

    # FASE 14 (Contabilidad General, ampliación de cierre): contabilización
    # automática, deliberadamente resiliente — nunca debe romper la
    # confirmación de la factura. Import diferido, mismo patrón que
    # apps.sales.services.confirm_sale.
    from apps.accounting.services import try_record_supplier_invoice_confirmed

    try_record_supplier_invoice_confirmed(locked, user)
    return locked


@transaction.atomic
def cancel_supplier_invoice(invoice, user, *, reason=""):
    locked = SupplierInvoice.all_objects.select_for_update().get(pk=invoice.pk, tenant=invoice.tenant)
    if locked.status == SupplierInvoice.Status.CANCELED:
        return locked
    if get_invoice_paid_amount(locked) > 0:
        raise InvalidPurchaseOperation(
            "No se puede cancelar una factura que ya tiene pagos aplicados — revierte los pagos primero."
        )
    locked.status = SupplierInvoice.Status.CANCELED
    locked.canceled_at = timezone.now()
    locked.canceled_by = user
    locked.save(update_fields=["status", "canceled_at", "canceled_by"])
    log_activity(
        locked.tenant, entity_type="supplier_invoice", entity_id=locked.pk, entity_label=locked.supplier_invoice_number,
        action=PurchasesActivityLog.Action.INVOICE_CANCELED, user=user, details=reason,
    )
    return locked


# ------------------------------------------------------------------
# Cuentas por Pagar: SupplierPayment + SupplierPaymentAllocation —
# mismo patrón append-only que apps.sales.Payment/PaymentAllocation
# (Cuentas por Cobrar). Un anticipo a proveedor es simplemente un
# SupplierPayment sin ninguna asignación todavía — nunca un modelo
# separado (mismo principio que "anticipo de cliente").
# ------------------------------------------------------------------


def get_invoice_paid_amount(invoice):
    return SupplierPaymentAllocation.all_objects.filter(
        tenant=invoice.tenant, supplier_invoice=invoice, status=SupplierPaymentAllocation.Status.ACTIVE,
        payment__status=SupplierPayment.Status.CONFIRMED,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")


def get_invoice_balance_due(invoice):
    return invoice.total - get_invoice_paid_amount(invoice)


def get_invoice_balance_due_bulk(invoices):
    invoices = list(invoices)
    if not invoices:
        return {}
    ids = [f.pk for f in invoices]
    tenant = invoices[0].tenant
    pagado_por_factura = dict(
        SupplierPaymentAllocation.all_objects.filter(
            tenant=tenant, supplier_invoice_id__in=ids, status=SupplierPaymentAllocation.Status.ACTIVE,
            payment__status=SupplierPayment.Status.CONFIRMED,
        ).values("supplier_invoice_id").annotate(total=Sum("amount")).values_list("supplier_invoice_id", "total")
    )
    return {
        factura.pk: factura.total - (pagado_por_factura.get(factura.pk) or Decimal("0"))
        for factura in invoices
    }


def get_supplier_pending_invoices(supplier):
    facturas = list(SupplierInvoice.all_objects.filter(
        tenant=supplier.tenant, supplier=supplier, status=SupplierInvoice.Status.CONFIRMED,
    ).order_by("issue_date", "id"))
    saldos = get_invoice_balance_due_bulk(facturas)
    return [factura for factura in facturas if saldos.get(factura.pk, Decimal("0")) > 0]


def get_unallocated_supplier_payment_amount(payment):
    asignado = SupplierPaymentAllocation.all_objects.filter(
        tenant=payment.tenant, payment=payment, status=SupplierPaymentAllocation.Status.ACTIVE
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return payment.amount - asignado


def get_supplier_advance_balance(supplier):
    """Saldo a favor NUESTRO frente al proveedor: suma del saldo sin
    aplicar de todos sus pagos confirmados — mismo principio que
    `apps.sales.services.get_customer_credit_balance`, ninguna tabla ni
    campo nuevo de saldo."""
    total = Decimal("0")
    pagos = SupplierPayment.all_objects.filter(
        tenant=supplier.tenant, supplier=supplier, status=SupplierPayment.Status.CONFIRMED
    )
    for pago in pagos:
        total += get_unallocated_supplier_payment_amount(pago)
    return total


def get_payment_allocations(payment):
    return (
        SupplierPaymentAllocation.all_objects.filter(tenant=payment.tenant, payment=payment)
        .select_related("supplier_invoice")
        .order_by("-created_at")
    )


def get_invoice_allocations(invoice):
    return (
        SupplierPaymentAllocation.all_objects.filter(
            tenant=invoice.tenant, supplier_invoice=invoice, status=SupplierPaymentAllocation.Status.ACTIVE
        )
        .select_related("payment")
        .order_by("-created_at")
    )


@transaction.atomic
def create_supplier_payment(
    tenant, *, supplier, method, amount, user, currency=None, reference="", idempotency_key="",
    notes="", cash_session=None, cash_movement_type=None,
):
    """Registra dinero entregado a un proveedor SIN aplicarlo todavía a
    ninguna factura — queda disponible como anticipo
    (`get_unallocated_supplier_payment_amount`) hasta llamar a
    `allocate_supplier_payment`/`apply_supplier_payment_to_invoices`/
    `record_supplier_payment_for_invoice`. Idempotente por
    `idempotency_key`. En efectivo, exige una `CashSession` abierta
    (`ensure_open_session_for_checkout`) y registra el `CashMovement`
    de salida correspondiente — nunca duplica esa lógica de caja."""
    if idempotency_key:
        existente = SupplierPayment.all_objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
        if existente:
            return existente
    if amount is None or amount <= 0:
        raise InvalidPurchaseOperation("El monto del pago debe ser mayor que cero.")
    if supplier.tenant_id != tenant.id:
        raise InvalidPurchaseOperation("El proveedor no pertenece a este tenant.")

    sesion = cash_session
    if method == PaymentMethod.CASH and sesion is None:
        sesion = ensure_open_session_for_checkout(tenant, user)

    pago = SupplierPayment.all_objects.create(
        tenant=tenant, supplier=supplier, method=method, amount=amount,
        currency=currency or supplier.currency, reference=reference, idempotency_key=idempotency_key,
        cash_session=sesion if method == PaymentMethod.CASH else None, user=user, notes=notes,
    )
    if method == PaymentMethod.CASH:
        record_cash_movement(
            sesion, movement_type=cash_movement_type or CashMovement.MovementType.SUPPLIER_PAYMENT_CASH,
            amount=amount, user=user, reason=f"Pago a {supplier.display_name}",
            reference_type="supplier_payment", reference_id=pago.pk,
        )
    log_activity(
        tenant, entity_type="supplier_payment", entity_id=pago.pk,
        entity_label=f"{pago.get_method_display()} {pago.amount}",
        action=PurchasesActivityLog.Action.PAYMENT_RECORDED, user=user, details=supplier.display_name,
    )

    from apps.accounting.services import try_record_supplier_payment

    try_record_supplier_payment(pago, user)
    return pago


@transaction.atomic
def allocate_supplier_payment(payment, invoice, amount, user):
    """Aplica `amount` de un pago a una factura concreta. Bloquea AMBAS
    filas antes de validar para que dos asignaciones concurrentes nunca
    sobre-apliquen — mismo patrón que `apps.sales.services.allocate_payment`."""
    locked_payment = SupplierPayment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    locked_invoice = SupplierInvoice.all_objects.select_for_update().get(pk=invoice.pk, tenant=invoice.tenant)

    if locked_payment.tenant_id != locked_invoice.tenant_id:
        raise InvalidPurchaseOperation("El pago y la factura deben pertenecer al mismo tenant.")
    if locked_payment.supplier_id != locked_invoice.supplier_id:
        raise InvalidPurchaseOperation("Un pago solo puede aplicarse a facturas del mismo proveedor.")
    if locked_payment.status != SupplierPayment.Status.CONFIRMED:
        raise InvalidPurchaseOperation("Solo un pago confirmado puede aplicarse a una factura.")
    if locked_invoice.status != SupplierInvoice.Status.CONFIRMED:
        raise InvalidPurchaseOperation(
            f"Solo se puede aplicar un pago a una factura confirmada (estado actual: {locked_invoice.get_status_display()})."
        )
    if amount is None or amount <= 0:
        raise InvalidPurchaseOperation("El monto a aplicar debe ser mayor que cero.")

    disponible_pago = get_unallocated_supplier_payment_amount(locked_payment)
    if amount > disponible_pago:
        raise InvalidPurchaseOperation(f"El pago solo tiene {disponible_pago} disponible sin aplicar.")
    saldo_factura = get_invoice_balance_due(locked_invoice)
    if amount > saldo_factura:
        raise InvalidPurchaseOperation(
            f"La factura «{locked_invoice.supplier_invoice_number}» solo tiene {saldo_factura} pendiente."
        )

    asignacion = SupplierPaymentAllocation.all_objects.create(
        tenant=locked_payment.tenant, payment=locked_payment, supplier_invoice=locked_invoice, amount=amount, user=user,
    )
    log_activity(
        locked_invoice.tenant, entity_type="supplier_invoice", entity_id=locked_invoice.pk,
        entity_label=locked_invoice.supplier_invoice_number,
        action=PurchasesActivityLog.Action.PAYMENT_ALLOCATED, user=user,
        details=f"{amount} del pago #{locked_payment.pk} ({locked_payment.get_method_display()})",
    )
    return asignacion


@transaction.atomic
def apply_supplier_payment_to_invoices(payment, allocations, user):
    """Aplica un mismo pago a VARIAS facturas en una sola operación —
    `allocations`: lista de `{"invoice": SupplierInvoice, "amount": Decimal}`."""
    if not allocations:
        raise InvalidPurchaseOperation("Debes indicar al menos una factura a la que aplicar el pago.")
    locked_payment = SupplierPayment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    total_solicitado = sum((entrada["amount"] for entrada in allocations), Decimal("0"))
    disponible = get_unallocated_supplier_payment_amount(locked_payment)
    if total_solicitado > disponible:
        raise InvalidPurchaseOperation(
            f"El total a aplicar ({total_solicitado}) excede el saldo disponible del pago ({disponible})."
        )
    return [
        allocate_supplier_payment(locked_payment, entrada["invoice"], entrada["amount"], user)
        for entrada in allocations
    ]


@transaction.atomic
def record_supplier_payment_for_invoice(
    invoice, *, method, amount, user, currency=None, reference="", idempotency_key="", notes="", cash_session=None,
):
    """Atajo: un pago que se entrega y se aplica de inmediato a una sola
    factura — mismo patrón que `apps.sales.services.record_payment_for_sale`."""
    locked_invoice = SupplierInvoice.all_objects.select_for_update().get(pk=invoice.pk, tenant=invoice.tenant)
    pago = create_supplier_payment(
        locked_invoice.tenant, supplier=locked_invoice.supplier, method=method, amount=amount, user=user,
        currency=currency or locked_invoice.currency, reference=reference, idempotency_key=idempotency_key,
        notes=notes, cash_session=cash_session,
    )
    disponible = get_unallocated_supplier_payment_amount(pago)
    if disponible > 0:
        allocate_supplier_payment(pago, locked_invoice, min(amount, disponible), user)
    return pago


@transaction.atomic
def reverse_supplier_allocation(allocation, user):
    locked = SupplierPaymentAllocation.all_objects.select_for_update().get(pk=allocation.pk, tenant=allocation.tenant)
    if locked.status == SupplierPaymentAllocation.Status.REVERSED:
        return locked
    locked.status = SupplierPaymentAllocation.Status.REVERSED
    locked.reversed_at = timezone.now()
    locked.reversed_by = user
    locked.save(update_fields=["status", "reversed_at", "reversed_by"])
    log_activity(
        locked.tenant, entity_type="supplier_invoice", entity_id=locked.supplier_invoice_id,
        entity_label=locked.supplier_invoice.supplier_invoice_number,
        action=PurchasesActivityLog.Action.PAYMENT_ALLOCATION_REVERSED, user=user,
        details=f"{locked.amount} del pago #{locked.payment_id}",
    )
    return locked


@transaction.atomic
def void_supplier_payment(payment, user):
    locked = SupplierPayment.all_objects.select_for_update().get(pk=payment.pk, tenant=payment.tenant)
    if locked.status == SupplierPayment.Status.VOIDED:
        return locked
    asignaciones_activas = SupplierPaymentAllocation.all_objects.filter(
        tenant=locked.tenant, payment=locked, status=SupplierPaymentAllocation.Status.ACTIVE
    )
    for asignacion in asignaciones_activas:
        reverse_supplier_allocation(asignacion, user)
    locked.status = SupplierPayment.Status.VOIDED
    locked.save(update_fields=["status"])
    log_activity(
        locked.tenant, entity_type="supplier_payment", entity_id=locked.pk,
        entity_label=f"{locked.get_method_display()} {locked.amount}",
        action=PurchasesActivityLog.Action.PAYMENT_VOIDED, user=user, details=locked.supplier.display_name,
    )
    return locked


def register_supplier_advance(tenant, *, supplier, method, amount, user, cash_session=None, reference="", notes=""):
    """Un anticipo NUNCA es una factura: dinero entregado a un proveedor
    antes de recibir su factura, sin aplicar todavía a nada — un
    `SupplierPayment` sin asignaciones. Mismo principio que
    `apps.pos.services.register_customer_advance`."""
    if supplier is None:
        raise InvalidPurchaseOperation("Un anticipo siempre debe asociarse a un proveedor.")
    return create_supplier_payment(
        tenant, supplier=supplier, method=method, amount=amount, user=user, reference=reference, notes=notes,
        cash_session=cash_session, cash_movement_type=CashMovement.MovementType.SUPPLIER_ADVANCE_CASH,
    )


@transaction.atomic
def apply_supplier_advance_to_invoice(supplier, invoice, amount, user):
    """Aplica anticipos disponibles del proveedor (pagos sin asignar,
    más antiguos primero) a una factura pendiente, hasta cubrir
    `amount` — nunca todo o nada. Mismo principio que
    `apps.pos.services.apply_customer_credit_to_sale`."""
    if amount is None or amount <= 0:
        raise InvalidPurchaseOperation("El monto a aplicar debe ser mayor que cero.")
    restante = amount
    aplicaciones = []
    pagos = SupplierPayment.all_objects.filter(
        tenant=supplier.tenant, supplier=supplier, status=SupplierPayment.Status.CONFIRMED
    ).order_by("created_at")
    for pago in pagos:
        if restante <= 0:
            break
        disponible = get_unallocated_supplier_payment_amount(pago)
        if disponible <= 0:
            continue
        a_aplicar = min(disponible, restante)
        aplicaciones.append(allocate_supplier_payment(pago, invoice, a_aplicar, user))
        restante -= a_aplicar
    if not aplicaciones:
        raise InvalidPurchaseOperation("Este proveedor no tiene anticipos disponibles para aplicar.")
    return aplicaciones


# ------------------------------------------------------------------
# Devolución a proveedor (inmutable, mismo principio que
# apps.sales.services.create_return)
# ------------------------------------------------------------------


def get_supplier_returns(purchase_order):
    return (
        SupplierReturn.all_objects.filter(tenant=purchase_order.tenant, purchase_order=purchase_order)
        .select_related("user")
        .order_by("-created_at")
    )


def get_return_items(return_document):
    return (
        SupplierReturnItem.all_objects.filter(tenant=return_document.tenant, return_document=return_document)
        .select_related("receipt_item", "inventory_unit")
        .order_by("id")
    )


@transaction.atomic
def create_supplier_return(purchase_order, *, items, user, reason=""):
    """`items`: lista de dicts, uno por línea a devolver:
    - QUANTITY: `{"receipt_item":, "quantity_returned": Decimal}` —
      reutiliza `register_stock_out`.
    - SERIALIZED: `{"receipt_item":}` — la unidad completa vinculada a
      esa línea de recepción transiciona `EN_STOCK → DEVUELTO_PROVEEDOR`
      (`transition_unit_status`, máquina de estados de FASE 8)."""
    locked_po = PurchaseOrder.all_objects.select_for_update().get(pk=purchase_order.pk, tenant=purchase_order.tenant)
    if not items:
        raise InvalidPurchaseOperation("Debes indicar al menos una línea a devolver.")

    numero = generate_document_number(locked_po.tenant, DocumentSequence.DocumentType.SUPPLIER_RETURN)
    devolucion = SupplierReturn.all_objects.create(
        tenant=locked_po.tenant, purchase_order=locked_po, number=numero, reason=reason, user=user,
    )

    for entrada in items:
        receipt_item = entrada["receipt_item"]
        if receipt_item.tenant_id != locked_po.tenant_id or receipt_item.purchase_order_item.purchase_order_id != locked_po.pk:
            raise InvalidPurchaseOperation(
                "Una línea de devolución debe pertenecer a una recepción de esta orden de compra."
            )

        if receipt_item.inventory_unit_id:
            unit = InventoryUnit.all_objects.select_for_update().get(
                pk=receipt_item.inventory_unit_id, tenant=locked_po.tenant
            )
            try:
                transition_unit_status(
                    unit=unit, new_status=InventoryUnit.Status.DEVUELTO_PROVEEDOR, user=user,
                    notes=f"Devuelta a proveedor — {devolucion.number}",
                )
            except InvalidInventoryOperation as error:
                raise InvalidPurchaseOperation(str(error)) from error
            SupplierReturnItem.all_objects.create(
                tenant=locked_po.tenant, return_document=devolucion, receipt_item=receipt_item,
                inventory_unit=unit, condition_notes=entrada.get("condition_notes", ""),
            )
        else:
            cantidad = entrada.get("quantity_returned")
            if cantidad is None or cantidad <= 0:
                raise InvalidPurchaseOperation("La cantidad devuelta debe ser mayor que cero.")
            if cantidad > (receipt_item.quantity_received or Decimal("0")):
                raise InvalidPurchaseOperation("No se puede devolver más de lo que se recibió en esa línea.")
            try:
                register_stock_out(
                    product=receipt_item.purchase_order_item.product, quantity=cantidad, user=user,
                    notes=f"Devolución a proveedor {numero}",
                )
            except InvalidInventoryOperation as error:
                raise InvalidPurchaseOperation(str(error)) from error
            SupplierReturnItem.all_objects.create(
                tenant=locked_po.tenant, return_document=devolucion, receipt_item=receipt_item,
                quantity_returned=cantidad, condition_notes=entrada.get("condition_notes", ""),
            )

    log_activity(
        locked_po.tenant, entity_type="supplier_return", entity_id=devolucion.pk, entity_label=devolucion.number,
        action=PurchasesActivityLog.Action.SUPPLIER_RETURN_CREATED, user=user, details=f"OC {locked_po.number}",
    )

    from apps.accounting.services import try_record_supplier_return

    try_record_supplier_return(devolucion, user)
    return devolucion


# ------------------------------------------------------------------
# Documentos adjuntos (reutiliza FASE 9 — no se crea un segundo sistema
# de archivos)
# ------------------------------------------------------------------


def register_attachment(*, tenant, document_type, document_id, archivo, category, user, notes=""):
    extension, content_type = validar_archivo_adjunto(archivo)
    adjunto = PurchaseDocumentAttachment.all_objects.create(
        tenant=tenant, document_type=document_type, document_id=document_id, category=category, file=archivo,
        original_filename=nombre_original_seguro(archivo.name), content_type=content_type, size_bytes=archivo.size,
        uploaded_by=user, notes=notes,
    )
    log_activity(
        tenant, entity_type=document_type, entity_id=document_id,
        action=PurchasesActivityLog.Action.ATTACHMENT_UPLOADED, user=user, details=adjunto.original_filename,
    )
    return adjunto


def get_attachments(*, tenant, document_type, document_id):
    return PurchaseDocumentAttachment.all_objects.filter(
        tenant=tenant, document_type=document_type, document_id=document_id
    ).order_by("-uploaded_at")


def delete_attachment(adjunto, user):
    tenant, document_type, document_id, nombre = (
        adjunto.tenant, adjunto.document_type, adjunto.document_id, adjunto.original_filename
    )
    adjunto.delete()
    log_activity(
        tenant, entity_type=document_type, entity_id=document_id,
        action=PurchasesActivityLog.Action.ATTACHMENT_DELETED, user=user, details=nombre,
    )


# ------------------------------------------------------------------
# Preparación para Dashboard (FASE 7) y Reportes (FASE 14) — agregaciones
# de solo lectura reutilizables; ningún dashboard/reporte se construye
# en esta fase.
# ------------------------------------------------------------------


def get_open_purchase_orders_count(tenant):
    return PurchaseOrder.all_objects.filter(
        tenant=tenant, status__in=[PurchaseOrder.Status.SENT, PurchaseOrder.Status.PARTIALLY_RECEIVED]
    ).count()


def get_period_purchases_total(tenant, *, start_date, end_date):
    return PurchaseOrder.all_objects.filter(
        tenant=tenant,
        status__in=[PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.PARTIALLY_RECEIVED, PurchaseOrder.Status.CLOSED],
        issue_date__gte=start_date, issue_date__lte=end_date,
    ).aggregate(total=Sum("total"))["total"] or Decimal("0")


def get_pending_supplier_invoices_total(tenant):
    facturas = SupplierInvoice.all_objects.filter(tenant=tenant, status=SupplierInvoice.Status.CONFIRMED)
    saldos = get_invoice_balance_due_bulk(list(facturas))
    return sum(saldos.values(), Decimal("0"))


def get_total_supplier_advances(tenant):
    total = Decimal("0")
    for proveedor in Supplier.all_objects.filter(tenant=tenant, is_active=True):
        total += get_supplier_advance_balance(proveedor)
    return total
