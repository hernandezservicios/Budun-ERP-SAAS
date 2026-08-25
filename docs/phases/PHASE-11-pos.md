# FASE 11 — POS

## Objetivo
POS rápido y usable: búsqueda, barcode, carrito, cliente, pago, cambio, recibo.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [ ] flujo completo
- [ ] mobile/touch usable
- [ ] no duplicados

## Verificación
- [ ] `python manage.py check` o la validación equivalente está en verde.
- [ ] Tests relevantes ejecutados.
- [ ] Smoke test realizado cuando aplique.
- [ ] Seguridad revisada para el alcance de la fase.
- [ ] Documentación actualizada.
- [ ] `docs/project-status/CURRENT_PHASE.md` y `PHASE_HISTORY.md` actualizados.
- [ ] Git commit creado.

## Nota de FASE 8 — Interfaz de Inventario Serializado a consumir

FASE 8 dejó preparada, en `apps/inventory/services.py`, la búsqueda
unificada y el flujo de carrito que este POS debe usar tal cual (ver
`docs/inventory.md`):

- `services.search_catalog(tenant, query)` identifica una búsqueda por
  nombre, SKU, código de barras, número de serie o IMEI (1 o 2), y
  devuelve una lista de `SearchResult(product, unit=None|InventoryUnit)`.
  Un QR escaneado normalmente solo codifica uno de estos valores como
  texto plano, así que se busca con el mismo `search_catalog` — no hace
  falta un campo ni una función de búsqueda aparte para QR.
- Flujo esperado en el POS, ya modelado por `SearchResult.requires_unit_selection`:
  - Producto por CANTIDAD: el resultado se agrega directo al carrito.
  - Producto SERIALIZADO encontrado por nombre/SKU/barcode (`requires_unit_selection == True`):
    el POS debe pedir a continuación el IMEI/serie concreto antes de
    agregarlo al carrito.
  - IMEI/serie escaneado o tecleado directamente: `search_catalog` ya
    devuelve la unidad exacta (`result.unit`) — validar con
    `services.ensure_unit_available_for_sale(result.unit)` antes de
    agregarla al carrito.
- No permitir agregar al carrito: una unidad inexistente (búsqueda sin
  resultados), una unidad ya en el carrito (revisar duplicados por
  `unit.pk` en el estado del carrito), o una unidad que
  `ensure_unit_available_for_sale` rechace (vendida, reservada, en
  reparación, dañada, perdida).
- Multi-Tenant: `search_catalog` ya recibe `tenant` explícito y nunca
  mezcla resultados de otro tenant — el POS debe seguir pasando siempre
  `request.tenant`, nunca un tenant elegido por el cliente.

## Nota de FASE 9 — Interfaz de Clientes a consumir

El POS debe poder seleccionar un cliente durante la venta reutilizando
`apps.customers.services.list_customers`/`get_active_customers`
(búsqueda por nombre/empresa/identificación/correo/teléfono ya
implementada, ver `docs/customers.md`) — nunca reimplementar esa
búsqueda ni consultar `Customer` directamente sin pasar por
`services.py`. La venta sin cliente seleccionado (venta anónima/al
contado) debe seguir siendo válida: `Sale.customer` en FASE 10 debería
ser opcional para ese caso.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.
