# FASE 10 — Sales Engine

## Objetivo
Ventas, items, impuestos, descuentos, pagos, transacciones e impacto en inventario.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] Venta atómica
- [ ] inventario actualizado
- [ ] totales correctos
- [ ] tests financieros

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 8 — Interfaz de Inventario Serializado a consumir

FASE 8 agregó soporte de inventario serializado (`Product.inventory_tracking_type`,
modelo `InventoryUnit`, ver `docs/inventory.md`). Esta fase (Ventas) debe
integrarse con esa interfaz ya existente, sin reinventarla:

- `SaleItem` debe poder asociarse opcionalmente a una `InventoryUnit`
  (`SaleItem.inventory_unit`, FK) cuando el producto vendido es
  SERIALIZADO. Para productos por cantidad, `SaleItem` sigue sin
  necesitar esa referencia.
- Antes de confirmar la venta de una unidad concreta, llamar a
  `services.ensure_unit_available_for_sale(unit)` (`apps/inventory/services.py`)
  dentro de la misma transacción atómica de la venta — nunca reimplementar
  esa validación de disponibilidad en `apps.sales`.
- Al confirmar la venta, la unidad debe transicionar a `VENDIDO` con
  `services.transition_unit_status(unit=..., new_status=InventoryUnit.Status.VENDIDO, user=...)`
  — nunca escribir `unit.status = "vendido"` directamente ni saltarse la
  máquina de estados.
- Para productos por CANTIDAD, la venta sigue impactando el inventario
  vía `services.register_stock_out` (StockMovement), exactamente igual
  que hoy.
- Un `SaleItem` nunca debe vender la misma `InventoryUnit` dos veces ni
  una unidad ya reservada por otro carrito/venta en curso — la
  validación de disponibilidad debe ocurrir dentro de la transacción,
  con la fila bloqueada (mismo patrón `select_for_update` que ya usa
  `apps/inventory/services.py`).

## Nota de FASE 9 — Interfaz de Clientes a consumir

FASE 9 agregó `apps/customers` (`Customer`, ver `docs/customers.md`).
Esta fase debe integrarse con esa interfaz ya existente, sin
reinventarla:

- `Sale` debe referenciar a `Customer` mediante su propia FK
  (`Sale.customer`, `on_delete=PROTECT` recomendado para preservar el
  historial), no al revés — `Customer` no necesita saber nada de
  ventas.
- Reutilizar `apps.customers.services.get_active_customers(tenant)`
  para poblar cualquier selector de cliente, en vez de reimplementar la
  consulta.
- Antes de confirmar una venta a crédito, esta fase es la primera que
  debe leer (nunca modificar el modelo de `Customer` para ello)
  `customer.credit_enabled`/`credit_limit`/`credit_days`/`currency` —
  campos ya preparados en FASE 9 pero sin ningún motor financiero
  detrás. Calcular un saldo/deuda real y decidir si una venta a crédito
  debe bloquearse por límite excedido es responsabilidad de esta fase
  (o de una fase de Billing/cuentas por cobrar), nunca de
  `apps.customers`.
- Registrar aquí (no en `apps.customers`) cualquier evento de venta en
  el historial del cliente: la pestaña "Historial" del detalle de
  cliente (FASE 9) hoy muestra un estado vacío explícito precisamente
  esperando esta fase.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
