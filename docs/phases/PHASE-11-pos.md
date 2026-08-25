# FASE 11 — POS

## Objetivo
POS rápido y usable: búsqueda, barcode, carrito, cliente, pago, cambio, recibo.

## Regla incremental
Crear únicamente lo necesario para esta fase y sus dependencias inmediatas. No implementar funcionalidades de fases futuras.

## Criterios de aceptación
- [x] flujo completo — buscar → carrito → cliente → descuento → cobrar (uno o varios métodos) → recibo; más caja (abrir/cerrar) y cobros de cuentas por cobrar (facturas pendientes/anticipos/saldo a favor/notas de crédito/refunds).
- [x] mobile/touch usable — Design System de FASE 5 (responsive ya establecido), sin componentes que dependan de hover/mouse.
- [x] no duplicados — mismo `SaleItem`/`InventoryUnit` no se puede vender dos veces (máquina de estados de FASE 8 a nivel de inventario); el POS reutiliza literalmente `apps.sales`/`apps.inventory`/`apps.customers`/`apps.approvals`, sin un segundo motor de ventas.

## Verificación
- [x] `python manage.py check` en verde.
- [x] Tests relevantes ejecutados — ver "Evidencia".
- [x] Smoke test HTTP real contra PostgreSQL de desarrollo (flujo completo caja→carrito→descuento con autorización→checkout multi-pago→cierre de caja→cobros→anticipo→nota de crédito→refund a crédito, más aislamiento Multi-Tenant).
- [x] Seguridad revisada — autorización (`LoginRequiredMixin`+`TenantRequiredMixin`+permiso de caja/propietario), IDs manipulados (404), CSRF, descuentos/crédito excedido nunca aplicables sin autorización real (servidor, no frontend).
- [x] Documentación actualizada — `docs/pos.md` (nuevo); `docs/cash-registers.md`/`docs/approvals.md`/`docs/accounts-receivable.md` actualizados de especificación a "construido".
- [x] `docs/project-status/CURRENT_PHASE.md`, `PHASE_HISTORY.md` y `KNOWN_ISSUES.md` actualizados.
- [x] Git commit creado. — Ver historial de Git.

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

## Nota de FASE 10 — El POS es una interfaz sobre el motor comercial, no un motor propio

FASE 10 construyó el motor comercial completo (`apps/sales`, ver
`docs/sales.md`) explícitamente para que este POS sea una interfaz
operacional sobre él — "el POS no debe tener su propio motor de
ventas". Reutilizar tal cual:

- **Buscar cliente**: `apps.customers.services.list_customers`/
  `get_active_customers` (ya lo anticipaba la nota de FASE 9 arriba).
- **Buscar producto / IMEI / serie**: `apps.inventory.services.search_catalog`
  (ya lo anticipaba la nota de FASE 8 arriba) — el resultado
  (`SearchResult`) ya indica si hace falta pedir IMEI/serie
  (`requires_unit_selection`) o si ya resolvió una unidad concreta.
- **Agregar al carrito**: el "carrito" del POS es, en términos de FASE 10,
  una `Sale` en estado `DRAFT` — cada producto agregado es
  `services.add_sale_item(sale, product=..., quantity=..., inventory_unit=...)`.
  No inventar una estructura de carrito paralela en memoria/sesión que
  luego haya que traducir a `Sale`; usar la `Sale` en `DRAFT` como el
  carrito real desde el primer clic evita esa traducción y hereda
  gratis el cálculo de totales con snapshot (`docs/sales.md`).
- **Reservar**: `services.create_reservation` (opcional, cuando el POS
  quiera apartar stock antes de cobrar — no es obligatorio en el flujo
  de mostrador típico).
- **Confirmar / cobrar**: `services.confirm_sale` seguido de uno o más
  `services.record_payment_for_sale` (efectivo + tarjeta, pago parcial o
  múltiple — ver `docs/payments.md`) — el "cambio" a entregar es
  `pago_recibido − sale.total`, calculado en la vista/plantilla del
  POS, no en `apps.sales`.
- **Cobrar facturas pendientes / un solo pago a varias facturas**:
  ampliación obligatoria de FASE 10 pedida explícitamente para que este
  POS pueda cobrar cuentas por cobrar reales, no solo la venta actual:
  `services.get_customer_pending_sales(customer)` para listar las
  facturas `CONFIRMED`/`PARTIALLY_RETURNED` con saldo pendiente de un
  cliente, y `services.create_payment` + `services.apply_payment_to_sales`
  para aplicar un único pago repartido entre varias de ellas (mismo
  mecanismo que el ejemplo "Pago 20,000 → Factura A 10,000 / B 7,500 /
  C 2,500" de `docs/payments.md`) — el motor ya valida que la suma
  nunca exceda ni lo disponible del pago ni el saldo de cada factura;
  el POS solo necesita construir la lista `[{sale, amount}, ...]` desde
  la selección del cajero.
- **Imprimir recibo**: reutilizar `sale_receipt.html`/la vista
  `SaleReceiptView` de FASE 10 (ver `docs/invoice-documents.md`), no
  crear una segunda plantilla de recibo.
- **Cancelar**: `services.cancel_sale` (solo válido en `DRAFT`, es decir,
  antes de confirmar/cobrar — igual que el resto del sistema).
- **Devolver**: `services.create_return` (ver `docs/returns.md`).
- **No duplicados**: el mismo `SaleItem`/`InventoryUnit` no debe poder
  agregarse dos veces al carrito — la máquina de estados de FASE 8
  (`EN_STOCK`/`RESERVADO` → `VENDIDO`) ya lo impide a nivel de
  inventario al confirmar; el POS además debe evitar agregar la misma
  unidad dos veces al carrito EN PANTALLA (antes de confirmar), por
  UX, revisando `unit.pk` en el estado del carrito.

## Cajas, Cuentas por Cobrar y Autorizaciones — construido en esta fase

Sincronización de doctrina ordenada por el usuario tras aprobar la
ampliación Payment + PaymentAllocation, previa a iniciar esta fase
(documentación y arquitectura en ese momento). Todo lo siguiente ya
está construido:

- **Múltiples cajas/terminales (`CashRegister`)**: el tenant puede
  crear cualquier cantidad de cajas, sin límite fijo de diseño. Ver
  `docs/cash-registers.md`.
- **`CashSession`**: apertura/cierre de jornada de caja, con las
  reglas de exclusividad (un usuario o una caja no pueden tener dos
  sesiones `OPEN` simultáneas salvo permiso explícito), conciliación
  al cierre (efectivo esperado vs. contado, sobrante/faltante), y
  **bloqueo obligatorio**: ninguna venta operativa de mostrador se
  confirma sin una `CashSession` abierta y válida. Ver
  `docs/cash-registers.md`.
- **`CashMovement`**: apertura, venta en efectivo, anticipo en
  efectivo, entradas/salidas, devoluciones en efectivo, retiros,
  ajustes autorizados. Solo el efectivo afecta el efectivo físico —
  tarjeta/transferencia/PayPal quedan registrados en la sesión sin
  sumar a `expected_cash`. Ver `docs/cash-registers.md`.
- **Anticipos y saldo a favor operacional**: el POS debe poder recibir
  un anticipo (`services.create_payment` sin aplicar todavía) y
  aplicar el saldo a favor de un cliente (`get_customer_credit_balance`)
  a una factura nueva o pendiente. Ver `docs/accounts-receivable.md`.
- **Notas de crédito**: el POS debe poder aplicar una `CreditNote`
  existente a una factura (cuando el modelo se construya en esta
  fase o una posterior autorizada) con la misma disciplina de
  validación que `PaymentAllocation`. Ver `docs/accounts-receivable.md`.
- **Refunds**: cobro/devolución de dinero en efectivo desde el POS
  reutiliza `services.record_refund` (nunca una segunda
  implementación); cuando la política lo permita, un refund puede
  convertirse en crédito en vez de salir como efectivo (ver
  `docs/accounts-receivable.md`, sección 5).
- **Autorización de descuentos**: por porcentaje Y por monto, cada uno
  con su propio límite por rol/usuario, resolviendo la jerarquía
  usuario → rol → tenant → negar. Exceder cualquiera de los dos
  límites dispara un `ApprovalRequest`. Ver `docs/approvals.md`.
- **Autorización de crédito excedido**: venta a crédito que supera
  `customer.credit_limit`/`credit_days` requiere `ApprovalRequest` si
  el cajero no tiene autorización suficiente. Ver `docs/approvals.md`.
- **`ApprovalService`**: servicio centralizado y reutilizable — el POS
  lo consume, nunca implementa su propia lógica de aprobación. Ver
  `docs/approvals.md`.

Estos documentos (`docs/accounts-receivable.md`, `docs/cash-registers.md`,
`docs/approvals.md`) son la fuente de verdad de diseño para esta fase;
deben releerse antes de implementar, no re-derivarse desde cero.

## Evidencia (FASE 11)

- Arquitectura: `apps/pos` (POS + caja, orquestación pura sobre `apps.sales`/`apps.inventory`/`apps.customers`/`apps.approvals`) y `apps/approvals` (autorizaciones, app nueva y reutilizable) — dos apps pequeñas y enfocadas, nunca un segundo motor de ventas.
- `CashRegister`/`CashSession`/`CashMovement`: ilimitadas por tenant; exclusividad por caja (`select_for_update()`) y por usuario (`UniqueConstraint` global, `IntegrityError` traducido a `InvalidPosOperation`); fondo inicial en 0 válido; solo el efectivo afecta el efectivo esperado; cierre calcula esperado/contado/diferencia y rechaza (no permite) cerrar una sesión ya cerrada.
- `ApprovalPolicy`/`ApprovalRequest`: jerarquía usuario→rol→tenant→negar; descuentos autorizables por % Y por monto (exceder cualquiera de los dos exige autorización); crédito excedido; `consumed_at`/`consumed_by` para que una aprobación nunca se reutilice; propietario del tenant siempre autorizado (regla explícita).
- `CreditNote`/`CreditNoteApplication` (en `apps.sales`): estructuralmente análogos a `Payment`/`PaymentAllocation`, misma disciplina de validación; `get_customer_credit_balance`/`get_sale_paid_amount` generalizados para sumar ambos ledgers — `CustomerCreditLedger` como tabla separada se descartó deliberadamente.
- Checkout: `confirm_sale` + uno o varios `record_payment_for_sale` (reutilizados literalmente); "cambio" calculado en la vista; crédito excedido y descuentos verificados antes de confirmar.
- Cobros: facturas pendientes (`apply_payment_to_sales`, un pago a varias facturas), anticipos (`Payment` sin aplicar), saldo a favor (agota pagos sin aplicar antes que notas de crédito, preserva el resto), refunds efectivo (con `CashMovement`) o a crédito (`convert_refund_to_credit`).
- 2 bugs reales encontrados y corregidos durante el desarrollo de los tests: `checkout_sale` devolvía `Sale.payment_status` desactualizado (`.update()` en base de datos nunca refresca la instancia en memoria — se agregó `refresh_from_db()`); `CashMovement` rechazaba fondo inicial 0 (`CheckConstraint` corregido para permitirlo solo en `OPENING`).
- 1 N+1 real encontrado y corregido: `get_customer_pending_sales` recalculaba el saldo de cada factura por separado — resuelto con `get_sale_balance_due_bulk` (3 consultas totales, nunca 2×N), verificado con comparación de conteo de queries.
- Concurrencia: 2 tests con hilos reales (`TransactionTestCase`) — doble apertura de la misma caja, doble apertura del mismo usuario en cajas distintas — exactamente una gana en ambos casos.
- Multi-Tenant: cobertura exhaustiva en `apps/pos/tests/test_isolation.py` y `apps/approvals/tests/test_isolation.py` (carrito, checkout, cobros, apertura de caja, `ApprovalRequest`, `apply_credit_note` cross-tenant a nivel de servicio).
- Seguridad: `LoginRequiredMixin`+`TenantRequiredMixin` en toda vista; permiso de caja (propietario o `authorized_users`) y de aprobación (propietario o `can_approve`) verificados en el servidor, nunca solo ocultando botones; IDs manipulados → 404; descuentos/crédito excedido nunca aplicables sin autorización real.
- 113 tests nuevos (68 en `apps.pos`, 45 en `apps.approvals` + notas de crédito de `apps.sales`) — 502/502 tests OK en total (389 de fases anteriores + 113 de FASE 11). Smoke test HTTP real contra PostgreSQL de desarrollo (44 verificaciones: apertura de caja con/sin autorización, carrito con producto por cantidad y serializado, descuento con flujo de autorización completo, checkout multi-pago, cierre de caja, cobro de factura pendiente, anticipo, nota de crédito, saldo a favor, refund a crédito, aislamiento Multi-Tenant), sin tenants huérfanos tras la limpieza.
- Documentado en `docs/pos.md` (nuevo); `docs/cash-registers.md`, `docs/approvals.md`, `docs/accounts-receivable.md` actualizados de especificación a "construido"; `docs/sales.md`/`docs/payments.md`/`docs/customers.md` referencian los documentos nuevos donde corresponde.
- Ningún módulo de negocio adicional (Compras, Gastos, Reportes, Roles/Audit/API, PayPal, Billing) fue construido; permisos granulares por acción más allá de caja/descuentos/crédito quedan para FASE 15; override de supervisor con PIN en el mismo terminal y escaneo por cámara/QR quedan documentados como simplificaciones deliberadas de UX (no de seguridad) en `docs/pos.md`.

## Nota de sincronización — Moneda, denominaciones y cierre de caja (posterior a FASE 12)

Doctrina oficial agregada en `docs/currency.md` (sin implementación,
sin cambios de código en `apps.pos`): `CashRegister` no tiene hoy
ningún campo de moneda — el diseño oficial prevé agregarle `currency`
(FK a un futuro `Currency`) para que su `CashSession` cuente
físicamente en una sola moneda. `CashDenominationCount`/`CashClosing`
(cierre por denominaciones, inmutable) quedan especificados, no
construidos. **Confirmado, sin cambio de código**: el vocabulario
`amount_due`/`amount_received`/`change_amount` y el efecto neto de
`CashMovement` en una venta con cambio (ej. venta 1275, cliente entrega
2000 → movimiento `+1275`, nunca `+2000`/`-725`) ya estaban
implementados correctamente en `CheckoutView`/`checkout_sale` desde el
cierre de esta fase — la sincronización solo los nombra oficialmente.
Ver `docs/currency.md`/`docs/cash-registers.md` secciones 11-12/`docs/pos.md`.

## Dependencias
Revisar fases anteriores y `docs/phases/PHASES.md`.

## Cierre
No cerrar la fase sin evidencia. Al cerrarla, detenerse y esperar autorización para iniciar la siguiente, salvo instrucción explícita del usuario.

**Estado: PASS.** Fase cerrada. Esperando autorización explícita para iniciar FASE 12 — Purchases.
