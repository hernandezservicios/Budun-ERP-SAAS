"""
Capa de orquestación del POS (FASE 11). Consume literalmente los
motores ya construidos — `apps.inventory.services` (búsqueda/stock),
`apps.sales.services` (cotizaciones/proformas/ventas/pagos/reservas/
devoluciones/notas de crédito), `apps.customers.services` (clientes) y
`apps.approvals.services` (autorizaciones) — sin reimplementar NINGUNA
de sus reglas de negocio. Lo único nuevo aquí es la caja
(`CashRegister`/`CashSession`/`CashMovement`, ver `docs/cash-registers.md`)
y el pegamento que decide CUÁNDO llamar a cada motor.

Mismos principios que el resto del proyecto:
- `all_objects` (nunca `objects`/TenantManager) en toda consulta de
  este módulo, con `tenant` filtrado explícitamente.
- `transaction.atomic()` + `select_for_update()` en toda operación que
  lea-y-luego-escriba bajo posible concurrencia.
- Errores de negocio como `InvalidPosOperation` (nunca una excepción
  genérica ni un `IntegrityError` de PostgreSQL sin traducir).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.approvals import services as approvals_services
from apps.approvals.models import ApprovalRequest
from apps.customers import services as customers_services
from apps.inventory import services as inv_services
from apps.sales import services as sales_services
from apps.sales.models import Payment, PaymentMethod, Sale
from apps.tenants.models import Membership

from .models import CashMovement, CashRegister, CashSession


class InvalidPosOperation(ValidationError):
    """Operación de POS/caja inválida: sin caja abierta, sesión ya
    cerrada, descuento sin autorización, etc."""


class DiscountRequiresApproval(InvalidPosOperation):
    """Se lanza cuando un descuento excede el límite del usuario y no
    se aportó una `ApprovalRequest` aprobada que lo cubra. La vista debe
    capturarla y ofrecer "Solicitar autorización"."""

    def __init__(self, *, limit_percent, limit_amount, requested_percent, requested_amount):
        self.limit_percent = limit_percent
        self.limit_amount = limit_amount
        self.requested_percent = requested_percent
        self.requested_amount = requested_amount
        super().__init__(
            f"Este descuento (({requested_percent}%, {requested_amount})) supera el límite autorizado "
            f"(({limit_percent}%, {limit_amount})) — se requiere autorización."
        )


class CreditOverageRequiresApproval(InvalidPosOperation):
    def __init__(self, *, limit, overage_amount):
        self.limit = limit
        self.overage_amount = overage_amount
        super().__init__(
            f"Esta venta a crédito excede el límite del cliente por {overage_amount} "
            f"(autorizable sin aprobación: {limit}) — se requiere autorización."
        )


class InsufficientPaymentError(InvalidPosOperation):
    """Se lanza cuando `amount_received` (la suma de los pagos indicados)
    no alcanza `amount_due` (el total de la venta) y no hay crédito
    habilitado que cubra la diferencia (ver `docs/currency.md` sección 7
    para el vocabulario oficial). Nunca se confirma la venta, nunca se
    mueve inventario, nunca se toca la caja cuando se lanza esta
    excepción — `checkout_sale` valida esto ANTES de llamar a
    `confirm_sale`/`record_payment_for_sale`."""

    def __init__(self, *, amount_due, amount_received):
        self.amount_due = amount_due
        self.amount_received = amount_received
        self.missing_amount = amount_due - amount_received
        super().__init__(
            f"El monto recibido ({amount_received}) es insuficiente para cubrir el total de la venta "
            f"({amount_due}) — faltan {self.missing_amount}. Agrega otro método de pago o aplica crédito autorizado."
        )


# ------------------------------------------------------------------
# Cajas
# ------------------------------------------------------------------


def get_registers(tenant):
    return CashRegister.all_objects.filter(tenant=tenant).order_by("code")


def is_user_authorized_for_register(register, user):
    """El propietario del tenant siempre puede operar cualquier caja
    (misma regla documentada que `apps.approvals`); cualquier otro
    usuario necesita estar explícitamente en `authorized_users`."""
    membership = Membership.objects.filter(tenant=register.tenant, user=user, is_active=True).first()
    if membership and membership.role == Membership.Role.OWNER:
        return True
    return register.authorized_users.filter(pk=user.pk).exists()


def get_active_session_for_user(tenant, user):
    return CashSession.all_objects.filter(tenant=tenant, user=user, status=CashSession.Status.OPEN).first()


def get_active_session_for_register(register):
    return CashSession.all_objects.filter(
        tenant=register.tenant, cash_register=register, status=CashSession.Status.OPEN
    ).first()


@transaction.atomic
def open_cash_session(tenant, *, cash_register, user, opening_amount, notes=""):
    """Abre una sesión de caja. Bloquea la fila de la caja antes de
    validar para que dos aperturas simultáneas de la MISMA CAJA nunca
    creen dos sesiones activas. La exclusividad por USUARIO (un usuario
    no puede tener dos sesiones abiertas, ni siquiera en cajas o
    tenants distintos) no tiene una única fila que bloquear con
    `select_for_update()` — la garantiza en última instancia la
    `UniqueConstraint` parcial del modelo a nivel de base de datos;
    aquí se traduce el `IntegrityError` resultante de esa carrera a
    `InvalidPosOperation`, nunca se deja escapar como un error de
    PostgreSQL sin traducir."""
    locked_register = CashRegister.all_objects.select_for_update().get(pk=cash_register.pk, tenant=tenant)
    if locked_register.status != CashRegister.Status.ACTIVE:
        raise InvalidPosOperation(f"La caja «{locked_register.code}» no está activa.")
    if not is_user_authorized_for_register(locked_register, user):
        raise InvalidPosOperation(f"No tienes permiso para operar la caja «{locked_register.code}».")
    if opening_amount is None or opening_amount < 0:
        raise InvalidPosOperation("El fondo inicial no puede ser negativo.")

    if get_active_session_for_register(locked_register):
        raise InvalidPosOperation(f"La caja «{locked_register.code}» ya tiene una sesión abierta.")
    if get_active_session_for_user(tenant, user):
        raise InvalidPosOperation("Ya tienes una sesión de caja abierta — ciérrala antes de abrir otra.")

    try:
        with transaction.atomic():
            sesion = CashSession.all_objects.create(
                tenant=tenant, cash_register=locked_register, user=user, opening_amount=opening_amount, notes=notes,
            )
    except IntegrityError as error:
        raise InvalidPosOperation("Ya tienes una sesión de caja abierta — ciérrala antes de abrir otra.") from error

    CashMovement.all_objects.create(
        tenant=tenant, cash_session=sesion, movement_type=CashMovement.MovementType.OPENING,
        amount=opening_amount, user=user, reason="Apertura de caja",
    )
    return sesion


_TIPOS_POSITIVOS = {
    CashMovement.MovementType.OPENING,
    CashMovement.MovementType.SALE_CASH,
    CashMovement.MovementType.CASH_IN,
    CashMovement.MovementType.CUSTOMER_ADVANCE_CASH,
}
_TIPOS_NEGATIVOS = {
    CashMovement.MovementType.CASH_OUT,
    CashMovement.MovementType.CASH_REFUND,
    CashMovement.MovementType.WITHDRAWAL,
    # FASE 12 (Compras): dinero que sale de la caja hacia un proveedor.
    CashMovement.MovementType.SUPPLIER_PAYMENT_CASH,
    CashMovement.MovementType.SUPPLIER_ADVANCE_CASH,
}
# ADJUSTMENT puede sumar o restar según el caso concreto — se registra
# con el signo que indique quien autoriza el ajuste (ver
# `record_cash_movement(..., signo=...)`), nunca asumido.


def get_expected_cash(session):
    """Efectivo esperado = agregación de `CashMovement` de la sesión,
    nunca un campo editado a mano. `ADJUSTMENT` se resuelve por su
    `reason`/metadata en la fila (ver `record_cash_movement`): aquí se
    suman/restan según el campo auxiliar `_signo_ajuste` calculado al
    registrar el movimiento (ver `record_cash_movement`)."""
    total = Decimal("0")
    movimientos = CashMovement.all_objects.filter(tenant=session.tenant, cash_session=session)
    for movimiento in movimientos:
        if movimiento.movement_type in _TIPOS_POSITIVOS:
            total += movimiento.amount
        elif movimiento.movement_type in _TIPOS_NEGATIVOS:
            total -= movimiento.amount
        elif movimiento.movement_type == CashMovement.MovementType.ADJUSTMENT:
            # El signo de un ajuste se codifica en `reason` con el
            # prefijo "+"/"-" (ver `record_cash_movement`) — nunca se
            # asume un signo por defecto para un ajuste.
            if movimiento.reason.startswith("-"):
                total -= movimiento.amount
            else:
                total += movimiento.amount
    return total


@transaction.atomic
def record_cash_movement(cash_session, *, movement_type, amount, user, reason="", reference_type="", reference_id=None, ajuste_resta=False):
    """Registra un movimiento de efectivo dentro de una sesión abierta.
    `ajuste_resta` solo aplica a `ADJUSTMENT` (indica si el ajuste debe
    restar del efectivo esperado en vez de sumar) y se codifica como
    prefijo en `reason` para que `get_expected_cash` lo pueda derivar
    siempre desde la fila, nunca desde un campo aparte."""
    locked_session = CashSession.all_objects.select_for_update().get(pk=cash_session.pk, tenant=cash_session.tenant)
    if locked_session.status != CashSession.Status.OPEN:
        raise InvalidPosOperation("No se pueden registrar movimientos en una sesión de caja cerrada.")
    if amount is None or amount <= 0:
        raise InvalidPosOperation("El monto del movimiento de caja debe ser mayor que cero.")

    motivo = reason
    if movement_type == CashMovement.MovementType.ADJUSTMENT and ajuste_resta:
        motivo = f"-{reason}" if reason else "-"

    return CashMovement.all_objects.create(
        tenant=locked_session.tenant, cash_session=locked_session, movement_type=movement_type, amount=amount,
        user=user, reason=motivo, reference_type=reference_type, reference_id=reference_id,
    )


@transaction.atomic
def close_cash_session(session, user, *, counted_cash, closing_notes=""):
    """Cierra la sesión — el resultado histórico nunca se modifica
    después: cerrar una sesión ya cerrada es un error explícito, no un
    no-op ni una edición silenciosa."""
    locked = CashSession.all_objects.select_for_update().get(pk=session.pk, tenant=session.tenant)
    if locked.status != CashSession.Status.OPEN:
        raise InvalidPosOperation("Esta sesión de caja ya fue cerrada.")
    if counted_cash is None or counted_cash < 0:
        raise InvalidPosOperation("El efectivo contado no puede ser negativo.")

    esperado = get_expected_cash(locked)
    locked.expected_cash = esperado
    locked.counted_cash = counted_cash
    locked.difference = counted_cash - esperado
    locked.status = CashSession.Status.CLOSED
    locked.closed_at = timezone.now()
    locked.closing_notes = closing_notes
    locked.save(update_fields=["expected_cash", "counted_cash", "difference", "status", "closed_at", "closing_notes"])

    # FASE 14 (Contabilidad General, ampliación de cierre): reconoce el
    # sobrante/faltante descubierto al contar como un asiento contable
    # nuevo — nunca duplica el efectivo esperado (ya contabilizado por
    # los eventos de venta/pago/gasto/nómina). Deliberadamente
    # resiliente, import diferido (mismo patrón que apps.sales/apps.expenses/
    # apps.payroll/apps.purchases).
    from apps.accounting.services import try_record_cash_session_closing

    try_record_cash_session_closing(locked, user)
    return locked


def ensure_open_session_for_checkout(tenant, user):
    """Regla obligatoria de FASE 11: ninguna venta operativa de
    mostrador se confirma sin una `CashSession` abierta y válida para
    quien está cobrando. Lanza `InvalidPosOperation` con un mensaje
    claro si no existe — nunca deja una operación parcial."""
    sesion = get_active_session_for_user(tenant, user)
    if sesion is None:
        raise InvalidPosOperation("No tienes una sesión de caja abierta. Abre caja antes de cobrar.")
    return sesion


# ------------------------------------------------------------------
# Autorización de descuentos (consume apps.approvals, nunca duplica
# su lógica — ver docs/approvals.md)
# ------------------------------------------------------------------


def _effective_discount_dimensions(base_amount, *, percent=None, amount=None):
    """Dado lo que el cajero escribió (% O monto fijo — nunca ambos a
    la vez, mismo criterio que `apps.sales.services._recalculate_item`),
    calcula las DOS dimensiones (% y monto) para poder comparar ambas
    contra sus límites independientes (ver docs/approvals.md sección
    4: exceder cualquiera de los dos exige autorización)."""
    if percent and percent > 0:
        monto_efectivo = (base_amount * percent / Decimal("100")).quantize(Decimal("0.01"))
        return percent, monto_efectivo
    if amount and amount > 0:
        porcentaje_efectivo = (amount / base_amount * Decimal("100")).quantize(Decimal("0.01")) if base_amount else Decimal("0")
        return porcentaje_efectivo, amount
    return Decimal("0"), Decimal("0")


def _find_usable_discount_approval(tenant, sale, user):
    return approvals_services.get_usable_approved_request(
        tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, document_type="sale", document_id=sale.pk,
    )


@transaction.atomic
def add_item_to_cart(sale, *, product, quantity, user, tenant, discount_percent=None, discount_amount=None, inventory_unit=None, use_approval=None):
    """Agrega una línea al carrito (la `Sale` en `DRAFT`, ver
    `docs/phases/PHASE-11-pos.md`) reutilizando literalmente
    `apps.sales.services.add_sale_item` — nunca reimplementa el
    snapshot ni el cálculo de totales. Si la línea lleva descuento y
    excede el límite del usuario, exige una `ApprovalRequest` aprobada
    y no consumida para esta venta (`use_approval`), o lanza
    `DiscountRequiresApproval`."""
    percent_solicitado, amount_solicitado = _effective_discount_dimensions(
        product.sale_price * quantity, percent=discount_percent, amount=discount_amount
    )
    if percent_solicitado > 0 or amount_solicitado > 0:
        autorizado, limite_percent, limite_amount = approvals_services.check_discount_authorization(
            tenant, user, percent=percent_solicitado, amount=amount_solicitado
        )
        if not autorizado:
            aprobacion = use_approval or _find_usable_discount_approval(tenant, sale, user)
            cubierto = (
                aprobacion is not None
                and aprobacion.status == ApprovalRequest.Status.APPROVED
                and aprobacion.consumed_at is None
                and (aprobacion.approved_value or Decimal("0")) >= amount_solicitado
            )
            if not cubierto:
                raise DiscountRequiresApproval(
                    limit_percent=limite_percent, limit_amount=limite_amount,
                    requested_percent=percent_solicitado, requested_amount=amount_solicitado,
                )
            approvals_services.mark_consumed(aprobacion, user)

    item = sales_services.add_sale_item(
        sale, product=product, quantity=quantity, user=user,
        discount_percent=discount_percent, discount_amount=discount_amount, inventory_unit=inventory_unit,
    )
    return item


@transaction.atomic
def set_cart_global_discount(sale, *, user, tenant, percent=None, amount=None, use_approval=None):
    """Igual que `add_item_to_cart` pero para el descuento GLOBAL del
    carrito."""
    percent_solicitado, amount_solicitado = _effective_discount_dimensions(
        sale.subtotal or Decimal("0"), percent=percent, amount=amount
    )
    if percent_solicitado > 0 or amount_solicitado > 0:
        autorizado, limite_percent, limite_amount = approvals_services.check_discount_authorization(
            tenant, user, percent=percent_solicitado, amount=amount_solicitado
        )
        if not autorizado:
            aprobacion = use_approval or _find_usable_discount_approval(tenant, sale, user)
            cubierto = (
                aprobacion is not None
                and aprobacion.status == ApprovalRequest.Status.APPROVED
                and aprobacion.consumed_at is None
                and (aprobacion.approved_value or Decimal("0")) >= amount_solicitado
            )
            if not cubierto:
                raise DiscountRequiresApproval(
                    limit_percent=limite_percent, limit_amount=limite_amount,
                    requested_percent=percent_solicitado, requested_amount=amount_solicitado,
                )
            approvals_services.mark_consumed(aprobacion, user)

    return sales_services.set_sale_global_discount(sale, percent=percent, amount=amount)


def request_discount_approval(tenant, sale, user, *, percent_solicitado, amount_solicitado, limite_percent, limite_amount):
    """Atajo que arma la solicitud de autorización de descuento con los
    datos ya calculados por `DiscountRequiresApproval` — la vista del
    POS captura esa excepción y llama a esta función."""
    return approvals_services.request_approval(
        tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=user,
        requested_value=amount_solicitado, allowed_limit=limite_amount,
        reason=f"Descuento {percent_solicitado}% / {amount_solicitado} en venta {sale.number}",
        document_type="sale", document_id=sale.pk,
        metadata={"discount_percent": str(percent_solicitado), "limit_percent": str(limite_percent)},
    )


# ------------------------------------------------------------------
# Crédito excedido
# ------------------------------------------------------------------


def check_credit_sale_authorization(tenant, user, *, customer, sale_total):
    """¿Esta venta a crédito para `customer` excede su límite? Si sí,
    ¿el usuario actual puede autorizarlo por sí mismo? Devuelve
    `(requiere_autorizacion: bool, excedente, limite_autorizable)`."""
    if customer is None or not customer.credit_enabled:
        return False, Decimal("0"), None
    pendientes = sales_services.get_customer_pending_sales(customer)
    saldos = sales_services.get_sale_balance_due_bulk(pendientes)
    deuda_actual = sum(saldos.values(), Decimal("0"))
    excedente = (deuda_actual + sale_total) - customer.credit_limit
    if excedente <= 0:
        return False, Decimal("0"), None
    autorizado, limite = approvals_services.check_credit_overage_authorization(tenant, user, overage_amount=excedente)
    return (not autorizado), excedente, limite


def request_credit_overage_approval(tenant, sale, user, *, excedente, limite):
    return approvals_services.request_approval(
        tenant, action_type=ApprovalRequest.ActionType.CREDIT_OVERAGE, requested_by=user,
        requested_value=excedente, allowed_limit=limite,
        reason=f"Venta a crédito {sale.number} excede el límite del cliente por {excedente}",
        document_type="sale", document_id=sale.pk,
    )


# ------------------------------------------------------------------
# Carrito y búsqueda (delegan literalmente en apps.inventory/apps.sales)
# ------------------------------------------------------------------


def search(tenant, query):
    """Delega en `apps.inventory.services.search_catalog` — nunca se
    duplica esa búsqueda aquí (ver docs/phases/PHASE-11-pos.md)."""
    return inv_services.search_catalog(tenant, query)


def start_cart(tenant, *, user, customer=None):
    """El carrito del POS es, en términos de FASE 10, una `Sale` en
    `DRAFT` — nunca una estructura paralela en memoria/sesión."""
    return sales_services.create_sale(tenant, user=user, customer=customer)


def get_cart_items(sale):
    return sales_services.get_sale_items(sale)


def remove_cart_item(item):
    return sales_services.remove_sale_item(item)


def update_cart_item_quantity(item, quantity):
    return sales_services.update_sale_item_quantity(item, quantity)


def set_cart_customer(sale, customer):
    """Cambiar el cliente de un carrito en `DRAFT` — venta de mostrador
    (`customer=None`) sigue siendo válida en cualquier momento."""
    if sale.status != Sale.Status.DRAFT:
        raise InvalidPosOperation(f"La venta «{sale.number}» ya no se puede editar (estado: {sale.get_status_display()}).")
    sale.customer = customer
    sale.save(update_fields=["customer", "updated_at"])
    return sale


# ------------------------------------------------------------------
# Checkout: confirmar + cobrar (uno o varios métodos) + caja
# ------------------------------------------------------------------


@transaction.atomic
def checkout_sale(sale, *, user, tenant, payments, cash_session=None, use_credit_approval=None):
    """Confirma la venta y aplica uno o varios pagos — reutiliza
    literalmente `apps.sales.services.confirm_sale`/
    `record_payment_for_sale`, nunca duplica esa lógica. `payments`:
    lista de `{"method":, "amount":, "reference": ""}`; la suma nunca
    debe exceder `sale.total` (la vista calcula el "cambio" a partir de
    lo recibido en efectivo — ver `docs/pos.md` — nunca se le pasa a
    este servicio un monto que exceda el saldo de la venta).

    Requiere una `CashSession` abierta para el usuario (regla
    obligatoria de FASE 11, `ensure_open_session_for_checkout`) —
    ninguna venta de mostrador se confirma sin ella."""
    sesion = cash_session or ensure_open_session_for_checkout(tenant, user)

    total_a_cobrar = sum((p["amount"] for p in payments), Decimal("0"))
    saldo_restante_estimado = sale.total - total_a_cobrar
    if saldo_restante_estimado > 0:
        # amount_received + pagos válidos < amount_due (ver
        # docs/currency.md sección 7): nunca se confirma la venta salvo
        # que exista una parte de crédito autorizada que cubra la
        # diferencia — se rechaza ANTES de confirmar la venta/mover
        # inventario/tocar la caja, nunca una venta parcialmente
        # confirmada.
        if not (sale.customer and sale.customer.credit_enabled):
            raise InsufficientPaymentError(amount_due=sale.total, amount_received=total_a_cobrar)
        requiere, excedente, limite = check_credit_sale_authorization(
            tenant, user, customer=sale.customer, sale_total=saldo_restante_estimado
        )
        if requiere:
            aprobacion = use_credit_approval or approvals_services.get_usable_approved_request(
                tenant, action_type=ApprovalRequest.ActionType.CREDIT_OVERAGE, document_type="sale", document_id=sale.pk,
            )
            cubierto = (
                aprobacion is not None
                and aprobacion.status == ApprovalRequest.Status.APPROVED
                and aprobacion.consumed_at is None
                and (aprobacion.approved_value or Decimal("0")) >= excedente
            )
            if not cubierto:
                raise CreditOverageRequiresApproval(limit=limite, overage_amount=excedente)
            approvals_services.mark_consumed(aprobacion, user)

    venta_confirmada = sales_services.confirm_sale(sale, user)

    pagos_creados = []
    for pago in payments:
        payment = sales_services.record_payment_for_sale(
            venta_confirmada, method=pago["method"], amount=pago["amount"], user=user,
            reference=pago.get("reference", ""),
            amount_received=pago.get("amount_received"), change_amount=pago.get("change_amount"),
        )
        pagos_creados.append(payment)
        if pago["method"] == PaymentMethod.CASH:
            record_cash_movement(
                sesion, movement_type=CashMovement.MovementType.SALE_CASH, amount=pago["amount"], user=user,
                reason=f"Venta {venta_confirmada.number}", reference_type="payment", reference_id=payment.pk,
            )

    # `record_payment_for_sale` actualiza `payment_status` con un
    # `.update()` directo en base de datos (recompute_payment_status),
    # que nunca refresca el objeto Python en memoria — se refresca aquí
    # explícitamente para que quien llame a `checkout_sale` reciba
    # siempre el estado real, sin tener que conocer ese detalle interno.
    venta_confirmada.refresh_from_db()
    return venta_confirmada, pagos_creados


# ------------------------------------------------------------------
# Cobro de cuentas por cobrar (facturas pendientes, uno o varios pagos
# a la vez — ver docs/accounts-receivable.md)
# ------------------------------------------------------------------


def get_pending_sales_for_customer(customer):
    return sales_services.get_customer_pending_sales(customer)


def get_customer_credit_summary(customer):
    """Para la pantalla de cobros: saldo a favor total y facturas
    pendientes — agregaciones de solo lectura, nunca un balance
    guardado (ver docs/accounts-receivable.md)."""
    return {
        "balance": sales_services.get_customer_credit_balance(customer),
        "pending_sales": get_pending_sales_for_customer(customer),
    }


@transaction.atomic
def collect_customer_payment(tenant, *, customer, method, amount, user, allocations, cash_session=None, reference=""):
    """Cobra un pago de un cliente y lo distribuye entre una o varias
    facturas pendientes (`allocations`: lista de `{"sale":, "amount":}`)
    — reutiliza literalmente `create_payment`/`apply_payment_to_sales`,
    que ya garantizan que nunca se sobre-aplica ni se cruzan clientes/
    tenants."""
    sesion = cash_session
    if method == PaymentMethod.CASH and sesion is None:
        sesion = ensure_open_session_for_checkout(tenant, user)
    payment = sales_services.create_payment(
        tenant, customer=customer, method=method, amount=amount, user=user, reference=reference
    )
    asignaciones = sales_services.apply_payment_to_sales(payment, allocations, user)
    if method == PaymentMethod.CASH:
        record_cash_movement(
            sesion, movement_type=CashMovement.MovementType.SALE_CASH, amount=amount, user=user,
            reason=f"Cobro de facturas pendientes — {customer.display_name}",
            reference_type="payment", reference_id=payment.pk,
        )
    return payment, asignaciones


@transaction.atomic
def apply_customer_credit_to_sale(customer, sale, amount, user):
    """Aplica saldo a favor del cliente a una factura pendiente:
    primero agota pagos sin aplicar (más antiguos primero), luego notas
    de crédito, hasta cubrir `amount` — preserva el saldo restante
    (nunca todo o nada). Nunca crea un balance manual: se apoya
    enteramente en `allocate_payment`/`apply_credit_note`, que ya
    validan sobre-aplicación/tenant/cliente."""
    if amount is None or amount <= 0:
        raise InvalidPosOperation("El monto a aplicar debe ser mayor que cero.")
    restante = amount
    aplicaciones = []

    pagos = Payment.all_objects.filter(
        tenant=customer.tenant, customer=customer, status=Payment.Status.CONFIRMED
    ).order_by("created_at")
    for pago in pagos:
        if restante <= 0:
            break
        disponible = sales_services.get_unallocated_payment_amount(pago)
        if disponible <= 0:
            continue
        monto = min(disponible, restante)
        aplicaciones.append(sales_services.allocate_payment(pago, sale, monto, user))
        restante -= monto

    if restante > 0:
        from apps.sales.models import CreditNote

        notas = CreditNote.all_objects.filter(
            tenant=customer.tenant, customer=customer,
            status__in=[CreditNote.Status.ISSUED, CreditNote.Status.PARTIALLY_APPLIED],
        ).order_by("created_at")
        for nota in notas:
            if restante <= 0:
                break
            disponible = sales_services.get_credit_note_remaining(nota)
            if disponible <= 0:
                continue
            monto = min(disponible, restante)
            aplicaciones.append(sales_services.apply_credit_note(nota, sale, monto, user))
            restante -= monto

    if restante > 0:
        raise InvalidPosOperation(
            f"El cliente no tiene suficiente saldo a favor ({amount - restante} disponible de {amount} solicitado)."
        )
    return aplicaciones


# ------------------------------------------------------------------
# Anticipos (Payment sin aplicar — ver docs/accounts-receivable.md)
# ------------------------------------------------------------------


@transaction.atomic
def register_customer_advance(tenant, *, customer, method, amount, user, cash_session=None, reference="", notes=""):
    """Un anticipo NUNCA es una venta: dinero recibido de un cliente
    antes de una factura, sin aplicar todavía a nada — un `Payment` sin
    asignaciones (`create_payment`, ya construido en la ampliación de
    FASE 10)."""
    if customer is None:
        raise InvalidPosOperation("Un anticipo siempre debe asociarse a un cliente.")
    sesion = cash_session
    if method == PaymentMethod.CASH and sesion is None:
        sesion = ensure_open_session_for_checkout(tenant, user)
    payment = sales_services.create_payment(
        tenant, customer=customer, method=method, amount=amount, user=user, reference=reference, notes=notes
    )
    if method == PaymentMethod.CASH:
        record_cash_movement(
            sesion, movement_type=CashMovement.MovementType.CUSTOMER_ADVANCE_CASH, amount=amount, user=user,
            reason=f"Anticipo de {customer.display_name}", reference_type="payment", reference_id=payment.pk,
        )
    return payment


# ------------------------------------------------------------------
# Notas de crédito desde el POS (delegan en apps.sales.services)
# ------------------------------------------------------------------


def issue_customer_credit_note(tenant, *, customer, amount, user, reason="", source_return=None):
    nota = sales_services.create_credit_note(
        tenant, customer=customer, amount=amount, user=user, reason=reason, source_return=source_return,
    )
    return sales_services.issue_credit_note(nota, user)


def apply_credit_note_to_sale(credit_note, sale, amount, user):
    return sales_services.apply_credit_note(credit_note, sale, amount, user)


# ------------------------------------------------------------------
# Refunds (delegan en apps.sales.services; separan mercancía vs. dinero
# — ver docs/returns.md)
# ------------------------------------------------------------------


@transaction.atomic
def refund_payment_cash(payment, amount, user, *, reason="", return_document=None, cash_session=None):
    """Reembolso en EFECTIVO: reutiliza `record_refund` y genera el
    `CashMovement CASH_REFUND` correspondiente — requiere sesión de
    caja abierta (requisito explícito de FASE 11)."""
    if payment.method != PaymentMethod.CASH:
        raise InvalidPosOperation("Solo se genera un movimiento de caja para reembolsos de pagos en efectivo.")
    sesion = cash_session or ensure_open_session_for_checkout(payment.tenant, user)
    refund = sales_services.record_refund(payment, amount=amount, user=user, reason=reason, return_document=return_document)
    record_cash_movement(
        sesion, movement_type=CashMovement.MovementType.CASH_REFUND, amount=amount, user=user,
        reason=reason or f"Reembolso pago #{payment.pk}", reference_type="refund", reference_id=refund.pk,
    )
    return refund


def refund_payment_to_credit(payment, amount, user, *, reason=""):
    """Reembolso a CRÉDITO: nunca sale efectivo de la caja — reutiliza
    literalmente `apps.sales.services.convert_refund_to_credit`."""
    return sales_services.convert_refund_to_credit(payment, amount, user, reason=reason)
