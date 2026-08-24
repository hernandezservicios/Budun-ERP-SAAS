"""
Mecanismo de "tenant context" y aislamiento tenant-aware (FASE 3).

Este módulo es la pieza central del aislamiento multi-tenant: define cómo
se guarda el tenant activo durante el procesamiento de una request (o de
un comando/servicio interno) y cómo los managers/querysets lo usan para
filtrar automáticamente los datos.

Diseño:
- El tenant activo se guarda en un `contextvars.ContextVar`, no en un
  atributo global mutable. Esto es seguro con hilos y con `async` (a
  diferencia de una variable de módulo simple), y cada request obtiene su
  propio valor aunque el servidor atienda varias al mismo tiempo.
- Nadie más que `TenantMiddleware` (o los tests) debe llamar a
  `set_current_tenant` directamente en código de vistas/servicios de
  negocio: el patrón esperado es leer con `get_current_tenant()` o usar
  el manager tenant-aware (`TenantManager`).
"""

import contextvars
from contextlib import contextmanager

_current_tenant = contextvars.ContextVar("current_tenant", default=None)


def get_current_tenant():
    """Tenant activo en el contexto de ejecución actual, o None si no hay
    ninguno (request no autenticada, usuario sin membresías, comando
    interno fuera de contexto, etc.)."""
    return _current_tenant.get()


def set_current_tenant(tenant):
    """Fija el tenant activo y devuelve un token para poder restaurarlo
    después (ver `reset_current_tenant`)."""
    return _current_tenant.set(tenant)


def reset_current_tenant(token):
    _current_tenant.reset(token)


@contextmanager
def tenant_context(tenant):
    """Context manager para fijar temporalmente el tenant activo: usado
    por `TenantMiddleware`, por comandos de administración y por los
    tests de aislamiento."""
    token = set_current_tenant(tenant)
    try:
        yield tenant
    finally:
        reset_current_tenant(token)
