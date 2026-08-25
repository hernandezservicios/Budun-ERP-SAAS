# FASE 10 — Sales Engine + Cotizaciones + Proformas/Prefacturas + Facturas + Pagos

## Objetivo
Motor comercial central del ERP: Cotizaciones, Proformas/Prefacturas, Ventas/Facturas, Pagos (múltiples, parciales), Reservas, Devoluciones y Reembolsos — profesional, transaccional, seguro, multi-tenant, auditable, diseñado para que FASE 11 (POS) sea únicamente una interfaz operacional sobre este mismo motor.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] Venta atómica — `confirm_sale`/`record_payment`/`create_return`/`create_reservation` con `transaction.atomic()` + `select_for_update()`; idempotentes ante reintentos (verificado con hilos reales).
- [x] inventario actualizado — reutiliza literalmente `apps.inventory.services` (QUANTITY: `register_stock_in`/`register_stock_out`; SERIALIZED: `transition_unit_status`), nunca duplica esa lógica.
- [x] totales correctos — snapshot histórico por línea, descuento por línea (%/monto) y global, impuesto sobre base ya descontada; verificado con tests numéricos explícitos.
- [x] tests financieros — pagos parciales/múltiples/idempotentes, reembolsos con tope, estados de pago derivados (nunca asumidos).
- [x] Cotizaciones — CRUD, envío/aceptación/rechazo/vencimiento/cancelación, duplicar, conversión a proforma o venta directa, impresión.
- [x] Proformas — CRUD, emisión/vencimiento/cancelación, reserva de stock explícita (nunca automática), conversión a venta, impresión.
- [x] Reservas — capa blanda sobre inventario real (nunca un segundo `StockMovement`), sin sobre-reserva bajo concurrencia.
- [x] Devoluciones/Reembolsos — separados (mercancía vs. dinero), parciales y totales, unidad serializada nunca reingresa sola a stock.
- [x] Numeración profesional — series por tipo de documento y tenant, nunca el ID de base de datos.
- [x] Multi-Tenant — cobertura exhaustiva (listados, detalle, acciones, IDs manipulados, sesión manipulada).
- [x] Concurrencia — probada con hilos reales (`TransactionTestCase`): doble reserva/venta de la misma unidad, sobre-reserva de cantidad.

## Verificación
- [x] `python manage.py check` en verde.
- [x] Tests relevantes ejecutados — ver "Evidencia".
- [x] Smoke test HTTP real contra PostgreSQL de desarrollo (flujo completo Cotización → Proforma → Reserva → Venta → Confirmación → Pago → Recibo → Adjunto, más aislamiento Multi-Tenant).
- [x] Seguridad revisada — autorización (`LoginRequiredMixin`+`TenantRequiredMixin`), IDs manipulados (404), CSRF, validación de archivos adjuntos (reutiliza FASE 9), sin exposición entre tenants.
- [x] Documentación actualizada — `docs/sales.md`, `docs/quotations.md`, `docs/proforma-invoices.md`, `docs/payments.md`, `docs/reservations.md`, `docs/returns.md`, `docs/invoice-documents.md` (nuevos); FASE 11-17 actualizadas con la interfaz que cada una debe consumir.
- [x] `docs/project-status/CURRENT_PHASE.md`, `PHASE_HISTORY.md` y `KNOWN_ISSUES.md` actualizados.
- [x] Git commit creado. — Ver historial de Git.

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

## Evidencia (FASE 10)

- Arquitectura separada: `models.py` (mixins compartidos, señal de limpieza de adjuntos), `services.py` (numeración, totales, máquinas de estado, conversión, reservas, pagos, devoluciones/reembolsos, auditoría), `forms.py`, `views.py` (delgadas, adjuntos compartidos entre los 3 documentos), `templates/sales/*.html` (Design System de FASE 5, tabs).
- `Quotation`/`ProformaInvoice`/`Sale` independientes (no una entidad con estados), líneas con `TenantScopedModel` propio (mismo patrón que `StockMovement`, FASE 8).
- Snapshot histórico verificado con test explícito: cambiar `Product.sale_price` después de agregar una línea no altera esa línea.
- Cálculo de totales: descuento por línea (% con prioridad sobre monto fijo, documentado) + descuento global (rebaja final documentada) + impuesto sobre base ya descontada — verificado con aritmética exacta en tests.
- Numeración `COT-`/`PRO-`/`FAC-`/`DEV-` por tenant y tipo de documento, `select_for_update()` sin duplicados.
- Reservas: capa derivada sobre `InventoryUnit`/stock real, nunca un segundo `StockMovement`; reserva EXPLÍCITA de proforma (nunca automática); liberación automática al cancelar/vencer.
- Confirmación de venta: reutiliza literalmente `apps.inventory.services` (QUANTITY/SERIALIZED), idempotente ante reintentos, rechaza SKU sin stock/unidad no disponible antes de escribir nada.
- Pagos: múltiples/parciales por venta, `payment_status` calculado (nunca asumido), `idempotency_key` sin duplicados, anulación idempotente.
- Devoluciones/Reembolsos: separados (mercancía vs. dinero); parcial/total; unidad serializada nunca reingresa sola a stock.
- Concurrencia: 3 tests con hilos reales (`TransactionTestCase`) — doble reserva de unidad, doble venta de unidad, sobre-reserva de cantidad — exactamente una operación gana en cada caso.
- Multi-Tenant: cobertura exhaustiva en `test_isolation.py` (lectura, listados, confirmar, cancelar, pagar, anular pago, liberar reserva, convertir, devolver, IDs manipulados, sesión manipulada).
- Performance: comparación de conteo de queries (listados y detalle con pagos) sin crecimiento.
- Bug real encontrado y corregido durante el desarrollo (mismo patrón de FASES 8/9): relación inversa `objects`/TenantManager fuera de request en `services.py` — detectado con un smoke test de servicios antes de escribir los tests formales, corregido con `get_quotation_items`/`get_proforma_items`/`get_sale_items` explícitos.
- 110 tests nuevos — 371/371 tests OK en total (261 de fases anteriores + 110 de FASE 10). Smoke test HTTP real contra PostgreSQL de desarrollo (flujo completo).
- Documentado en `docs/sales.md`, `docs/quotations.md`, `docs/proforma-invoices.md`, `docs/payments.md`, `docs/reservations.md`, `docs/returns.md`, `docs/invoice-documents.md`. Especificaciones de FASE 11-17 actualizadas con la interfaz que cada una debe consumir.
- Ningún módulo de negocio adicional (POS, Compras, Gastos, Reportes, Roles/Audit/API, PayPal, Billing, motor de facturación fiscal, `PaymentAllocation`, PDF binario) fue construido — todos documentados explícitamente en `docs/sales.md`.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 11 — POS.
