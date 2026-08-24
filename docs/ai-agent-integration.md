# Integración con Agente CRM IA

## Flujo
Agente CRM IA → HTTPS → Inventory API v1 → autenticación API Key → tenant context → Django service → PostgreSQL.

## Capacidades iniciales
Consultar productos, categorías, stock actual, stock bajo y movimientos.

## Principio de seguridad
La API es read-only por defecto. El agente no recibe credenciales de PostgreSQL ni Django.

## Credenciales
La API Key debe guardarse en el backend/secret manager del consumidor. No colocarla en prompts públicos, frontend o repositorios.

## Ejemplos de intención
- consultar stock por SKU.
- listar productos con stock bajo.
- consultar precio/disponibilidad.
- buscar productos por categoría.
