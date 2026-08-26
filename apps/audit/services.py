"""
Única vía sancionada para escribir y consultar la auditoría
transversal (ver `docs/audit.md`). `log_event` es la única forma de
crear un `AuditLog` — nunca `AuditLog.objects.create(...)` directo
desde otro módulo. Inmutable por diseño: este archivo NO define
`update`/`delete` para `AuditLog` (una corrección es un evento nuevo,
nunca una edición del histórico — mismo principio que
`reverse_journal_entry`/`PaymentAllocation` revertida).
"""

from django.db.models import CharField, F, Q, Value
from django.db.models.functions import Cast

from apps.accounting.models import AccountingActivityLog
from apps.customers.models import ActivityLog as CustomersActivityLog
from apps.expenses.models import ExpensesActivityLog
from apps.hr.models import HRActivityLog
from apps.inventory.models import StockMovement
from apps.payroll.models import PayrollActivityLog
from apps.purchases.models import PurchasesActivityLog
from apps.sales.models import SalesActivityLog

from .models import AuditLog


def get_client_ip(request):
    """IP real del cliente — respeta `X-Forwarded-For` (primer valor,
    el más cercano al cliente) cuando el proyecto corra detrás de un
    proxy/balanceador en producción (ver `docs/setup/*`), con
    `REMOTE_ADDR` como respaldo en desarrollo directo."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(
    tenant, *, action, domain, user=None, object_type="", object_id=None,
    ip_address=None, user_agent="", request_id="", before=None, after=None,
    reason="", metadata=None,
):
    """Crea un evento de auditoría. `tenant` puede ser `None`
    (login fallido de un email que no pertenece a ningún tenant, o que
    ni siquiera existe) — nunca se inventa un tenant para poder
    guardar la fila."""
    return AuditLog.objects.create(
        tenant=tenant, user=user, action=action, domain=domain,
        object_type=object_type, object_id="" if object_id is None else str(object_id),
        ip_address=ip_address, user_agent=(user_agent or "")[:255], request_id=request_id or "",
        before=before, after=after, reason=reason, metadata=metadata or {},
    )


def log_event_from_request(request, *, action, domain, tenant=None, user=None, **kwargs):
    """Envoltorio de `log_event` que deriva IP/user agent/tenant/usuario
    de una request HTTP real cuando estén disponibles."""
    return log_event(
        tenant if tenant is not None else getattr(request, "tenant", None),
        action=action, domain=domain,
        user=user if user is not None else getattr(request, "user", None),
        ip_address=get_client_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", ""),
        **kwargs,
    )


# ------------------------------------------------------------------
# Búsqueda federada — une (SQL UNION, nunca una tabla nueva) los 7
# registros de actividad ya existentes por dominio + `AuditLog` +
# `StockMovement` (movimientos de inventario), proyectados a una
# forma común.
# ------------------------------------------------------------------

_COLUMNS = ["source", "tenant_id", "row_id", "domain", "action", "object_type", "object_id", "label", "summary", "user_id", "created_at"]

# (modelo, dominio, etiqueta legible) de cada uno de los 7 registros
# de actividad por-dominio ya existentes — NUNCA se agrega un octavo
# aquí sin que exista de verdad en su propia app.
_LEGACY_SOURCES = {
    "sales": (SalesActivityLog, "sales", "Ventas"),
    "customers": (CustomersActivityLog, "customers", "Clientes/Proveedores"),
    "accounting": (AccountingActivityLog, "accounting", "Contabilidad"),
    "expenses": (ExpensesActivityLog, "expenses", "Gastos"),
    "hr": (HRActivityLog, "hr", "RRHH"),
    "payroll": (PayrollActivityLog, "payroll", "Nómina"),
    "purchases": (PurchasesActivityLog, "purchases", "Compras"),
}

SOURCE_CHOICES = [(src, etiqueta) for src, (_m, _d, etiqueta) in _LEGACY_SOURCES.items()] + [
    ("audit", "Transversal (auth/permisos/API)"), ("inventory", "Inventario"),
]


def _project_legacy(queryset, *, source, domain):
    return queryset.annotate(
        source=Value(source, output_field=CharField()),
        row_id=F("id"),
        domain=Value(domain, output_field=CharField()),
        object_type=F("entity_type"),
        object_id=Cast("entity_id", output_field=CharField()),
        label=F("entity_label"),
        summary=F("details"),
    ).values(*_COLUMNS)


def _project_audit(queryset):
    return queryset.annotate(
        source=Value("audit", output_field=CharField()),
        row_id=F("id"),
        label=Value("", output_field=CharField()),
        summary=F("reason"),
    ).values(*_COLUMNS)


def _project_inventory(queryset):
    return queryset.annotate(
        source=Value("inventory", output_field=CharField()),
        row_id=F("id"),
        domain=Value("inventory", output_field=CharField()),
        action=F("movement_type"),
        object_type=Value("product", output_field=CharField()),
        object_id=Cast("product_id", output_field=CharField()),
        label=F("product__name"),
        summary=F("notes"),
    ).values(*_COLUMNS)


def search_audit_events(
    tenant, *, source=None, domain=None, action=None, user=None,
    date_from=None, date_to=None, q="", ip_address=None, limit=50, offset=0,
):
    """Búsqueda federada. Todos los filtros se aplican POR RAMA antes
    de `.union()` (Django no garantiza `.filter()` fiable sobre el
    resultado ya combinado) — nunca se trae todo a Python para
    filtrar ahí. Devuelve `{"rows": [...], "total": N}`, paginado en
    la base de datos."""
    ramas = []

    for src, (modelo, domain_value, _etiqueta) in _LEGACY_SOURCES.items():
        if source and source != src:
            continue
        if domain and domain != domain_value:
            continue
        qs = modelo.all_objects.filter(tenant=tenant)
        if user is not None:
            qs = qs.filter(user=user)
        if date_from is not None:
            qs = qs.filter(created_at__gte=date_from)
        if date_to is not None:
            qs = qs.filter(created_at__lte=date_to)
        if action:
            qs = qs.filter(action=action)
        if q:
            qs = qs.filter(Q(entity_label__icontains=q) | Q(details__icontains=q) | Q(entity_type__icontains=q))
        ramas.append(_project_legacy(qs, source=src, domain=domain_value))

    if not source or source == "audit":
        qs = AuditLog.objects.filter(tenant=tenant)
        if domain:
            qs = qs.filter(domain=domain)
        if user is not None:
            qs = qs.filter(user=user)
        if date_from is not None:
            qs = qs.filter(created_at__gte=date_from)
        if date_to is not None:
            qs = qs.filter(created_at__lte=date_to)
        if action:
            qs = qs.filter(action=action)
        if ip_address:
            qs = qs.filter(ip_address=ip_address)
        if q:
            qs = qs.filter(Q(object_type__icontains=q) | Q(reason__icontains=q) | Q(domain__icontains=q))
        ramas.append(_project_audit(qs))

    if not source or source == "inventory":
        if not domain or domain == "inventory":
            qs = StockMovement.all_objects.filter(tenant=tenant).select_related("product")
            if user is not None:
                qs = qs.filter(user=user)
            if date_from is not None:
                qs = qs.filter(created_at__gte=date_from)
            if date_to is not None:
                qs = qs.filter(created_at__lte=date_to)
            if action:
                qs = qs.filter(movement_type=action)
            if q:
                qs = qs.filter(Q(product__name__icontains=q) | Q(notes__icontains=q))
            ramas.append(_project_inventory(qs))

    if not ramas:
        return {"rows": [], "total": 0}

    combinado = ramas[0].union(*ramas[1:], all=True) if len(ramas) > 1 else ramas[0]
    combinado = combinado.order_by("-created_at")
    total = combinado.count()
    fila_pagina = list(combinado[offset : offset + limit])
    return {"rows": fila_pagina, "total": total}


def get_event_detail(tenant, *, source, row_id):
    """Recupera la fila COMPLETA (todos sus campos originales, no solo
    la proyección común usada en la búsqueda) desde su fuente real —
    usado por la vista de detalle."""
    if source == "audit":
        return AuditLog.objects.filter(tenant=tenant, pk=row_id).first()
    if source == "inventory":
        return StockMovement.all_objects.filter(tenant=tenant, pk=row_id).select_related("product", "user").first()
    entrada = _LEGACY_SOURCES.get(source)
    if entrada is None:
        return None
    modelo, _domain, _etiqueta = entrada
    return modelo.all_objects.filter(tenant=tenant, pk=row_id).select_related("user").first()
