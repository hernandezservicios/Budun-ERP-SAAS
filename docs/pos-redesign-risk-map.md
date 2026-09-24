# FASE 7 — POS LAB PROFUNDO — ETAPA 1 — MAPA DE RIESGO Y DECISIONES FUNCIONALES PENDIENTES

Complemento de `docs/pos-redesign-discovery.md`. Cada punto de esta lista
es una **DECISIÓN FUNCIONAL PENDIENTE**: ninguna se implementó, todas
requieren autorización explícita separada del usuario antes de tocar
código, según la regla de seguridad de esta etapa.

---

## 1. Brecha de autorización real en `apps.pos`/`apps.sales`

**Qué existe hoy**: el catálogo de permisos (`apps/permissions/catalog.py`)
define `pos.use`, `cash.view`, `sales.create`/`update`/`cancel`/`refund`,
`payments.create`/`reverse`, `credit.view`/`apply`, `credit_note.*`, y los
asigna por defecto a roles (`MANAGER`/`CASHIER` sí los tienen,
`EMPLOYEE`/`MEMBER` no). Solo 3 permisos de todo ese conjunto
(`cash.open`, `cash.close`, `cash.move`) están realmente verificados con
`require_permission` en el código. Ninguna vista de `apps/sales/views.py`
llama a `require_permission`/`require_role` en ningún punto del archivo.

**Qué problema presenta**: `TerminalStartView`, `TerminalDetailView`,
`AddItemView`, `RemoveItemView`, `SetCustomerView`,
`SetGlobalDiscountView`, `CancelCartView`, `CheckoutView` (todo el
terminal de venta) y todas las vistas de `apps/sales/views.py` (crear/
confirmar/cancelar venta, agregar/eliminar línea, registrar/reversar
pago, crear devolución) heredan únicamente `LoginRequiredMixin` +
`TenantRequiredMixin`, que solo exige que exista una membresía activa en
el tenant — sin distinguir rol. Un usuario `EMPLOYEE`/`MEMBER`, que por
diseño de `DEFAULT_ROLE_PERMISSIONS` no debería poder "usar el punto de
venta" ni "crear/cancelar/reembolsar ventas", puede hacerlo hoy en la
práctica porque el código nunca pregunta.

**Qué cambio requeriría**: añadir `require_permission(request, "pos.use")`
(u otro código pertinente) al `dispatch`/`post` de cada vista involucrada
en `apps/pos/views.py` y `apps/sales/views.py`, siguiendo exactamente el
mismo patrón ya usado en `CashSessionOpenView`/`CashSessionCloseView`/
`CashMovementCreateView`.

**Qué archivos/lógica probablemente afectaría**: `apps/pos/views.py`
(8 vistas del terminal), `apps/sales/views.py` (creación/confirmación/
cancelación de venta, líneas, pagos, devoluciones — el archivo completo),
más los tests que hoy ejercen esas vistas sin ninguna membresía de rol
específico (podrían empezar a fallar si el fixture de test usa un rol sin
esos permisos) — habría que auditar `apps/pos/tests/` y
`apps/sales/tests/` para confirmar qué rol usan sus fixtures antes de
tocar nada.

**Qué riesgo tendría**: alto pero controlado — es una adición de
verificación (más restrictivo, no menos), el riesgo real es de regresión
funcional en tests/flujos existentes si algún fixture de test o flujo de
producción depende hoy de que un rol sin `pos.use`/`sales.*` pueda operar
el POS. Requiere decidir explícitamente, antes de tocar código, si el
comportamiento correcto es "bloquear" (como el catálogo ya lo define) o
si el catálogo mismo necesita revisarse primero.

---

## 2. `cash.view` no aplicado en `CashSessionSummaryView`

**Qué existe hoy**: `cash.view` está en el catálogo de permisos y
asignado por defecto a `MANAGER`/`CASHIER`, pero `CashSessionSummaryView`
no llama a `require_permission` en ningún punto — solo hereda
`LoginRequiredMixin`+`TenantRequiredMixin`.

**Qué problema presenta**: cualquier usuario con membresía activa en el
tenant (de cualquier rol) puede ver el resumen de **cualquier** sesión de
caja del tenant, incluida la de otro cajero, con solo conocer o adivinar
el `pk` en la URL — no hay tampoco un índice/listado que lo enlace, pero
tampoco hay protección si se accede directamente.

**Qué cambio requeriría**: añadir `require_permission(request,
"cash.view")` al `get` de `CashSessionSummaryView`.

**Qué archivos/lógica probablemente afectaría**: `apps/pos/views.py`
(una vista), posiblemente `apps/reports/templates/reports/cash_report.html`
si en el futuro se decide enlazar el reporte histórico a este detalle
(hoy no lo hace).

**Qué riesgo tendría**: bajo — cambio acotado a una sola vista, sin
lógica de negocio involucrada.

---

## 3. Validación de disponibilidad de stock/unidad al agregar al carrito

**Qué existe hoy**: `add_item_to_cart`/`add_sale_item` nunca consultan
stock disponible (QUANTITY) ni el `status` de la unidad (SERIALIZED) al
agregar una línea al carrito. La función `ensure_unit_available_for_sale`
(`apps/inventory/services.py`) existe exactamente para este propósito
pero no está conectada a ningún flujo real — solo se usa en tests. El
único punto real de rechazo es `confirm_sale`, en el momento de cobrar.

**Qué problema presenta**: un cajero puede armar un carrito completo,
capturar montos de pago, y solo entonces enterarse de que un producto no
tenía stock o que la unidad serializada ya fue vendida/reservada/dañada —
incluyendo el caso de dos cajeros agregando la misma unidad serializada a
dos carritos distintos simultáneamente sin ningún aviso previo.

**Qué cambio requeriría**: invocar `ensure_unit_available_for_sale` (o una
validación de stock equivalente para QUANTITY) dentro de
`add_item_to_cart`/`add_sale_item`, antes de crear la línea.

**Qué archivos/lógica probablemente afectaría**: `apps/pos/services.py`
(`add_item_to_cart`), `apps/sales/services.py` (`add_sale_item`), tests
existentes de ambos paquetes que hoy agregan líneas sin verificar
disponibilidad (podrían necesitar ajuste de fixtures).

**Qué riesgo tendría**: medio — cambia el momento en que un error de
negocio real se manifiesta (de "al cobrar" a "al agregar"), lo cual es
una mejora de UX pero también un cambio de comportamiento observable que
debe decidirse explícitamente, no inferirse.

---

## 4. Cierre de caja por denominaciones

**Qué existe hoy**: el cierre (`CloseSessionForm`) es un único campo
`counted_cash` (monto total). No existen `CashDenominationCount`,
`CurrencyDenomination`, `CurrencyConfiguration` ni `Currency` — confirmado
como ausencia real, no solo no verificada. `docs/currency.md` ya
documenta esto como doctrina pendiente, no como algo construido.

**Qué problema presenta**: el arqueo depende enteramente de que el
cajero cuente y escriba un único número correcto — sin desglose que
ayude a encontrar el origen de una diferencia, y sin preparación para
multi-moneda.

**Qué cambio requeriría**: los modelos completos de la doctrina de
moneda (`Currency`, `CurrencyDenomination`, `CurrencyConfiguration`,
`CashDenominationCount`), migraciones nuevas, un nuevo formulario/UI de
conteo por denominación, y decidir si el `CashRegister` necesita un campo
de moneda operativa.

**Qué archivos/lógica probablemente afectaría**: `apps/pos/models.py`
(nuevos modelos o campos), `apps/pos/forms.py`/`views.py`/`services.py`
(flujo de cierre), migraciones nuevas, templates de cierre.

**Qué riesgo tendría**: alto — es la ampliación más grande de las
listadas aquí, toca el núcleo de caja y requiere el diseño explícito que
`docs/currency.md` ya reserva para una implementación futura formal, no
algo a improvisar dentro de un Design Lab visual.

---

## 5. Movimiento manual de caja y tipo `adjustment` sin UI

**Qué existe hoy**: `CashMovementCreateView`/`CashMovementForm`/
`services.record_cash_movement` están completos y funcionan a nivel HTTP,
pero ningún template del proyecto tiene un botón/enlace/formulario hacia
esa URL — es inalcanzable en la práctica para un usuario real. El tipo
`adjustment` ni siquiera está en las 3 opciones que expone
`CashMovementForm` (`cash_in`/`cash_out`/`withdrawal`).

**Qué problema presenta**: un cajero no puede registrar un ingreso/salida
de efectivo manual (ej. cambio de fondo, retiro parcial) desde ninguna
pantalla, pese a que el backend lo soporta.

**Qué cambio requeriría**: agregar un enlace/botón en `terminal.html` (o
`session_close.html`) hacia `pos:cash_movement_create`, y decidir si
`adjustment` se expone también (hoy deliberadamente fuera del form, quizás
porque requiere una autorización que aún no existe).

**Qué archivos/lógica probablemente afectaría**: `apps/pos/templates/pos/
terminal.html` (o el template que se decida), posiblemente
`apps/pos/forms.py` si se agrega `adjustment` al form.

**Qué riesgo tendría**: bajo-medio — es mayormente un cambio de UI sobre
lógica ya existente y ya probada, pero exponer `adjustment` sin una
autorización asociada podría ser un vector de ajuste no controlado de
caja — a decidir explícitamente.

---

## 6. Devolución de mercancía accesible desde el flujo del POS

**Qué existe hoy**: `Return`/`SaleReturnCreateView` viven exclusivamente
en `apps.sales`, sin ninguna ruta ni enlace desde `apps/pos`.
`pos:cancel_cart` solo cancela carritos `DRAFT`, nunca ventas
`CONFIRMED`.

**Qué problema presenta**: un cajero que necesita procesar una devolución
de mercancía debe salir del módulo POS y navegar al módulo general de
Ventas — sin ningún puente contextual, pese a que conceptualmente es una
operación de mostrador.

**Qué cambio requeriría**: decidir si se agrega un enlace desde el
terminal/recibo hacia `sales:sale_return_create` (cambio de navegación
menor) o si se construye un flujo de devolución propio dentro de
`apps.pos` (cambio de lógica mayor, contradice el principio de "el POS
nunca reimplementa reglas de `apps.sales`").

**Qué archivos/lógica probablemente afectaría**: dependiendo de la
decisión, solo templates (enlace) o un flujo nuevo completo en
`apps/pos`.

**Qué riesgo tendría**: bajo si es solo un enlace de navegación; alto si
se decide reimplementar lógica de devolución dentro de `apps.pos`
(violaría el principio de diseño ya confirmado del proyecto).

---

## 7. Persistencia de `amount_received`/`change_amount` y su reflejo en el recibo

**Qué existe hoy**: el cambio se calcula con variables locales
(`total_recibido`/`exceso`/`cambio`) dentro de `CheckoutView.post` y solo
se comunica al cajero vía mensaje flash — nunca se persiste en `Payment`
ni aparece en `sale_receipt.html`. `docs/currency.md` ya anticipa
`amount_received`/`change_amount` como campos futuros de `Payment`, no
construidos todavía.

**Qué problema presenta**: el comprobante entregado al cliente no
documenta cuánto entregó ni cuánto cambio recibió — un vacío de
trazabilidad para el propio negocio, no solo de UX.

**Qué cambio requeriría**: agregar campos `amount_received`/
`change_amount` a `Payment` (migración nueva), poblarlos en
`checkout_sale`, mostrarlos en `sale_receipt.html`.

**Qué archivos/lógica probablemente afectaría**: `apps/sales/models.py`
(migración), `apps/pos/services.py` (`checkout_sale`),
`apps/sales/templates/sales/sale_receipt.html`.

**Qué riesgo tendría**: medio — toca el modelo `Payment`, que es
compartido con Cobros/Cuentas por Cobrar (FASE 10/11); cualquier cambio
ahí debe verificarse contra todos los flujos que ya lo consumen.

---

## 8. Integración de `TaxCode`/`SaleItemTax` (FASE 14) al POS

**Qué existe hoy**: `TaxCode`/`SaleItemTax` existen en `apps.accounting`
como sistema aditivo multi-impuesto, pero ningún llamador real los invoca
desde `apps/pos` ni `apps/sales`. El POS usa exclusivamente los campos
planos `SaleItem.tax_rate`/`tax_amount`, heredados del producto sin poder
elegirse en el checkout.

**Qué problema presenta**: un tenant que necesite más de un código de
impuesto por línea (ej. dos impuestos distintos sobre el mismo producto)
no puede hacerlo desde el POS hoy, pese a que el modelo ya lo soportaría
en teoría.

**Qué cambio requeriría**: conectar `apply_tax_code_to_sale_item`
(ya existente en `apps.accounting.services`) al flujo de
`add_item_to_cart`/`add_sale_item`, y decidir cómo se expone en la UI del
POS (¿selector de código de impuesto por línea?).

**Qué archivos/lógica probablemente afectaría**: `apps/pos/services.py`,
`apps/pos/forms.py` (`PosAddItemForm`), `apps/sales/services.py`,
templates del terminal.

**Qué riesgo tendría**: medio — el modelo ya existe y está probado en
`apps.accounting`, pero conectar dos sistemas de impuestos (el plano y el
multi-código) en el mismo flujo de venta requiere decidir explícitamente
la regla de interacción entre ambos.

---

## Resumen para cierre de Etapa 1

Ninguna de estas 8 decisiones se implementó. Todas requieren autorización
explícita e independiente del usuario, con la prioridad natural sugerida
por severidad: §1 y §2 (autorización/permisos, sin cambio de lógica de
negocio, solo verificación) primero; §3 y §6 (UX/flujo, tocan servicios
existentes) después; §4, §7 y §8 (ampliaciones de modelo/dominio) al
final, por ser las de mayor alcance.
