# API de Inventario

## Objetivo
Exponer inventario del tenant de forma segura para un agente CRM IA u otras integraciones.

## Base URL
`https://<dominio>/api/v1/`

## Seguridad
API Key por tenant. Read-only por defecto. La key debe almacenarse de forma segura; si solo se necesita validar posesión, preferir hash. Mantener metadata como prefix/last4/created_at/revoked_at/last_used_at.

## Configuración
Ruta conceptual: Configuración → API de Inventario.
Debe mostrar Base URL, API Key enmascarada, generación/rotación/revocación, probar conexión, estado, última prueba y último error.

## Endpoints iniciales
- `GET /api/v1/health/`
- `GET /api/v1/products/`
- `GET /api/v1/products/{id}/`
- `GET /api/v1/categories/`
- `GET /api/v1/inventory/`
- `GET /api/v1/inventory/low-stock/`
- `GET /api/v1/inventory/movements/`

## Reglas
Tenant isolation, rate limiting, pagination, filtering, safe errors, audit log, no acceso directo a PostgreSQL, no escritura por defecto.

## Respuestas
Usar un contrato consistente con `success`, `data`/`results`, `pagination` y `error` cuando corresponda. No incluir secrets ni stack traces.
