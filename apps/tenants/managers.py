"""
Manager/QuerySet tenant-aware reutilizables (FASE 3).

`TenantScopedModel` (en `models.py`) es la base abstracta que, a partir de
FASE 8 (Products + Inventory), heredarán los modelos de negocio reales
(productos, ventas, movimientos de inventario, etc.) para obtener
aislamiento automático por tenant sin tener que reimplementar el filtrado
en cada vista, serializer o servicio.
"""

from django.db import models

from .scoping import get_current_tenant


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        """Filtra explícitamente por un tenant concreto."""
        return self.filter(tenant=tenant)

    def for_current_tenant(self):
        """Filtra por el tenant activo del contexto actual. Si no hay
        ningún tenant activo, devuelve un queryset vacío — nunca "todos los
        tenants" por accidente."""
        tenant = get_current_tenant()
        if tenant is None:
            return self.none()
        return self.filter(tenant=tenant)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Manager tenant-aware: el queryset por defecto (`Modelo.objects`)
    SOLO devuelve filas del tenant activo. El aislamiento es así el
    comportamiento por defecto, no algo que cada vista deba recordar
    aplicar manualmente."""

    def get_queryset(self):
        return super().get_queryset().for_current_tenant()
