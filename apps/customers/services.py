"""
Capa de servicios de Clientes y Proveedores (FASE 9).

CRUD y consultas reutilizables: no hay aquí ninguna operación de dinero
que proteger con `transaction.atomic()` (ver la nota sobre crédito/
saldos en `models.py` — esta fase solo prepara la configuración
comercial, no un motor financiero con movimientos reales), pero se
mantiene la misma separación de responsabilidades del resto del
proyecto — la lógica reutilizable vive aquí, no en las vistas ni en las
plantillas.

Igual que en `apps.inventory.services`, aquí se usa deliberadamente
`all_objects` (no `objects`/TenantManager), filtrando SIEMPRE por
`tenant` de forma explícita: así estas funciones dan el mismo resultado
se llamen desde una vista (con una request HTTP real detrás) o desde un
test unitario/comando interno sin esa request activa.
"""

from django.db.models import Q

from .file_validation import nombre_original_seguro, validar_archivo_adjunto
from .models import ActivityLog, Customer, CustomerDocument, Supplier, SupplierDocument

_CAMPOS_BUSQUEDA_CUSTOMER = ["first_name", "last_name", "company_name", "trade_name", "identification_number", "email", "phone"]
_CAMPOS_BUSQUEDA_SUPPLIER = ["legal_name", "trade_name", "identification_number", "email", "phone"]

# Lista blanca de campos de ordenamiento aceptados desde la URL (`?orden=`):
# nunca se pasa el valor del querystring directamente a `.order_by()` sin
# verificarlo contra esta lista — evita construir un `ORDER BY` sobre un
# campo/relación arbitraria a partir de una entrada del cliente.
ORDENAMIENTOS_CUSTOMER = {
    "nombre": ["first_name", "last_name"],
    "-nombre": ["-first_name", "-last_name"],
    "reciente": ["-created_at"],
    "antiguo": ["created_at"],
}
ORDENAMIENTOS_SUPPLIER = {
    "nombre": ["legal_name"],
    "-nombre": ["-legal_name"],
    "reciente": ["-created_at"],
    "antiguo": ["created_at"],
}


def _filtrar_busqueda(queryset, search, campos):
    if not search:
        return queryset
    filtro = Q()
    for campo in campos:
        filtro |= Q(**{f"{campo}__icontains": search})
    return queryset.filter(filtro)


def list_customers(tenant, *, search="", only_active=True, order="nombre"):
    """Clientes del tenant, con búsqueda, filtro por estado activo y
    ordenamiento — todos por lista blanca, nunca a partir de un valor
    de querystring sin verificar."""
    queryset = Customer.all_objects.filter(tenant=tenant)
    if only_active:
        queryset = queryset.filter(is_active=True)
    queryset = _filtrar_busqueda(queryset, search, _CAMPOS_BUSQUEDA_CUSTOMER)
    return queryset.order_by(*ORDENAMIENTOS_CUSTOMER.get(order, ORDENAMIENTOS_CUSTOMER["nombre"]))


def list_suppliers(tenant, *, search="", only_active=True, order="nombre"):
    """Proveedores del tenant, con el mismo criterio de búsqueda/filtro/
    ordenamiento que `list_customers`."""
    queryset = Supplier.all_objects.filter(tenant=tenant)
    if only_active:
        queryset = queryset.filter(is_active=True)
    queryset = _filtrar_busqueda(queryset, search, _CAMPOS_BUSQUEDA_SUPPLIER)
    return queryset.order_by(*ORDENAMIENTOS_SUPPLIER.get(order, ORDENAMIENTOS_SUPPLIER["nombre"]))


def get_active_customers(tenant):
    """Clientes activos del tenant, listos para un selector (p. ej. al
    registrar una venta en FASE 10) — punto de extensión, sin implementar
    todavía ninguna funcionalidad de Ventas."""
    return Customer.all_objects.filter(tenant=tenant, is_active=True).order_by("first_name", "last_name")


def get_active_suppliers(tenant):
    """Proveedores activos del tenant — mismo punto de extensión que
    `get_active_customers`, pensado para FASE 12 (Compras)."""
    return Supplier.all_objects.filter(tenant=tenant, is_active=True).order_by("legal_name")


# ------------------------------------------------------------------
# Auditoría (bitácora mínima, ver models.ActivityLog)
# ------------------------------------------------------------------


def log_activity(tenant, *, entity_type, entity_id, entity_label, action, user, details=""):
    return ActivityLog.all_objects.create(
        tenant=tenant,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        action=action,
        user=user,
        details=details,
    )


def get_activity_log(tenant, *, entity_type, entity_id, limit=20):
    return ActivityLog.all_objects.filter(
        tenant=tenant, entity_type=entity_type, entity_id=entity_id
    ).select_related("user")[:limit]


# ------------------------------------------------------------------
# Documentos adjuntos
# ------------------------------------------------------------------


def register_customer_document(*, customer, archivo, category, user, notes=""):
    """Valida (extensión + firma binaria + tamaño, ver `file_validation.py`)
    y guarda un documento adjunto de un cliente. Nunca guarda un archivo
    sin pasar primero por `validar_archivo_adjunto` — es la única vía
    sancionada para crear un `CustomerDocument`."""
    extension, content_type = validar_archivo_adjunto(archivo)
    documento = CustomerDocument.all_objects.create(
        tenant=customer.tenant,
        customer=customer,
        category=category,
        file=archivo,
        original_filename=nombre_original_seguro(archivo.name),
        content_type=content_type,
        size_bytes=archivo.size,
        uploaded_by=user,
        notes=notes,
    )
    log_activity(
        customer.tenant,
        entity_type="customer",
        entity_id=customer.pk,
        entity_label=customer.display_name,
        action=ActivityLog.Action.DOCUMENT_UPLOADED,
        user=user,
        details=documento.original_filename,
    )
    return documento


def register_supplier_document(*, supplier, archivo, category, user, notes=""):
    """Equivalente de `register_customer_document` para proveedores."""
    extension, content_type = validar_archivo_adjunto(archivo)
    documento = SupplierDocument.all_objects.create(
        tenant=supplier.tenant,
        supplier=supplier,
        category=category,
        file=archivo,
        original_filename=nombre_original_seguro(archivo.name),
        content_type=content_type,
        size_bytes=archivo.size,
        uploaded_by=user,
        notes=notes,
    )
    log_activity(
        supplier.tenant,
        entity_type="supplier",
        entity_id=supplier.pk,
        entity_label=supplier.display_name,
        action=ActivityLog.Action.DOCUMENT_UPLOADED,
        user=user,
        details=documento.original_filename,
    )
    return documento


def delete_customer_document(*, documento, user):
    # El archivo físico se borra vía la señal `post_delete` en models.py
    # (cubre también un borrado directo desde el admin o un queryset
    # masivo, no solo esta función) — aquí solo se borra la fila y se
    # registra la auditoría.
    tenant = documento.tenant
    entidad = documento.customer
    nombre = documento.original_filename
    documento.delete()
    log_activity(
        tenant,
        entity_type="customer",
        entity_id=entidad.pk,
        entity_label=entidad.display_name,
        action=ActivityLog.Action.DOCUMENT_DELETED,
        user=user,
        details=nombre,
    )


def delete_supplier_document(*, documento, user):
    # Ver nota en `delete_customer_document`: el archivo físico se borra
    # vía la señal `post_delete` en models.py.
    tenant = documento.tenant
    entidad = documento.supplier
    nombre = documento.original_filename
    documento.delete()
    log_activity(
        tenant,
        entity_type="supplier",
        entity_id=entidad.pk,
        entity_label=entidad.display_name,
        action=ActivityLog.Action.DOCUMENT_DELETED,
        user=user,
        details=nombre,
    )
