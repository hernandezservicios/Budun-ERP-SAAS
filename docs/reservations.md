# Reservas (FASE 10)

`Reservation` — una capa "blanda" sobre el inventario real, nunca un
segundo libro mayor. Ver `docs/sales.md` para el resumen y
`docs/proforma-invoices.md` para cómo se originan desde una proforma.

## Diseño: nunca toca `StockMovement`

Una reserva **no** crea un `StockMovement`. Para productos QUANTITY, la
disponibilidad "para prometer" es un cálculo derivado:

```
services.get_available_to_promise(product) =
    services.get_current_stock(product) − services.get_reserved_quantity(product)
```

`get_reserved_quantity` suma la `quantity` de las `Reservation` en
estado `ACTIVE` de ese producto. Para productos SERIALIZADOS, reservar
transiciona la `InventoryUnit` concreta a `RESERVADO` (reutilizando la
máquina de estados de FASE 8) — como `get_current_stock` para
serializados ya cuenta solo unidades `EN_STOCK`, la disponibilidad
refleja la reserva automáticamente, sin restar nada aparte.

## Origen genérico (`source_type`/`source_id`)

Una reserva puede originarse en una `PROFORMA`, una `QUOTATION` (previsto
en el enum aunque hoy solo `reserve_stock_for_proforma` la usa) o de
forma `MANUAL`. Se modeló como una referencia genérica (`source_type` +
`source_id`, mismo patrón que `ActivityLog` en FASE 9) en vez de FKs
directas a cada posible origen, para no acoplar `Reservation` a cada
tipo de documento que pudiera reservar en el futuro.

## Constraint: cantidad XOR unidad

Una reserva es de una **cantidad** (productos QUANTITY) o de una
**unidad concreta** (productos SERIALIZED), nunca ambas ni ninguna —
`CheckConstraint` a nivel de PostgreSQL (`reservation_cantidad_xor_unidad`),
verificado incluso saltándose el servicio.

## No permitir sobre-reservar (concurrencia)

`create_reservation`:
- SERIALIZED: bloquea la fila de la `InventoryUnit`
  (`select_for_update()`) y llama a `transition_unit_status(...,
  RESERVADO, ...)` — si la unidad no está `EN_STOCK` (ya reservada,
  vendida, en reparación, etc.), la máquina de estados de FASE 8 la
  rechaza automáticamente.
- QUANTITY: bloquea la fila del `Product` (mismo patrón de
  `apps.inventory.services._register_movement`) y verifica
  `get_available_to_promise` **con la fila ya bloqueada** antes de
  crear la reserva — dos reservas concurrentes que en conjunto
  excederían el stock nunca pueden tener éxito las dos (verificado con
  hilos reales en `test_concurrency.py`).

## Liberación

`release_reservation(reservation, user)`: si la reserva está `ACTIVE`,
la libera (`RELEASED`) y, si era de una unidad SERIALIZADA en
`RESERVADO`, la regresa a `EN_STOCK`. Idempotente: liberar una reserva
ya liberada/convertida/vencida es un no-op.

## Vencimiento

`expire_due_reservations(tenant=None)`: mismo patrón que el vencimiento
de cotizaciones/proformas — pensado para una tarea programada futura,
no construida en esta fase (solo la función idempotente que la
alimentaría).

## Conversión

Cuando la venta que consume una reserva se **confirma**
(`confirm_sale`), las reservas `ACTIVE` originadas por la proforma de
origen se marcan `CONVERTED` (no `RELEASED`) — un estado terminal
distinto, para distinguir en el historial "se usó" de "se liberó sin
usar".

## Multi-Tenancy

Cobertura en `test_isolation.py`: `get_reserved_quantity` nunca suma
reservas de otro tenant (incluso con productos de nombre/SKU
coincidente en ambos tenants, se filtra por instancia real de
`Product`, que ya es tenant-scoped); liberar una reserva de otro tenant
da 404.
