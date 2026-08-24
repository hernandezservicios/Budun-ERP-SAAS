# ADR-005 — PayPal y PayPal MCP

## Decisión
PayPal se integra mediante una capa de servicio de pagos en Django. MCP sirve como herramienta del agente/desarrollo/operación cuando corresponda y no reemplaza el backend de pagos.

## Regla
Sandbox primero. Production únicamente tras pasar las verificaciones de seguridad y producción.
