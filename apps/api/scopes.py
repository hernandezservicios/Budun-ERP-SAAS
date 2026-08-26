"""
Catálogo de scopes de la API de Inventario v1 (FASE 15, ver
`docs/api-inventory.md`). Código-definido, igual criterio que
`apps.permissions.catalog` — un scope es funcionalidad del código, no
una fila configurable por el tenant. **Nunca acceso financiero por
defecto**: no existe (todavía) ningún scope de ventas/pagos/nómina/
contabilidad/RRHH — solo inventario/catálogo, de solo lectura."""

SCOPE_CHOICES = [
    ("health:read", "Estado de la API"),
    ("products:read", "Productos"),
    ("categories:read", "Categorías"),
    ("inventory:read", "Inventario (stock por cantidad)"),
    ("inventory_movements:read", "Movimientos de inventario"),
    ("serialized_inventory:read", "Inventario serializado (IMEI/serie)"),
]

SCOPE_CODES = {codigo for codigo, _etiqueta in SCOPE_CHOICES}


def is_valid_scope(codigo):
    return codigo in SCOPE_CODES


def is_valid_scope_list(scopes):
    return isinstance(scopes, list) and all(is_valid_scope(codigo) for codigo in scopes)
