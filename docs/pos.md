# POS + Caja + Cobros + Autorizaciones (FASE 11)

`apps/pos` — la interfaz operacional de mostrador sobre el motor
comercial de FASE 10. **No es un segundo motor de ventas**: el carrito
es una `Sale` en `DRAFT` (`apps.sales`), la búsqueda es
`apps.inventory.services.search_catalog`, los clientes son
`apps.customers`, y los descuentos/crédito excedido pasan por
`apps.approvals`. Lo único nuevo en datos es la caja (`CashRegister`/
`CashSession`/`CashMovement`) y las notas de crédito (`CreditNote`/
`CreditNoteApplication`, en `apps.sales`, ver `docs/accounts-receivable.md`).

```
POS (apps.pos)
  ↓ orquesta, nunca duplica
Sales Engine (apps.sales) — Payment / PaymentAllocation / CreditNote
  ↓
Inventory (apps.inventory)
  ↓
Customers (apps.customers)
  ↓
CashRegister / CashSession (apps.pos, nuevo)
```

## Cajas y sesiones

Ver `docs/cash-registers.md` para el diseño completo. Resumen de lo
construido:

- `CashRegister`: sin límite fijo por tenant, con `authorized_users`
  (M2M) — el propietario del tenant siempre está autorizado para
  cualquier caja, sin necesidad de agregarlo explícitamente
  (`services.is_user_authorized_for_register`).
- `CashSession`: `UniqueConstraint` parcial por caja (`status=open`) Y
  por usuario (`status=open`, **deliberadamente global, sin `tenant`
  en los campos** — un usuario no puede tener dos sesiones abiertas ni
  siquiera en tenants distintos, no puede manejar efectivo en dos
  cajas físicas a la vez). La exclusividad por caja se protege con
  `select_for_update()` sobre la fila de la caja; la exclusividad por
  usuario, al no tener una única fila que bloquear, se protege en
  última instancia por la `UniqueConstraint` de base de datos —
  `services.open_cash_session` traduce el `IntegrityError` resultante
  de esa carrera a `InvalidPosOperation`, nunca lo deja escapar sin
  traducir.
- Fondo inicial de **0 es válido** (una caja puede abrirse sin efectivo
  de arranque) — el `CheckConstraint` de `CashMovement` permite monto 0
  únicamente para el tipo `OPENING`; cualquier otro movimiento debe ser
  estrictamente positivo.
- `CashMovement`: `OPENING`/`SALE_CASH`/`CASH_IN`/`CASH_OUT`/
  `CASH_REFUND`/`CUSTOMER_ADVANCE_CASH`/`WITHDRAWAL`/`ADJUSTMENT`.
  Solo el efectivo (`PaymentMethod.CASH`) genera movimientos — tarjeta/
  transferencia/PayPal quedan registrados como `Payment` en
  `apps.sales` sin tocar el efectivo físico.
- `services.get_expected_cash(session)`: agregación pura sobre
  `CashMovement`, nunca un campo editado a mano.
- `services.close_cash_session`: calcula esperado/contado/diferencia y
  **rechaza explícitamente** cerrar una sesión ya cerrada (no es un
  no-op: el resultado histórico de un cierre nunca se modifica).
- Regla obligatoria: `services.ensure_open_session_for_checkout`
  bloquea el checkout del POS sin sesión abierta y válida para quien
  cobra.

## Búsqueda y carrito

- `services.search(tenant, query)` delega literalmente en
  `apps.inventory.services.search_catalog` — nunca se reimplementa.
- `services.start_cart`/`add_item_to_cart`/`remove_cart_item`/
  `set_cart_customer`/`set_cart_global_discount` son delgados sobre
  `apps.sales.services` (`create_sale`/`add_sale_item`/
  `remove_sale_item`/`set_sale_global_discount`, esta última agregada
  en esta fase porque FASE 10 solo permitía fijar el descuento global
  al crear la venta).
- Producto SERIALIZADO encontrado por nombre/SKU/barcode
  (`SearchResult.requires_unit_selection`): la plantilla pide el IMEI/
  serie antes de poder agregarlo. IMEI/serie escaneado o tecleado
  directo: se resuelve server-side contra `InventoryUnit` (mismo
  patrón que `SaleItemForm` de FASE 10) y se agrega de inmediato.
- El identificador de una unidad en el carrito se muestra
  **enmascarado** (`···` + últimos 4 dígitos), mismo criterio de
  seguridad ya usado en `InventoryUnitAdmin` (FASE 8) — nunca el
  IMEI/serie completo en pantalla sin necesidad real.

## Descuentos: autorización por porcentaje Y por monto

`services.add_item_to_cart`/`set_cart_global_discount` calculan
**ambas** dimensiones del descuento (porcentaje y monto efectivo, sin
importar cuál escribió el cajero — ver
`_effective_discount_dimensions`) y llaman a
`apps.approvals.services.check_discount_authorization`. Si excede
cualquiera de los dos límites:

1. Se lanza `DiscountRequiresApproval` (nunca se aplica el descuento).
2. La vista captura la excepción y crea automáticamente una
   `ApprovalRequest` (`request_discount_approval`), mostrando el
   número al cajero.
3. Un usuario con permiso de aprobar (el propietario, siempre; o
   cualquier rol/usuario con `ApprovalPolicy.can_approve=True`) la
   resuelve en `/autorizaciones/`.
4. El cajero **reintenta la misma acción** (mismo producto/cantidad/
   descuento) — `add_item_to_cart` busca automáticamente una
   `ApprovalRequest` `APPROVED` y no consumida para esa venta
   (`_find_usable_discount_approval`) y, si el monto aprobado cubre lo
   solicitado, aplica el descuento y marca la solicitud como consumida
   (`mark_consumed`) — **nunca reutilizable** para una segunda línea.

Este flujo de dos pasos (bloquear → solicitar → aprobar en otra
pantalla → reintentar) es una simplificación deliberada frente a un
override de supervisor con PIN en el mismo terminal (no construido en
esta fase) — ver "Qué NO se construyó" más abajo.

## Crédito excedido

`services.check_credit_sale_authorization` calcula la deuda pendiente
actual del cliente (`apps.sales.services.get_customer_pending_sales`/
`get_sale_balance_due_bulk`, en una sola pasada — ver "Performance")
más el saldo que dejaría esta venta, y la compara contra
`customer.credit_limit` (FASE 9). Si excede y el usuario no tiene
autorización suficiente (`apps.approvals.services.check_credit_overage_authorization`),
`checkout_sale` lanza `CreditOverageRequiresApproval` — mismo flujo de
solicitud/aprobación/reintento que los descuentos, con
`action_type=CREDIT_OVERAGE`. Un cliente con `credit_enabled=False`
nunca dispara esta validación.

## Checkout: confirmar + cobrar (uno o varios métodos)

`services.checkout_sale` reutiliza literalmente `apps.sales.services.confirm_sale`
+ `record_payment_for_sale` (una llamada por método de pago) — nunca
reimplementa la aplicación de inventario ni el ledger de pagos. El
**cambio** (`pago_recibido − sale.total`) se calcula en la vista
(`CheckoutView`), nunca en `apps.sales`: el monto que llega a
`checkout_sale` para el método en efectivo ya está recortado al saldo
real de la venta — `record_payment_for_sale`/`allocate_payment` siguen
rechazando cualquier intento de aplicar más de lo que la venta debe,
exactamente como en FASE 10.

## Cobros de cuentas por cobrar (`/pos/cobros/`)

- **Facturas pendientes**: `apps.sales.services.get_customer_pending_sales`
  + `apply_payment_to_sales` (ya construidos en la ampliación de
  FASE 10) — un pago puede aplicarse a varias facturas del mismo
  cliente en una sola operación, seleccionando las casillas de la
  tabla.
- **Anticipos**: `services.register_customer_advance` — un `Payment`
  sin aplicar (`apps.sales.services.create_payment`), nunca una venta;
  en efectivo genera `CashMovement CUSTOMER_ADVANCE_CASH`.
- **Saldo a favor**: `services.apply_customer_credit_to_sale` agota
  primero los pagos sin aplicar del cliente (más antiguos primero),
  luego sus notas de crédito, hasta cubrir el monto pedido —
  **preserva el saldo restante** (nunca todo o nada) y nunca crea un
  balance manual: se apoya enteramente en `allocate_payment`/
  `apply_credit_note`, que ya validan sobre-aplicación/tenant/cliente.
- **Notas de crédito**: `services.issue_customer_credit_note`/
  `apply_credit_note_to_sale`, delgados sobre
  `apps.sales.services.create_credit_note`/`issue_credit_note`/
  `apply_credit_note` — ver `docs/accounts-receivable.md` para el
  diseño completo (ahora construido, ya no solo especificado).
- **Refunds**: `services.refund_payment_cash` (reutiliza
  `record_refund`, exige sesión de caja abierta, genera
  `CashMovement CASH_REFUND`) y `services.refund_payment_to_credit`
  (reutiliza `convert_refund_to_credit`, nunca toca la caja). Ninguno
  de los dos borra el `Payment` original — `on_delete=PROTECT` en toda
  la cadena, igual que el resto del proyecto desde FASE 8.

## Permisos

- **Operar una caja**: propietario del tenant siempre; cualquier otro
  usuario debe estar en `CashRegister.authorized_users`
  (`services.is_user_authorized_for_register`), verificado en el
  servidor — nunca solo ocultando el botón "Abrir caja" en la
  plantilla.
- **Crear cajas**: solo el propietario (`require_role(request, Membership.Role.OWNER)`).
- **Resolver autorizaciones / configurar políticas**: solo el
  propietario o un usuario con `ApprovalPolicy.can_approve=True` — ver
  `docs/approvals.md`.
- Cualquier otra operación del POS (vender, cobrar, registrar
  anticipos) está disponible para cualquier miembro autenticado del
  tenant — la restricción real está en los DESCUENTOS/CRÉDITO
  EXCEDIDO, no en el acceso a las pantallas en sí (FASE 15 podrá
  refinar esto con permisos más granulares por acción).

## Multi-Tenancy

Cobertura exhaustiva en `apps/pos/tests/test_isolation.py`: carrito,
checkout, cobros de cliente, apertura de caja y `ApprovalRequest` de
otro tenant siempre dan 404 o son invisibles — nunca confirman ni
niegan su existencia de otra forma. `apply_credit_note`/
`allocate_payment` además rechazan cross-tenant explícitamente a nivel
de servicio (segunda barrera, no solo HTTP).

## Concurrencia

Probado con hilos reales (`TransactionTestCase`, ver
`apps/pos/tests/test_concurrency.py`): dos aperturas simultáneas de la
misma caja, y dos aperturas simultáneas del mismo usuario en cajas
distintas — exactamente una gana en ambos casos.

## Performance

`apps.sales.services.get_sale_balance_due_bulk` (nueva en esta fase):
calcula el saldo pendiente de VARIAS ventas en 3 consultas totales, no
2×N — usada por `get_customer_pending_sales` y por la pantalla de
cobros del POS, evitando el N+1 que tendría iterar
`get_sale_balance_due` por cada factura pendiente de un cliente con
mucho historial. Verificado con comparación de conteo de queries
(pocas vs. muchas facturas/líneas de carrito).

## Moneda, denominaciones y cierre de caja (sincronización posterior a FASE 12, ver `docs/currency.md`)

El vocabulario oficial de cambio (`amount_due`/`amount_received`/
`change_amount`) y la regla de "el cambio se calcula solo sobre la
parte en efectivo de un pago mixto" **ya están implementados
correctamente** en `CheckoutView`/`checkout_sale` (ver arriba,
"Checkout: confirmar + cobrar") — esta sincronización solo formaliza
ese comportamiento como doctrina, sin ningún cambio de código. El
`CashMovement` de una venta con cambio ya registra el efecto neto
(nunca el bruto recibido y el cambio como dos movimientos separados).

Pendiente como especificación pura (nada de esto construido): moneda
operativa por `CashRegister`, catálogo `Currency`/`CurrencyDenomination`,
cierre por denominaciones (`CashDenominationCount`/`CashClosing`,
inmutable), y sugerencia de cambio por denominaciones (nunca
obligatoria para el cajero). Ver `docs/currency.md` para el diseño
completo. Hallazgo documentado (no corregido, fuera de alcance de una
sincronización documental): `checkout_sale` no bloquea explícitamente
un cobro insuficiente cuando la venta no tiene cliente o el cliente no
tiene crédito habilitado — ver `docs/currency.md` sección 7 y
`KNOWN_ISSUES.md`.

## Qué NO se construyó en esta fase (deliberado)

- **Override de supervisor con PIN en el mismo terminal**: el flujo de
  autorización es "bloquear → solicitar → aprobar en otra pantalla →
  reintentar", no un segundo factor inline sin salir de la venta en
  curso. Documentado como simplificación de UX, no de seguridad (la
  regla de negocio — nunca aplicar sin autorización real — se cumple
  igual).
- **Escaneo de cámara/QR**: primera versión es lector USB/teclado +
  entrada manual (`unit_identifier`), tal como pidió explícitamente el
  usuario. La arquitectura (`services.search`/`add_item_to_cart`) no
  depende de ningún hardware concreto — un futuro selector por cámara
  solo necesita producir el mismo texto que hoy escribe el cajero.
- **Permisos granulares por acción vía FASE 15**: hoy la única
  restricción real más allá de "miembro del tenant" es autorizar cajas
  y descuentos/crédito excedido — el resto de permisos listados en la
  autorización de esta fase (ver/realizar cierres, ajustes de caja,
  etc.) se refinarán cuando FASE 15 construya el modelo de roles más
  rico.
- **`CustomerCreditLedger` como tabla separada**: el saldo a favor
  sigue derivándose de `Payment`/`PaymentAllocation` +
  `CreditNote`/`CreditNoteApplication` (dos ledgers reales ya
  existentes), nunca de una tercera tabla que los resuma — ver
  `docs/accounts-receivable.md`, "Regla de no-duplicación".
- POS multi-idioma, reportes de caja consolidados multi-sucursal,
  Compras (FASE 12), Gastos (FASE 13), Reportes completos (FASE 14).
