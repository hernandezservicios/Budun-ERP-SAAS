# Cuentas por Cobrar: Anticipos, Saldo a Favor, Notas de Crédito

> **Estado: `Payment`/`PaymentAllocation` (FASE 10 + ampliación) y
> `CreditNote`/`CreditNoteApplication` (FASE 11) están CONSTRUIDOS y en
> producción.** Anticipo/saldo a favor son 100% funcionales — ver
> `docs/pos.md` para el flujo operacional completo desde el POS.
> `CustomerCreditLedger` como TABLA separada **deliberadamente no se
> construyó**: la "Regla de no-duplicación" (sección 1) se resolvió con
> la opción 1 (generalizar `get_customer_credit_balance`/
> `get_sale_paid_amount` para sumar también `CreditNote`), no con la
> opción 2 — nunca hicieron falta las dos a la vez. Este documento
> sigue siendo la fuente de verdad de diseño; se actualizó para
> reflejar exactamente qué se construyó y qué sigue siendo
> especificación pura (`Customer Statement` como vista, sección 6).

## 1. Los tres conceptos, unificados en un solo saldo

El usuario fue explícito: **"No crear dos balances separados para
'anticipo' y 'saldo a favor'."** Este proyecto reconoce un único saldo
a favor por cliente, alimentado por distintos ORÍGENES:

| Concepto | Qué es | Cómo se representa hoy | Cómo se representará cuando exista `CustomerCreditLedger` |
|---|---|---|---|
| **Anticipo** | Dinero recibido de un cliente ANTES de que exista una factura/venta definitiva que lo consuma. | Un `Payment` creado sin ninguna `PaymentAllocation` todavía (`services.create_payment`, ya implementado). | Un movimiento `ADVANCE` en el ledger, generado automáticamente al crear ese `Payment`. |
| **Sobrepago** | Un `Payment` que cubre más de lo que una factura necesitaba. | La parte no aplicada del `Payment` (`get_unallocated_payment_amount`), ya implementado. | Un movimiento `PAYMENT_OVERAGE`. |
| **Saldo a favor (saldo total)** | El crédito disponible del cliente, utilizable en facturas futuras. | `services.get_customer_credit_balance(customer)` — suma el saldo sin aplicar de todos los `Payment` `CONFIRMED` del cliente. | La suma de todos los movimientos ACTIVOS del `CustomerCreditLedger` (ver sección 3) — **generaliza**, no reemplaza en paralelo, la función actual. |

Un anticipo **no es una venta**: no crea `Sale`, no reduce inventario,
no genera un número `FAC-`. Es dinero que existe fuera de cualquier
factura hasta que se aplique — exactamente lo que ya hace un `Payment`
sin asignaciones hoy.

### Regla de no-duplicación (obligatoria para cualquier fase futura)

Cuando se construya `CustomerCreditLedger`, **no puede coexistir** con
`get_customer_credit_balance` como dos saldos independientes que
puedan divergir. La fase que lo construya debe elegir una de estas dos
rutas — ambas válidas, ninguna decidida todavía porque no es necesario
decidirla hasta que exista una necesidad real:

1. **Generalizar la función existente** para que también sume
   movimientos del ledger que no provienen de un `Payment` (notas de
   crédito, reembolsos convertidos a crédito).
2. **Migrar la fuente de verdad al ledger por completo**: cada
   `Payment` sin aplicar genera su movimiento `ADVANCE`/
   `PAYMENT_OVERAGE` correspondiente, y `get_customer_credit_balance`
   se reimplementa como una simple suma sobre el ledger.

Cualquiera de las dos es aceptable; lo que nunca es aceptable es un
tercer número de "saldo a favor" calculado de una forma distinta en
algún reporte o vista.

## 2. `Payment.customer` nulo nunca genera crédito

Regla explícita, ya cumplida por la implementación actual y confirmada
aquí como doctrina permanente: un `Payment` con `customer=None`
(venta de mostrador/consumidor final sin cliente registrado) **nunca
puede generar saldo a favor de ningún cliente** — no existe ningún
cliente al que atribuírselo. `get_customer_credit_balance(customer)`
ya solo suma pagos con `customer=customer` explícito, así que un pago
anónimo simplemente no participa en el cálculo de nadie. Cuando exista
`CustomerCreditLedger`, esta misma regla se traduce en: **nunca crear
un movimiento del ledger sin un `customer` no nulo** — un sobrepago o
anticipo de una venta anónima se queda como saldo sin aplicar del
`Payment` (recuperable solo por reembolso directo), nunca como crédito
de cuenta.

## 3. `CustomerCreditLedger` — resuelto SIN una tabla nueva (FASE 11)

Mismo principio que `StockMovement` (FASE 8) y `PaymentAllocation`
(FASE 10): **el saldo se deriva siempre de la suma de movimientos,
nunca se guarda como un número editable.** Un campo `balance` en
`Customer` actualizado a mano sería exactamente el error que este
proyecto evita desde FASE 8 ("nunca un campo desnormalizado sin fuente
real").

**Decisión final (FASE 11)**: no se construyó una tabla
`CustomerCreditLedger` separada. `Payment`/`PaymentAllocation` (FASE 10)
y `CreditNote`/`CreditNoteApplication` (FASE 11, sección 4) son, juntos,
los dos ledgers append-only reales — construir una TERCERA tabla que
resumiera movimientos de ambos habría sido exactamente la segunda
fuente de verdad que este documento prohíbe en la sección 1 ("Regla de
no-duplicación"). En su lugar, `apps.sales.services.get_customer_credit_balance`
se generalizó para sumar el saldo sin aplicar de ambas fuentes en una
sola función — la tabla siguiente documenta los movimientos
CONCEPTUALES tal como se pidieron, y de dónde sale cada uno hoy:

Movimientos conceptuales (mapeados a los dos ledgers reales, no a una tabla `CustomerCreditLedger`):

| Tipo | Signo | Origen | Ejemplo |
|---|---|---|---|
| `ADVANCE` | + | `Payment` creado sin aplicar | Cliente paga RD$5,000 por adelantado de un pedido futuro. |
| `PAYMENT_OVERAGE` | + | `PaymentAllocation` con sobrante | Pago de RD$1,000 sobre una factura de RD$800. |
| `CREDIT_NOTE` | + | `CreditNote` emitida (ver sección 4) | Ajuste de precio compensatorio, sin devolución física. |
| `REFUND_TO_CREDIT` | + | Un `Refund` que, en vez de salir como dinero, se convierte en crédito | Cliente pide reembolso, el negocio ofrece crédito para su próxima compra. |
| `APPLICATION` | − | El crédito se aplica a una factura/proforma | Se usa el saldo a favor para pagar una factura nueva. |
| `REVERSAL` | ± | Corrige un movimiento anterior (nunca se edita el original) | Una aplicación equivocada se revierte con un movimiento inverso. |

`REVERSAL` existe en dos formas reales, una por ledger: `reverse_allocation`
(`PaymentAllocation`) y `reverse_credit_note_application`
(`CreditNoteApplication`) — ambas nunca editan la fila original,
siempre crean el estado `REVERSED` con auditoría (`reversed_at`/
`reversed_by`), misma filosofía de inmutabilidad que `Return`.

El saldo del cliente (`get_customer_credit_balance`) es siempre:
`suma(saldo sin aplicar de cada Payment CONFIRMADO) + suma(saldo sin
aplicar de cada CreditNote ISSUED/PARTIALLY_APPLIED)`, calculado en el
momento de la consulta (agregación SQL sobre las filas reales), nunca
cacheado sin recalcular.

## 4. `CreditNote` / `CreditNoteApplication` — CONSTRUIDO en FASE 11

Una nota de crédito es un **crédito compensatorio a favor del
cliente**, independiente de que haya existido o no una devolución
física de mercancía. Casos de uso: ajuste de precio post-venta, gesto
comercial, corrección de una factura ya emitida (que — igual que
`Return` — nunca se edita retroactivamente: la factura histórica queda
intacta, la nota de crédito es el instrumento que compensa la
diferencia).

**`CreditNote`** (cabecera, mismo patrón que `Quotation`/`Sale`):
`tenant`, `customer`, `number` (secuencia propia, prefijo `NC-`,
reutilizando `DocumentSequence`/`generate_document_number` — nunca una
segunda numeración paralela), `amount`, `reason`, `source_return`
(FK opcional a `Return`, cuando la nota de crédito compensa una
devolución física — `null=True`, igual que `Refund.return_document`),
`status`, `issue_date`, `user`, `created_at`.

Estados (`CreditNote.Status`):

```
DRAFT → ISSUED → PARTIALLY_APPLIED → FULLY_APPLIED
                → CANCELED (solo desde DRAFT o ISSUED sin aplicaciones)
```

`DRAFT` no genera crédito todavía (mismo principio que `Quotation`
`DRAFT`: existe pero no compromete nada); `ISSUED` es el momento en que
se registra el movimiento `CREDIT_NOTE` en el ledger.

**`CreditNoteApplication`**: la aplicación de una nota de crédito a una
factura — **estructuralmente idéntica a `PaymentAllocation`**, mismas
reglas de validación:

- El monto aplicado nunca excede el saldo restante de la nota de
  crédito ni el saldo pendiente de la factura destino.
- `credit_note.customer_id == sale.customer_id` obligatorio (nunca
  cruza clientes).
- `credit_note.tenant_id == sale.tenant_id` obligatorio (nunca cruza
  tenants).
- Nunca sobre-aplicación — misma validación con `select_for_update()`
  sobre ambas filas antes de escribir, mismo patrón que
  `allocate_payment`.
- Inmutable: una aplicación equivocada se corrige con
  `status=REVERSED` (+ auditoría), nunca se edita ni se borra.

Puede aplicarse a facturas **nuevas** o **pendientes** (parcial o
totalmente) — la misma factura puede recibir simultáneamente
`PaymentAllocation` (de uno o varios `Payment`) y `CreditNoteApplication`
(de una o varias `CreditNote`); `get_sale_paid_amount`/
`get_sale_balance_due` **ya están generalizados** (FASE 11) para restar
ambas fuentes juntas, nunca solo una. Aplicar a una `ProformaInvoice`
sigue sin construirse (por defecto, no — una proforma no es todavía un
compromiso definitivo, mismo razonamiento que ya impide que una
proforma reduzca inventario por sí sola, ver
`docs/proforma-invoices.md`); queda como extensión futura si una fase
posterior la necesita.

## 5. `Refund`: relación con crédito y con notas de crédito — CONSTRUIDO

`Refund` (ver `docs/returns.md`/`docs/payments.md`) sigue significando
**dinero que sale del sistema**, con su contrato exactamente intacto
(`record_refund` no cambió). `services.convert_refund_to_credit(payment,
amount, user, reason="")` (FASE 11) es la alternativa: en vez de crear
un `Refund`, emite y activa una `CreditNote` (`source_type=REFUND`,
`source_payment=payment`) por ese monto — el dinero nunca sale del
negocio, el cliente recibe saldo a favor. Decisión de diseño final: no
se agregó ningún campo a `Refund` (`converted_to_credit` nunca se
construyó) — es una función separada que nunca toca el modelo
`Refund`, exactamente la opción que este documento dejaba abierta.
`get_unallocated_payment_amount(payment)` se generalizó para restar
también lo ya convertido a crédito desde ese pago (consultando
`CreditNote.source_payment`), así que el mismo dinero nunca puede
reembolsarse Y convertirse a crédito a la vez.

## 6. Estado de cuenta del cliente (`Customer Statement`, vista futura)

Una vista de solo lectura (ningún modelo nuevo requerido) que muestra,
en orden cronológico, todo el historial financiero de un cliente:

- Facturas emitidas (`Sale`, con su `total`/`status`).
- Pagos recibidos (`Payment`).
- Asignaciones de pago (`PaymentAllocation`, incluyendo revertidas).
- Anticipos (`Payment` sin aplicar — mismo dato que "pagos", filtrado).
- Notas de crédito (`CreditNote`/`CreditNoteApplication`).
- Reembolsos (`Refund`, incluyendo los convertidos a crédito).
- Saldo pendiente por factura (`get_sale_balance_due`) y saldo a favor
  acumulado (`get_customer_credit_balance`/`CustomerCreditLedger`) al
  final del listado.

Es una **agregación de lectura** sobre los modelos ya existentes o
diseñados aquí — nunca una tabla que duplique estos datos. Pertenece a
FASE 14 (Reportes) como vista, aunque el usuario debe poder acceder a
un resumen básico desde la ficha del cliente (FASE 9) antes de que
exista el reporte completo, reutilizando las mismas funciones de
`apps.sales.services`.

## 7. Trazabilidad obligatoria

Todo movimiento de crédito (`CustomerCreditLedger`), toda aplicación de
nota de crédito (`CreditNoteApplication`) y toda conversión de
reembolso a crédito debe poder responder, sin ambigüedad: **de dónde
vino el dinero/crédito** (qué `Payment`/`CreditNote`/`Refund` lo
originó) y **a dónde fue aplicado** (qué factura, o si sigue sin
aplicar). Mismo estándar de trazabilidad documental que
`Quotation → ProformaInvoice → Sale` en FASE 10 (ver `docs/sales.md`).

## 8. Moneda (sincronización posterior a FASE 12, especificación — ver `docs/currency.md`)

`Payment.currency`/`Sale.currency`/`CreditNote.currency` (campo propio
desde la corrección de esta sección — antes se derivaba implícitamente
de `Customer`/`Sale` sin persistirse) son snapshots de texto libre, sin
catálogo real detrás — ver `docs/currency.md` para la doctrina oficial
(`Currency`/`CurrencyDenomination`), que no los migra con este
documento.

**Corregido (ver `KNOWN_ISSUES.md` #83 y `DECISIONS.md`)**:
`get_customer_credit_balance` ahora filtra los `Payment`/`CreditNote`
de un cliente por `currency=customer.currency` antes de sumar — un
pago o nota en una moneda distinta a la del cliente simplemente no
participa en este saldo, en vez de mezclarse aritméticamente como si
fuera la misma unidad. Mismo principio aplicado a `allocate_payment`
(rechaza aplicar un `Payment` a una `Sale` en otra moneda) y
`apply_credit_note` (rechaza aplicar una `CreditNote` a una `Sale` en
otra moneda) — ambos con `InvalidSalesOperation` y un mensaje de
negocio claro. Sin un motor de tipos de cambio (ver `docs/currency.md`
sección 7), **no hay conversión automática**: cuando exista FX real en
una fase futura, la conversión deberá ser explícita, auditada y con
tasa.

## 9. Qué se construyó y qué sigue pendiente

**Construido (FASE 10 + FASE 11)**: `Payment`, `PaymentAllocation`,
`CreditNote`, `CreditNoteApplication`; `get_customer_credit_balance`/
`get_sale_paid_amount`/`get_sale_balance_due`/
`get_unallocated_payment_amount` generalizados para sumar ambos
ledgers; `convert_refund_to_credit`; anticipos y saldo a favor
operacionales desde el POS (`docs/pos.md`).

**Sigue sin construirse**: ninguna tabla `CustomerCreditLedger` (ver
sección 3 — decisión final de no construirla), ninguna vista de
"Estado de cuenta" (`Customer Statement`, sección 6 — sigue siendo
FASE 14), aplicación de `CreditNoteApplication`/saldo a favor a una
`ProformaInvoice` (sección 4). Cualquier fase futura que los necesite
debe releer este documento antes de diseñar, no partir de cero.
