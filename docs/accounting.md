# Contabilidad General (FASE 14, ampliada en el cierre controlado posterior)

`apps/accounting` es la **fuente financiera central** del ERP —
plan de cuentas jerárquico, períodos contables, asientos de partida
doble (`JournalEntry`/`JournalEntryLine`), inmutabilidad contable
(reverso, nunca edición) y una capa de contabilización automática
(`record_business_event`) que traduce eventos de negocio ya
construidos (venta confirmada, pago recibido, pago de gasto, pago de
nómina, COGS, factura de proveedor, pago a proveedor, devolución a
proveedor, cierre de sesión de caja) en asientos reales, sin que
ningún módulo reimplemente su propia lógica contable.

**Ampliación de cierre de FASE 14**: el cierre inicial de FASE 14
dejó documentadas 4 integraciones sin conectar (COGS, Compras/Cuentas
por Pagar, cierre de caja, impuestos multi-código) porque requerían
decisiones de política contable que el usuario no había dado
todavía. El usuario entregó esas decisiones explícitamente (costeo
específico para SERIALIZED, promedio ponderado para QUANTITY, cuentas
Cash Over/Short, arquitectura `TaxCode`) y esta ampliación las cierra
— ver secciones 11-15 más abajo.

## 1. Plan de cuentas (`Account`)

Jerárquico vía `parent` (self, profundidad no limitada). `level` se
calcula una sola vez al crearse (`parent.level + 1`, raíz = 1) y no
cambia después — mover una cuenta de padre no está soportado hoy (sin
un caso de uso real que lo exija). `allows_posting=False` marca una
cuenta de agrupación (ej. «1000 Activos») que nunca recibe líneas de
asiento directamente — solo sus hijas "hoja" (`allows_posting=True`)
lo hacen; `post_journal_entry` lo verifica explícitamente.

`normal_balance` (débito/crédito) se deriva automáticamente del
`account_type` (`Account.DEFAULT_NORMAL_BALANCE`, único lugar donde
existe ese mapeo) salvo que se indique explícitamente — activo/costo/
gasto son de naturaleza débito; pasivo/patrimonio/ingreso son de
naturaleza crédito.

**Decisión de diseño**: no existe un modelo "ChartOfAccounts" separado
— el plan de cuentas de un tenant es simplemente el conjunto de sus
filas `Account`. Un tenant no necesita múltiples planes de cuentas
nombrados hoy; si esa necesidad apareciera, se agregaría sin romper
`Account` (que ya es tenant-scoped).

## 2. Período contable (`AccountingPeriod`)

```
OPEN ──(primer descuadre detectado al cerrar → rechazado)──> CLOSED ──reabrir (con motivo, auditado)──> REOPENED ──> (puede cerrarse de nuevo)
CLOSING es un estado transicional preparado, no usado activamente hoy.
```

Un período **no** tiene número comercial vía `DocumentSequence`
(decisión deliberada): se identifica por su rango de fechas (`name`,
ej. «2025-01») — no es un documento que se emite, es un contenedor de
tiempo. Dos períodos del mismo tenant nunca pueden solaparse en fechas
(salvo que uno ya esté `CLOSED`).

`close_period` valida, como red de seguridad adicional, que
SUM(débitos) == SUM(créditos) de todas las líneas `POSTED` del
período antes de cerrarlo — en un sistema de partida doble correcto
esto siempre debería cumplirse si cada asiento individual cuadró al
contabilizarse (`post_journal_entry`), pero la verificación agregada
detecta cualquier inconsistencia real antes de bloquear el período.

Una vez `CLOSED`, no se admiten asientos normales — reabrir exige un
motivo (auditado, `AccountingActivityLog`).

## 3. Asiento contable (`JournalEntry`/`JournalEntryLine`)

Numerado vía la misma `DocumentSequence` de Ventas/Compras/Gastos/
Nómina (`DocumentType.JOURNAL_ENTRY`, prefijo «AST-») — nunca un
segundo sistema de numeración. Cada línea es débito O crédito, nunca
ambos ni ninguno (`CheckConstraint`). `post_journal_entry` valida,
antes de contabilizar:

- SUM(debit) == SUM(credit) — **nunca se permite un asiento
  descuadrado**.
- Todas las líneas comparten la MISMA moneda (sin motor de FX
  completo, ver `docs/currency.md` — mezclar monedas en un mismo
  asiento se rechaza explícitamente).
- Cada cuenta referenciada `allows_posting=True` y está activa.
- El período está `OPEN`/`REOPENED` (nunca `CLOSED`/`CLOSING`).

## 4. Inmutabilidad — reverso, nunca edición

Un asiento `POSTED` nunca se edita ni se borra. `reverse_journal_entry`
crea un asiento NUEVO con los montos invertidos (débito↔crédito),
enlazado vía `reversal_of`, contabilizado de inmediato — el asiento
original permanece exactamente como fue creado. Idempotente: reversar
un asiento ya reversado devuelve la reversa existente en vez de crear
una segunda.

## 5. Numeración

Ver sección 3 — `JournalEntry.number` reutiliza literalmente
`apps.sales.services.generate_document_number`/`DocumentSequence`,
nunca un contador propio ni el ID de PostgreSQL como número comercial.

## 6. Idempotencia de la contabilización automática

`JournalEntry` tiene una `UniqueConstraint` parcial sobre (tenant,
source_type, source_event_key) cuando `source_event_key` no está
vacío — la garantía real de que un reintento de la operación de
negocio que originó el asiento (ej. una venta confirmada dos veces por
una race condition de red) nunca contabiliza dos veces.
`record_business_event` verifica esto ANTES de crear nada: si ya
existe un asiento para esa clave, lo devuelve tal cual.

## 7. Contabilización automática — arquitectura (Business Event → Accounting Service → Journal Entry)

`apps.accounting.services.record_business_event` es el punto de
entrada genérico. Sobre él se construyen los integradores concretos
(`record_sale_confirmed`, `record_sale_cogs`, `record_customer_payment`,
`record_return_cogs_reversal`, `record_expense_payment_event`,
`record_payroll_payment_event`, `record_supplier_invoice_confirmed`,
`record_supplier_payment`, `record_supplier_return`,
`record_cash_session_closing`), cada uno traduciendo su evento a
líneas de asiento usando **cuentas de control** resueltas vía
`AccountMapping` (tabla `clave → Account` por tenant, hoy 12 claves) —
nunca una cuenta hardcodeada.

### Regla de resiliencia obligatoria

La contabilización automática **nunca** puede romper la operación de
negocio que la origina. Cada integrador real (`apps.sales.services.
confirm_sale`/`create_payment`/`create_return`, `apps.expenses.services.
record_expense_payment`, `apps.payroll.services.record_payroll_payment`,
`apps.purchases.services.confirm_supplier_invoice`/
`create_supplier_payment`/`create_supplier_return`, `apps.pos.services.
close_cash_session`) llama a un wrapper `try_record_*` que captura
CUALQUIER excepción, registra el fallo (`AccountingActivityLog.
AUTO_POSTING_FAILED`, `logger.warning`) y continúa — la operación de
negocio se completa exactamente igual que antes de que existiera
`apps.accounting`. Sin `AccountMapping` configurado para las claves
que un integrador necesita, ese evento simplemente NO se contabiliza
(`return None`), tampoco es un error. Regla arquitectónica
**permanente** para cualquier integración automática futura, no solo
las ya construidas.

Los imports de `apps.accounting.services` dentro de
`apps.sales`/`apps.expenses`/`apps.payroll`/`apps.purchases`/`apps.pos`
son **diferidos** (dentro de la función, no al nivel de módulo) —
`apps.accounting.services` ya importa `apps.sales.services`/
`apps.sales.models`/`apps.purchases.models` (para la numeración y las
integraciones de Compras/AP), así que un import a nivel de módulo en
sentido contrario crearía un ciclo de importación real.

### Qué está conectado HOY (9 integraciones reales, probadas)

| Evento | Asiento generado | Cuentas de control necesarias |
|---|---|---|
| Venta confirmada (`confirm_sale`) | Dr Cuentas por cobrar (total) / Cr Ingresos (subtotal−descuento) / Cr Impuestos por pagar (si aplica, o una línea por cada cuenta de `TaxCode` distinta — ver sección 15) | `accounts_receivable`, `sales_revenue`, `sales_tax_payable` |
| Costo de ventas de la misma venta (`record_sale_cogs`) — **entrada separada** | Dr Costo de ventas / Cr Inventario, por `SUM(SaleItem.cost_amount)` | `cost_of_goods_sold`, `inventory_asset` |
| Pago de cliente registrado (`create_payment`) | Dr Efectivo y equivalentes / Cr Cuentas por cobrar | `cash_and_equivalents`, `accounts_receivable` |
| Devolución de mercancía (`create_return`) — reverso de COGS | Dr Inventario / Cr Costo de ventas, por el costo de lo REALMENTE devuelto (proporcional en devoluciones parciales) — solo si la venta original tiene COGS contabilizado | `cost_of_goods_sold`, `inventory_asset` |
| Pago de gasto (`record_expense_payment`) | Dr Gastos operativos / Cr Efectivo y equivalentes | `operating_expense`, `cash_and_equivalents` |
| Pago de nómina (`record_payroll_payment`) | Dr Gasto de nómina / Cr Efectivo y equivalentes | `payroll_expense`, `cash_and_equivalents` |
| Factura de proveedor confirmada (`confirm_supplier_invoice`) | Dr Inventario (líneas ligadas a una orden de compra) y/o Dr Gasto operativo (líneas sin orden) y/o Dr Impuesto por recuperar (si hay impuesto) / Cr Cuentas por pagar | `inventory_asset`, `operating_expense`, `purchase_tax_receivable`, `accounts_payable` |
| Pago a proveedor (`create_supplier_payment`) | Dr Cuentas por pagar / Cr Efectivo y equivalentes — espejo exacto del pago de cliente | `accounts_payable`, `cash_and_equivalents` |
| Devolución a proveedor (`create_supplier_return`) | Dr Cuentas por pagar / Cr Inventario, por el costo de lo devuelto — **solo si** ya existe una factura de ese proveedor/orden contabilizada | `accounts_payable`, `inventory_asset` |
| Cierre de sesión de caja con diferencia (`close_cash_session`) | Sobrante: Dr Efectivo / Cr Sobrante de caja. Faltante: Dr Faltante de caja / Cr Efectivo — nada si la diferencia es 0 | `cash_and_equivalents`, `cash_over`, `cash_short` |

### Qué queda PREPARADO, no conectado automáticamente (deliberado)

- **GRNI (Goods Received Not Invoiced)**: recibir mercancía
  (`receive_purchase_order`) mueve el inventario físico
  (`StockMovement`/`InventoryUnit`) de inmediato, pero el asiento
  contable (Dr Inventario / Cr Cuentas por Pagar) solo se genera
  cuando la FACTURA del proveedor se confirma — una recepción sin
  factura todavía no genera pasivo contable. Modelar el pasivo
  provisional de "recibido pero no facturado" (GRNI/accrual) es una
  decisión de política contable adicional, no pedida explícitamente;
  documentada aquí como el próximo paso natural si se necesitara.
- **Impuestos multi-código en Compras**: `TaxCode`/`SaleItemTax`
  (sección 15) se conectó solo en Ventas — `apps.purchases` sigue
  usando el impuesto plano existente (`SupplierInvoiceItem.tax_rate`/
  `tax_amount`, hacia la cuenta única `purchase_tax_receivable`).
  Extender `TaxCode` a líneas de compra es simétrico y queda
  preparado, no conectado, para no duplicar el trabajo de una
  arquitectura que la propia especificación pide "preparar, no
  implementar legislación de un país".
- **Impuestos con retenciones/normativa fiscal de un país específico**:
  `TaxCode` cubre tasa/cuenta simples; retenciones, normativa
  específica y documentos fiscales electrónicos NO se construyen sin
  una definición normativa validada.

## 8. Reportes contables (leen directamente de `JournalEntry`/`JournalEntryLine`, nunca recalculan de otra fuente)

- **Balance de comprobación** (`get_trial_balance`): por cuenta,
  total débito/crédito/saldo de las líneas `POSTED` del período — debe
  cuadrar siempre.
- **Libro Mayor** (`get_general_ledger`): movimientos cronológicos de
  UNA cuenta con saldo acumulado — permite drill-down al asiento
  origen.
- **Libro Diario** (`get_general_journal`): asientos `POSTED`
  cronológicos con sus líneas.
- **Balance General** (`get_balance_sheet`): activo/pasivo/patrimonio,
  **acumulado** desde siempre hasta `period.end_date` — son saldos,
  no flujos del período.
- **Estado de Resultados** (`get_income_statement`): ingreso/costo/
  gasto, **solo el flujo DENTRO del rango** del período — a diferencia
  del balance general, se reinicia cada período.
- **Flujo de efectivo / Patrimonio (cambios)**: no construidos en esta
  fase — el balance general ya expone el saldo de patrimonio;
  un estado de flujo de efectivo por actividad (operación/inversión/
  financiación) requiere clasificar cada cuenta por actividad, una
  decisión de diseño que no fue provista y que se documenta aquí como
  pendiente, nunca inventada.

## 9. Multi-Tenancy y Seguridad

Todo modelo hereda `TenantScopedModel`; todo servicio filtra `tenant`
explícitamente y usa `all_objects`. Cuenta padre/mapeo de otro tenant
se rechazan explícitamente. Vistas usan `get_object_or_404(...,
tenant=request.tenant)`.

## 10. Qué NO se construyó (deliberado)

- Motor de tipos de cambio completo (mismo criterio que
  `docs/currency.md` en todo el proyecto) — un asiento con líneas en
  monedas distintas se rechaza, nunca se convierte automáticamente.
  Los campos `original_amount`/`original_currency`/`exchange_rate` en
  `JournalEntryLine` están preparados para cuando exista FX real.
- GRNI, impuestos multi-código en Compras, retenciones/normativa
  fiscal de país específico, documentos fiscales electrónicos — ver
  sección 7 ("Qué queda PREPARADO").
- Flujo de efectivo y estado de cambios en el patrimonio como
  reportes formales — el balance general/estado de resultados cubren
  el núcleo pedido explícitamente por la especificación (secciones
  21-26), estos dos requieren decisiones de clasificación adicionales
  no provistas.
- Reportes programados (envío automático) — ver `docs/reports.md`.
  Exportación PDF/XLSX de reportes **sí se construyó** en la
  ampliación de cierre (sección 16 de `docs/reports.md`) — ya no es
  una brecha.

## 11. Política de costeo (ampliación de cierre de FASE 14)

Dos políticas de costeo, una por tipo de seguimiento de inventario —
nunca la misma para ambos, nunca FIFO en esta ampliación (explícitamente
descartado por el usuario):

- **SERIALIZED → costo específico por unidad**: ya existía desde
  FASE 8/12 (`InventoryUnit.unit_cost`, congelado al recibir la
  unidad). Sin cambios de modelo en esta ampliación.
- **QUANTITY → costo promedio ponderado (nuevo)**: `StockMovement`
  (`apps/inventory/models.py`) gana dos columnas nuevas, en el MISMO
  patrón que `stock_before`/`stock_after` (calculadas y guardadas una
  sola vez por movimiento, nunca editadas después):
  - `unit_cost`: costo de ESE movimiento — el costo del lote en una
    entrada (recibido de una compra, o restaurado en una devolución
    de venta a SU costo original), o el promedio vigente consumido en
    una salida. `null` en un ajuste (un conteo físico no trae un
    costo confiable — nunca se fabrica uno).
  - `average_cost_after`: promedio ponderado por unidad vigente
    DESPUÉS de este movimiento. "Costo promedio actual de un
    producto" = `average_cost_after` del `StockMovement` más
    reciente — exactamente como el stock actual = `stock_after` del
    más reciente (`apps.inventory.services.get_current_average_cost`).
  - Fórmula en una entrada con costo conocido: `nuevo_promedio =
    (stock_anterior×promedio_anterior + cantidad×costo_del_lote) /
    stock_posterior`. En una salida, el promedio NO cambia (retirar
    unidades a su propio costo promedio nunca altera el promedio de
    las que quedan) — el costo consumido es el promedio vigente en
    ese instante.
  - `apps.purchases.services.receive_purchase_order` ahora pasa el
    costo real recibido a `register_stock_in` (antes lo registraba
    "a ciegas", sin costo — hallazgo corregido en esta ampliación, ver
    `docs/project-status/KNOWN_ISSUES.md`).
- Arquitectura preparada para un método alternativo (ej. FIFO por
  capas) sin reescribir `apps.sales`/`apps.inventory`: el costo
  consumido siempre se lee de `StockMovement.unit_cost`/
  `average_cost_after` (para QUANTITY) o `InventoryUnit.unit_cost`
  (para SERIALIZED) — cambiar el método de cálculo interno de
  `_register_movement` nunca requiere tocar `apps.sales.services.
  confirm_sale` ni la contabilización automática.

## 12. COGS — Costo de Ventas

`SaleItem` gana `cost_amount` (Decimal, default 0) — snapshot del
costo de ESA línea, poblado en `confirm_sale` en el momento en que el
inventario REALMENTE se mueve (nunca al agregar la línea a un
borrador, porque el promedio ponderado puede cambiar entre ambos
momentos). `record_sale_cogs` genera Dr Costo de Ventas / Cr
Inventario por `SUM(cost_amount)` — asiento SEPARADO del de ingresos,
clave `sale-cogs-{sale.pk}` (idempotente). Si el costo no se pudo
determinar (p. ej. una venta de un producto sin ninguna entrada con
costo conocido todavía), `cost_amount=0` y NO se postea ningún asiento
de COGS — la venta y su asiento de ingresos se completan igual,
resiliencia intacta.

Devolución de mercancía (`create_return`): reversa el COGS de lo
REALMENTE devuelto (proporcional en devoluciones parciales por
cantidad; el costo específico de la unidad en devoluciones
serializadas) — SOLO si la venta original ya tiene un asiento de COGS
contabilizado (si no, no-op). Un `Refund` monetario (modelo separado,
nunca referenciado desde `create_return`) **nunca** dispara esta
reversa — por construcción, no por un chequeo adicional: son dos
código-caminos completamente independientes.

## 13. Compras + Cuentas por Pagar

`confirm_supplier_invoice` separa cada línea por `purchase_order_item_id`
(no nulo → Dr Inventario, real compra de inventario; nulo → Dr Gasto
Operativo, servicio o costo no ligado a inventario) más una línea Dr
Impuesto por Recuperar si hay impuesto, Cr Cuentas por Pagar por el
total. `create_supplier_payment` es el espejo exacto de
`record_customer_payment` (Dr Cuentas por Pagar / Cr Efectivo).
`create_supplier_return` reversa Dr Cuentas por Pagar / Cr Inventario
por el costo de lo devuelto, solo si ya existe una factura
contabilizada para esa orden — nunca mezclado con Cuentas por Cobrar
(mismas cuentas de control nunca compartidas entre ambos lados salvo
`cash_and_equivalents`, el mismo efectivo físico). `SupplierAdvance`
no es un modelo nuevo — un anticipo sigue siendo un `SupplierPayment`
sin aplicar (doctrina de FASE 12, sin cambios).

## 14. Cierre de Caja — Cash Over / Cash Short

No se creó un modelo `CashClosing` nuevo — el cierre YA es
`CashSession.status=CLOSED` con `expected_cash`/`counted_cash`/
`difference` (`apps.pos.services.close_cash_session`, FASE 11), el
evento de cierre real hoy. (`CashClosing`/`CashDenominationCount`
siguen siendo doctrina futura de `docs/currency.md`, ligada a
Moneda/Denominaciones — construirlos ahora, fuera de esa cadena de
dependencia, inventaría arquitectura no pedida.) Convención contable
estándar "Cash Over and Short": sobrante (`difference > 0`) → Dr
Efectivo / Cr Sobrante de caja (`cash_over`, tipo REVENUE); faltante
(`difference < 0`) → Dr Faltante de caja (`cash_short`, tipo EXPENSE)
/ Cr Efectivo. Sin diferencia, no hay nada que reconocer. El efectivo
físico esperado (ventas/pagos/gastos/nómina en efectivo) ya se
contabiliza vía las integraciones existentes — este asiento reconoce
únicamente la DIFERENCIA descubierta al contar, nunca la duplica.

## 15. Impuestos multi-código

Nuevo modelo tenant-configurable `TaxCode` (`code`/`name`/`rate`/
`account` — su propia cuenta de control, nunca a través del enum fijo
`AccountMapping.Key`, porque los códigos son ilimitados y definidos
por el tenant) y `SaleItemTax` (cero, una o varias filas por línea de
venta — `rate_snapshot`/`base_amount`/`tax_amount` congelados al
aplicarse). **Aditivo**: los campos planos existentes `SaleItem.
tax_rate`/`tax_amount` siguen funcionando exactamente igual para
cualquier tenant que nunca asigne un `TaxCode` — cero cambio de
comportamiento para tenants existentes. `record_sale_confirmed`
detecta si la venta tiene filas `SaleItemTax`: si sí, genera una
línea Cr por cada cuenta de `TaxCode` distinta usada (agrupando
montos); si no, usa exactamente el camino simple existente
(`sales_tax_payable`). Sin legislación de un país específico
hardcodeada — el tenant define sus propios códigos y tasas.

## 16. Nota de consolidación de documentación

La especificación de FASE 14 pide tres documentos separados —
`docs/accounting-periods.md`, `docs/journal.md`, `docs/general-ledger.md`
— además de este archivo. Se consolidó su contenido aquí en vez de
triplicar documentos muy cortos y con referencias cruzadas constantes
entre sí (período↔asiento↔libro mayor son tres caras del mismo motor,
nunca se explican de forma aislada sin repetirse): "Período contable"
es la sección 2, "Asiento contable" la sección 3, "Libro Mayor" vive
dentro de la sección 8 (Reportes contables, `get_general_ledger`). Los
tres archivos nombrados existen igualmente en `docs/` como archivos
delgados que redirigen a estas secciones, para que un enlace o
búsqueda por ese nombre exacto siga encontrando el contenido real —
nunca contenido duplicado que pueda desincronizarse de esta fuente
única.
