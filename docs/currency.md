# Moneda, Denominaciones y Cierre de Caja (especificación)

> **Estado: ESPECIFICACIÓN, no implementación.** Diseño aprobado como
> doctrina oficial del proyecto — ningún modelo, campo ni migración se
> crea a partir de este documento. La fase que lo implemente (probablemente
> una ampliación de `apps.pos`/`apps.sales`, a decidir cuando exista
> necesidad real) debe releerlo completo antes de diseñar. Ver
> `docs/cash-registers.md`/`docs/pos.md` (caja y POS ya construidos,
> FASE 11), `docs/payments.md` (pagos, FASE 10/11) y `docs/purchases.md`
> (compras, FASE 12) para cómo esta doctrina se conecta con lo que ya
> existe.

## 0. Por qué este documento existe

El ERP debe ser **internacional desde su arquitectura**, nunca asumir
que "la moneda" es una sola ni que sus denominaciones físicas son fijas.
Hoy, `currency` ya existe como un `CharField(max_length=3)` (código
ISO 4217 en texto libre, ej. `"USD"`) en varios modelos —
`Customer`/`Supplier` (`ContactoMixin`, FASE 9), `Quotation`/
`ProformaInvoice`/`Sale`/`Payment` (`apps.sales`, FASE 10/11),
`PurchaseOrder`/`SupplierInvoice`/`SupplierPayment` (`apps.purchases`,
FASE 12) — un snapshot de texto simple, suficiente para lo que cada
fase necesitó en su momento, pero **sin ningún catálogo real
detrás**: nada valida hoy que `"USD"` sea una moneda real, ni existe
ningún concepto de sus denominaciones físicas. Este documento formaliza
el catálogo real (`Currency`/`CurrencyDenomination`) y todo lo que se
construye encima (caja por denominaciones, cierre, cambio) — sin
romper ni migrar todavía los campos `currency` de texto libre que ya
existen (ver sección 11).

## 1. `Currency` y `CurrencyDenomination` — el catálogo real

**`Currency`** (catálogo global o por tenant — a decidir en
implementación; el diseño no depende de cuál): `code` (ISO 4217, único,
ej. `"DOP"`/`"USD"`), `name` (ej. "Peso dominicano"), `symbol` (ej.
`"RD$"`/`"$"`), `decimal_places` (ej. `2`), `is_active`.

**`CurrencyDenomination`**: `currency` (FK), `value` (`Decimal`, ej.
`2000`, `1000`, ..., `1`, o `0.25`/`0.10`/`0.05`/`0.01` para monedas con
denominaciones fraccionarias), `kind` (`BILL`/`COIN` — billete/moneda),
`is_active`, `display_order` (entero, orden de presentación en el
conteo de caja).

**Nunca asumir que todas las monedas comparten las mismas
denominaciones** — cada `Currency` tiene su propia lista, definida por
quien administra el catálogo (o poblada por una fixture inicial con las
monedas más comunes). Ejemplos ilustrativos, no exhaustivos ni
hardcodeados en código:

```
DOP: 2000, 1000, 500, 200, 100, 50, 25, 10, 5, 1
USD: 100, 50, 20, 10, 5, 2, 1, 0.25, 0.10, 0.05, 0.01
```

Estos valores son **datos** (filas de `CurrencyDenomination`), nunca
constantes en el código de `apps.pos`/`apps.sales` — agregar una moneda
nueva o corregir sus denominaciones es una operación de datos, nunca un
cambio de código.

## 2. `CurrencyConfiguration` — configuración por tenant

Un tenant necesita decidir, sin que ningún dato quede hardcodeado:

- **Moneda principal/funcional** del tenant (`CurrencyConfiguration.functional_currency`,
  FK a `Currency`) — la moneda en la que el negocio piensa sus reportes
  financieros.
- **Monedas habilitadas** (`CurrencyConfiguration.enabled_currencies`,
  M2M a `Currency`) — el subconjunto del catálogo que ese tenant puede
  usar en documentos/cajas/clientes.
- **Moneda de cada `CashRegister`** — vive en `CashRegister` misma (ver
  sección 3), no en `CurrencyConfiguration`; cada caja física opera en
  una sola moneda a la vez.
- **Moneda de cada documento** — ya vive en cada documento (`Sale.currency`,
  `PurchaseOrder.currency`, etc.) como snapshot al momento de crearse,
  igual que hoy; esta configuración solo acota qué monedas son válidas
  de elegir para ese tenant.
- **Moneda del cliente/proveedor** — ya vive en `Customer.currency`/
  `Supplier.currency` (FASE 9), sin cambios.
- **Tipos de cambio (FX)**: se **prepara conceptualmente** una tabla de
  tasas (`ExchangeRate`: `from_currency`, `to_currency`, `rate`, `as_of`
  — fecha/hora de la tasa) para que un documento en una moneda distinta
  a la funcional del tenant pueda, en el futuro, convertirse a la
  funcional para reportes consolidados. **No se construye ningún motor
  de conversión completo con este documento** — mismo criterio que
  landed cost en FASE 12 o valorización de inventario en FASE 14: no
  adelantar un cálculo financiero sin necesidad real explícita.

## 3. `CashRegister` multi-moneda

Una `CashRegister` (FASE 11, `apps.pos`) tendrá una **moneda operativa
principal** (`CashRegister.currency`, FK a `Currency`, campo nuevo —
hoy `CashRegister` no tiene ningún campo de moneda). La `CashSession`
que abre esa caja cuenta físicamente **en esa única moneda**.

**Nunca mezclar físicamente denominaciones de monedas distintas dentro
de un mismo conteo** — un conteo de cierre es siempre de UNA moneda. Si
en el futuro se necesita soportar efectivo de una moneda extranjera de
forma física (ej. una caja que acepta USD además de DOP), debe existir
una **separación explícita por `Currency`**: conceptualmente, cada
combinación (`CashRegister`, `Currency`) que maneje efectivo físico
tendría su propio conteo/cierre independiente — nunca un solo cierre
que sume montos de monedas distintas como si fueran la misma unidad.
Esto no se construye con este documento; se deja preparado para que una
fase futura decida el modelo exacto (¿una `CashRegister` por moneda?
¿una `CashRegister` con varias "cajas físicas" internas por moneda?) si
alguna vez hay una necesidad real.

## 4. Denominaciones en el conteo de caja

**`CashDenominationCount`**: la fila real del conteo — `cash_closing`
(FK, ver sección 5), `denomination` (FK a `CurrencyDenomination`,
**nunca un segundo catálogo**: "CashDenomination" en el sentido
conceptual de esta doctrina es exactamente una `CurrencyDenomination`
usada en el contexto de un conteo de caja, no una tabla paralela —
mismo principio de "no dupliques fuentes de verdad" ya aplicado a
`CustomerCreditLedger` en FASE 11), `quantity` (entero, cuántas unidades
contó el cajero), `subtotal` (`Decimal`, snapshot de `denomination.value
× quantity` **congelado en el momento del cierre** — igual que
`PurchaseReceiptItem.unit_cost`, FASE 12: si el catálogo de
denominaciones cambia después, un cierre histórico nunca se altera).

Ejemplo (moneda DOP):

```
2000 × 5   = 10,000
1000 × 8   =  8,000
 500 × 6   =  3,000
 200 × 10  =  2,000
...
Total contado = suma de todos los subtotales
```

El sistema calcula el subtotal por denominación y el total contado
**siempre sumando `CashDenominationCount.subtotal`** — nunca un total
tecleado por separado cuando el conteo por denominaciones está
habilitado. El cajero **no debe tener que escribir manualmente el
efectivo total** en ese modo: es la suma, no un campo paralelo que
pudiera no coincidir.

**Modo rápido por total** (opción administrativa, no el modo
recomendado): un tenant puede permitir que un cierre se registre con un
solo monto total, sin desglose por denominación — para negocios
pequeños o pruebas. El **modo profesional recomendado es por
denominaciones**; cuál de los dos modos usa un tenant es una decisión
de configuración (`CurrencyConfiguration` o un flag equivalente), no
una limitación de arquitectura — ambos modos producen el mismo
`CashClosing.counted_cash` al final, solo difieren en si existen filas
`CashDenominationCount` detrás o no.

## 5. `CashClosing`

Representa el cierre de una `CashSession` — hoy esos datos viven
directamente en campos de `CashSession` (`closed_at`, `expected_cash`,
`counted_cash`, `difference`, `notes`, ver `docs/cash-registers.md`
sección 2). `CashClosing` formaliza esto como su propia entidad para
que pueda tener denominaciones asociadas (`CashDenominationCount`) sin
sobrecargar `CashSession` — decisión de modelado a confirmar en
implementación (¿campos nuevos en `CashSession` + tabla de
denominaciones aparte, o `CashClosing` como entidad propia
uno-a-uno con `CashSession`? Ambas opciones son válidas; ninguna se
decide aquí).

Campos: `cash_session` (FK), `currency` (FK a `Currency`, snapshot de
la moneda operativa de la caja en ese cierre), `expected_cash`,
`counted_cash`, `difference` (`counted_cash − expected_cash`, **el
único campo real** — ver nota de diseño abajo), `closed_at`, `user`,
denominaciones (relación con `CashDenominationCount`), `notes`.

**Nota de diseño — sobrante/faltante son lecturas de `difference`, no
campos nuevos**: "sobrante" y "faltante" son simplemente
`max(difference, 0)` y `max(-difference, 0)` — dos formas de LEER el
mismo número, nunca dos campos almacenados que pudieran contradecir a
`difference` (mismo principio de "nunca un campo desnormalizado que
pueda desincronizarse" aplicado desde `StockMovement` en FASE 8). Un
reporte puede mostrarlos como columnas separadas (ver `docs/reports.md`)
sin que eso signifique que existen como columnas de base de datos.

### Fórmula del efectivo esperado (confirmada, ya construida — FASE 11)

```
Efectivo esperado
  = fondo inicial (opening_amount)
  + ventas en efectivo
  + anticipos en efectivo
  + entradas de efectivo
  − salidas de efectivo
  − refunds en efectivo
  ± otros movimientos autorizados (ADJUSTMENT)
```

Esta fórmula **ya está implementada exactamente así**
(`apps.pos.services.get_expected_cash`, ver `docs/cash-registers.md`
sección 7) — esta sincronización solo la reafirma como doctrina
permanente, sin ningún cambio de código. **Nunca incluir pagos no
monetarios** (tarjeta, transferencia, PayPal) como efectivo físico — ya
garantizado hoy porque solo `PaymentMethod.CASH` genera `CashMovement`.

## 6. Cierre inmutable

Una vez que un `CashClosing` (o el cierre de `CashSession`, en el
diseño actual) queda `CLOSED`:

- **No se edita históricamente** ningún campo del cierre.
- **No se cambian** las filas de `CashDenominationCount` ya guardadas.
- **No se modifica** `difference` después del hecho.

Esto **ya es el comportamiento actual**: `apps.pos.services.close_cash_session`
rechaza explícitamente cerrar una sesión ya cerrada (ver
`docs/cash-registers.md` sección 7) — nunca un no-op silencioso ni un
`UPDATE` permitido. Correcciones posteriores a un cierre ya realizado
deben pasar por un **proceso administrativo/auditado separado** —
reutilizando lo ya construido: un nuevo `CashMovement` de tipo
`ADJUSTMENT` (requiere `ApprovalRequest`, ver `docs/approvals.md`) en
una `CashSession` **nueva**, nunca reabriendo ni editando la sesión/cierre
ya cerrado. Mismo principio de inmutabilidad que `Return`/
`PaymentAllocation` revertida (FASE 10/11): una corrección es una
operación nueva, nunca una edición silenciosa del historial.

## 7. Cambio en el POS: vocabulario oficial

Se formaliza el vocabulario `amount_due`/`amount_received`/
`change_amount` para lo que **ya está implementado correctamente**
desde FASE 11 (`apps.pos.views.CheckoutView`, ver `docs/pos.md`
"Checkout: confirmar + cobrar"):

- `amount_due`: el saldo que la venta requiere en el momento del cobro
  (`sale.total`, o el saldo pendiente si es un pago parcial de una
  factura ya existente).
- `amount_received`: la suma de lo que el cliente entrega (hoy
  `total_recibido` en `CheckoutView`, sin ese nombre formal).
- `change_amount`: `amount_received − amount_due` cuando es positivo
  (hoy `exceso`/`cambio` en `CheckoutView`).

```
change = amount_received - amount_due   (solo si es positivo)
```

Si `amount_received < amount_due`: la venta queda **pendiente** (saldo
por cobrar) — **no se permite completar la venta con monto
insuficiente**, salvo:

- **crédito autorizado** (`customer.credit_enabled` + límite verificado
  — ya construido, `check_credit_sale_authorization`);
- **otro método de pago** que cubra la diferencia;
- **una combinación válida de pagos** que sume el total.

**Corregido (posterior a esta sincronización, ver `KNOWN_ISSUES.md`
#82 y `DECISIONS.md`)**: `checkout_sale` ahora rechaza explícitamente
—con `InsufficientPaymentError`, antes de confirmar la venta, mover
inventario o tocar la caja— un cobro insuficiente cuando la venta **no
tiene cliente, o el cliente no tiene crédito habilitado**. Regla
exacta: la venta solo se confirma si `amount_received` (suma de los
pagos indicados) cubre `amount_due` (`sale.total`), salvo que exista
una parte de crédito autorizada que cubra la diferencia (mismo flujo
de `check_credit_sale_authorization`/`ApprovalRequest` ya existente
para crédito excedido). Caso de referencia: venta=5000,
recibido=2000, cliente sin crédito habilitado → rechazado, ninguna
venta parcialmente confirmada.

## 8. Cambio y pagos mixtos

El POS ya soporta múltiples métodos en una sola venta (efectivo,
tarjeta, transferencia, otros). Regla oficial: **el cambio se calcula
únicamente sobre la parte en efectivo**, nunca prorrateado entre
métodos.

Ejemplo (el del enunciado):

```
Venta = 2000
Efectivo = 1500
Tarjeta = 500
```

No hay cambio (1500 + 500 = 2000 exacto). Si el cliente hubiera
entregado 2000 en efectivo en vez de 1500, y aun así se cobrara 500 con
tarjeta, el sistema tendría 2500 recibidos contra 2000 debidos — el
excedente de 500 debe salir del efectivo, nunca de la tarjeta (una
tarjeta siempre se cobra por el monto exacto autorizado, nunca "de
más"). Esto **ya está implementado así**: `CheckoutView` descuenta el
exceso del último pago en efectivo indicado y, si el exceso no cabe en
ningún pago en efectivo, rechaza la operación explícitamente ("El
cambio solo puede entregarse en efectivo; ajusta los montos") en vez de
intentar dar cambio desde un método que no lo permite.

**No se duplican movimientos de caja** por dar cambio — ver sección 9.

## 9. `CashMovement`: efecto neto, nunca doble conteo

El `CashMovement` asociado a una venta en efectivo debe representar el
**impacto neto real** sobre el efectivo físico, nunca el monto bruto
recibido y el cambio como dos movimientos separados.

Ejemplo (el del enunciado):

```
Venta = 1275
Cliente entrega = 2000
Cambio = 725
```

El impacto neto sobre el efectivo físico es **+1275** — nunca `+2000`
y `-725` como si fueran dos ventas. **Esto ya está implementado
correctamente**: `CheckoutView` resta el cambio del monto en efectivo
ANTES de llamar a `services.checkout_sale`, así que el `amount` que
`record_cash_movement` recibe para el `CashMovement` tipo `SALE_CASH`
**ya es el neto** (`1275`, en el ejemplo), nunca el monto bruto
entregado por el cliente. Esta sincronización confirma esto como
doctrina permanente, sin ningún cambio de código.

El detalle `amount_received`/`change_amount` (cuánto entregó realmente
el cliente y cuánto cambio se le dio) **puede vivir en `Payment`** como
campos nuevos preparados (`Payment.amount_received`,
`Payment.change_amount`, nulos, solo relevantes para `method=CASH`) —
**no se agregan con este documento** — mientras que `CashMovement`
sigue representando siempre el efecto monetario neto real, nunca el
bruto.

## 10. Cambio sugerido por denominaciones

Se prepara la arquitectura para sugerir una combinación de
denominaciones que sume el `change_amount`, sin construirla todavía:
una función de solo cálculo (sin modelo nuevo) que, dado un monto y la
lista ordenada (`display_order` descendente) de `CurrencyDenomination`
activas de la moneda operativa de la caja, sugiera una combinación
codiciosa (mayor denominación primero) que sume el monto exacto.

Ejemplo:

```
Cambio = 725
Sugerencia: 500 + 200 + 25
```

**El cajero nunca está obligado a usar la combinación sugerida** — es
una ayuda de UX, no una restricción de negocio; el cajero puede entregar
el cambio con cualquier combinación física real que tenga disponible en
la gaveta. La sugerencia, en su primera versión, se basa en las
denominaciones **canónicas** del catálogo (`CurrencyDenomination`), no
en un inventario en vivo de "cuánto de cada denominación hay
físicamente en la gaveta ahora mismo" — un refinamiento futuro podría
llevar ese inventario en vivo (sumando/restando `CashDenominationCount`
de aperturas/movimientos) si se decide que la sugerencia debe ser
"solo con lo que hay disponible", pero eso no se construye con este
documento.

## 11. Relación con lo ya construido — qué cambia, qué no

- Los campos `currency` de texto libre (`Customer`/`Supplier`,
  `Quotation`/`ProformaInvoice`/`Sale`/`Payment`,
  `PurchaseOrder`/`SupplierInvoice`/`SupplierPayment`)
  **siguen siendo válidos exactamente como están** — esta doctrina no
  los migra ni los reemplaza con este documento. `CreditNote` no tiene
  hoy su propio campo `currency` (hereda implícitamente la moneda del
  `Customer`/`Sale` que la origina, ver `docs/accounts-receivable.md`
  sección 8). Cuando `Currency` exista como modelo real, la migración
  de esos campos de texto libre a una FK (o su validación contra el
  catálogo) es una decisión de implementación futura, documentada aquí
  como pendiente, no resuelta.
- `CashRegister` **no tiene hoy ningún campo de moneda** — esta
  doctrina define que lo tendrá (`CashRegister.currency`, sección 3),
  campo nuevo que no existe todavía.
- El cálculo de efectivo esperado, el cambio en el POS, y el efecto
  neto de `CashMovement` en una venta con cambio **ya están construidos
  correctamente** desde FASE 11, tal como se confirma en las secciones
  5, 7 y 9 — esta sincronización documenta el vocabulario oficial y
  formaliza el comportamiento existente, sin ningún cambio de código.
- **Contabilidad General (`apps.accounting`, FASE 14)**: la doctrina
  de moneda a nivel de ASIENTO CONTABLE (un `JournalEntry` nunca
  mezcla monedas entre sus líneas; campos FX-prep `original_amount`/
  `original_currency`/`exchange_rate` en `JournalEntryLine`) vive en
  `docs/accounting.md` — este documento no la duplica. `CashClosing`/
  `CashDenominationCount` (secciones 4-5 de este documento) siguen sin
  construirse; el cierre de sesión de caja SÍ se conectó a
  contabilidad en la ampliación de cierre de FASE 14 (Cash Over/Cash
  Short, ver `docs/accounting.md` sección 14) usando el evento de
  cierre YA existente (`CashSession.status=CLOSED`), sin esperar a que
  exista el motor de denominaciones.

## 12. Qué NO se construye con este documento

Ningún modelo (`Currency`, `CurrencyDenomination`, `CurrencyConfiguration`,
`CashDenominationCount`, `CashClosing`, `ExchangeRate`), ningún campo
nuevo (`CashRegister.currency`, `Payment.amount_received`/
`change_amount`), ninguna migración, ninguna función de sugerencia de
cambio, ningún motor de conversión FX. La fase que decida implementar
esta doctrina debe releer este documento completo antes de diseñar, no
partir de cero.
