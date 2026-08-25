# Cuentas por Cobrar: Anticipos, Saldo a Favor, Notas de Crédito (especificación)

> **Estado: ESPECIFICACIÓN, no implementación.** Este documento define
> oficialmente el dominio de cuentas por cobrar del ERP como fuente de
> verdad arquitectónica — para que ninguna fase futura (FASE 11 y
> siguientes) invente un diseño incompatible. Los modelos `Payment` y
> `PaymentAllocation` (FASE 10 + su ampliación, ver `docs/payments.md`)
> **ya están construidos y en producción**; `CustomerCreditLedger`,
> `CustomerAdvance` (como concepto, no necesariamente un modelo nuevo —
> ver más abajo) y `CreditNote`/`CreditNoteApplication` son diseño
> aprobado, pendiente de construcción en la fase que los requiera. No
> se agrega ningún modelo, campo ni migración a partir de este
> documento.

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

## 3. `CustomerCreditLedger` (append-only, diseño futuro)

Mismo principio que `StockMovement` (FASE 8) y `PaymentAllocation`
(FASE 10): **el saldo se deriva siempre de la suma de movimientos,
nunca se guarda como un número editable.** Un campo `balance` en
`Customer` actualizado a mano sería exactamente el error que este
proyecto evita desde FASE 8 ("nunca un campo desnormalizado sin fuente
real").

Movimientos conceptuales (`CustomerCreditLedger.MovementType`):

| Tipo | Signo | Origen | Ejemplo |
|---|---|---|---|
| `ADVANCE` | + | `Payment` creado sin aplicar | Cliente paga RD$5,000 por adelantado de un pedido futuro. |
| `PAYMENT_OVERAGE` | + | `PaymentAllocation` con sobrante | Pago de RD$1,000 sobre una factura de RD$800. |
| `CREDIT_NOTE` | + | `CreditNote` emitida (ver sección 4) | Ajuste de precio compensatorio, sin devolución física. |
| `REFUND_TO_CREDIT` | + | Un `Refund` que, en vez de salir como dinero, se convierte en crédito | Cliente pide reembolso, el negocio ofrece crédito para su próxima compra. |
| `APPLICATION` | − | El crédito se aplica a una factura/proforma | Se usa el saldo a favor para pagar una factura nueva. |
| `REVERSAL` | ± | Corrige un movimiento anterior (nunca se edita el original) | Una aplicación equivocada se revierte con un movimiento inverso. |

Cada fila: `tenant`, `customer`, `movement_type`, `amount` (siempre
positivo; el signo lo determina `movement_type`, nunca un monto
negativo almacenado), `source_type`/`source_id` (referencia genérica
al `Payment`/`CreditNote`/`Refund`/factura de origen — mismo patrón de
referencia genérica ya usado por `SalesDocumentAttachment`/
`SalesActivityLog` en `apps.sales`), `user`, `created_at`, `notes`.
Nunca se edita una fila existente; una corrección es un nuevo
movimiento `REVERSAL` que referencia al original — misma filosofía de
inmutabilidad que `PaymentAllocation`/`Return`.

El saldo del cliente es siempre: `suma(movimientos positivos activos) −
suma(movimientos de aplicación activos)`, calculado en el momento de la
consulta (agregación SQL), nunca cacheado sin recalcular.

## 4. `CreditNote` / `CreditNoteApplication`

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
(de una o varias `CreditNote`); el saldo pendiente de la factura
(`get_sale_balance_due`, cuando se generalice) deberá restar ambas
fuentes, nunca solo una. También podrá aplicarse a una `ProformaInvoice`
cuando la política del tenant lo permita explícitamente (por defecto,
no — una proforma no es todavía un compromiso definitivo, mismo
razonamiento que ya impide que una proforma reduzca inventario por sí
sola, ver `docs/proforma-invoices.md`); esa política es una decisión de
la fase que implemente `CreditNoteApplication`, no de este documento.

## 5. `Refund`: relación con crédito y con notas de crédito

`Refund` (ya construido, ver `docs/returns.md`/`docs/payments.md`)
sigue significando **dinero que sale del sistema**. La ampliación
conceptual pedida aquí es que un reembolso pueda, alternativamente,
**convertirse en crédito** en vez de salir como dinero físico — decisión
del negocio en el momento de atenderlo, no una regla automática. Esto
NO cambia el modelo `Refund` existente hoy; el diseño futuro es:

- `record_refund` (dinero sale) sigue exactamente igual — ninguna
  fase futura debe romper su contrato actual.
- Una función nueva (p. ej. `convert_refund_to_credit(payment, amount,
  user, ...)`, sin construir todavía) generaría un movimiento
  `REFUND_TO_CREDIT` en el ledger en vez de un `Refund` `COMPLETED` —
  el dinero nunca sale del negocio, el cliente recibe saldo a favor.
- Ambos caminos deben referenciar siempre el `Payment` original (nunca
  un reembolso "huérfano" sin origen) y quedar auditados con acciones
  distintas.
- Este documento **no decide todavía** si `Refund` gana un campo
  `converted_to_credit`/`credit_note_generated` o si
  `convert_refund_to_credit` vive como una función separada que nunca
  toca `Refund` — es una decisión de diseño de la fase que lo
  construya, con la única restricción de no crear un segundo tipo de
  "reembolso" incompatible con el actual.

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

## 8. Qué NO se construye con este documento

Este documento es una especificación aprobada, no una implementación.
No se creó: ningún modelo (`CustomerCreditLedger`, `CreditNote`,
`CreditNoteApplication`), ningún campo nuevo en `Payment`/`Refund`,
ninguna migración, ninguna vista de "Estado de cuenta". La fase que
primero necesite uno de estos conceptos (probablemente FASE 11 para
anticipos/saldo a favor operacional, o una fase de Cuentas por
Cobrar dedicada si el usuario la autoriza) debe releer este documento
antes de diseñar, no partir de cero.
