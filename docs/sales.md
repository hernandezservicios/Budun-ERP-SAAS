# Motor Comercial: Ventas (FASE 10)

`apps/sales` — el motor comercial central del ERP: Cotizaciones,
Proformas, Ventas/Facturas, Pagos, Reservas, Devoluciones y Reembolsos.
Diseñado explícitamente para que FASE 11 (POS) sea una interfaz
operacional sobre este mismo motor, no un sistema de ventas paralelo.
Ver también `docs/quotations.md`, `docs/proforma-invoices.md`,
`docs/payments.md`, `docs/reservations.md`, `docs/returns.md` y
`docs/invoice-documents.md` para el detalle de cada dominio.

## Por qué documentos independientes, no una sola entidad con estados

`Quotation`, `ProformaInvoice` y `Sale` son modelos separados — no una
única entidad "Document" con un campo `type` — porque son
conceptualmente distintos: una cotización es una propuesta sin
compromiso; una proforma es un documento intermedio que puede iniciar
una reserva real de stock; una venta/factura es la transacción
comercial definitiva, la única que produce efectos reales en
inventario. Cada uno tiene su propia tabla de líneas
(`QuotationItem`/`ProformaInvoiceItem`/`SaleItem`) y su propia máquina
de estados, pero comparten forma a través de dos mixins abstractos:

- `CommercialDocumentMixin`: cabecera (cliente, vendedor, moneda,
  condiciones de pago, notas, términos, descuento global, subtotal/
  descuento/impuesto/total).
- `CommercialDocumentItemMixin`: línea (producto, unidad de inventario
  opcional, descripción/SKU/precio/impuesto **snapshot**, descuento,
  totales de línea).

## Snapshot histórico

Cada línea copia `description`, `sku_snapshot`, `unit_price` y
`tax_rate` del producto **en el momento de agregarse** — nunca se
vuelve a leer `Product` para recalcular una línea ya guardada. Cambiar
después el precio o el impuesto de un producto no altera ninguna venta
histórica (verificado con un test explícito). Es el mismo principio que
llevó a que `InventoryUnit`/`StockMovement` (FASE 8) nunca dependan de
un valor mutable calculado a posteriori.

## Cálculo de totales

Cada línea calcula, en este orden: `subtotal = cantidad × precio
unitario`; el descuento EFECTIVO (el de **porcentaje** tiene prioridad
sobre el de **monto fijo** si ambos llegaran a estar presentes — nunca
se suman); el impuesto se calcula sobre la base ya descontada
(`subtotal − descuento`); `total de línea = base imponible + impuesto`.

El descuento GLOBAL del documento (`global_discount_percent`/
`global_discount_amount`, con la misma prioridad porcentaje > monto
fijo) se aplica como una **rebaja final** sobre la suma de los totales
de línea — **simplificación deliberada y documentada**: no se
redistribuye proporcionalmente en la base imponible de cada línea (eso
exigiría recalcular el impuesto de cada línea en función de un
descuento agregado, una complejidad no pedida explícitamente). Si en el
futuro se requiere un cálculo fiscal más estricto sobre el descuento
global, es un cambio localizado en
`services.recalculate_document_totals`.

`services.recalculate_document_totals(document)` es la única función
que escribe la cabecera — siempre a partir de sus líneas, nunca al
revés.

## Numeración de documentos

`DocumentSequence` (una fila por tenant y tipo de documento) — nunca se
usa el ID de base de datos como número comercial. Prefijos: `COT-`
(cotización), `PRO-` (proforma), `FAC-` (venta/factura), `DEV-`
(devolución), seguidos de un consecutivo con ceros a la izquierda
(`services.generate_document_number`, `select_for_update()` sobre la
fila de secuencia — dos documentos creados al mismo tiempo nunca
reciben el mismo número).

## Multi-Tenancy

Igual que en FASES 8/9: todos los modelos heredan `TenantScopedModel`
(incluyendo las líneas — `QuotationItem`/`ProformaInvoiceItem`/
`SaleItem` tienen su propio `tenant`, mismo patrón que `StockMovement`
en FASE 8, no solo el de su documento padre). `services.py` usa
deliberadamente `all_objects` con filtro explícito en toda consulta —
nunca la relación inversa por defecto (`documento.items`), que depende
del `ContextVar` de una request HTTP real y devolvería vacío si se
llama desde un test o una tarea en segundo plano (mismo bug ya
documentado y corregido en FASES 8/9; se encontró y corrigió aquí
también durante el desarrollo, ver `KNOWN_ISSUES.md`). Las vistas, en
cambio, sí usan el manager tenant-aware por defecto (`objects`), porque
siempre corren dentro de una request real.

## Concurrencia

Toda operación que lea-y-luego-escriba un valor que pueda cambiar bajo
concurrencia usa `transaction.atomic()` + `select_for_update()`:
numeración (`DocumentSequence`), confirmación de venta (`Sale` +
`InventoryUnit`/`Product` vía `apps.inventory.services`), reservas
(`InventoryUnit`/`Product`), y pagos/asignaciones/reembolsos (`Payment`
+ `PaymentAllocation`, bloqueando ambas filas antes de validar). Probado
explícitamente con hilos reales sobre `TransactionTestCase` (no
`TestCase`, que nunca hace commit real): dos reservas concurrentes de
la misma unidad, dos ventas concurrentes de la misma unidad, dos
reservas concurrentes que exceden el stock combinado, dos asignaciones
concurrentes del mismo pago que juntas exceden lo disponible, y dos
asignaciones concurrentes a la misma factura que juntas exceden su
saldo pendiente — en los cinco casos, exactamente una operación gana y
la otra se rechaza limpiamente. Ver `docs/reservations.md` y
`docs/payments.md`.

## Idempotencia

- **Confirmar una venta** (`confirm_sale`) es idempotente: si la venta
  ya está `CONFIRMED`, la función devuelve la misma venta sin volver a
  aplicar ningún efecto de inventario — un reintento de red nunca
  produce una salida de stock duplicada ni una doble venta de unidad.
- **Registrar un pago** (`create_payment`/`record_payment_for_sale`)
  acepta una `idempotency_key` opcional: un reintento con la misma
  clave devuelve el pago ya existente (y, en el caso de
  `record_payment_for_sale`, no vuelve a aplicarlo si ya estaba
  aplicado) en vez de crear/aplicar uno duplicado.
- **Anular un pago** (`void_payment`) y **revertir una asignación**
  (`reverse_allocation`) también son idempotentes. Ver `docs/payments.md`
  para el diseño completo del ledger `PaymentAllocation`.

## No duplicar lógica de inventario

Ninguna función de `apps.sales.services` reimplementa una validación o
un movimiento de inventario — todas llaman a `apps.inventory.services`:
`register_stock_in`/`register_stock_out` (productos QUANTITY),
`transition_unit_status` (productos SERIALIZED, reutilizando
literalmente la máquina de estados de FASE 8 — `EN_STOCK`/`RESERVADO`
→ `VENDIDO` al confirmar, `VENDIDO` → `DEVUELTO` al devolver), y
`get_current_stock`. Cualquier `InvalidInventoryOperation` que esas
funciones lancen (unidad ya vendida, stock insuficiente, etc.) se
traduce a `InvalidSalesOperation` en el límite de este módulo.

## Reservas: una capa "blanda", nunca un segundo libro mayor

`Reservation` nunca crea un `StockMovement`. Para productos QUANTITY,
la disponibilidad "para prometer"
(`services.get_available_to_promise`) es `stock actual − cantidad
reservada activa` — un cálculo derivado, no un movimiento nuevo. Para
SERIALIZED, reservar sí transiciona la unidad a `RESERVADO`
(reutilizando la máquina de estados de FASE 8), así que
`get_current_stock` (que ya solo cuenta unidades `EN_STOCK`) refleja la
reserva automáticamente sin necesidad de restar nada aparte. Ver
`docs/reservations.md`.

## Cancelación: por qué solo se puede cancelar una venta en BORRADOR

Una venta en `DRAFT` nunca tocó inventario — cancelarla es una
operación trivial (solo cambia el estado, sin reversión de stock/
reservas/pagos que hacer). Una venta ya `CONFIRMED` que necesite
anularse se maneja con una **devolución total** (`create_return` con
todas las líneas) — nunca con una función de cancelación aparte. Esta
decisión evita mantener dos caminos de reversión de inventario
distintos (uno para "cancelar" y otro para "devolver") que podrían
divergir con el tiempo; devolver ya cubre exactamente los mismos
efectos (restaurar stock/unidad) con las mismas reglas de negocio
(SERIALIZED nunca reingresa solo a `EN_STOCK`, requiere revisión
manual). Ver `docs/returns.md`.

## Auditoría

`SalesActivityLog` — bitácora **mínima, acotada a este módulo**
(creación, edición, envío/aceptación/rechazo/vencimiento/cancelación/
conversión, emisión, reserva/liberación, confirmación, pago
registrado/anulado, devolución, reembolso, adjunto subido/eliminado).
Explícitamente **no** es el sistema de auditoría transversal que
construirá FASE 15 (Roles + Audit) para todo el proyecto — mismo
principio ya establecido por `apps.customers.models.ActivityLog` en
FASE 9.

## Documentos adjuntos e impresión

Ver `docs/invoice-documents.md`.

## Arquitectura (separación de responsabilidades)

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Modelos | `models.py` | Datos, constraints, mixins compartidos, señal de limpieza de adjuntos |
| Servicios | `services.py` | Numeración, cálculo de totales, máquinas de estado, conversión, reservas, pagos, devoluciones/reembolsos, auditoría |
| Formularios | `forms.py` | Validación de entrada (cabecera, líneas por IMEI/serie, pagos, devoluciones, adjuntos) |
| Vistas | `views.py` | Deliberadamente delgadas; vistas de adjuntos compartidas entre los 3 tipos de documento |
| Plantillas | `templates/sales/*.html` | Design System de FASE 5, tabs para Líneas/Pagos/Devoluciones/Documentos/Actividad |

## Moneda (sincronización posterior a FASE 12 — ver `docs/currency.md`)

`Sale.currency`/`Quotation.currency`/`ProformaInvoice.currency`
(heredados de `CommercialDocumentMixin`) son snapshots de texto simple
(`CharField(max_length=3)`, sin catálogo real) tomados de
`customer.currency` al crear el documento — nunca recalculados si el
cliente cambia de moneda después. `CreditNote.currency` sigue el mismo
principio (agregado tras la corrección descrita abajo). Sin un motor
de tipos de cambio (ver `docs/currency.md` sección 7), `allocate_payment`
y `apply_credit_note` rechazan explícitamente aplicar un `Payment`/
`CreditNote` a una `Sale` en una moneda distinta (`InvalidSalesOperation`,
nunca una conversión automática) — ver `docs/payments.md` regla 9 y
`docs/accounts-receivable.md` sección 8 para el detalle completo.

## Qué NO se construyó en esta fase (deliberado)

- **Motor de facturación fiscal electrónica**: ningún campo se agregó a
  los documentos — no hay ninguna integración real que los fuera a
  usar hoy. Diseñar para no bloquear su incorporación futura no
  significa agregar columnas sin uso hoy (mismo criterio que en
  FASE 9 con el motor de crédito). Documentado en
  `docs/invoice-documents.md`.
- **PDF real**: vistas HTML imprimibles (`@media print`) en vez de
  generación de archivos PDF binarios — instalar una librería de PDF
  no está aprobado como dependencia nueva sin decisión explícita del
  usuario. Ver `docs/invoice-documents.md`.
- **Integración real de pagos (PayPal, pasarelas)**: `Payment.method`
  incluye `OTHER` como valor extensible, hoy usado únicamente para que
  un tenant registre manualmente un pago recibido por un medio no
  listado. **Corrección de sincronización**: la integración real de
  PayPal de FASE 16 es exclusivamente para el Billing SaaS (FASE 17,
  ver `docs/paypal.md`/`docs/billing.md`) — nunca se acopla a `Sale`/
  `Payment` de este módulo. Una futura pasarela de cobro para que un
  cliente le pague a un tenant sería una decisión nueva y explícita,
  no anticipada aquí.
- **Ledger contable completo de cuentas por cobrar**: `get_customer_credit_balance`/
  `get_customer_pending_sales` son agregaciones de solo lectura sobre
  `Payment`/`PaymentAllocation`/`Refund`, no una tabla ni un motor de
  estado de cuenta — ver `docs/payments.md`.
- **`CreditNote`/`CreditNoteApplication`, `CashRegister`/`CashSession`/
  `CashMovement`, `ApprovalPolicy`/`ApprovalRequest`**: no se
  construyeron en FASE 10 — quedaron especificados como doctrina
  (sincronización previa a FASE 11) y **FASE 11 los construyó** (ver
  `docs/accounts-receivable.md`, `docs/cash-registers.md` y
  `docs/approvals.md`). `CustomerCreditLedger` como tabla separada
  nunca se construyó, ni en FASE 11 ni antes — decisión final
  documentada en `docs/accounts-receivable.md` sección 3.
- **Comisiones de vendedor**: se registra `salesperson`/`confirmed_by`
  en cada documento (preparación explícita pedida), pero ningún cálculo
  de comisión — corresponde a una fase de Reportes/Nómina futura.
- POS (FASE 11), Compras (FASE 12), Gastos (FASE 13), Reportes
  (FASE 14), Roles/Audit/API (FASE 15), Billing (FASE 17).
