# Contabilidad General (FASE 14)

`apps/accounting` es la **fuente financiera central** del ERP —
plan de cuentas jerárquico, períodos contables, asientos de partida
doble (`JournalEntry`/`JournalEntryLine`), inmutabilidad contable
(reverso, nunca edición) y una capa de contabilización automática
(`record_business_event`) que traduce eventos de negocio ya
construidos (venta confirmada, pago recibido, pago de gasto, pago de
nómina) en asientos reales, sin que ningún módulo reimplemente su
propia lógica contable.

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
(`record_sale_confirmed`, `record_customer_payment`,
`record_expense_payment_event`, `record_payroll_payment_event`), cada
uno traduciendo su evento a líneas de asiento usando **cuentas de
control** resueltas vía `AccountMapping` (tabla `clave → Account` por
tenant) — nunca una cuenta hardcodeada.

### Regla de resiliencia obligatoria

La contabilización automática **nunca** puede romper la operación de
negocio que la origina. Cada integrador real (`apps.sales.services.
confirm_sale`/`create_payment`, `apps.expenses.services.
record_expense_payment`, `apps.payroll.services.record_payroll_payment`)
llama a un wrapper `try_record_*` que captura CUALQUIER excepción,
registra el fallo (`AccountingActivityLog.AUTO_POSTING_FAILED`,
`logger.warning`) y continúa — la venta/pago/gasto/nómina se completa
exactamente igual que antes de que existiera `apps.accounting`. Sin
`AccountMapping` configurado para las claves que un integrador
necesita, ese evento simplemente NO se contabiliza (`return None`),
tampoco es un error.

Los imports de `apps.accounting.services` dentro de
`apps.sales`/`apps.expenses`/`apps.payroll` son **diferidos** (dentro
de la función, no al nivel de módulo) — `apps.accounting.services` ya
importa `apps.sales.services`/`apps.sales.models` (para la
numeración), así que un import a nivel de módulo en sentido contrario
crearía un ciclo de importación real.

### Qué está conectado HOY (4 integraciones reales, probadas)

| Evento | Asiento generado | Cuentas de control necesarias |
|---|---|---|
| Venta confirmada (`confirm_sale`) | Dr Cuentas por cobrar (total) / Cr Ingresos (subtotal−descuento) / Cr Impuestos por pagar (si aplica) | `accounts_receivable`, `sales_revenue`, `sales_tax_payable` |
| Pago de cliente registrado (`create_payment`) | Dr Efectivo y equivalentes / Cr Cuentas por cobrar | `cash_and_equivalents`, `accounts_receivable` |
| Pago de gasto (`record_expense_payment`) | Dr Gastos operativos / Cr Efectivo y equivalentes | `operating_expense`, `cash_and_equivalents` |
| Pago de nómina (`record_payroll_payment`) | Dr Gasto de nómina / Cr Efectivo y equivalentes | `payroll_expense`, `cash_and_equivalents` |

### Qué queda PREPARADO, no conectado automáticamente (deliberado)

- **Costo de ventas / valorización de inventario (COGS)**: sin una
  política de costeo definida por el usuario (FIFO/promedio
  ponderado/identificación específica), inventar un método aquí
  violaría la instrucción explícita de la fase ("NO inventar
  automáticamente un método contable complejo sin documentarlo"). La
  arquitectura (`record_business_event`) puede recibir este evento el
  día que exista esa definición, sin cambiar el diseño.
- **Compras / recepción / factura de proveedor / Cuentas por Pagar
  completas**: mismo motivo — requiere decisiones de cuentas de
  control (inventario, IVA acreditable, cuentas por pagar) que no
  fueron provistas; `apps.purchases` sigue funcionando exactamente
  igual que antes de esta fase.
- **Cierre de sesión de caja (`CashSession`)**: los movimientos de
  efectivo ya generados por Ventas/Gastos/Nómina en efectivo se
  contabilizan a través de los 4 integradores de arriba (el pago en
  efectivo SÍ dispara `try_record_customer_payment`/
  `try_record_expense_payment`/`try_record_payroll_payment` igual que
  cualquier otro método) — un asiento de "cierre de caja" agregado
  aparte no se construyó por no ser necesario: el efectivo físico
  sigue siendo el libro mayor de `apps.pos` (`CashMovement`), la
  contabilidad NUNCA lo duplica (ver `CLAUDE.md`).
- **Impuestos completos (tax engine)**: `AccountMapping.Key.SALES_TAX_PAYABLE`
  cubre el caso más simple (impuesto de venta como un único pasivo);
  códigos de impuesto múltiples, retenciones, y normativa fiscal de un
  país específico NO se construyen sin una definición normativa
  validada (ver sección 19 de la especificación de esta fase).
- **Documentos fiscales electrónicos**: sin integración específica
  definida — preparación conceptual únicamente (ningún campo nuevo
  agregado sin un caso de uso real).

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

## 10. Qué NO se construyó en esta fase (deliberado)

- Motor de tipos de cambio completo (mismo criterio que
  `docs/currency.md` en todo el proyecto) — un asiento con líneas en
  monedas distintas se rechaza, nunca se convierte automáticamente.
  Los campos `original_amount`/`original_currency`/`exchange_rate` en
  `JournalEntryLine` están preparados para cuando exista FX real.
- Costeo de inventario/COGS automático, Cuentas por Pagar completas,
  impuestos multi-código, documentos fiscales electrónicos — ver
  sección 7.
- Flujo de efectivo y estado de cambios en el patrimonio como
  reportes formales — el balance general/estado de resultados cubren
  el núcleo pedido explícitamente por la especificación (secciones
  21-26), estos dos requieren decisiones de clasificación adicionales
  no provistas.
- Exportaciones PDF/XLSX (ninguna librería nueva instalada sin
  aprobación explícita, mismo criterio que `docs/invoice-documents.md`
  desde FASE 10) y reportes programados — ver `docs/reports.md`.
