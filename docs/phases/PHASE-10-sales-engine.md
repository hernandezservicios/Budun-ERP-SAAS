# FASE 10 — Sales Engine + Cotizaciones + Proformas/Prefacturas + Facturas + Pagos

## Objetivo
Motor comercial central del ERP: Cotizaciones, Proformas/Prefacturas, Ventas/Facturas, Pagos (múltiples, parciales), Reservas, Devoluciones y Reembolsos — profesional, transaccional, seguro, multi-tenant, auditable, diseñado para que FASE 11 (POS) sea únicamente una interfaz operacional sobre este mismo motor.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] Venta atómica — `confirm_sale`/`record_payment_for_sale`/`allocate_payment`/`create_return`/`create_reservation` con `transaction.atomic()` + `select_for_update()`; idempotentes ante reintentos (verificado con hilos reales).
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
- [x] Smoke test HTTP real contra PostgreSQL de desarrollo (flujo completo Cotización → Proforma → Reserva → Venta → Confirmación → Pago → Recibo → Adjunto, más aislamiento Multi-Tenant; ampliación: ejemplo de un pago aplicado a 3 facturas, límites de sobre-aplicación, cross-tenant/cross-customer, reversa+reembolso, saldo a favor, flujo HTTP real de la pestaña "Pagos").
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
- Pagos y cuentas por cobrar: `Payment` + `PaymentAllocation` (ampliación obligatoria pedida por el usuario tras el cierre inicial de esta fase) — un pago puede aplicarse a una o varias facturas del mismo cliente, y una factura puede recibir asignaciones de varios pagos; `payment_status` calculado siempre desde el ledger (nunca asumido); saldo pendiente por factura y saldo sin aplicar por pago siempre calculados; `idempotency_key` sin duplicados; anulación/reversa idempotentes; saldo a favor del cliente y facturas pendientes como consultas reutilizables (preparación explícita para FASE 11); cross-tenant y cross-customer rechazados explícitamente; sobre-aplicación (más allá del pago o de la factura) rechazada incluso bajo concurrencia real (hilos). Ver `docs/payments.md`.
- Devoluciones/Reembolsos: separados (mercancía vs. dinero); parcial/total; unidad serializada nunca reingresa sola a stock.
- Concurrencia: 5 tests con hilos reales (`TransactionTestCase`) — doble reserva de unidad, doble venta de unidad, sobre-reserva de cantidad, doble asignación del mismo pago que excede lo disponible, doble asignación a la misma factura que excede su saldo pendiente — exactamente una operación gana en cada caso.
- Multi-Tenant: cobertura exhaustiva en `test_isolation.py` (lectura, listados, confirmar, cancelar, pagar, anular pago, liberar reserva, convertir, devolver, IDs manipulados, sesión manipulada).
- Performance: comparación de conteo de queries (listados y detalle con pagos) sin crecimiento.
- Bug real encontrado y corregido durante el desarrollo (mismo patrón de FASES 8/9): relación inversa `objects`/TenantManager fuera de request en `services.py` — detectado con un smoke test de servicios antes de escribir los tests formales, corregido con `get_quotation_items`/`get_proforma_items`/`get_sale_items` explícitos.
- **Ampliación obligatoria (Payment + PaymentAllocation)**: pedida explícitamente por el usuario tras el cierre inicial de esta fase ("un Payment puede aplicarse a una o varias facturas del mismo Customer"). `Payment.sale` se eliminó (reemplazado por `Payment.customer`, nulo solo para venta de mostrador); `PaymentAllocation` es el ledger append-only. Cambio de comportamiento intencional y documentado: un reembolso ahora solo puede salir del saldo SIN APLICAR de un pago (antes derivaba `REFUNDED` directamente) — `reverse_allocation` primero, `record_refund` después; dos tests de FASE 10 se actualizaron para reflejarlo (ver `docs/payments.md`). Vistas/plantillas de la pestaña "Pagos" del detalle de venta actualizadas para listar `PaymentAllocation` (no `Payment` directamente) y mostrar el saldo pendiente.
- 110 tests nuevos del cierre inicial + 18 de la ampliación Payment/PaymentAllocation (128 en `apps.sales`) — 389/389 tests OK en total (261 de fases anteriores + 128 de FASE 10). Smoke test HTTP real contra PostgreSQL de desarrollo (flujo completo).
- Documentado en `docs/sales.md`, `docs/quotations.md`, `docs/proforma-invoices.md`, `docs/payments.md`, `docs/reservations.md`, `docs/returns.md`, `docs/invoice-documents.md`. Especificaciones de FASE 11-17 actualizadas con la interfaz que cada una debe consumir.
- Ningún módulo de negocio adicional (POS, Compras, Gastos, Reportes, Roles/Audit/API, PayPal, Billing, motor de facturación fiscal, ledger contable completo de cuentas por cobrar, PDF binario) fue construido — todos documentados explícitamente en `docs/sales.md`/`docs/payments.md`.

## Doctrina de Cuentas por Cobrar (sincronización de fuentes de verdad, sin implementación nueva)

Tras aprobar la ampliación Payment + PaymentAllocation, el usuario
ordenó formalizar el dominio completo de cuentas por cobrar como
doctrina oficial del proyecto — documentación y arquitectura
únicamente, sin construir ningún sistema contable completo. Quedan
incorporados oficialmente a partir de esta fase (diseño aprobado,
implementación en la fase que corresponda):

- **`Payment`/`PaymentAllocation`** — ya construidos y en producción
  (ver arriba y `docs/payments.md`).
- **`Refund`** — ya construido (dinero que sale del sistema, separado
  de `Return`); extendido conceptualmente para poder convertirse en
  crédito en vez de salir como dinero, sin romper su contrato actual.
  Ver `docs/returns.md` y `docs/accounts-receivable.md` sección 5.
- **`CustomerCreditLedger`** — ledger append-only conceptual que
  unifica anticipo, sobrepago, nota de crédito y reembolso convertido
  a crédito en un único saldo a favor por cliente (nunca dos balances
  paralelos). Ver `docs/accounts-receivable.md`.
- **Anticipo (`CustomerAdvance`, concepto — no necesariamente un
  modelo nuevo)** — dinero recibido antes de una factura definitiva;
  ya representable hoy como un `Payment` sin `PaymentAllocation`. Un
  anticipo nunca es una venta. Ver `docs/accounts-receivable.md`.
- **`CreditNote`/`CreditNoteApplication`** — nota de crédito
  compensatoria, estructuralmente análoga a `Payment`/
  `PaymentAllocation` (misma validación de sobre-aplicación, mismo
  aislamiento por tenant/cliente, misma inmutabilidad vía reversa).
  Nunca altera la factura histórica. Ver `docs/accounts-receivable.md`.
- **Estado de cuenta del cliente (`Customer Statement`)** — vista
  futura de solo lectura sobre los modelos anteriores; pertenece a
  FASE 14, con un resumen básico anticipado en la ficha de cliente de
  FASE 9. Ver `docs/accounts-receivable.md`.
- **Trazabilidad financiera** — todo movimiento de crédito y toda
  aplicación de nota de crédito debe poder responder de dónde vino y a
  dónde se aplicó, mismo estándar que `Quotation → ProformaInvoice →
  Sale`.
- **Reversos e idempotencia** — `reverse_allocation`/`void_payment` ya
  cumplen este estándar; `CreditNoteApplication` deberá seguir
  exactamente el mismo patrón cuando se construya.

**No se agregó ningún modelo, campo ni migración con esta
sincronización** — `docs/accounts-receivable.md` es la fuente de
verdad completa para cuando una fase futura los construya.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada, incluyendo la ampliación Payment + PaymentAllocation y la sincronización de doctrina de cuentas por cobrar. Esperando autorización explícita para iniciar FASE 11 — POS.
