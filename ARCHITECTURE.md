# Arquitectura

## Capas
1. Presentación: templates/componentes y JavaScript ligero.
2. Aplicación: views, serializers, permissions y services.
3. Dominio: reglas de negocio.
4. Datos: Django ORM + PostgreSQL.
5. Integraciones: PayPal, API de Inventario y futuras integraciones.

## Desarrollo
Windows → Python virtualenv → Django → PostgreSQL local → pgAdmin 4.

## Producción
Hostinger VPS → Linux → Nginx → Gunicorn → Django → PostgreSQL.

## Multi-tenant
Single database, tenant isolation a nivel de aplicación y base de datos mediante relaciones, constraints, managers/querysets y permissions. La arquitectura debe permitir evolucionar a particionado o separación de bases si fuese necesario, sin diseñar eso ahora.

## API
`/api/v1/` es el contrato versionado inicial. La API de Inventario es tenant-scoped, read-only por defecto, autenticada mediante API Key, limitada por rate limit y auditada.

## Inventario: dos fuentes de verdad, una por producto
Incorporado oficialmente a partir de FASE 8. Cada producto tiene un tipo de seguimiento de inventario, y ese tipo determina cuál es su única fuente de verdad de stock — nunca dos a la vez:

| Tipo | Fuente de verdad | Disponibilidad |
|---|---|---|
| QUANTITY | `StockMovement` (libro mayor append-only) | `stock_after` del movimiento más reciente |
| SERIALIZED | `InventoryUnit` (una fila por unidad física) | conteo de unidades en estado EN_STOCK |

Prohibido cualquier campo de stock desnormalizado o cualquier segunda fuente que pueda desincronizarse de la anterior. `serial`/`imei_1`/`imei_2` de `InventoryUnit` son únicos por tenant (no global) entre valores no vacíos; `imei_1` ≠ `imei_2`; toda unidad requiere al menos un identificador. Ver `docs/inventory.md` para el diseño completo (estados, máquina de estados, búsqueda unificada, reglas de venta).

## UI
Dashboard custom; no Django Admin como UI principal. Dirección visual: SaaS moderno, empresarial, sobrio, legible, azul/verde con neutrales y sin colores estridentes.
