# FASE 12 — Purchases

## Objetivo
Compras, recepción y actualización de inventario.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] purchase workflow
- [ ] stock increase
- [ ] tests

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 8 — Interfaz de Inventario Serializado a consumir

FASE 8 agregó `apps/inventory/services.register_serialized_unit(...)`
(ver `docs/inventory.md`) como la única vía sancionada para dar de alta
una `InventoryUnit` nueva. Al recibir una compra de un producto
SERIALIZADO, esta fase debe:

- Por cada unidad física recibida, llamar a `register_serialized_unit`
  con `product`, `user`, y al menos uno de `serial`/`imei_1`/`imei_2`,
  más `unit_cost` (del costo real de esa compra) y `entry_date`. La
  unidad queda automáticamente en estado `EN_STOCK`.
- Pasar `purchase_origin` con una referencia legible a la compra/orden
  de FASE 12 (por ahora ese campo es texto libre en `InventoryUnit`,
  documentado como provisional en `docs/inventory.md`; cuando exista el
  modelo `Purchase` real, lo natural es que `Purchase`/`PurchaseItem`
  referencien a `InventoryUnit` con su propia FK, no al revés).
- Para productos por CANTIDAD, la recepción de compra sigue impactando
  el inventario vía `services.register_stock_in` (StockMovement),
  exactamente igual que hoy.
- Nunca crear una `InventoryUnit` a mano (fuera de `services.py`): así se
  preservan las constraints de unicidad por tenant y las validaciones
  (IMEI 1 ≠ IMEI 2, al menos un identificador) en un único punto.

## Nota de FASE 9 — Interfaz de Proveedores a consumir

FASE 9 agregó `apps/customers` (`Supplier`, ver `docs/suppliers.md`).
Esta fase debe integrarse con esa interfaz ya existente, sin
reinventarla:

- `Purchase`/`PurchaseItem` deben referenciar a `Supplier` mediante su
  propia FK (`Purchase.supplier`, `on_delete=PROTECT` recomendado), no
  al revés.
- Reutilizar `apps.customers.services.get_active_suppliers(tenant)`
  para poblar cualquier selector de proveedor.
- Los campos comerciales de `Supplier` (`payment_terms`, `credit_days`,
  `credit_enabled`, `currency`) ya están preparados desde FASE 9 sin
  ningún motor financiero detrás — esta fase (o una fase de cuentas por
  pagar) es responsable de calcular cualquier saldo/deuda real y de
  decidir cómo aplicar esas condiciones a una compra concreta.
- Registrar aquí cualquier evento de compra en el historial del
  proveedor: la pestaña "Historial" del detalle de proveedor (FASE 9)
  hoy muestra un estado vacío explícito esperando esta fase.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
