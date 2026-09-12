# FASE 17 — Billing SaaS Completo

> **Estado: CONSTRUIDO.** Ver `docs/billing.md` para el detalle completo
> de la implementación (`apps.billing`: modelos, servicios, Portal del
> tenant, Super Admin, middleware de estado, comandos de
> administración). El checklist de la sección 35 se marcó abajo con
> evidencia. OCR real, contabilidad del operador SaaS, otro proveedor
> de pagos y WACRM siguen sin implementarse (fuera del alcance de esta
> fase).

## 1. Objetivo

Construir el sistema profesional de Billing de la plataforma SaaS.

Billing SaaS administra lo que los tenants pagan al operador de la plataforma.

Es independiente de:

- ventas del tenant;
- CxC del tenant;
- CxP del tenant;
- caja del tenant;
- contabilidad tenant-scoped.

## 2. Componentes principales

Como mínimo, evaluar e implementar según necesidad real:

- SaaS Customer;
- Plan;
- Subscription;
- SaaS Invoice;
- SaaS Payment;
- SaaS Payment Allocation;
- Credit Balance;
- Advance;
- Credit Note;
- Credit Note Application;
- Refund;
- Bank Account;
- Bank Transfer;
- Payment Proof;
- Payment Verification;
- Renewal;
- Plan Change;
- Suspension/Reactivation;
- Notifications;
- Billing Reports;
- auditoría de Billing.

No crear modelos duplicados si uno existente puede cumplir exactamente el mismo concepto.

## 3. Separación con el ERP del tenant

`apps.customers.Customer` = cliente comercial de un tenant.

`SaaS Customer` = cliente/comprador de la plataforma.

No mezclarlos.

Asimismo:

```text
ERP Accounts Receivable
≠
SaaS Billing
```

El patrón de `Payment`/`PaymentAllocation` del ERP puede servir como referencia estructural, pero Billing SaaS debe mantener sus propios registros y reglas.

No utilizar el antiguo concepto `CustomerCreditLedger` como fuente de verdad separada si contradice la decisión vigente del ERP: los saldos deben derivarse de los ledgers reales y sus aplicaciones.

## 4. Creación de tenants

El Super Admin debe poder crear tenants manualmente.

Flujo:

```text
Super Admin
→ Cliente SaaS
→ Tenant
→ Plan
→ Suscripción
```

El tenant puede quedar en estado pendiente hasta que se cumpla la condición de activación.

## 5. Venta SaaS desde Landing

Debe existir:

```text
Landing
→ Pricing
→ Plan
→ Periodicidad
→ Método de pago
```

Métodos iniciales:

- PayPal/pago online;
- transferencia bancaria.

El diseño debe permitir agregar métodos futuros.

## 6. Transferencia bancaria — alta inicial

Flujo recomendado:

```text
Cliente
→ selecciona transferencia
→ ve datos bancarios
→ recibe referencia única
→ Tenant = PENDING_PAYMENT
→ sube comprobante
→ Payment = PENDING_VERIFICATION
→ Super Admin recibe notificación
→ revisa
→ APPROVED / REJECTED
```

La subida del comprobante nunca activa por sí sola el tenant.

## 7. Venta manual desde Super Admin

Debe existir:

```text
Super Admin
→ crear/seleccionar cliente SaaS
→ crear/seleccionar tenant
→ plan
→ periodicidad
→ registrar venta/pago
→ método manual
→ comprobante
→ verificar
→ activar
```

Debe ser la misma base de Billing, no un sistema paralelo.

## 8. Billing recurrente

Soportar:

- mensual;
- anual;
- fecha de inicio;
- fecha de vencimiento;
- fecha de renovación;
- recordatorios;
- período de gracia;
- PAST_DUE;
- suspensión;
- reactivación.

No asumir que la recurrencia depende exclusivamente de PayPal.

## 9. Transferencias mensuales

Dentro del Billing del tenant debe existir una sección como:

```text
Billing
→ Transferencia bancaria
```

Debe permitir:

- ver obligación/factura;
- ver datos bancarios;
- ver referencia;
- subir comprobante;
- ver estado;
- consultar historial.

## 10. Payment Proof

El comprobante debe estar vinculado al pago.

Registrar:

- usuario que subió;
- fecha;
- referencia;
- banco;
- monto declarado;
- moneda;
- factura/período relacionado;
- estado de verificación.

Utilizar almacenamiento seguro.

No hacer público un comprobante.

## 11. Verificación manual

Estados sugeridos:

- PENDING;
- SUBMITTED;
- UNDER_REVIEW;
- APPROVED;
- REJECTED;
- REVERSED;
- REFUNDED.

Guardar:

- quién verificó;
- cuándo;
- resultado;
- motivo.

## 12. OCR futuro

OCR se documenta como extensión futura, no como requisito de la primera entrega.

Flujo futuro:

```text
Comprobante
→ OCR
→ banco/referencia/monto/fecha
→ matching
→ score de confianza
→ aprobación automática o revisión humana
```

El OCR no debe aprobar por sí solo una transferencia.

Debe existir protección contra comprobantes manipulados.

## 13. SaaS Payment + Payment Allocation

Un pago SaaS debe poder aplicarse:

- a una factura;
- a varias facturas;
- parcialmente.

Ejemplo:

```text
Pago 10,000
→ Factura A 3,000
→ Factura B 2,500
→ Factura C 4,500
```

Controlar:

- sobreaplicación;
- idempotencia;
- reversas;
- trazabilidad.

## 14. Anticipo vs saldo a favor

### Anticipo

Dinero recibido antes de aplicarse a una obligación concreta.

### Saldo a favor

Crédito disponible del cliente SaaS resultante, por ejemplo, de:

- sobrepago;
- nota de crédito;
- refund convertido a crédito;
- otro ajuste autorizado.

El origen debe conservarse.

No tratar ambos términos como sinónimos.

## 15. Sobrepago

Ejemplo:

```text
Factura = 3,500
Pago = 5,000
```

Resultado:

```text
3,500 → factura
1,500 → saldo a favor
```

Nunca perder el sobrante.

## 16. Notas de crédito

Permitir:

- total;
- parcial;
- aplicación a factura;
- aplicación futura según reglas.

Nunca borrar una factura/pago histórico para corregirlo.

## 17. Refunds

Distinguir:

- refund;
- nota de crédito;
- saldo a favor.

Registrar reversas y estado.

No deshacer allocations silenciosamente.

## 18. Planes

Soportar:

- mensual;
- anual;
- renovación;
- upgrade;
- downgrade;
- cambio de periodicidad;
- prorrateo.

La regla de prorrateo debe quedar explícita y auditable.

## 19. Descuentos

Billing debe reutilizar el sistema central de autorizaciones.

Los límites deben contemplar:

- porcentaje;
- monto.

Nunca depender solo de la UI.

## 20. Multi-moneda

Toda obligación y pago debe tener moneda.

No mezclar monedas.

No realizar conversión implícita.

Si existe conversión, registrar:

- moneda origen;
- moneda destino;
- tasa;
- fecha;
- origen de la tasa.

## 21. Bank Accounts

El Super Admin debe poder configurar cuentas bancarias de la plataforma:

- banco;
- país;
- moneda;
- titular;
- número/IBAN cuando corresponda;
- activa/inactiva.

Las cuentas visibles al cliente deben depender de su moneda/región/política.

## 22. Renovaciones

Soportar:

- renovación automática cuando corresponda;
- renovación manual;
- PayPal;
- transferencia;
- periodo de gracia;
- suspensión;
- reactivación.

## 23. Cambio de plan

Soportar:

- upgrade;
- downgrade;
- cambio de periodicidad.

El efecto económico debe quedar trazable.

## 24. Estados del tenant y suscripción

Como mínimo, cubrir estados equivalentes a:

- PENDING_SETUP;
- PENDING_PAYMENT;
- ACTIVE;
- PAST_DUE;
- SUSPENDED;
- CANCELLED;
- EXPIRED.

Mantener coherencia entre:

```text
Tenant
Subscription
Invoice
Payment
```

Sin usar un único booleano `paid=true` como fuente de verdad.

## 25. Idempotencia

Obligatoria para:

- PayPal webhooks;
- recurrencia;
- creación de facturas periódicas;
- pagos;
- allocations;
- aprobación de transferencias;
- refunds;
- reintentos.

Un evento externo repetido no debe duplicar dinero ni período.

## 26. Notificaciones

Como mínimo:

- nueva solicitud de transferencia;
- comprobante recibido;
- pago aprobado;
- pago rechazado;
- factura próxima a vencer;
- factura vencida;
- PAST_DUE;
- suspensión;
- reactivación;
- renovación;
- fallo de pago.

## 27. Seguridad

Separar estrictamente:

```text
Platform Super Admin
Tenant User
```

El tenant:

- solo ve su Billing;
- solo ve sus comprobantes;
- solo ve sus facturas/pagos;
- no puede aprobarse;
- no puede cambiar su estado;
- no puede ver otro tenant.

## 28. Auditoría

Auditar:

- creación/modificación de planes;
- cambios de precios;
- suscripciones;
- facturas;
- pagos;
- allocations;
- reversas;
- refunds;
- notas de crédito;
- verificaciones;
- cuentas bancarias;
- creación manual de tenant;
- activación;
- suspensión;
- reactivación.

Nunca registrar secretos.

## 29. Billing y contabilidad

No registrar automáticamente la suscripción SaaS en `apps.accounting` del tenant.

La contabilidad del operador SaaS es un dominio separado si se decide implementarla.

El Billing debe conservar trazabilidad financiera propia aunque no exista todavía un ledger contable completo del operador.

## 30. Reportes

Como mínimo:

- ingresos por período;
- ingresos por plan;
- suscripciones activas;
- nuevas altas;
- renovaciones;
- cancelaciones/churn;
- PAST_DUE;
- suspendidos;
- facturas pendientes;
- transferencias por verificar;
- pagos PayPal;
- pagos manuales;
- anticipos;
- saldo a favor;
- notas de crédito;
- refunds;
- conciliación.

Exportaciones deben respetar el sistema general de reportes.

## 31. Internacionalización

Billing debe estar preparado para:

- múltiples monedas;
- países;
- datos bancarios regionales;
- métodos de pago adicionales;
- impuestos/reglas que posteriormente se definan explícitamente.

No inventar reglas fiscales de países no especificados.

## 32. OCR

No es requisito de implementación inicial.

Dejar interfaz/arquitectura documentada para integrar posteriormente un proveedor de OCR con:
- extracción;
- confidence score;
- matching;
- antifraude;
- revisión humana.

## 33. Testing

Cubrir:

### Core
- plans;
- subscriptions;
- invoices;
- payments;
- allocations;
- credit balance;
- advance;
- credit notes;
- refunds.

### Transfers
- submission;
- upload;
- verification;
- rejection;
- duplicate proof;
- isolation.

### Lifecycle
- activation;
- renewal;
- past due;
- suspension;
- reactivation;
- cancellation.

### Manual admin
- create tenant;
- sell plan;
- register payment;
- verify;
- activate.

### Security
- tenant isolation;
- platform authorization;
- file access;
- no secret leakage.

### Concurrency / idempotency
- duplicate payment;
- duplicate webhook;
- duplicate recurring generation;
- concurrent allocation.

## 34. Smoke tests

Flujo Landing:

```text
plan
→ transfer
→ tenant pending
→ proof
→ admin approval
→ active
```

Flujo PayPal:

```text
plan
→ checkout
→ provider
→ webhook
→ paid
→ active
```

Flujo mensual por transferencia:

```text
invoice
→ transfer
→ proof
→ verification
→ paid
```

Flujo manual:

```text
Super Admin
→ tenant
→ plan
→ payment
→ verification
→ active
```

## 35. Criterios de aceptación

- [x] Billing SaaS separado del ERP tenant-scoped — `apps.billing` nunca toca `apps.sales.Payment`/CxC/CxP; tabla comparativa en `docs/billing.md`.
- [x] Alta desde Landing — `OnboardingView` → `billing_portal:select_plan` (PENDING_SETUP hasta pagar).
- [x] Alta manual — `ManualTenantSaleView`, mismo núcleo de `Subscription`.
- [x] PayPal — conectado vía `apps.billing.services.paypal_integration` (señales de FASE 16), nunca duplicado.
- [x] Transferencias — `submit_payment_proof`/`approve_payment_proof`/`reject_payment_proof`.
- [x] Comprobantes — `PaymentProof`, `media-private/`, nunca público.
- [x] Verificación — estados `PENDING`/`SUBMITTED`/`UNDER_REVIEW`/`APPROVED`/`REJECTED`/`REVERSED`.
- [x] Billing recurrente — `generate_due_renewal_invoices` (comando `generate_saas_invoices`), idempotente por `UniqueConstraint`.
- [x] Multi-factura — `apply_payment_to_invoices`/`auto_apply_payment` reparten un pago entre varias facturas.
- [x] Anticipo — un `SaaSPayment` confirmado sin aplicar.
- [x] Saldo a favor — `get_subscription_credit_balance`, nunca una tabla nueva.
- [x] Notas de crédito — `CreditNote`/`CreditNoteApplication`.
- [x] Refunds — `BillingRefund`, conectado a PayPal cuando aplica, manual cuando no.
- [x] Renovaciones — `generate_due_renewal_invoices` avanza el período.
- [x] Upgrade/downgrade — `change_plan`.
- [x] Prorrateo — `calculate_proration`, fórmula lineal por día documentada.
- [x] Multi-moneda — moneda propia en cada modelo, nunca mezclada con el ERP del tenant.
- [x] Auditoría — dominio `"billing_saas"`, nunca secretos.
- [x] Reportes — `apps.billing.services.reports` (dashboard/ingresos/suscripciones/aging).
- [x] Seguridad — Super Admin vs. Tenant separados y verificados con tests (403 cruzado); `all_objects` explícito en toda relación inversa.
- [x] Idempotencia — `UniqueConstraint` en `SaaSInvoice`/aprobación de comprobante vía `select_for_update`.
- [x] Concurrencia — hilos reales: generación de factura duplicada, sobre-aplicación de pago, doble aprobación de comprobante — exactamente una gana en los tres casos.
- [x] Regresión completa — ver reporte de cierre para el número exacto.
- [x] Smoke tests — ver reporte de cierre.
- [x] Documentación — `docs/billing.md` (reescrito a CONSTRUIDO), `CLAUDE.md`/`docs/MASTER-PROMPT.md`/`ARCHITECTURE.md`, `docs/project-status/*`.

## Corrección posterior al cierre: Alta inicial + Activación (Gate Local)

Durante el Gate Local de validación manual (posterior al cierre de
FASE 20), se encontraron 2 gaps reales en el criterio "Alta manual"
(punto 646 arriba) que la marca `[x]` original no reflejaba con
precisión:

1. `ManualTenantSaleView` creaba `Tenant`+`Owner`+`Subscription` pero
   nunca generaba la primera `SaaSInvoice` — corregido llamando a
   `generate_invoice_for_subscription` (mismo servicio idempotente ya
   usado por la renovación recurrente) y moviendo el tenant a
   `PENDING_PAYMENT`.
2. No existía ninguna acción explícita de activación inicial para una
   `Subscription` en `PENDING` — la única UI disponible
   (`Suspender`/`Reactivar`/`Cancelar`) podía intentar "Reactivar"
   sobre una suscripción nunca activada, lanzando una excepción sin
   manejar (error 500). Corregido con `activate_pending_subscription`
   (nuevo servicio, exclusivo de `PENDING`, nunca reutiliza
   `reactivate_subscription` — `ACTIVATE != REACTIVATE`) + botón
   `Activar` en la UI + manejo de errores en `TenantDetailView.post`.

Ver `docs/billing.md` sección "Alta inicial y activación", `KNOWN_ISSUES.md`
y `DECISIONS.md` para el detalle completo. Ningún estado nuevo se
inventó (`PENDING`/`ACTIVE`/`PAST_DUE`/`SUSPENDED`/`CANCELLED`/`EXPIRED`
siguen siendo los únicos); la separación Billing SaaS vs.
`apps.sales.Payment` y la independencia de la herramienta de prueba de
PayPal de FASE 16 se preservaron sin cambios.

## Corrección posterior al cierre: Billing recurrente con PayPal (Gate Local, "FASE DE CORRECCIÓN 2C")

FASE 16 conectó PayPal vía Orders API v2 (pago único, deliberadamente
sin Subscriptions API porque en ese momento el `Plan`/`Subscription`
real de FASE 17 todavía no existía). Con FASE 17 ya cerrada, esta
corrección posterior agrega el cobro automático recurrente que la
especificación original de la fase siempre exigió (mensual/anual,
renovación, PAST_DUE, suspensión, reactivación) pero que nunca se había
construido — `generate_due_renewal_invoices` solo generaba la factura
del siguiente período, sin ningún intento de cobro real.

Arquitectura evaluada oficialmente antes de escribir código: PayPal
Subscriptions API (Catalog Products + Billing Plans + Subscriptions),
NUNCA PayPal Reference Transactions/Vault (exige aprobación especial de
PayPal para cuentas LIVE). Nuevos campos `PlanVersion.paypal_product_id`/
`paypal_plan_id` y `Subscription.paypal_subscription_id`/
`paypal_subscription_status` (migración `billing.0003`); nuevo módulo
`apps.billing.services.recurring`; nuevos webhooks de Subscriptions
(`PAYMENT.SALE.COMPLETED`, `BILLING.SUBSCRIPTION.PAYMENT.FAILED`/
`SUSPENDED`/`CANCELLED`/`EXPIRED`/`ACTIVATED`) con dispatch separado del
de Orders API v2. `Budun` sigue siendo la única fuente de verdad de
negocio; PayPal solo autoriza/ejecuta el cobro. Ver `docs/billing.md`
sección "Billing recurrente con PayPal", `docs/paypal.md`,
`KNOWN_ISSUES.md` y `DECISIONS.md` para el detalle completo, incluidas
las fuentes oficiales de PayPal consultadas.

## 36. Regla de parada

FASE 17 no se considera PASS sin evidencia de todos los criterios aplicables.

Al cerrar la fase:

**DETENERSE.**
