"""
Catálogo de permisos (FASE 15, ver docs/roles-permissions.md).

Los permisos son funcionalidad del CÓDIGO, no datos de negocio
configurables por el tenant (a diferencia de `ExpenseCategory`/
`LeaveType`/`TaxCode`) — por eso el catálogo es una constante
Python, nunca una tabla con CRUD propio. Lo que SÍ es configurable
por tenant es QUÉ ROL tiene cada permiso (`RolePermission`) y qué
EXCEPCIÓN tiene un usuario específico (`UserPermissionOverride`) —
ver `models.py`/`services.py`.

Cada entrada: (código, etiqueta, dominio). El dominio agrupa la UI de
Roles y Permisos, no tiene efecto en la resolución.
"""

PERMISSION_CATALOG = [
    ("dashboard.view", "Ver panel", "dashboard"),

    ("customers.view", "Ver clientes", "customers"),
    ("customers.create", "Crear clientes", "customers"),
    ("customers.update", "Editar clientes", "customers"),
    ("customers.delete", "Desactivar clientes", "customers"),
    ("customers.export", "Exportar clientes", "customers"),
    ("customers.financial.view", "Ver saldo financiero de clientes", "customers"),
    ("customers.financial.export", "Exportar saldo financiero de clientes", "customers"),

    ("suppliers.view", "Ver proveedores", "suppliers"),
    ("suppliers.create", "Crear proveedores", "suppliers"),
    ("suppliers.update", "Editar proveedores", "suppliers"),
    ("suppliers.delete", "Desactivar proveedores", "suppliers"),

    ("products.view", "Ver productos", "products"),
    ("products.create", "Crear productos", "products"),
    ("products.update", "Editar productos", "products"),
    ("products.delete", "Desactivar productos", "products"),

    ("inventory.view", "Ver inventario", "inventory"),
    ("inventory.adjust", "Ajustar inventario", "inventory"),
    ("inventory.stock_in", "Registrar entradas de inventario", "inventory"),
    ("inventory.stock_out", "Registrar salidas de inventario", "inventory"),
    ("inventory.serialized.view", "Ver unidades serializadas (IMEI/serie)", "inventory"),

    ("sales.view", "Ver ventas", "sales"),
    ("sales.create", "Crear ventas", "sales"),
    ("sales.update", "Editar ventas", "sales"),
    ("sales.cancel", "Cancelar ventas", "sales"),
    ("sales.refund", "Reembolsar ventas", "sales"),

    ("quotations.view", "Ver cotizaciones", "quotations"),
    ("quotations.create", "Crear cotizaciones", "quotations"),
    ("quotations.convert", "Convertir cotizaciones", "quotations"),

    ("pos.use", "Usar el punto de venta", "pos"),
    ("cash.open", "Abrir caja", "pos"),
    ("cash.close", "Cerrar caja", "pos"),
    ("cash.move", "Registrar movimientos de caja", "pos"),
    ("cash.view", "Ver caja", "pos"),

    ("payments.create", "Registrar pagos", "payments"),
    ("payments.reverse", "Reversar pagos", "payments"),
    ("credit.view", "Ver crédito de clientes", "payments"),
    ("credit.apply", "Aplicar saldo a favor", "payments"),
    ("credit_note.view", "Ver notas de crédito", "payments"),
    ("credit_note.create", "Crear notas de crédito", "payments"),
    ("credit_note.apply", "Aplicar notas de crédito", "payments"),

    ("purchases.view", "Ver compras", "purchases"),
    ("purchases.create", "Crear órdenes de compra", "purchases"),
    ("purchases.receive", "Recibir compras", "purchases"),
    ("purchases.return", "Devolver compras a proveedor", "purchases"),

    ("expenses.view", "Ver gastos", "expenses"),
    ("expenses.create", "Crear gastos", "expenses"),
    ("expenses.approve", "Aprobar gastos", "expenses"),

    ("hr.view", "Ver RRHH", "hr"),
    ("hr.create", "Crear registros de RRHH", "hr"),
    ("hr.update", "Editar registros de RRHH", "hr"),
    ("hr.sensitive.view", "Ver datos sensibles de RRHH (salario/bancarios)", "hr"),

    ("payroll.view", "Ver nómina", "payroll"),
    ("payroll.process", "Procesar nómina", "payroll"),
    ("payroll.approve", "Aprobar nómina", "payroll"),
    ("payroll.pay", "Pagar nómina", "payroll"),
    ("payroll.sensitive.view", "Ver desglose sensible de nómina", "payroll"),
    ("payroll.sensitive.export", "Exportar desglose sensible de nómina", "payroll"),

    ("accounting.view", "Ver contabilidad", "accounting"),
    ("accounting.post", "Contabilizar asientos", "accounting"),
    ("accounting.reverse", "Reversar asientos", "accounting"),
    ("accounting.close_period", "Cerrar período contable", "accounting"),
    ("accounting.reopen_period", "Reabrir período contable", "accounting"),
    ("accounting.export", "Exportar información contable", "accounting"),

    ("reports.view", "Ver reportes", "reports"),
    ("reports.export", "Exportar reportes", "reports"),
    ("reports.financial.view", "Ver reportes financieros", "reports"),
    ("reports.hr.view", "Ver reportes de RRHH/nómina", "reports"),
    ("reports.sensitive.export", "Exportar reportes con datos sensibles", "reports"),

    ("api.inventory.read", "Consultar la API de Inventario", "api"),
    ("api.inventory.manage", "Administrar la API de Inventario", "api"),
    ("api.inventory.rotate", "Rotar la clave de la API de Inventario", "api"),
    ("api.inventory.revoke", "Revocar la clave de la API de Inventario", "api"),

    # Integraciones externas / Catalog API (ampliación final de FASE 15).
    ("api.integration.view", "Ver integraciones externas", "api"),
    ("api.integration.create", "Crear integraciones externas", "api"),
    ("api.integration.update", "Editar integraciones externas (scopes, activar/desactivar)", "api"),
    ("api.integration.rotate", "Rotar la credencial de una integración", "api"),
    ("api.integration.revoke", "Revocar una integración", "api"),
    ("api.integration.test", "Probar conexión de una integración", "api"),

    ("audit.view", "Ver auditoría", "audit"),
    ("audit.export", "Exportar auditoría", "audit"),
    ("audit.sensitive.view", "Ver eventos de auditoría sensibles", "audit"),

    ("settings.view", "Ver configuración", "settings"),
    ("settings.manage", "Administrar configuración", "settings"),
]

PERMISSION_CODES = {code for code, _label, _domain in PERMISSION_CATALOG}
PERMISSION_LABELS = {code: label for code, label, _domain in PERMISSION_CATALOG}
PERMISSIONS_BY_DOMAIN = {}
for _code, _label, _domain in PERMISSION_CATALOG:
    PERMISSIONS_BY_DOMAIN.setdefault(_domain, []).append((_code, _label))


def is_valid_permission_code(code):
    return code in PERMISSION_CODES


# ------------------------------------------------------------------
# Permisos por defecto de cada rol (código-definidos — el tenant puede
# personalizar vía `RolePermission`, esto es solo el punto de partida
# "de fábrica" cuando no hay ninguna fila configurada). OWNER nunca
# aparece aquí: siempre está autorizado, regla permanente ya
# establecida (ver `services.has_permission`).
# ------------------------------------------------------------------

_TODOS = list(PERMISSION_CODES)

_ADMIN_EXCLUYE = {
    "accounting.close_period", "accounting.reopen_period",
    "api.inventory.manage", "api.inventory.rotate", "api.inventory.revoke",
    "api.integration.create", "api.integration.update", "api.integration.rotate", "api.integration.revoke",
    "settings.manage",
}

_MANAGER_INCLUYE = {
    "dashboard.view",
    "customers.view", "customers.create", "customers.update", "customers.export",
    "suppliers.view", "suppliers.create", "suppliers.update",
    "products.view", "products.create", "products.update",
    "inventory.view", "inventory.adjust", "inventory.stock_in", "inventory.stock_out", "inventory.serialized.view",
    "sales.view", "sales.create", "sales.update", "sales.cancel", "sales.refund",
    "quotations.view", "quotations.create", "quotations.convert",
    "pos.use", "cash.open", "cash.close", "cash.move", "cash.view",
    "payments.create", "payments.reverse", "credit.view", "credit.apply",
    "credit_note.view", "credit_note.create", "credit_note.apply",
    "purchases.view", "purchases.create", "purchases.receive", "purchases.return",
    "expenses.view", "expenses.create", "expenses.approve",
    "hr.view", "hr.create", "hr.update",
    "payroll.view",
    "accounting.view",
    "reports.view", "reports.export", "reports.financial.view",
    "settings.view",
}

_CASHIER_INCLUYE = {
    "dashboard.view",
    "customers.view",
    "products.view",
    "inventory.view",
    "sales.view", "sales.create",
    "quotations.view",
    "pos.use", "cash.open", "cash.close", "cash.move", "cash.view",
    "payments.create",
    "credit.view", "credit_note.view", "credit_note.apply",
    "reports.view",
}

_EMPLOYEE_INCLUYE = {
    "dashboard.view",
    "customers.view",
    "products.view",
    "inventory.view",
    "sales.view",
    "quotations.view",
    "purchases.view",
    "expenses.view", "expenses.create",
    "hr.view",
    "reports.view",
}

DEFAULT_ROLE_PERMISSIONS = {
    "admin": set(_TODOS) - _ADMIN_EXCLUYE,
    "manager": set(_MANAGER_INCLUYE),
    "cashier": set(_CASHIER_INCLUYE),
    "employee": set(_EMPLOYEE_INCLUYE),
    # "member" (rol histórico anterior a FASE 15, preservado sin
    # cambios): se trata igual que EMPLOYEE por defecto — el mínimo
    # común denominador seguro, nunca datos sensibles/operaciones
    # críticas sin configuración explícita del tenant.
    "member": set(_EMPLOYEE_INCLUYE),
}
