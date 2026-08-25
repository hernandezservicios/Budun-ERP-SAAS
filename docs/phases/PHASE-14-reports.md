# FASE 14 — Reports

## Objetivo
Reportes de ventas, inventario, productos, clientes, compras, gastos y utilidad; filtros y exportaciones según alcance.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] filtros
- [ ] tenant scoped
- [ ] queries optimizadas

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 8 — Interfaz de Inventario Serializado a consumir

Los reportes de inventario/stock deben distinguir explícitamente los dos
tipos de seguimiento definidos en FASE 8 (`Product.inventory_tracking_type`,
ver `docs/inventory.md`), nunca sumarlos como si fueran una sola cifra
homogénea:

- Productos por CANTIDAD: cantidad disponible desde `StockMovement`
  (vía `services.get_current_stock`/`services.list_products_with_stock`).
- Productos SERIALIZADOS: conteo de unidades por estado desde
  `InventoryUnit` (p. ej. cuántas `EN_STOCK`, cuántas `VENDIDO`,
  `REPARACION`, `GARANTIA`, etc. — cada estado es una dimensión de
  reporte útil que no existe para productos por cantidad).
- Reutilizar `services.get_current_stock`/`services.list_products_with_stock`
  (que ya devuelven el valor correcto para ambos tipos vía el mismo
  campo anotado `current_stock`) en vez de recalcular el stock con una
  consulta propia — evita una tercera fuente de verdad.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
