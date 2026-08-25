# API de Inventario (especificación)

> **Estado: ESPECIFICACIÓN, no implementación.** Diseño aprobado para
> FASE 15 — ningún endpoint, modelo ni migración se crea a partir de
> este documento. Consolida lo ya definido en `CLAUDE.md`/
> `docs/MASTER-PROMPT.md` (fuentes de verdad) y las notas de
> sincronización de `docs/phases/PHASE-15-roles-plus-audit-plus-inventory-api.md`.

## Principio central

Integración para agentes CRM IA externos, bajo
`Configuración → API de Inventario`. **Read-only por defecto.** El
agente IA nunca accede directamente a PostgreSQL — solo a través de
esta API, con una API Key propia por tenant.

## API Key

- Una API Key pertenece a exactamente un tenant (`CLAUDE.md`,
  Multi-tenancy).
- Generar, regenerar y revocar.
- La clave completa solo se muestra en el momento controlado de
  creación/rotación; después se enmascara (mismo criterio ya usado
  para IMEI/serie: nunca mostrar el secreto completo sin necesidad
  real).
- Botón "Probar Conexión" con estado resultante: Conectado, No
  conectado, Error, Deshabilitado; última prueba, último error.
- Auditoría de creación/rotación/revocación/uso.

## Endpoints mínimos (`/api/v1/`)

- `GET /api/v1/health/`
- `GET /api/v1/products/`
- `GET /api/v1/products/{id}/` — debe incluir `inventory_tracking_type`.
- `GET /api/v1/categories/`
- `GET /api/v1/inventory/`
- `GET /api/v1/inventory/low-stock/`
- `GET /api/v1/inventory/movements/`
- Inventario serializado (FASE 8): un endpoint/scope adicional (p. ej.
  `GET /api/v1/products/{id}/units/`) que exponga `InventoryUnit`,
  filtradas siempre por el tenant dueño de la API Key. Nunca exponer
  el IMEI/serie completo salvo que el scope de la API Key lo requiera
  explícitamente (decisión de scope, no comportamiento por defecto).

Reutilizar `apps.inventory.services.search_catalog`/`get_current_stock`
como fuente de datos — nunca reimplementar esas consultas en la capa
de API.

## Scopes (por dominio, nunca compartidos entre módulos)

Regla permanente: la API **solo podrá exponer recursos financieros
(o de cualquier dominio) mediante scopes explícitos** — nunca por
defecto, nunca reutilizando el scope de otro módulo.

| Scope | Dominio | Estado |
|---|---|---|
| `products:read` / `categories:read` / `inventory:read` | Inventario (FASE 8) | Mínimo previsto desde el inicio |
| `customers:read` / `suppliers:read` | Clientes/Proveedores (FASE 9) | Futuro, si se decide exponer |
| `sales:read` / `quotations:read` | Ventas (FASE 10) | Futuro, si se decide exponer |
| `payments:read` | `Payment`/`PaymentAllocation` (FASE 10) | Futuro, nunca mezclado con `inventory:read` |
| Scope propio (a definir) | `CreditNote`/`CreditNoteApplication` (FASE 11) | Futuro |
| Scope propio (a definir) | `ApprovalRequest` (FASE 11) — información sensible | Futuro, si se decide exponer |
| Scope propio (a definir) | `CashSession`/`CashMovement` (FASE 11) | Futuro, si se decide exponer |

## No negociable

- Rate limiting.
- Audit log de cada request (quién, qué scope, cuándo).
- Pagination/filtering en toda lista.
- Tenant isolation absoluto: el backend determina el tenant desde la
  API Key, nunca confía en un `tenant_id` recibido en la petición.
- Documentación para el agente CRM IA (formato/ejemplos de cada
  endpoint).

## Qué NO se construye con este documento

Ningún endpoint, modelo de `ApiKey`, ni vista de configuración. La
fase que implemente FASE 15 debe releer este documento y
`docs/phases/PHASE-15-roles-plus-audit-plus-inventory-api.md` antes de
diseñar.
