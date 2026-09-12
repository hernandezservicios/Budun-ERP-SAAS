# SaaS Billing (`apps.billing`)

> **Estado: CONSTRUIDO en FASE 17** (ver `docs/phases/PHASE-17-billing-saas.md`
> para el checklist completo). Reemplaza la especificación anterior de
> este documento — todo lo descrito aquí abajo ya existe en el código,
> no es un plan. El proveedor PayPal (FASE 16) sigue documentado en
> `docs/paypal.md`; esta fase lo CONECTA con el núcleo real de Billing
> (`Subscription`/`SaaS Invoice`/`SaaS Payment`) en vez de duplicarlo.

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
| Modelos | `Customer`, `Sale`, `Payment`, `PaymentAllocation`, `CreditNote` | `SaaSCustomer`, `Plan`/`PlanVersion`, `Subscription`, `SaaSInvoice`, `SaaSPayment` |
| PayPal | No se integra en esta capa (ver `docs/paypal.md`) | Provider oficial de pagos (FASE 16, conectado en esta fase) |

`apps.customers.Customer` (cliente comercial de un tenant) **nunca**
se confunde con `SaaSCustomer` (quien contrata el plan para uno o
varios `Tenant`) — son conceptos distintos aunque ambos se llamen
coloquialmente "cliente". `CustomerCreditLedger` como tabla separada
**no existe** — el saldo a favor de Billing SaaS se deriva SIEMPRE
sumando el saldo sin aplicar de `SaaSPayment` + el saldo sin aplicar
de `CreditNote` (`apps.billing.services.credits.
get_subscription_credit_balance`), exactamente el mismo criterio que
ya rigió Cuentas por Cobrar/Pagar del ERP — nunca una tercera fuente
de verdad.

## Modelos (`apps.billing.models`)

- **`SaaSCustomer`**: NO hereda `TenantScopedModel` — puede asociarse
  a varios `Tenant` (`Tenant.saas_customer`, FK perezosa
  `"billing.SaaSCustomer"` para no acoplar `apps.tenants`, la app más
  fundacional, a una app mucho más tardía).
- **`Plan`/`PlanVersion`**: catálogo global (NO tenant-scoped) con
  versionado real de precios — `PlanVersion.UniqueConstraint(plan,
  frequency, condition=is_current)` (índice único parcial de
  PostgreSQL) garantiza a nivel de BASE DE DATOS que solo una versión
  esté vigente por plan+frecuencia. Cambiar el precio nunca edita una
  fila existente — crea una nueva `PlanVersion`; una `Subscription` ya
  creada referencia la versión VIGENTE al momento de suscribirse
  (snapshot histórico, mismo principio que `SaleItem`). Reemplaza a
  `apps.core.pricing.PLANS` (FASE 6) como fuente de verdad real
  (`apps.billing.services.subscriptions.resolve_plan_pricing` prueba
  primero el `Plan` real, cae al estático solo si no existe) — `PLANS`
  se conserva sin cambios como referencia histórica.
- **`Subscription`**: a diferencia de los modelos de FASE 16, SÍ hereda
  `TenantScopedModel` — el propio tenant la consulta en su Portal de
  Billing dentro de una request normal (`request.tenant` ya resuelto);
  el Super Admin cruza tenants vía `all_objects`, mismo patrón dual que
  `ApiKey`/`Integration` (FASE 15). Estados: `PENDING`/`ACTIVE`/
  `PAST_DUE`/`SUSPENDED`/`CANCELLED`/`EXPIRED`.
- **`SaaSInvoice`/`SaaSInvoiceLine`**: `UniqueConstraint(subscription,
  period_start)` es la garantía REAL (de base de datos) de que la
  generación recurrente nunca duplica la factura de un período —
  `apps.billing.services.invoicing.generate_invoice_for_subscription`
  captura el `IntegrityError` y devuelve la fila existente, idéntico
  patrón a `PayPalWebhookEvent.event_id` en FASE 16. Numeración vía la
  MISMA `DocumentSequence` del proyecto (`SAAS_INVOICE`, prefijo
  `INV-SAAS-`) — nunca un generador paralelo.
- **`SaaSPayment`/`SaaSPaymentAllocation`**: espejo estructural de
  `apps.sales.Payment`/`PaymentAllocation` (mismas reglas de
  no-sobre-aplicación, `select_for_update` en pago Y factura, reverso
  en vez de edición). `SaaSPayment.paypal_transaction` referencia el
  detalle de PayPal (FASE 16) sin duplicar sus campos.
- **`CreditNote`/`CreditNoteApplication`**: espejo de `apps.sales.
  CreditNote`, numeración `NC-SAAS-` vía la misma `DocumentSequence`.
- **`BillingRefund`**: registro de NEGOCIO "este pago SaaS fue
  reembolsado" — nombre deliberado (no "Refund" a secas) para nunca
  confundirse con `apps.sales.Refund` ni con el seguimiento interno de
  refund de `PayPalTransaction` (FASE 16).
- **`BankAccount`** (plataforma, NO tenant-scoped) / **`PaymentProof`**
  (tenant-scoped, archivo en `media-private/`, mismo mecanismo que
  `apps.customers` — nombre de archivo generado, nunca público, nunca
  el original). Estados de verificación exactos de la especificación:
  `PENDING`/`SUBMITTED`/`UNDER_REVIEW`/`APPROVED`/`REJECTED`/`REVERSED`.
  `PaymentProof.file` forma parte del backup de media pendiente de
  implementación real en FASE 20 (ver `docs/backup-recovery.md`).
- **`Coupon`**: estructura simple (sin tabla de redención separada,
  `times_redeemed` incrementado atómicamente) — "no crear un motor
  innecesariamente complejo si el proyecto no lo necesita".
- **`BillingPolicy`**: fila única — días de gracia, días para
  suspender, días de anticipación de factura — NUNCA hardcodeados en
  código (sección 31 de la fase).

## Estado del tenant: `Tenant.billing_status`

Campo nuevo en `Tenant` (`apps.tenants`), deliberadamente SEPARADO de
`is_active` (que conserva su significado histórico de FASE 3, sin
relación con Billing). `default=ACTIVE` — decisión crítica de
compatibilidad: TODO tenant/fixture preexistente a esta fase conserva
su comportamiento exacto; solo los tenants NUEVOS (creados vía
`OnboardingView` o la venta manual de Super Admin) arrancan
explícitamente en `PENDING_SETUP`. Nunca se edita desde un formulario
directo — solo `apps.billing.services.tenants` (activar/marcar
past_due/suspender/reactivar/cancelar), siempre como consecuencia de
un evento de negocio real.

`apps.billing.middleware.BillingStatusMiddleware` (registrado después
de `TenantMiddleware`) es el ÚNICO punto que bloquea la operación
completa del ERP cuando `billing_status` no es `ACTIVE`/`PAST_DUE`
(en gracia) — redirige (nunca lanza una excepción) al Portal de
Billing propio del tenant, salvo en una lista exenta (`/facturacion/`,
`/cuentas/`, `/plataforma/`, `/webhooks/`, `/admin/`, `/static/`).
Deliberadamente un middleware nuevo, NUNCA una modificación de
`apps.tenants.permissions.require_tenant`/`TenantRequiredMixin` (el
choke point ya usado por ~100 vistas existentes) — bajo riesgo, cero
impacto en tests/fixtures preexistentes gracias al default `ACTIVE`.

## PayPal como provider, conectado (no un segundo sistema de pagos)

`apps.billing.services.paypal_integration` conecta las señales de
FASE 16 (`payment_confirmed`/`payment_failed`/`refund_completed`/
`refund_failed`) con el núcleo real: al confirmarse un pago PayPal, se
localiza el `SaaSPayment` asociado (`paypal_transaction` FK), se
confirma, se aplica automáticamente a las facturas abiertas
(`auto_apply_payment`) y se activa la suscripción/tenant si
corresponde — conectado en `apps.billing.apps.BillingConfig.ready()`
(patrón estándar de Django para receptores de señales). Ninguna lógica
de OAuth/webhook/credenciales se reimplementa — se reutiliza
literalmente `apps.billing.services.create_checkout`/`capture_checkout`/
`request_refund` de FASE 16.

## Flujo de alta (Landing/Onboarding → Billing)

`apps.accounts.views.OnboardingView` (FASE 4/7) — cambio de
comportamiento DELIBERADO: un tenant nuevo ya no llega directo al
Panel; queda `PENDING_SETUP` y se redirige a
`billing_portal:select_plan` (test actualizado en el mismo commit,
`apps/accounts/tests.py`). El Portal (`/facturacion/`,
`apps.billing.portal_views`) deja elegir un `PlanVersion` real + método
de pago (PayPal o transferencia); ambos flujos generan la primera
`SaaSInvoice` mediante el mismo servicio (`generate_invoice_for_subscription`).
La venta manual por Super Admin (`/plataforma/billing/admin/venta-manual/`,
`ManualTenantSaleView`) usa EXACTAMENTE el mismo núcleo (`Tenant` +
`Membership` OWNER + `SaaSCustomer` + `Subscription` PENDING vía
`create_subscription`) — nunca escribe `Tenant.billing_status=ACTIVE`
directamente.

## Disponibilidad de métodos de pago (Corrección de Gate Local — "FASE DE CORRECCIÓN 2")

El Portal NUNCA hardcodea qué métodos de pago mostrar — ambos flags se
calculan en cada request a partir de configuración real, nunca de una
lista fija:

- `apps.billing.services.is_paypal_available()` → lee
  `PayPalGatewayStatus.is_enabled` (el mismo interruptor que
  `create_checkout` ya usaba para RECHAZAR el checkout si está
  deshabilitado — antes de esta corrección, el backend ya se protegía
  correctamente, pero la UI nunca lo consultaba).
- `apps.billing.services.transfers.is_bank_transfer_available()` →
  `BankAccount.objects.filter(is_active=True).exists()` — la
  transferencia nunca tuvo un interruptor único como PayPal; su
  disponibilidad real siempre fue "¿hay al menos una cuenta activa?".

Ambos flags alimentan dos puntos: `portal_forms.SelectPlanForm` (el
desplegable de método de pago al elegir plan, antes con las dos
opciones fijas en el código) y `BillingPortalStatusView`/
`portal_status.html` (la tabla de facturas pendientes de
`/facturacion/`, que antes SOLO enlazaba a transferencia — nunca
ofrecía PayPal, aunque el checkout ya funcionaba perfectamente si se
llegaba a él por otra vía, como probó el hallazgo que originó esta
corrección). Ver `KNOWN_ISSUES.md` #130 para el hallazgo completo.

## Integridad del monto de factura en PayPal (Corrección de Gate Local — "FASE DE CORRECCIÓN 2B")

**Una `SaaSInvoice` emitida es un snapshot contractual del importe y la
moneda a pagar** — `invoice.total`/`invoice.currency`, congelados al
generarse (`generate_invoice_for_subscription`). Cualquier cobro
posterior de esa factura debe cobrar EXACTAMENTE ese monto/moneda,
nunca recalcular el precio VIGENTE del plan (que pudo cambiar después
de emitirse la factura). Regla permanente, reusable para cualquier
proveedor de pago futuro.

`apps.billing.services.create_checkout_for_invoice(invoice, ...)` es
ahora la ÚNICA vía real del Portal del tenant para pagar una factura
por PayPal (`CheckoutPayPalInitiateView`) — reemplaza la lógica que
antes vivía inline en la vista y que pasaba `plan_id` a
`create_checkout`, dejando que ésta recalculara el monto vía
`resolve_plan_pricing` (el hallazgo real, ver `KNOWN_ISSUES.md` #131).
Hace, en orden, dentro de un único `transaction.atomic()` con
`select_for_update()` sobre la propia `SaaSInvoice`:

1. Rechaza si la factura no está `OPEN`/`PARTIALLY_PAID` (una ya
   `PAID`/`VOID`/`DRAFT` nunca admite un nuevo cobro).
2. Rechaza un monto no positivo o una moneda mal formada.
3. Rechaza si ya existe un `PayPalTransaction` sin resolver
   (`CREATED`/`PENDING_CAPTURE`) para la misma suscripción — cierra la
   ventana de carrera de dos clics simultáneos/dos pestañas.
4. Registra el `SaaSPayment` y llama a `create_checkout(..., amount=
   invoice.total, currency=invoice.currency, ...)` — los nuevos
   parámetros opcionales de `create_checkout` que, cuando se pasan
   explícitamente, DESACTIVAN el recálculo desde `resolve_plan_pricing`.

`create_checkout` (la función genérica basada en `plan_id`) sigue
siendo, sin ningún cambio de comportamiento, la única vía de la
herramienta de prueba de plataforma (`CheckoutCreateView`, FASE 16,
sin ninguna factura real de por medio) — esa herramienta SÍ debe seguir
resolviendo el precio vigente del plan, porque no existe ninguna
factura de la cual tomar un snapshot.

## Transferencia bancaria

`apps.billing.services.transfers`: `submit_payment_proof` (valida el
archivo con `apps.customers.file_validation`, genera una referencia
única, marca el tenant `PENDING_PAYMENT` — nunca activa nada) →
`approve_payment_proof` (Super Admin, crea el `SaaSPayment` CONFIRMED,
lo aplica automáticamente, activa suscripción/tenant) o
`reject_payment_proof` (nunca activa). Validaciones agregadas en la
Corrección de Gate Local #2 (antes ausentes): rechaza un comprobante
para una factura que ya no está `OPEN`/`PARTIALLY_PAID` (pagada,
anulada o en borrador), rechaza un segundo comprobante mientras uno
sigue `SUBMITTED`/`UNDER_REVIEW` para la misma factura, exige un monto
declarado positivo, y exige que la moneda declarada coincida con la de
la cuenta bancaria receptora seleccionada. Notificaciones por correo
(`apps.billing.services.notifications`, reutiliza `EMAIL_BACKEND`
existente desde FASE 4 — no existe todavía ningún centro de
notificaciones in-app en el proyecto, construir uno sería un
subsistema nuevo fuera del alcance de esta fase).

## Anticipo, saldo a favor, sobrepago

Generalizado exactamente como Cuentas por Cobrar del ERP — nunca una
tabla nueva:
- **Anticipo** = un `SaaSPayment` CONFIRMED sin aplicar todavía.
- **Saldo a favor** = `get_subscription_credit_balance` = suma del
  saldo sin aplicar de los pagos confirmados + el saldo sin aplicar de
  las notas de crédito.
- **Sobrepago**: `auto_apply_payment` aplica a las facturas abiertas
  más antiguas en orden hasta agotar el pago o las facturas — el
  sobrante queda simplemente SIN APLICAR, que es, por definición, el
  saldo a favor (nunca se pierde, nunca requiere un campo nuevo).
- **Refund convertido a crédito**: `convert_payment_to_credit` reversa
  las asignaciones activas del pago — el monto vuelve a quedar sin
  aplicar (saldo a favor), sin crear ningún modelo nuevo.

## Cambio de plan y prorrateo

`apps.billing.services.subscriptions.change_plan` — el período NO
cambia, solo la `PlanVersion` referenciada. Prorrateo lineal por DÍA
(`calculate_proration`, fórmula explícita y documentada, ver
`DECISIONS.md`): `valor_diario = precio / días_del_período`; `crédito
= valor_diario_actual × días_restantes`; `cargo = valor_diario_nuevo ×
días_restantes`; `neto = cargo − crédito`. Un neto negativo (downgrade)
emite una `CreditNote` automáticamente; un neto positivo (upgrade) se
audita pero no genera cargo inmediato en esta fase (queda reflejado en
la próxima factura recurrente, que ya usa el nuevo precio) — decisión
explícita, ver `DECISIONS.md`.

## PAST_DUE / Suspensión / Reactivación

`BillingPolicy` (fila única) define `grace_period_days`/
`past_due_to_suspend_days`/`invoice_advance_days` — nunca hardcodeados.
Dos comandos de administración (pensados para cron real en producción;
no hay Celery/Redis en este proyecto, ver CLAUDE.md):
`manage.py generate_saas_invoices` (renovación recurrente, idempotente
por el `UniqueConstraint` de `SaaSInvoice`) y
`manage.py apply_billing_past_due_policy` (ACTIVE → PAST_DUE cuando una
factura supera el período de gracia; PAST_DUE → SUSPENDED cuando además
supera `past_due_to_suspend_days`). `manage.py seed_billing_plans`
siembra los 3 planes reales a partir de `apps.core.pricing.PLANS`
(idempotente).

## Alta inicial y activación: `ACTIVATE != REACTIVATE`

Gap real encontrado y corregido durante el Gate Local de validación
manual (ver `KNOWN_ISSUES.md`): `ManualTenantSaleView` creaba
`Tenant`+`Owner`+`Subscription` pero NUNCA generaba la primera
`SaaSInvoice` — el tenant quedaba "pendiente de pago" sin ninguna
factura real contra la cual pagar. Corregido llamando a
`invoicing_services.generate_invoice_for_subscription` (el mismo
servicio idempotente ya usado por la renovación recurrente, real vía
`UniqueConstraint(subscription, period_start)`, nunca duplica) justo
después de crear la `Subscription`, y moviendo `Tenant.billing_status`
a `PENDING_PAYMENT` (en vez de dejarlo en `PENDING_SETUP` a secas) —
ya existe una factura real esperando pago.

**`ACTIVATE` y `REACTIVATE` son dos operaciones DISTINTAS, con guardas
distintas, deliberadamente nunca intercambiables**:

- `subscription_services.activate_pending_subscription` — activación
  INICIAL, exclusiva de una `Subscription` en `PENDING` (nunca
  `SUSPENDED`/`PAST_DUE`). Nunca activa "porque sí": genera (o
  recupera, idempotente) la factura inicial y, si todavía tiene saldo
  pendiente, registra y confirma un `SaaSPayment`
  (`method=MANUAL_OTHER`) que lo cubre ANTES de activar — la misma
  garantía de seguridad por la que la Transacción de PayPal de la
  herramienta de prueba de FASE 16 nunca activa nada por sí sola (no
  tiene ningún `SaaSPayment` asociado, ver más abajo): aquí SÍ se crea
  esa evidencia real antes de activar, nunca se activa sin ella.
  Expuesta en la UI del Super Admin como el botón **Activar**
  (`/plataforma/billing/admin/tenants/<id>/`, acción `activar`),
  visible solo cuando la suscripción está `PENDING`.
- `subscription_services.reactivate_subscription` — **sin modificar**:
  sigue exigiendo `SUSPENDED`/`PAST_DUE` exclusivamente (lanza
  `InvalidSubscriptionOperation` para cualquier otro estado, incluido
  `PENDING`). Botón **Reactivar**, visible solo cuando la suscripción
  está `SUSPENDED`/`PAST_DUE`.

`TenantDetailView.post` ahora atrapa `ValidationError` (antes: una
transición inválida, p. ej. "Reactivar" sobre una `Subscription`
`PENDING`, producía un error 500 sin manejar — hallazgo real,
corregido en el mismo cambio) y muestra un mensaje de error legible en
vez de romper la página. El período de la suscripción se muestra como
"pendiente de activación" en vez de un guion ambiguo cuando todavía no
se ha fijado.

**Seguridad (sin excepciones)**: ninguna activación ocurre solo porque
exista una `PayPalTransaction`/Order ID/Capture ID — la herramienta de
prueba de PayPal de plataforma (`/plataforma/billing/admin/cobrar/`,
FASE 16) es deliberadamente independiente del ciclo de vida de Billing
SaaS (su propio receptor de señal, `apps.billing.services.
paypal_integration._on_payment_confirmed`, ya documentaba en código
"transacción de PayPal sin un SaaSPayment asociado — nada que hacer");
ahora además muestra una advertencia visible en su UI, y la vista de
detalle de cada transacción indica explícitamente si tiene o no un
`SaaSPayment` real asociado.

## Super Admin (`/plataforma/billing/admin/`) y Portal del tenant (`/facturacion/`)

Dos superficies completamente separadas, mismo criterio que FASE 16:

- **Super Admin** (`apps.billing.admin_views`, exclusivo
  `is_superuser` — `apps.tenants.permissions.require_superuser`, el
  catálogo tenant-scoped de `apps.permissions` no aplica a un recurso
  de plataforma): Dashboard (MRR/ARR/altas/cancelaciones/transferencias
  pendientes/ingresos/reembolsos), Clientes SaaS, Tenants (activar/
  suspender/reactivar/cancelar — ver "Alta inicial y activación" más
  abajo para la diferencia real entre activar y reactivar), Venta manual, Planes (crear plan + nueva versión
  de precio), Suscripciones, Facturas (detalle con líneas/pagos
  aplicados/notas de crédito aplicadas), Pagos (solicitar reembolso),
  Transferencias (cola + aprobar/rechazar), Notas de crédito,
  Reembolsos, Cuentas bancarias, Reportes.
- **Portal del tenant** (`apps.billing.portal_views`, permisos
  `billing.saas.view`/`billing.saas.manage` — nuevos en
  `apps.permissions.catalog`, dominio "billing", excluidos de ADMIN por
  defecto igual que `accounting.close_period`/`api.inventory.manage`:
  solo el propietario ve/gestiona por defecto): estado de la
  suscripción, elegir plan, pagar por PayPal o transferencia, subir
  comprobante, cambiar de plan, cancelar. Enlazado desde la barra
  lateral principal ("Mi Facturación").

## Seguridad

Separación estricta Platform Super Admin / Tenant User verificada con
tests: un tenant normal recibe 403 en cualquier vista
`/plataforma/billing/admin/...`; el Portal siempre filtra por
`request.tenant` (nunca un ID enviado por el cliente); los archivos de
comprobante nunca se sirven públicamente. `all_objects` explícito en
TODO acceso a relación inversa sobre un modelo `TenantScopedModel`
dentro de `apps.billing.services` — nunca `instancia.relacion_inversa`
(que usa el manager tenant-scoped por defecto, dependiente de un
`ContextVar` que no existe en un comando de administración, un
receptor de señal de webhook, o un test) — ver `KNOWN_ISSUES.md`.

## Auditoría

Dominio `"billing_saas"` (distinto de `"billing_paypal"`, FASE 16) vía
`apps.billing.services._saas_audit.audit_event` — mismo patrón
resiliente de siempre (nunca rompe la operación de negocio). Nunca se
audita ningún secreto.

## Concurrencia e idempotencia

Probado con hilos reales (`TransactionTestCase`): dos generaciones
simultáneas de la factura del mismo período (una gana, nunca duplica),
dos asignaciones simultáneas que exceden el saldo de un pago (una
gana), dos aprobaciones simultáneas del mismo comprobante (un solo
`SaaSPayment` creado). Idempotencia real (constraints de base de
datos, nunca solo "el código no se llama dos veces") en: generación de
factura por período, aprobación de comprobante (`select_for_update`
sobre `PaymentProof`), renovación recurrente.

## Reportes

`apps.billing.services.reports` (nunca `apps.reports`, exclusivamente
tenant-scoped) — dashboard (MRR/ARR/altas/cancelaciones/transferencias
pendientes/ingresos/reembolsos/notas de crédito/facturas vencidas),
ingresos por método/plan, suscripciones por estado, antigüedad de
facturas pendientes (aging). `{"summary": ..., "rows": ...}`, mismo
contrato que `apps.reports`.

## Moneda

`Plan`/`PlanVersion.price_currency`, `Subscription` (heredada de
`plan_version`), `SaaSInvoice`/`SaaSPayment`/`CreditNote`/`BillingRefund.currency`
— cada obligación/pago tiene su propia moneda, nunca mezclada con la
del ERP del tenant (`Sale.currency`/`Payment.currency`, eje
completamente distinto). Sin conversión automática en ningún punto.

## Qué NO se construyó en FASE 17

OCR real (documentado como extensión futura, arquitectura preparada
conceptualmente, sin campos/dependencias nuevas); contabilidad del
operador SaaS (`apps.accounting` tenant-scoped nunca se toca); un
segundo proveedor de pagos; WACRM; exportaciones PDF/XLSX específicas
de Billing (los reportes están listos para reutilizar
`apps.reports.exports`, no se conectó en esta fase — ver `KNOWN_ISSUES.md`).
