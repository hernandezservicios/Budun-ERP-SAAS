"""
Única vía sancionada para consultar límites de autorización, crear
solicitudes y resolverlas (ver `docs/approvals.md`). Ningún otro módulo
debe reimplementar esta lógica ni escribir estos modelos directamente.

Mismos principios que `apps.inventory.services`/`apps.sales.services`:
- `all_objects` (nunca `objects`/TenantManager) en toda consulta,
  filtrando siempre `tenant` explícitamente — este servicio debe
  funcionar igual llamado desde una vista, un test o una tarea en
  segundo plano.
- `transaction.atomic()` + `select_for_update()` en toda operación que
  lea-y-luego-escriba (resolver una solicitud).

## Regla de OWNER (documentada, no un bypass de frontend)
El propietario del tenant (`Membership.Role.OWNER`) siempre está
autorizado — para dar cualquier descuento, para exceder el crédito de
un cliente, y para resolver cualquier solicitud pendiente — sin
necesidad de una `ApprovalPolicy` configurada. Es una regla de negocio
explícita y documentada (el dueño ya tiene autoridad administrativa
completa sobre su propio tenant en el resto del sistema desde FASE 4),
aplicada aquí en el servidor, nunca delegada al frontend. Cualquier
otro rol/usuario sin política configurada se resuelve como límite 0
(requiere autorización para cualquier excepción) — el default seguro.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.tenants.models import Membership

from .models import ApprovalPolicy, ApprovalRequest


class InvalidApprovalOperation(ValidationError):
    """Se lanza cuando una operación de autorización no es válida:
    resolver una solicitud ya resuelta por otro estado, o un usuario
    sin permiso intentando resolver una solicitud."""


def _get_membership(tenant, user):
    if user is None or getattr(user, "is_authenticated", True) is False:
        return None
    return Membership.objects.filter(tenant=tenant, user=user, is_active=True).first()


def is_owner(tenant, user):
    membership = _get_membership(tenant, user)
    return bool(membership and membership.role == Membership.Role.OWNER)


def get_effective_policy(tenant, user):
    """Resuelve la política efectiva: usuario → rol → tenant → `None`
    (ninguna política configurada). Nunca usa `objects`/TenantManager:
    debe dar el mismo resultado llamado desde una vista o un test."""
    politica_usuario = ApprovalPolicy.all_objects.filter(
        tenant=tenant, scope=ApprovalPolicy.Scope.USER, user=user
    ).first()
    if politica_usuario:
        return politica_usuario

    membership = _get_membership(tenant, user)
    if membership:
        politica_rol = ApprovalPolicy.all_objects.filter(
            tenant=tenant, scope=ApprovalPolicy.Scope.ROLE, role=membership.role
        ).first()
        if politica_rol:
            return politica_rol

    return ApprovalPolicy.all_objects.filter(tenant=tenant, scope=ApprovalPolicy.Scope.TENANT).first()


def can_user_approve(tenant, user):
    """Quién puede RESOLVER (aprobar/rechazar) una solicitud pendiente
    — distinto de quién necesita solicitar. El propietario siempre
    puede; cualquier otro usuario necesita `can_approve=True` en su
    política efectiva."""
    if is_owner(tenant, user):
        return True
    politica = get_effective_policy(tenant, user)
    return bool(politica and politica.can_approve)


def check_discount_authorization(tenant, user, *, percent=None, amount=None):
    """¿Puede este usuario aplicar este descuento sin autorización
    adicional? Requiere autorización si excede el % configurado O el
    monto configurado — basta que uno de los dos se exceda (nunca los
    dos a la vez de forma independiente). Devuelve
    `(autorizado: bool, limite_percent, limite_amount)`."""
    if is_owner(tenant, user):
        return True, None, None
    politica = get_effective_policy(tenant, user)
    limite_percent = politica.max_discount_percent if politica else Decimal("0")
    limite_amount = politica.max_discount_amount if politica else Decimal("0")
    excede_percent = percent is not None and percent > limite_percent
    excede_amount = amount is not None and amount > limite_amount
    autorizado = not (excede_percent or excede_amount)
    return autorizado, limite_percent, limite_amount


def check_credit_overage_authorization(tenant, user, *, overage_amount):
    """¿Puede este usuario autorizar por sí mismo que una venta a
    crédito exceda el límite del cliente en `overage_amount`? Devuelve
    `(autorizado: bool, limite)`."""
    if is_owner(tenant, user):
        return True, None
    politica = get_effective_policy(tenant, user)
    limite = politica.max_credit_overage if politica else Decimal("0")
    return overage_amount <= limite, limite


def check_purchase_authorization(tenant, user, *, amount):
    """FASE 12 (Compras): ¿puede este usuario enviar/confirmar una orden
    de compra por `amount` sin autorización adicional? Mismo patrón que
    `check_credit_overage_authorization` — jerarquía usuario → rol →
    tenant → negar, propietario siempre autorizado. Devuelve
    `(autorizado: bool, limite)`."""
    if is_owner(tenant, user):
        return True, None
    politica = get_effective_policy(tenant, user)
    limite = politica.max_purchase_order_amount if politica else Decimal("0")
    return amount <= limite, limite


def check_expense_authorization(tenant, user, *, amount):
    """FASE 13 (Gastos): ¿puede este usuario aprobar un gasto por
    `amount` sin autorización adicional? Mismo patrón que
    `check_purchase_authorization`. Devuelve `(autorizado: bool, limite)`."""
    if is_owner(tenant, user):
        return True, None
    politica = get_effective_policy(tenant, user)
    limite = politica.max_expense_amount if politica else Decimal("0")
    return amount <= limite, limite


def check_over_receiving_authorization(tenant, user, *, excess_percent):
    """FASE 12 (Compras): ¿puede este usuario recibir por encima de la
    cantidad pendiente de una línea de orden de compra, en el porcentaje
    `excess_percent`, sin autorización adicional? Mismo patrón que
    `check_discount_authorization` (una sola dimensión). Devuelve
    `(autorizado: bool, limite_percent)`."""
    if is_owner(tenant, user):
        return True, None
    politica = get_effective_policy(tenant, user)
    limite = politica.max_over_receiving_percent if politica else Decimal("0")
    return excess_percent <= limite, limite


@transaction.atomic
def request_approval(
    tenant, *, action_type, requested_by, requested_value=None, allowed_limit=None,
    reason="", document_type="", document_id=None, metadata=None,
):
    """Crea una solicitud `PENDING`. No decide nada por sí sola — la
    decisión de bloquear la operación hasta que se resuelva pertenece
    al llamador (p. ej. `apps.pos.services`)."""
    solicitud = ApprovalRequest.all_objects.create(
        tenant=tenant, action_type=action_type, requested_by=requested_by,
        requested_value=requested_value, allowed_limit=allowed_limit, reason=reason,
        document_type=document_type, document_id=document_id, metadata=metadata or {},
    )
    return solicitud


@transaction.atomic
def resolve_approval(approval_request, *, approved, user, approved_value=None, decision_reason=""):
    """Aprueba o rechaza una solicitud `PENDING`. Solo un usuario con
    `can_user_approve` puede hacerlo. No es idempotente ante un
    reintento con una decisión distinta (resolver una solicitud ya
    resuelta siempre es un error, nunca un no-op silencioso) — el
    historial de la primera decisión nunca se sobreescribe."""
    locked = ApprovalRequest.all_objects.select_for_update().get(
        pk=approval_request.pk, tenant=approval_request.tenant
    )
    if locked.status != ApprovalRequest.Status.PENDING:
        raise InvalidApprovalOperation(
            f"La solicitud #{locked.pk} ya fue resuelta (estado actual: {locked.get_status_display()})."
        )
    if not can_user_approve(locked.tenant, user):
        raise InvalidApprovalOperation("Este usuario no tiene permiso para resolver solicitudes de autorización.")

    locked.status = ApprovalRequest.Status.APPROVED if approved else ApprovalRequest.Status.REJECTED
    locked.approved_by = user
    locked.approved_value = approved_value if approved else None
    locked.decision_reason = decision_reason
    locked.decided_at = timezone.now()
    locked.save(update_fields=["status", "approved_by", "approved_value", "decision_reason", "decided_at"])
    return locked


@transaction.atomic
def cancel_approval(approval_request, user):
    """El propio solicitante (o el propietario) desiste de una
    solicitud antes de que alguien la resuelva. Idempotente: cancelar
    una solicitud ya resuelta de cualquier forma es un no-op."""
    locked = ApprovalRequest.all_objects.select_for_update().get(
        pk=approval_request.pk, tenant=approval_request.tenant
    )
    if locked.status != ApprovalRequest.Status.PENDING:
        return locked
    locked.status = ApprovalRequest.Status.CANCELED
    locked.decided_at = timezone.now()
    locked.save(update_fields=["status", "decided_at"])
    return locked


@transaction.atomic
def mark_consumed(approval_request, user):
    """Marca una solicitud APROBADA como usada, para que la misma
    autorización nunca pueda reaplicarse dos veces (p. ej. a dos líneas
    de descuento distintas). Lanza si no está en condiciones de
    consumirse."""
    locked = ApprovalRequest.all_objects.select_for_update().get(
        pk=approval_request.pk, tenant=approval_request.tenant
    )
    if locked.status != ApprovalRequest.Status.APPROVED:
        raise InvalidApprovalOperation("Solo una solicitud aprobada puede consumirse.")
    if locked.consumed_at is not None:
        raise InvalidApprovalOperation("Esta autorización ya fue utilizada.")
    locked.consumed_at = timezone.now()
    locked.consumed_by = user
    locked.save(update_fields=["consumed_at", "consumed_by"])
    return locked


def get_usable_approved_request(tenant, *, action_type, document_type, document_id, requested_by=None):
    """Una solicitud APROBADA, no consumida todavía, para esta acción y
    documento exactos — lo que una vista debe buscar antes de decidir
    si puede aplicar una operación que excede el límite del usuario sin
    volver a bloquear. `requested_by`, si se indica, exige que sea el
    mismo usuario que la solicitó originalmente."""
    queryset = ApprovalRequest.all_objects.filter(
        tenant=tenant, action_type=action_type, document_type=document_type, document_id=document_id,
        status=ApprovalRequest.Status.APPROVED, consumed_at__isnull=True,
    )
    if requested_by is not None:
        queryset = queryset.filter(requested_by=requested_by)
    return queryset.order_by("-decided_at").first()


def get_pending_requests(tenant):
    return (
        ApprovalRequest.all_objects.filter(tenant=tenant, status=ApprovalRequest.Status.PENDING)
        .select_related("requested_by")
        .order_by("-requested_at")
    )


def get_request_history(tenant, *, limit=50):
    return (
        ApprovalRequest.all_objects.filter(tenant=tenant)
        .exclude(status=ApprovalRequest.Status.PENDING)
        .select_related("requested_by", "approved_by")
        .order_by("-decided_at")[:limit]
    )


def get_policies(tenant):
    return ApprovalPolicy.all_objects.filter(tenant=tenant).select_related("user").order_by("scope", "role")


@transaction.atomic
def set_role_policy(
    tenant, *, role, max_discount_percent, max_discount_amount, max_credit_overage, can_approve, notes="",
    max_purchase_order_amount=Decimal("0"), max_over_receiving_percent=Decimal("0"), max_expense_amount=Decimal("0"),
):
    politica, _creada = ApprovalPolicy.all_objects.update_or_create(
        tenant=tenant, scope=ApprovalPolicy.Scope.ROLE, role=role,
        defaults=dict(
            max_discount_percent=max_discount_percent, max_discount_amount=max_discount_amount,
            max_credit_overage=max_credit_overage, can_approve=can_approve, notes=notes,
            max_purchase_order_amount=max_purchase_order_amount, max_over_receiving_percent=max_over_receiving_percent,
            max_expense_amount=max_expense_amount,
        ),
    )
    return politica


@transaction.atomic
def set_user_policy(
    tenant, *, user, max_discount_percent, max_discount_amount, max_credit_overage, can_approve, notes="",
    max_purchase_order_amount=Decimal("0"), max_over_receiving_percent=Decimal("0"), max_expense_amount=Decimal("0"),
):
    politica, _creada = ApprovalPolicy.all_objects.update_or_create(
        tenant=tenant, scope=ApprovalPolicy.Scope.USER, user=user,
        defaults=dict(
            max_discount_percent=max_discount_percent, max_discount_amount=max_discount_amount,
            max_credit_overage=max_credit_overage, can_approve=can_approve, notes=notes,
            max_purchase_order_amount=max_purchase_order_amount, max_over_receiving_percent=max_over_receiving_percent,
            max_expense_amount=max_expense_amount,
        ),
    )
    return politica


@transaction.atomic
def set_tenant_default_policy(
    tenant, *, max_discount_percent, max_discount_amount, max_credit_overage, can_approve=False, notes="",
    max_purchase_order_amount=Decimal("0"), max_over_receiving_percent=Decimal("0"), max_expense_amount=Decimal("0"),
):
    politica, _creada = ApprovalPolicy.all_objects.update_or_create(
        tenant=tenant, scope=ApprovalPolicy.Scope.TENANT,
        defaults=dict(
            max_discount_percent=max_discount_percent, max_discount_amount=max_discount_amount,
            max_credit_overage=max_credit_overage, can_approve=can_approve, notes=notes,
            max_purchase_order_amount=max_purchase_order_amount, max_over_receiving_percent=max_over_receiving_percent,
            max_expense_amount=max_expense_amount,
        ),
    )
    return politica
