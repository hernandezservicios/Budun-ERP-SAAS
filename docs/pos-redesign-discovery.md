# FASE 7 — POS LAB PROFUNDO — ETAPA 1 — DISCOVERY

Auditoría de solo lectura del POS operativo real de Budun ERP SaaS
(`apps/pos`, más las dependencias reales en `apps/sales`, `apps/inventory`,
`apps/customers`, `apps/approvals`, `apps/accounting`, `apps/permissions`).
Cero archivos modificados. Cero funcionalidad inventada — todo lo descrito
aquí está citado contra código real (archivo:línea donde fue posible).
Metodología: 6 auditorías paralelas de solo lectura (terminal/carrito/
productos/inventario; cliente/descuentos/impuestos/pagos; venta/
devoluciones/IMEI/contabilidad; caja completa; comprobantes/permisos/
estados/tests; UI-UX/CSS-JS/aislamiento), sintetizadas en este documento.

---

## 1. Pantallas reales encontradas

| Template | Vista | URL name | Extiende |
|---|---|---|---|
| `apps/pos/templates/pos/terminal.html` | `TerminalDetailView`/`TerminalStartView` | `pos:terminal_detail`/`pos:terminal_start` | `layout_app.html` |
| `apps/pos/templates/pos/register_list.html` | `CashRegisterListView` | `pos:register_list` | `layout_app.html` |
| `apps/pos/templates/pos/session_open.html` | `CashSessionOpenView` | `pos:session_open` | `layout_app.html` |
| `apps/pos/templates/pos/session_close.html` | `CashSessionCloseView` | `pos:session_close` | `layout_app.html` |
| `apps/pos/templates/pos/session_summary.html` | `CashSessionSummaryView` | `pos:session_summary` | `layout_app.html` |
| `apps/pos/templates/pos/collections_search.html` | `CollectionsSearchView` | `pos:collections_search` | `layout_app.html` |
| `apps/pos/templates/pos/customer_collections.html` | `CustomerCollectionsView` | `pos:customer_collections` | `layout_app.html` — **ya migrado a Atlas en FASE 5, fuera del alcance de FASE 7** |
| `apps/sales/templates/sales/sale_receipt.html` | `SaleReceiptView` (`apps.sales`) | `sales:sale_receipt` | `base.html` directamente (**no** `layout_app.html`) — comprobante final del checkout POS, adyacente pero fuera de `apps.pos` |

**No existe** ningún template de "movimiento de caja" (la vista `CashMovementCreateView` no tiene ningún template/botón que la invoque — ver §14.3) ni ningún template propio de "comprobante POS" (reutiliza `sales:sale_receipt`).

---

## 2. Flujos reales (reconstruidos del código, no asumidos)

### 2.1 Flujo de venta — terminal → carrito → checkout
1. `GET pos:terminal_start` — busca/crea la `Sale` `DRAFT` del cajero actual (`services.start_cart`). Regla: **nunca más de un carrito activo por cajero**.
2. Buscar producto: campo único `q` → `services.search` → `inventory.services.search_catalog`. Coincidencia exacta de serial/IMEI resuelve una unidad directamente; si no, busca por nombre/SKU/código de barras entre productos activos.
3. Resultado: si el producto es SERIALIZED y no se resolvió por IMEI exacto, exige un campo `unit_identifier` (texto) antes de poder agregar.
4. Agregar al carrito (`AddItemView` → `services.add_item_to_cart` → `sales.services.add_sale_item`): snapshot de `unit_price`/`tax_rate` del producto, recálculo de totales de línea y documento. Descuento por línea evaluado contra `apps.approvals`.
5. Carrito: única acción sobre una línea existente es "Quitar" — no hay edición de cantidad/precio/descuento ya agregado.
6. Cliente: `<select>` opcional (`CustomerSelectForm`) — vacío = "Consumidor final". Cambiable en cualquier momento mientras `DRAFT`.
7. Descuento global: mismo mecanismo de autorización que el de línea, sobre `sale.subtotal`.
8. Cobrar (`CheckoutView` → `services.checkout_sale`): exige `CashSession` abierta; valida que lo cobrado cubra el total o que el cliente tenga crédito suficiente (si no, exige `ApprovalRequest`); llama a `sales.services.confirm_sale` (aquí se mueve inventario de verdad — `register_stock_out` para QUANTITY, `transition_unit_status(..., VENDIDO)` para SERIALIZED, snapshot de `cost_amount`); registra `Payment`+`PaymentAllocation` por cada método; si hay efectivo, registra `CashMovement` tipo `SALE_CASH` (monto neto, ya con el cambio restado).
9. Redirige a `sales:sale_receipt` (recibo HTML imprimible, fuera del namespace `pos:`, sin enlace de regreso al terminal).

Todo el checkout corre en una única transacción atómica; `confirm_sale` es idempotente (reintento no duplica).

### 2.2 Flujo de caja
1. **Apertura** (`pos:session_open`): elegir `CashRegister` activa del tenant + `opening_amount` (monto único) + notas → crea `CashSession(OPEN)` + `CashMovement(OPENING)` automático.
2. **Movimientos manuales**: backend completo (`cash_in`/`cash_out`/`withdrawal`) vía `CashMovementForm`, pero **sin ningún botón/enlace en ninguna pantalla del proyecto** — inalcanzable desde la UI (ver §14.3).
3. **Cierre** (`pos:session_close`): un único campo `counted_cash` (monto total, sin desglose por denominación) + notas → calcula `expected_cash` (agregación de todos los `CashMovement`), `difference = counted_cash - expected_cash`, cierra la sesión, dispara contabilización automática de sobrante/faltante (`cash_over`/`cash_short`).
4. **Resumen** (`pos:session_summary`): solo alcanzable inmediatamente tras cerrar (sin índice histórico, sin protección de permiso real — ver §10).

### 2.3 Flujo de devoluciones/reembolsos (dos caminos separados, ninguno dentro del terminal)
- **Devolución de mercancía** (`Return`): vive exclusivamente en `apps.sales` (`sale_detail.html` → "Registrar devolución"), no enlazada desde ningún template de `apps.pos`.
- **Reembolso de dinero** (`Refund`): accesible desde `pos:customer_collections` (Cobros), un módulo separado del terminal, alcanzado buscando primero al cliente.

---

## 3. Modelos involucrados

**`apps/pos/models.py`** (únicos modelos propios del POS):
- `CashRegister`: `tenant`, `name`, `code` (único por tenant), `status` (`active`/`inactive`), `terminal`, `authorized_users` (M2M), `created_at`. Sin campo `currency`.
- `CashSession`: `cash_register` FK, `user` FK, `opened_at`, `opening_amount`, `closed_at`, `expected_cash`, `counted_cash` (monto único), `difference`, `status` (`open`/`closed`), `notes`, `closing_notes`. Constraints DB: una sesión abierta por caja y una por usuario (esta última deliberadamente global, sin tenant).
- `CashMovement`: `cash_session` FK, `movement_type` (12 valores, ver §11), `amount` (>0, salvo `opening`), `user` FK, `reason` (opcional pese a que la doctrina documentada lo pide obligatorio para salidas/ajustes), `reference_type`/`reference_id`, `created_at`. Append-only.

**El "carrito" NO es un modelo del POS**: es literalmente una `Sale` (`apps.sales.models.Sale`) en estado `DRAFT` — el POS no reimplementa el modelo de venta.

**Consumidos por el POS (nunca reimplementados)**: `apps.sales.Sale`/`SaleItem`/`Payment`/`PaymentAllocation`/`PaymentMethod`/`Return`/`Refund`/`CreditNote`/`CreditNoteApplication`/`Reservation`; `apps.inventory.Product`/`InventoryUnit`; `apps.customers.Customer`; `apps.approvals.ApprovalPolicy`/`ApprovalRequest`.

**No implementados aún** (verificado ausencia real): `CashDenominationCount`, `CurrencyDenomination`, `CurrencyConfiguration`, `CashClosing`, `Currency` — todos parte de la doctrina de moneda (`docs/currency.md`), confirmada por el propio documento como "no construido todavía".

---

## 4. Views reales

`apps/pos/views.py`: `TerminalStartView`, `TerminalDetailView`, `AddItemView`, `RemoveItemView`, `SetCustomerView`, `SetGlobalDiscountView`, `CancelCartView`, `CheckoutView`, `CashRegisterListView`, `CashSessionOpenView`, `CashSessionCloseView`, `CashSessionSummaryView`, `CashMovementCreateView`, `CollectionsSearchView`, `CustomerCollectionsView`, `CollectPaymentView`, `RegisterAdvanceView`, `IssueCreditNoteView`, `ApplyCreditView`, `RefundView`.

Todas heredan únicamente `LoginRequiredMixin` + `TenantRequiredMixin` (que solo exige `request.tenant is not None`, sin distinguir rol). Enforcement de permisos granulares real solo en 3: `CashSessionOpenView`/`CashSessionCloseView`/`CashMovementCreateView` (`cash.open`/`cash.close`/`cash.move`). `CashRegisterListView` usa `require_role(OWNER)` (rol binario, no permiso granular). El resto —incluido todo el terminal de venta— no llama a `require_permission` en absoluto (ver §10).

Dependencias reales invocadas por `apps/pos/views.py`: `apps.sales.services` (`create_sale`, `add_sale_item`, `remove_sale_item`, `set_sale_global_discount`, `confirm_sale`, `cancel_sale`, `record_payment_for_sale`, `create_payment`/`apply_payment_to_sales`, `get_sale_balance_due(_bulk)`, `get_customer_pending_sales`, `get_customer_credit_balance`, `create_credit_note`/`issue_credit_note`, `record_refund`/`convert_refund_to_credit`), `apps.inventory.services.search_catalog`, `apps.approvals.services` (`check_discount_authorization`, `check_credit_sale_authorization`, `request_approval`, `mark_consumed`, `get_usable_approved_request`), `apps.customers.services.list_customers` (solo en Cobros, no en el terminal).

---

## 5. Forms reales

`apps/pos/forms.py`: `PosSearchForm` (campo único `q`), `PosAddItemForm` (`product_id`, `unit_identifier`, `quantity`, `discount_percent`, `discount_amount` — sin campo de precio unitario ni de impuesto), `CustomerSelectForm` (`customer` + `customer_search` **vestigial, sin efecto real**), `GlobalDiscountForm`, `CheckoutPaymentForm`/`CheckoutPaymentFormSet` (`extra=2`, sin botón de agregar fila adicional en la UI), `OpenSessionForm` (`cash_register`, `opening_amount`, `notes`), `CashMovementForm` (solo 3 de los 12 tipos reales del modelo: `cash_in`/`cash_out`/`withdrawal`), `CloseSessionForm` (`counted_cash` único + `closing_notes` — sin ningún campo de denominaciones), `CollectPaymentForm`, `CustomerAdvanceForm`, `RefundForm` (`mode`: `cash`/`credit`).

La fila de "Agregar producto" en `terminal.html` (columnas Cantidad/Descuento %/Descuento $/IMEI) **no pasa por `_campo.html`** — está escrita a mano en HTML, sin `<label>` asociado (solo `placeholder` en descuentos).

---

## 6. Services reales

`apps/pos/services.py` es la capa de orquestación completa: `search`, `start_cart`, `get_cart_items`, `remove_cart_item`, `set_cart_customer`, `add_item_to_cart`, `set_cart_global_discount`, `checkout_sale`, `ensure_open_session_for_checkout`, `open_cash_session`, `record_cash_movement`, `get_expected_cash`, `close_cash_session`, `collect_customer_payment`, `register_customer_advance`, `apply_customer_credit_to_sale`, `issue_customer_credit_note`, `refund_payment_cash`/`refund_payment_to_credit`, `request_discount_approval`/`request_credit_overage_approval`.

Principio de diseño confirmado línea por línea: el POS **nunca reimplementa reglas de negocio de ventas** — delega literalmente en `apps.sales.services`. Excepciones propias del POS: `DiscountRequiresApproval`, `CreditOverageRequiresApproval`, `InsufficientPaymentError` (excepciones específicas del checkout).

---

## 7. URLs reales

`apps/pos/urls.py` (namespace `pos:`): `terminal/`, `terminal/<pk>/`, `terminal/<pk>/agregar/`, `terminal/<pk>/lineas/<item_pk>/eliminar/`, `terminal/<pk>/cliente/`, `terminal/<pk>/descuento/`, `terminal/<pk>/cancelar/`, `terminal/<pk>/cobrar/`, rutas de `register_list`/`session_open`/`session_close`/`session_summary`/`cash_movement_create`, `collections_search`/`customer_collections`/`collect_payment`/`register_advance`/`issue_credit_note`/`apply_credit`/`refund_payment`.

**Sin ninguna ruta** de devolución/anulación de venta confirmada, ni de edición de línea de carrito.

---

## 8. JavaScript

**Sin JS propio del POS.** Cero archivo dedicado en `static/js/`, cero `<script>` inline en los 6 templates en alcance (único `onsubmit="return confirm(...)"` en "Cancelar carrito"). Todo el flujo es HTML + POST/GET con recarga completa de página — cero AJAX, cero autocompletar, cero cálculo de cambio en vivo, cero autofocus, cero atajos de teclado.

`static/js/ui.js` (compartido, cargado en toda página vía `base.html`) provee sidebar/dropdown/toasts genéricos — ninguna función referencia carrito/caja/POS.

---

## 9. CSS

**Sin CSS propio del POS.** Cero archivo dedicado, cero `<style>` inline. Cascada compartida: `base.css` (tokens/reset) → `design-system.css` (librería global de componentes, sin scope de shell — `.btn`/`.tarjeta`/`.tabla`/`.badge`/`.campo`/`.kpi*` etc.) → `design-system-erp.css` (Atlas, scope `.shell--erp`).

**Hallazgo central**: el POS **hereda pasivamente el theming Atlas** porque `layout_app.html` (shell migrado en FASE 5) envuelve sus 6 pantallas en `.shell--erp`, y usa las mismas clases compartidas que las 13 pantallas migradas — mismo azul `#1D4E89`, misma tipografía IBM Plex, sin que nadie haya tocado su HTML. Lo que NO hereda son las utilidades de nivel de plantilla introducidas en FASE 5 (`.u-cifra`, `.u-num`, `.u-grid-2col`, iconos SVG en vacíos) — cero ocurrencias en los 6 templates.

**Riesgos reales confirmados** (no hipotéticos, verificados por grep):
- `terminal.html:125` — grid `1fr 1fr` inline sin colapsar en móvil — el mismo patrón que `design-system-erp.css` (líneas 129-145) documenta explícitamente como anti-patrón ya resuelto en `customer_collections.html` vía `.u-grid-2col`, pero **nunca aplicado al terminal**. Confirmado independientemente por 4 de los 6 agentes.
- Anchos fijos en `rem` (`width:5rem`/`9rem`) en los inputs de la fila de búsqueda, sin responsive.
- Filas `display:flex` sin `flex-wrap` (formulario de búsqueda, fila de pago) — en viewport angosto, combinado con `body{overflow-x:hidden}` global, el contenido se recorta silenciosamente en vez de generar scroll visible.
- Cero colores hardcodeados, cero `!important` en los templates del POS (el único `!important` de todo el flujo vive en `sale_receipt.html`, fuera de `apps.pos`, dentro de un `@media print`).
- `sale_receipt.html` extiende `base.html` directamente (no `layout_app.html`) — no tiene sidebar/topbar Atlas, usa el azul `#1d4ed8` (SaaS/compartido) en vez del azul Atlas `#1D4E89` — el cajero termina el flujo de cobro en una pantalla visualmente distinta.
- Emoji como iconos de estado vacío (🛒/🗂️/🏪/🔍) en los 6 templates del POS, pese a que la regla Atlas documentada explícitamente dice "nunca emoji" (ya aplicada en `customer_collections.html` con SVG).
- Duplicación de código notada: tabla de "Movimientos de sesión" copiada verbatim entre `session_close.html` y `session_summary.html`; patrón de tarjeta-con-formulario repetido 3+ veces sin `{% include %}`; breadcrumb repetido idéntico en 4 templates.

---

## 10. Permisos reales — HALLAZGO CRÍTICO

Catálogo (`apps/permissions/catalog.py`), dominio `"pos"`: `pos.use`, `cash.open`, `cash.close`, `cash.move`, `cash.view`. Dominio `"sales"`: `sales.create`/`sales.update`/`sales.cancel`/`sales.refund`, `payments.create`/`payments.reverse`, `credit.view`/`credit.apply`, `credit_note.*`.

**Solo 3 de todos estos están realmente aplicados en código** (`require_permission`): `cash.open`, `cash.close`, `cash.move` (los 3 en `apps/pos/views.py`, endpoints de caja).

**No aplicados en ninguna vista (confirmado por grep exhaustivo):**
- `pos.use` — nada impide a un usuario sin este permiso usar el terminal.
- `cash.view` — `CashSessionSummaryView` no tiene ningún chequeo de permiso; cualquier miembro del tenant puede ver el resumen de cualquier sesión de caja (incluida la de otro cajero) conociendo/adivinando el `pk`.
- **Todo `apps/sales/views.py`**: `sales.create`, `sales.update`, `sales.cancel`, `sales.refund`, `payments.create`, `payments.reverse`, `credit.view`, `credit.apply`, `credit_note.*` — ninguno tiene un `require_permission`/`require_role` real en el archivo completo.

Consecuencia práctica verificada: todas las vistas del terminal (agregar/quitar línea, cliente, descuento, cancelar, checkout) y todas las de `apps.sales` (crear/confirmar/cancelar venta, pago, devolución) heredan solo `LoginRequiredMixin`+`TenantRequiredMixin` — **cualquier usuario con membresía activa de cualquier rol** (incluso `EMPLOYEE`/`MEMBER`, que por defecto NO tienen `pos.use` en `DEFAULT_ROLE_PERMISSIONS`) puede técnicamente vender, cancelar ventas, reversar pagos y crear devoluciones. El catálogo de permisos existe y está asignado por rol, pero es **decorativo** para estas rutas — no las protege.

`CashRegisterListView` usa `require_role(OWNER)` (binario) en vez del motor de permisos granular — inconsistente con el resto de acciones de caja.

**Sí funciona como control real** (mecanismo distinto, `apps.approvals`, no `apps.permissions`): descuentos por encima del límite y crédito excedido, vía `ApprovalPolicy`/`ApprovalRequest`, jerarquía usuario→rol→tenant→negar, OWNER siempre autorizado.

Este hallazgo se documenta como **DECISIÓN FUNCIONAL PENDIENTE** — ver `docs/pos-redesign-risk-map.md` §1.

---

## 11. Estados / enums reales (inventario completo)

- `CashRegister.status`: `active`/`inactive`. Sin vista para desactivar tras crear.
- `CashSession.status`: `open`/`closed`.
- `CashMovement.movement_type` (12 valores): `opening`, `sale_cash`, `cash_in`, `cash_out`, `cash_refund`, `customer_advance_cash`, `withdrawal`, `adjustment`, `supplier_payment_cash`, `supplier_advance_cash`, `expense_payment_cash`, `payroll_payment_cash`. **`adjustment` es un estado fantasma**: existe en el modelo y en la lógica de cálculo, pero no es alcanzable desde ninguna vista/formulario/template ni tiene cobertura de test.
- `Sale.Status`: `draft`/`confirmed`/`canceled`/`returned`/`partially_returned`. El POS solo transita `DRAFT→CONFIRMED` (checkout) y `DRAFT→CANCELED` (cancelar carrito) — nunca produce `RETURNED`/`PARTIALLY_RETURNED` (eso solo ocurre vía `apps.sales.create_return`, inaccesible desde el POS).
- `Sale.PaymentStatus`: `unpaid`/`partially_paid`/`paid`/`refunded`/`partially_refunded` — siempre derivado, nunca asignado a mano.
- `PaymentMethod`: `cash`/`card`/`transfer`/`other` — únicos 4 valores reales, sin PayPal/cheque/billetera digital/QR/cripto.
- `Payment.Status`: `confirmed`/`voided`. `PaymentAllocation.Status`: `active`/`reversed`. `Refund.Status`: `pending`/`completed`/`failed` (siempre `completed` de inmediato en el flujo actual, sin pasarela real). `CreditNote.Status`: 5 valores. `Return`: **sin campo `status`**, inmutable por diseño.
- `InventoryUnit.Status`: `en_stock`/`reservado`/`vendido`/`devuelto`/`reparacion`/`garantia`/`danado`/`perdido`/`devuelto_proveedor`.
- `ApprovalRequest.ActionType`: incluye `discount`/`credit_overage` (únicos generados realmente desde el POS) y `refund`/`cancellation`/`cash_movement` (existen en el enum pero sin ningún caller real desde `apps.pos`/`apps.sales` — reembolsos/anulaciones/movimientos especiales no pasan por autorización pese a que el enum lo sugiere).

---

## 12. Tests

`apps/pos/tests/` — **71 tests, todos pasan** (`manage.py test apps.pos -v 2` → `OK`, 424s contra PostgreSQL real). Cobertura sólida confirmada: apertura/cierre de caja (fondos inválidos, caja inactiva, usuario no autorizado, exclusividad de sesión, concurrencia con threads), cobros/anticipos/notas de crédito/reembolsos, descuentos y crédito excedido con autorización (incluyendo reintento tras aprobación y no-reutilización), aislamiento multi-tenant (7 tests dedicados), rendimiento (sin N+1), flujo HTTP completo del terminal incluyendo multipago efectivo+tarjeta con unidad serializada y cálculo de cambio.

`apps/sales/tests/` (usado indirectamente por el POS): `confirm_sale`/`cancel_sale` (incluye rechazo de unidad ya vendida, rechazo sin stock, idempotencia), devoluciones de mercancía (`test_returns.py`, 9 tests — **no accesibles desde el terminal**, solo desde `apps.sales`), motor de pagos/notas de crédito (56 tests combinados).

**Sin cobertura evidente**: `CashMovement.ADJUSTMENT` (sin caller, sin test); devolución de mercancía iniciada desde el flujo POS (no existe la función); permisos granulares aplicados al POS/sales (ningún test verifica que un `EMPLOYEE` sin `pos.use` sea rechazado — consistente con que tampoco se aplica en código); `CashMovementCreateView` vía HTTP (los tests prueban el servicio, no el POST real); `CashRegister.Status.INACTIVE` alcanzable solo por fixture, sin endpoint de desactivación real.

`manage.py check` → `System check identified no issues (0 silenced)`.

---

## 13. Integraciones reales

- **Inventario**: QUANTITY vía `register_stock_out` (valida negativos solo en `confirm_sale`, nunca al agregar al carrito); SERIALIZED vía `transition_unit_status(..., VENDIDO)` (máquina de estados existente reutilizada, nunca una segunda). `ensure_unit_available_for_sale` existe pero está desconectada del flujo real (código muerto respecto a su uso previsto).
- **Clientes**: `Customer.display_name`, `credit_enabled`/`credit_limit` (decide venta a crédito), `is_active` (filtra dropdown). Identificación/email/teléfono no se muestran en ningún template del POS.
- **Ventas**: el POS es una capa fina 100% delegante sobre `apps.sales.services` — no reimplementa ninguna regla.
- **Contabilidad**: sí, vía patrón resiliente `try_record_*` (nunca rompe la operación de negocio si falla): `confirm_sale`→`try_record_sale_confirmed`+`try_record_sale_cogs`; pago→`try_record_customer_payment`; cierre de caja→`try_record_cash_session_closing` (reconoce `cash_over`/`cash_short`). Idempotente por `(tenant, source_type, source_event_key)`.
- **Aprobaciones**: descuentos (línea y global) y crédito excedido, jerarquía usuario→rol→tenant→negar, OWNER siempre autorizado.

---

## 14. Riesgos identificados

1. **Brecha de autorización real** (§10) — el hallazgo de mayor severidad: permisos definidos y asignados por rol pero no aplicados en el terminal ni en `apps.sales`.
2. **`cash.view` no aplicado** — exposición de datos de sesión de caja de otros cajeros dentro del mismo tenant.
3. **Sin validación de stock/disponibilidad al agregar al carrito** — el error solo aparece al cobrar, después de que el cajero ya armó el carrito y capturó pagos; riesgo de UX y de dos cajeros compitiendo por la misma unidad serializada.
4. **Movimiento manual de caja y tipo `adjustment` inalcanzables desde la UI** — funcionalidad backend sin uso real posible.
5. **Cierre de caja sin desglose por denominaciones** — solo un monto total, dependiente enteramente de la honestidad/precisión del conteo manual del cajero.
6. **Grid inline no responsive en el terminal** — la pantalla más usada del ERP en un mostrador físico (potencialmente tablet/monitor secundario angosto) tiene un defecto de responsive ya diagnosticado y resuelto en otra pantalla, pero no en esta.
7. **Salto de contexto visual en el recibo** — el cajero termina el flujo de cobro en una pantalla sin sidebar/topbar Atlas y con un azul distinto.

---

## 15. Problemas UX/UI observados (solo observación)

- Sin edición de línea en el carrito (solo "Quitar").
- Sin override de precio unitario en ningún punto.
- Sin enforcement de cantidad=1 para líneas con unidad serializada.
- Campo "Buscar cliente" vestigial (se renderiza, no filtra nada).
- Dropdown de cliente sin paginar/filtrar server-side (carga todos los clientes activos).
- Sin visibilidad de stock disponible en la búsqueda de productos.
- Cero JS: sin autocompletar, sin cálculo de cambio en vivo, sin indicador de carga, sin autofocus, sin atajos de teclado.
- El "Total" de la venta no tiene ninguna prominencia visual adicional respecto a Subtotal/Descuento/Impuesto (4 KPIs visualmente idénticos).
- Sin confirmación ni protección de doble-submit client-side en "Confirmar y cobrar" (mitigado server-side por idempotencia de `confirm_sale`).
- Inputs de la fila "Agregar producto" sin `<label>` (accesibilidad).
- Emoji en estados vacíos, inconsistente con la regla Atlas ya aplicada en otras pantallas del mismo módulo.
- El recibo no muestra el cambio entregado ni tiene ajuste para impresoras térmicas angostas (58/80mm).
- Navegación fragmentada: terminal, Cobros y Devoluciones son 3 superficies sin enlaces cruzados entre sí.

## 16. Problemas responsive observados

- Grid `1fr 1fr` inline en `terminal.html:125` sin colapsar en móvil (mismo defecto ya resuelto en otra pantalla vía `.u-grid-2col`, nunca aplicado aquí).
- Filas `display:flex` sin `flex-wrap` en formulario de búsqueda y formset de pago.
- Anchos fijos en `rem` en inputs de la fila de búsqueda.
- `body{overflow-x:hidden}` global implica que el contenido que desborda esas filas se recorta silenciosamente en vez de generar scroll visible.
- Lo que SÍ es responsive de forma heredada, sin esfuerzo propio del POS: colapso de sidebar a off-canvas, `.tabla-envoltorio{overflow-x:auto}` en todas las tablas, `.kpi-grid` con `auto-fit`.

---

## 17. Dependencias con ERP Atlas / SaaS

El POS hereda el shell Atlas completo (sidebar/topbar, tokens de color/tipografía) de forma pasiva vía `layout_app.html`+`.shell--erp`, sin que su HTML interno haya sido tocado — usa el mismo vocabulario de clases (`.btn`/`.tarjeta`/`.tabla`/`.badge`/`.campo`/`.kpi*`) que las 13 pantallas ya migradas y que el Super Admin SaaS, porque esas clases están declaradas sin scope de shell en `design-system.css`. **No hay ningún "cortafuegos" de nomenclatura**: cualquier clase nueva que FASE 7 introduzca debe elegirse con cuidado para no colisionar con las ~3300 líneas combinadas de `design-system.css`+`design-system-erp.css`. `sale_receipt.html` es la única pieza del flujo POS que NO hereda el shell Atlas (extiende `base.html` directamente).

---

## 18. Mejoras posibles (PROPUESTA / POSIBLE MEJORA — no implementadas)

Todo lo siguiente es una observación de lo que "sería razonable" pero no existe hoy. Ninguna se implementó.

- PROPUESTA: mostrar stock disponible en la tabla de resultados de búsqueda.
- PROPUESTA: permitir editar cantidad/descuento de una línea ya agregada sin tener que quitarla y re-agregarla.
- PROPUESTA: cálculo de cambio en vivo (JS) antes de confirmar el pago.
- PROPUESTA: enlace de regreso al terminal desde el recibo, y enlaces cruzados entre terminal/Cobros/Devoluciones.
- PROPUESTA: autofocus en el campo de búsqueda tras cada recarga.
- PROPUESTA: reemplazar emoji por iconos SVG en los estados vacíos del POS (mismo patrón ya usado en `customer_collections.html`).
- PROPUESTA: aplicar `.u-grid-2col` al grid Cliente/Descuento del terminal (fix ya existente en el proyecto, solo no aplicado aquí).
- PROPUESTA: mostrar el monto entregado/cambio en el recibo impreso.
- PROPUESTA: botón/UI para registrar movimientos manuales de caja (`cash_in`/`cash_out`/`withdrawal`), hoy inalcanzable.
- PROPUESTA: índice de sesiones de caja históricas dentro de `apps.pos`.

Ninguna de estas propuestas se evalúa aquí como aprobada ni se implementa — quedan para que la siguiente etapa decida cuáles, si alguna, se incorporan a un futuro Design Lab de POS.

---

## 19. Decisiones funcionales pendientes

Ver `docs/pos-redesign-risk-map.md` para el detalle completo (qué existe hoy, qué problema presenta, qué cambio requeriría, qué archivos/lógica afectaría, qué riesgo tendría) de cada una de las siguientes:

1. Brecha de autorización real en `apps.pos`/`apps.sales` (permisos definidos, no aplicados).
2. `cash.view` no aplicado en `CashSessionSummaryView`.
3. Validación de disponibilidad de stock/unidad al agregar al carrito (hoy solo al confirmar).
4. Cierre de caja por denominaciones (hoy solo monto total).
5. Movimiento manual de caja y tipo `adjustment` sin UI.
6. Devolución de mercancía accesible desde el flujo del POS (hoy solo desde `apps.sales`).
7. Persistencia real de `amount_received`/`change_amount` y su reflejo en el recibo.
8. Integración de `TaxCode`/`SaleItemTax` (FASE 14) al POS (hoy usa solo el impuesto plano del producto).

---

## 20. Recomendación para la siguiente etapa

Antes de cualquier Design System/Design Lab de POS, la siguiente etapa debería:
1. Resolver (como decisión de negocio del usuario, no del agente) cuáles de las 8 "decisiones funcionales pendientes" de §19 se autorizan a implementarse y en qué orden, empezando por la brecha de autorización (§19.1), que es la de mayor severidad.
2. Definir si el rediseño visual de POS reutiliza el vocabulario de clases compartido (`design-system.css`/`design-system-erp.css`, con el riesgo de colisión ya documentado en §17) o introduce un namespace propio para el terminal.
3. Decidir si `sale_receipt.html` se integra al shell Atlas (`layout_app.html`) o se mantiene deliberadamente aislado como documento imprimible.
4. Solo después de esas decisiones, iniciar un Design Lab de POS acotado a lo que el código real soporta — nunca a partir de las 10 propuestas de §18 dadas por aprobadas.

---

## 21. Matriz final

| Área | Existe | Estado actual | Riesgo | Rediseñable visualmente | Requiere decisión funcional |
|---|---|---|---|---|---|
| Terminal | Sí | Server-rendered, sin JS, grid inline no responsive | Medio | Sí | No |
| Carrito | Sí | Solo agregar/quitar, sin editar línea | Bajo | Sí | Sí (§19.3, opcional §18) |
| Productos | Sí | Búsqueda por texto/SKU/código/IMEI, sin filtros de categoría | Bajo | Sí | No |
| Cliente | Sí | Dropdown simple, buscador vestigial | Bajo | Sí | No (mejora, no defecto) |
| Descuentos | Sí | Línea + global, con autorización real vía `apps.approvals` | Bajo | Sí | No |
| Impuestos | Sí (parcial) | Solo impuesto plano del producto; `TaxCode` no conectado | Medio | Sí | Sí (§19.8) |
| Pagos | Sí | 4 métodos reales, multipago, solo efectivo mueve caja | Bajo | Sí | Sí (§19.7, vocabulario de cambio) |
| Venta | Sí | Checkout atómico, idempotente, contabilización automática | Bajo | Sí | No |
| IMEI/Serial | Sí | Búsqueda/asociación real; sin validar disponibilidad al agregar | Alto | Sí | Sí (§19.3) |
| Caja | Sí | Modelo sólido, append-only | Medio | Sí | No |
| Apertura | Sí | Monto único, selección de caja si hay varias | Bajo | Sí | No |
| Movimientos | Sí (backend) | Sin UI accesible; tipo `adjustment` huérfano | Alto | Sí (una vez autorizado) | Sí (§19.5) |
| Cierre | Sí | Monto total manual, sin denominaciones | Medio | Sí | Sí (§19.4) |
| Comprobante | Sí | HTML imprimible, sin PDF servidor, sin mostrar cambio, fuera del shell Atlas | Medio | Sí | Sí (§19.7) |
| Permisos | Parcial | Catálogo definido, mayoría no aplicada | **Crítico** | No aplica | Sí (§19.1, §19.2) |
| Responsive | Parcial | Heredado (sidebar/tablas) funciona; contenido interno del terminal no | Medio | Sí | No |
