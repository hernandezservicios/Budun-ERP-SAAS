"""Permiso DRF genérico basado en scopes — cada vista declara
`required_scope = "products:read"` como atributo de clase; esta única
clase de permiso lee ese atributo, nunca se escribe una subclase por
scope."""

from rest_framework.permissions import BasePermission


class HasScope(BasePermission):
    message = "La clave de API no tiene el scope requerido para este recurso."

    def has_permission(self, request, view):
        api_key = getattr(request, "api_key", None)
        if api_key is None:
            return False
        requerido = getattr(view, "required_scope", None)
        if requerido is None:
            return True
        return requerido in (api_key.scopes or [])
