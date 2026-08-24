"""
Capa de servicios de referencia (FASE 3).

ARCHITECTURE.md define una capa de "servicios" separada de las vistas
(ver `## Capas`). Estas dos funciones son un ejemplo mínimo de ese patrón,
operando sobre `IsolationSample` (el modelo de referencia de `models.py`):
las apps de negocio reales (desde FASE 8) seguirán el mismo patrón —
servicios que dependen del manager tenant-aware en vez de recibir y
filtrar manualmente un `tenant_id` en cada función.
"""

from .models import IsolationSample


def create_isolation_sample(tenant, label):
    """Crea un registro perteneciente a `tenant`. La creación no depende
    del tenant activo del contexto (un INSERT no filtra), por eso recibe
    `tenant` explícitamente."""
    return IsolationSample.objects.create(tenant=tenant, label=label)


def list_isolation_samples_for_current_tenant():
    """Devuelve los registros del tenant ACTIVO (contexto actual), nunca
    de otros — porque usa el manager tenant-aware (`objects`), no
    `all_objects`."""
    return list(IsolationSample.objects.all())
