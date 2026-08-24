# ADR-004 — API de Inventario para CRM IA

## Decisión
Crear `/api/v1/` con API Keys por tenant. La API será read-only inicialmente.

## Funciones
- Base URL visible en Configuración.
- Generar, regenerar y revocar API Key.
- API Key enmascarada después de mostrarse una vez.
- Prueba de conexión.
- Estado, última prueba y último error.
- Tenant isolation, scopes, rate limiting y audit log.
