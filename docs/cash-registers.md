# Cajas y Sesiones de Caja

> **Estado: CONSTRUIDO en FASE 11** (`apps/pos`). Este documento se
> escribió originalmente como especificación previa a la fase; el
> diseño se implementó tal como está descrito aquí, sin desviaciones.
> Ver `docs/pos.md` para el resumen operacional completo (checkout,
> descuentos, cobros) y detalles de implementación adicionales
> (`IntegrityError` traducido, fondo inicial en 0, etc.). Ver
> `docs/currency.md` (sincronización posterior a FASE 12, especificación
> pura) para la doctrina de moneda por caja, denominaciones, cierre por
> denominaciones y vocabulario oficial de cambio — secciones 11-12.

## 1. Múltiples cajas por tenant (requisito oficial)

Una misma tienda/tenant puede tener **cualquier cantidad** de cajas o
terminales — el diseño **no se limita a un número fijo** (ni a 1, ni a
3). El administrador del tenant podrá crear tantas `CashRegister` como
necesite (`CAJA-01`, `CAJA-02`, `CAJA-03`, ...), cada una identificada
por un código propio.

**`CashRegister`** (`TenantScopedModel`, mismo patrón de aislamiento
que todo modelo de negocio desde FASE 3): `tenant`, `name`, `code`
(único por tenant), `status` (activa/inactiva), `terminal` (identificador
de hardware/estación cuando corresponda, texto libre opcional),
usuarios autorizados a operarla (relación con el sistema de permisos —
FASE 3 ya tiene `Membership.Role`; FASE 15 puede refinarlo con
permisos más granulares, ver `docs/approvals.md`).

## 2. `CashSession`: una jornada de caja abierta

**`CashSession`** (`TenantScopedModel`): representa el período entre
una apertura y un cierre de una `CashRegister` concreta, operada por un
usuario/cajero.

Campos: `tenant`, `cash_register` (FK), `user` (cajero), `opened_at`,
`opening_amount` (fondo inicial), `closed_at` (nulo mientras está
abierta), `expected_cash` (calculado al cerrar, ver sección 5),
`counted_cash` (contado físicamente por el cajero al cerrar),
`difference` (`counted_cash − expected_cash`, calculado, nunca
editado a mano), `status` (`OPEN`/`CLOSED`), `notes`.

## 3. Reglas de sesiones (obligatorias desde el diseño, no opcionales)

- **Un usuario no puede tener dos `CashSession` `OPEN` simultáneas** —
  ni en la misma caja ni en cajas distintas, salvo que una política de
  permiso explícita lo autorice (caso excepcional, no el
  comportamiento por defecto).
- **Una `CashRegister` no puede tener dos `CashSession` `OPEN`
  simultáneas** — abrir una caja ya abierta por otro usuario debe
  rechazarse con un mensaje claro, nunca silenciosamente crear una
  segunda sesión concurrente sobre la misma caja física.
- Cualquier excepción a estas dos reglas requiere permiso explícito
  (vía `apps.approvals`, construido en esta misma fase — ver
  `docs/approvals.md`) — nunca un bypass silencioso desde el frontend.
  Nota: FASE 11 no llegó a necesitar una excepción real a estas dos
  reglas de exclusividad (ninguna operación las requirió); quedan
  documentadas como el mecanismo a usar si una fase futura lo necesita.
- Toda apertura y todo cierre se auditan (usuario, caja, fecha, montos)
  — mismo estándar de auditoría que el resto del sistema desde FASE 8.
- Toda operación de caja (venta en efectivo, anticipo en efectivo,
  entrada, salida, devolución en efectivo) debe quedar asociada a la
  `CashSession` activa en el momento en que ocurrió, cuando corresponda
  — nunca "flotando" sin sesión cuando la operación es una operación de
  caja real. Esto implica que `Payment` necesitará, en FASE 11, una FK
  opcional `cash_session` (nulo para pagos que no pasan por una caja
  física, p. ej. cobros administrativos futuros) — campo a agregar en
  FASE 11, no en esta especificación.

## 4. Apertura de caja

Se registra: `usuario`, `caja`, `fecha/hora` (`opened_at`), `fondo
inicial` (`opening_amount`), `notas` opcionales. Estado resultante:
`OPEN`. Ninguna venta que requiera caja puede confirmarse antes de que
exista una `CashSession` `OPEN` para el usuario/caja que está operando
(ver sección 8, regla obligatoria para POS).

## 5. Movimientos de caja (`CashMovement`)

Cada operación que afecta el efectivo físico (o que debe quedar
registrada dentro de una sesión aunque no mueva efectivo) genera una
fila — mismo principio append-only que `StockMovement`/
`PaymentAllocation`/`CreditNoteApplication`:

| Tipo | Efecto en efectivo físico |
|---|---|
| Apertura (fondo inicial) | + (es el punto de partida, no un movimiento sumado aparte) |
| Venta en efectivo | + |
| Anticipo en efectivo | + |
| Entrada de efectivo (aporte manual) | + |
| Salida de efectivo (retiro/gasto menor) | − |
| Devolución en efectivo (`Refund` con método efectivo) | − |
| Retiro | − |
| Ajuste autorizado (requiere `ApprovalRequest`, ver `docs/approvals.md`) | ± |
| Otros tipos explícitamente configurables por el tenant | ± |

Cada movimiento: `tenant`, `cash_session` (FK), `movement_type`,
`amount` (siempre positivo; el signo lo determina `movement_type`),
`user`, `created_at`, `reason` (obligatorio para salidas/ajustes),
referencia genérica al `Payment`/`Refund` de origen cuando aplique
(mismo patrón de referencia genérica ya usado en `apps.sales`).

## 6. Medios de pago vs. efectivo físico

**Solo el efectivo (`PaymentMethod.CASH`) afecta el efectivo físico de
la caja.** Tarjeta, transferencia, PayPal y cualquier otro método
quedan registrados en la `CashSession` (para el resumen de "cobrado por
método" de esa jornada) pero **nunca incrementan `expected_cash`** —
un pago con tarjeta no pone billetes en la gaveta.

## 7. Cierre de caja

```
Efectivo esperado
  = fondo inicial (opening_amount)
  + entradas
  + ventas en efectivo
  + anticipos en efectivo
  − salidas
  − refunds en efectivo
```

calculado siempre como una **agregación sobre los `CashMovement` de la
sesión** (nunca un número editado a mano) y comparado contra
`counted_cash` (el conteo físico real que hace el cajero). Se registra:
`expected_cash`, `counted_cash`, `difference` (sobrante si es positivo,
faltante si es negativo), `user`, `closed_at`, `notes`. **El resultado
histórico de un cierre nunca se modifica manualmente** — una corrección
después del hecho es un nuevo movimiento/nota auditada, nunca un
`UPDATE` silencioso sobre una sesión ya `CLOSED` (mismo principio de
inmutabilidad que `Return`/`PaymentAllocation` revertida en vez de
editada).

## 8. Regla obligatoria para el POS (FASE 11)

**Ninguna venta operativa de mostrador que requiera caja puede
confirmarse/cobrarse sin una `CashSession` `OPEN` y válida** para el
usuario/caja que la está procesando. Si no existe:

- Bloquear la operación antes de escribir nada.
- Mostrar un mensaje claro indicando que debe abrirse una sesión de
  caja primero.
- Nunca confirmar la venta "igual" y dejar la reconciliación para
  después.

Una futura factura administrativa que **no** sea una operación física
de caja (p. ej. una venta a crédito facturada desde una pantalla de
oficina, sin cobro en efectivo en el momento) podrá tener un flujo
distinto — esta regla aplica específicamente a operaciones de caja/POS,
no a todo el motor de ventas (`apps.sales` ya permite crear/confirmar
una venta sin ningún pago asociado, ver `docs/sales.md`).

## 9. Relación con `apps.sales` (ya construido)

`CashRegister`/`CashSession`/`CashMovement` son una capa **operacional
sobre** el motor comercial ya existente, no una segunda fuente de
verdad de ventas/pagos:

- Una "venta en efectivo" sigue siendo un `Sale` confirmado +
  `Payment(method=CASH)` aplicado vía `record_payment_for_sale` — el
  `CashMovement` correspondiente solo referencia ese `Payment`, nunca
  duplica su monto en una tabla paralela.
- Un "anticipo en efectivo" sigue siendo `services.create_payment(...,
  method=CASH)` sin aplicar — igual que arriba.
- Una "devolución en efectivo" sigue siendo `services.record_refund(...)`
  con el método heredado del `Payment` original.

## 11. Moneda, denominaciones y cierre por denominaciones (especificación futura, ver `docs/currency.md`)

Sincronización posterior a FASE 12: `CashRegister` no tiene hoy ningún
campo de moneda — la doctrina oficial (`docs/currency.md`) prevé
agregarle `currency` (FK a un futuro `Currency`), de modo que su
`CashSession` cuente físicamente en una sola moneda, sin mezclar
denominaciones de monedas distintas en un mismo conteo. El cierre por
denominaciones (`CashDenominationCount`, referenciando siempre
`CurrencyDenomination` — nunca un segundo catálogo) es el modo
profesional recomendado, con un modo rápido por total como opción
administrativa. `CashClosing` formaliza el cierre como entidad propia
(hoy esos datos viven en los campos de `CashSession` descritos en la
sección 2) — inmutable una vez cerrado, con "sobrante"/"faltante" como
lecturas de `difference`, nunca campos nuevos que puedan
desincronizarse. **Nada de esto está construido todavía** — ver
`docs/currency.md` para el diseño completo antes de implementar.

## 12. Cambio, pagos mixtos y `CashMovement` neto — ya correcto (confirmado)

`docs/currency.md` formaliza el vocabulario oficial `amount_due`/
`amount_received`/`change_amount` y confirma, tras revisión explícita,
que el comportamiento actual de `apps.pos` (`CheckoutView`/
`checkout_sale`) **ya cumple correctamente** ambas reglas: el cambio se
calcula solo sobre la parte en efectivo de un pago mixto, y el
`CashMovement` de una venta con cambio registra siempre el efecto neto
(ej. venta 1275, cliente entrega 2000 → movimiento de `+1275`, nunca
`+2000`/`-725` por separado) — nunca se modificó código con esta
sincronización, solo se confirmó y nombró oficialmente lo ya existente.

## 13. Estado de implementación (FASE 11)

`CashRegister`, `CashSession` y `CashMovement` están construidos en
`apps/pos` tal como se diseñó aquí, con una diferencia menor respecto
a la sección 3: **no se agregó un campo `cash_session` a `Payment`**
— en su lugar, `apps.pos.services` crea el `CashMovement`
correspondiente (`SALE_CASH`/`CUSTOMER_ADVANCE_CASH`/`CASH_REFUND`)
referenciando el `Payment`/`Refund` de origen mediante
`reference_type`/`reference_id` (referencia genérica, mismo patrón ya
usado por `SalesActivityLog`), evitando acoplar `apps.sales` a
`apps.pos`. Ver `docs/pos.md` para el resto de detalles de
implementación (incluyendo la exclusividad de sesión por usuario, que
no tiene una única fila que bloquear con `select_for_update()` y se
resuelve traduciendo el `IntegrityError` de la `UniqueConstraint` a
`InvalidPosOperation`).
