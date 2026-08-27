# SaaS Billing (especificación)

> **Estado: ESPECIFICACIÓN, no implementación.** Diseño aprobado para
> FASE 17 — ningún modelo, campo ni migración se crea a partir de este
> documento. Detalle completo (36 secciones: componentes, flujos,
> transferencias, verificación, notas de crédito, refunds, renovaciones,
> reportes, testing) en `docs/phases/PHASE-17-billing-saas.md`.
>
> **Actualización FASE 16**: el proveedor PayPal (Payment Provider
> Interface → PayPal Provider, `apps.billing`) ya está **construido**
> — ver `docs/paypal.md`. `Plan`/`Subscription`/`SaaS Invoice`/`SaaS
> Payment` siguen sin existir como modelos: siguen siendo alcance de
> esta fase (FASE 17). `apps.core.pricing.PLANS` (FASE 6) ganó
> `price_amount`/`price_currency` — el mínimo necesario para que FASE
> 16 pudiera crear una orden real de PayPal con un monto exacto, sin
> convertirse en el `Plan` real que esta fase construirá.

Billing de la **suscripción del tenant al SaaS** — lo que un `Tenant`
le debe a Budun ERP por usar la plataforma. Administra planes,
suscripciones, facturación recurrente, pagos (PayPal y transferencia
bancaria), verificación manual de comprobantes, créditos, refunds,
renovaciones/cambios de plan y la administración de tenants por el
Super Admin de la plataforma.

## Separación obligatoria de Cuentas por Cobrar del ERP

**Nunca se mezcla** con lo que un `Customer` le debe a un `Tenant`
(`apps.sales`: `Payment`/`PaymentAllocation`/`CreditNote`, FASE 10/11)
— son ejes ortogonales:

| | ERP Accounts Receivable | SaaS Billing |
|---|---|---|
| Qué es | Lo que un CLIENTE le debe a un TENANT | Lo que un TENANT le debe a Budun ERP |
| Quién administra | El propio tenant (dueño/empleados) | El Super Admin de la plataforma |
| Modelos | `Customer`, `Sale`, `Payment`, `PaymentAllocation`, `CreditNote` (construidos) | `SaaS Customer`, `Plan`, `Subscription`, `SaaS Invoice`, `SaaS Payment` (esta fase) |
| PayPal | No se integra en esta capa (ver `docs/paypal.md`) | Provider oficial de pagos (FASE 16) |

`apps.customers.Customer` (cliente comercial de un tenant) **nunca**
se confunde con "SaaS Customer" (el cliente/comprador de la
plataforma, es decir, quien contrata el plan para un `Tenant`) — son
conceptos distintos aunque ambos se llamen coloquialmente "cliente".

`CustomerCreditLedger` como tabla separada **no existe ni se
construirá** como fuente de verdad del ERP (decisión final ya
documentada en `docs/accounts-receivable.md`) — si Billing SaaS
necesita un concepto de saldo a favor propio, será una construcción
NUEVA y propia de Billing (ver sección de Anticipo/saldo a favor más
abajo), nunca una reutilización cruzada del ledger del ERP.

Ver `docs/phases/PHASE-17-billing-saas.md` para el razonamiento
completo. Si en el futuro se quisiera un plan de Billing basado en el
volumen de ventas/cuentas por cobrar de un tenant (métrica de uso),
sería una agregación de solo lectura sobre `apps.sales`, nunca una
relación estructural directa entre `Subscription` y `Customer`.

## PayPal como provider, nunca un segundo sistema de pagos

Ver `docs/paypal.md` (reescrito tras esta sincronización): PayPal se
integra exclusivamente vía `Payment Provider Interface → PayPal
Provider`, terminando siempre en los modelos propios de Billing SaaS
(`SaaS Payment`) — nunca en `apps.sales.Payment`.

## Alcance previsto (resumen — ver PHASE-17 para el detalle completo)

- **Creación de tenants y venta**: alta desde Landing (plan →
  periodicidad → método de pago) y alta manual por el Super Admin
  (mismo flujo de Billing subyacente, nunca un sistema paralelo) —
  ambas terminan en el mismo `Tenant`/`Subscription`.
- **Métodos de pago iniciales**: PayPal (online) y transferencia
  bancaria — diseño abierto a métodos futuros.
- **Transferencia bancaria**: referencia única por solicitud,
  `Tenant`/`SaaS Invoice` quedan `PENDING_PAYMENT`/`PENDING_VERIFICATION`
  hasta que el Super Admin revisa el comprobante (`Payment Proof`,
  almacenamiento seguro, nunca público) y aprueba/rechaza
  manualmente — subir un comprobante **nunca** activa el tenant por sí
  solo. Estados de verificación: `PENDING`/`SUBMITTED`/`UNDER_REVIEW`/
  `APPROVED`/`REJECTED`/`REVERSED`/`REFUNDED`.
- **OCR**: documentado como extensión FUTURA (extracción + matching +
  score de confianza + revisión humana) — no es requisito de la
  primera entrega; el OCR nunca aprueba una transferencia por sí solo.
- **`SaaS Payment`/`SaaS Payment Allocation`**: un pago puede aplicarse
  a una o varias facturas, parcialmente — mismo patrón estructural que
  `Payment`/`PaymentAllocation` del ERP (nunca la misma tabla, nunca
  compartida entre dominios), con las mismas reglas de no-sobre-aplicación
  e idempotencia.
- **Anticipo vs. saldo a favor**: dos conceptos distintos con origen
  propio (sobrepago, nota de crédito, refund convertido a crédito,
  otro ajuste) — nunca sinónimos, nunca se pierde el sobrante de un
  pago mayor a la factura.
- **Notas de crédito y refunds**: total o parcial, aplicación a
  factura o futura; refund/nota de crédito/saldo a favor se
  distinguen siempre, nunca se deshacen allocations en silencio.
- **Planes**: mensual/anual, renovación, upgrade/downgrade, cambio de
  periodicidad, prorrateo (regla explícita y auditable, nunca
  implícita).
- **Descuentos**: reutilizan el sistema central de autorizaciones
  (`apps.approvals`, ver `docs/approvals.md`) — nunca un segundo
  sistema de límites/aprobación.
- **Cuentas bancarias de la plataforma**: configurables por el Super
  Admin (banco/país/moneda/titular/IBAN/activa), visibles al cliente
  según su moneda/región.
- **Estados de tenant/suscripción**: como mínimo
  `PENDING_SETUP`/`PENDING_PAYMENT`/`ACTIVE`/`PAST_DUE`/`SUSPENDED`/
  `CANCELLED`/`EXPIRED` — nunca un único booleano `paid=true` como
  fuente de verdad; coherencia obligatoria entre
  `Tenant`/`Subscription`/`Invoice`/`Payment`.
- **Notificaciones**: nueva solicitud de transferencia, comprobante
  recibido, pago aprobado/rechazado, factura próxima a vencer/vencida,
  `PAST_DUE`, suspensión, reactivación, renovación, fallo de pago.
- **Seguridad**: separación estricta Platform Super Admin / Tenant
  User — un tenant nunca puede aprobarse a sí mismo, cambiar su propio
  estado, ni ver el Billing de otro tenant.
- **Auditoría**: ciclo de vida completo (planes, precios,
  suscripciones, facturas, pagos, allocations, reversas, refunds,
  notas de crédito, verificaciones, cuentas bancarias, creación/
  activación/suspensión/reactivación de tenant) — nunca secretos.
- **Reportes**: ingresos por período/plan, altas, renovaciones,
  churn, `PAST_DUE`, suspendidos, facturas pendientes, transferencias
  por verificar, pagos por método, anticipos, saldo a favor, notas de
  crédito, refunds, conciliación — exportaciones vía el sistema
  general de reportes (`apps.reports`), nunca un exportador paralelo.
- **Contabilidad**: nunca se registra automáticamente en
  `apps.accounting` tenant-scoped — un dominio contable separado del
  operador SaaS, si se decide implementarlo, nunca mezclado con la
  contabilidad de cada tenant.
- **Idempotencia**: obligatoria para webhooks de PayPal, recurrencia,
  facturación periódica, pagos, allocations, aprobación de
  transferencias y refunds — un evento externo repetido nunca duplica
  dinero ni período.

## Moneda (sincronización posterior a FASE 12, especificación — ver `docs/currency.md`)

`Plan.currency` (la moneda en la que se fija el precio del plan) y
`Subscription.currency` (heredada del plan al momento de suscribirse,
snapshot histórico — un cambio de precio/moneda del plan después nunca
debe alterar lo que ya paga un tenant suscrito, mismo principio de
snapshot que `SaleItem`/`PurchaseOrderItem`) — ninguno de los dos campos
existe hoy. `provider_currency` (la moneda que PayPal Subscriptions
reporta) se mantiene igual que en `docs/paypal.md`. Esto sigue sin
mezclarse con la moneda de las ventas/cuentas por cobrar del ERP de
cada tenant (`Sale.currency`/`Payment.currency`) — la separación
ERP Accounts Receivable / SaaS Billing (ver arriba) aplica también a la
moneda: cada eje tiene la suya, nunca una FK compartida entre ambos.
Toda obligación/pago de Billing debe tener moneda propia; si existe
conversión, se registra moneda origen/destino/tasa/fecha/origen de la
tasa — nunca una conversión implícita.

## Qué NO se construye con este documento

Ningún modelo (`Plan`, `Subscription`, `SaaS Payment`, etc.), ninguna
integración con PayPal, ningún límite de plan aplicado, ninguna
implementación de OCR. Ver `docs/phases/PHASE-17-billing-saas.md`
para el checklist completo de la fase.
