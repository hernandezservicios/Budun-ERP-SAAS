"""
Límite de tasa de la API de Inventario — `LocMemCache` (ver
`CACHES` en `config/settings.py`), apropiado para un solo proceso;
Redis queda deferido hasta que una fase futura demuestre necesidad
real (`CLAUDE.md`). Límite configurable a nivel de PROYECTO
(`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["api_key"]`) — un límite
distinto por API Key individual queda documentado como extensión
futura simple, no construida en esta fase."""

from rest_framework.throttling import SimpleRateThrottle


class ApiKeyRateThrottle(SimpleRateThrottle):
    scope = "api_key"

    def get_cache_key(self, request, view):
        api_key = getattr(request, "api_key", None)
        if api_key is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": api_key.pk}


class CatalogRateThrottle(SimpleRateThrottle):
    """Límite de tasa SEPARADO para la Catalog API (ampliación final de
    FASE 15, sección 20: "preparar separación Inventory API limits /
    Catalog API limits") — su propio scope de DRF
    (`DEFAULT_THROTTLE_RATES["integration"]`), su propia clave de
    caché por `Integration` (nunca comparte contador con `ApiKey`)."""

    scope = "integration"

    def get_cache_key(self, request, view):
        integration = getattr(request, "integration", None)
        if integration is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": integration.pk}
