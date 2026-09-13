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
lo aplica automáticamente, activa/reactiva suscripción/tenant según
corresponda) o `reject_payment_proof` (nunca activa). Estados reales de
`PaymentProof.Status`: `SUBMITTED`/`UNDER_REVIEW` (equivalentes de
"pendiente de revisión", ambos aceptan aprobar/rechazar),
`APPROVED`/`REJECTED` (terminales), `REVERSED` (reservado, sin
disparador todavía). `PENDING` existe en el enum como valor por
defecto del campo pero ningún flujo real lo produce (`submit_payment_
proof` siempre crea directamente en `SUBMITTED`) — documentado, nunca
"limpiado" innecesariamente vía migración.

Validaciones (servicio, nunca solo el formulario): rechaza un
comprobante para una factura que ya no está `OPEN`/`PARTIALLY_PAID`
(pagada, anulada o en borrador), rechaza un segundo comprobante
mientras uno sigue `SUBMITTED`/`UNDER_REVIEW` para la misma factura,
exige un monto declarado positivo, exige que la cuenta receptora siga
activa (defensa en profundidad — el formulario ya solo lista cuentas
activas), y exige que la moneda declarada coincida EXACTAMENTE con la
de la cuenta receptora Y con la de la factura (FASE DE CORRECCIÓN 4,
sección 9 — sin motor de tipos de cambio, `docs/currency.md`, nunca una
conversión implícita; mismo criterio reforzado en el núcleo del ledger,
`apps.billing.services.payments.apply_payment_to_invoices`/
`auto_apply_payment`, que nunca aplican un pago a una factura en otra
moneda). Notificaciones por correo (`apps.billing.services.
notifications`, reutiliza `EMAIL_BACKEND` existente desde FASE 4 — no
existe todavía ningún centro de notificaciones in-app en el proyecto,
construir uno sería un subsistema nuevo fuera del alcance de esta
fase).

**Consultar el comprobante (FASE DE CORRECCIÓN 4, hallazgo real)**: antes
de esta corrección, NINGUNA vista (ni Super Admin ni tenant) podía ver
el contenido real del archivo subido — `proof_detail.html` solo
mostraba el nombre de archivo como texto plano, así que aprobar/
rechazar una transferencia se decidía completamente a ciegas. Nuevas
vistas protegidas `apps.billing.admin_views.ProofDownloadView`
(`/plataforma/billing/admin/transferencias/<id>/descargar/`, exclusivo
Super Admin, cualquier tenant) y `apps.billing.portal_views.
PaymentProofDownloadView` (`/facturacion/comprobantes/<id>/descargar/`,
filtrada por `tenant=request.tenant`) sirven el archivo vía
`FileResponse` (mismo patrón que `apps.customers.
_ContactDocumentDownloadView`) — nunca por `MEDIA_URL` estático
(`PaymentProof.file` vive en `media-private/`).

**Historial del tenant (FASE DE CORRECCIÓN 4)**: `/facturacion/` ahora
muestra "Historial de comprobantes de transferencia" (factura, fecha,
monto, moneda, estado, motivo de rechazo cuando corresponde, enlace de
descarga) — antes de esta corrección, un comprobante rechazado solo se
comunicaba por correo, sin ninguna vista consultable en el propio
Portal.

**Concurrencia (FASE DE CORRECCIÓN 4, dos gaps reales corregidos)**:
(1) `submit_payment_proof` ahora bloquea (`select_for_update()`) la
propia `SaaSInvoice` antes de comprobar "sin comprobante pendiente" —
antes, dos envíos concurrentes del mismo formulario podían crear dos
`PaymentProof` `SUBMITTED` para la misma factura (la comprobación era
un `.exists()` sin ningún lock). (2) `reject_payment_proof` ahora
rechaza rechazar un comprobante que ya está `APPROVED` — antes no
existía ese guard, así que la carrera real "aprobar + rechazar el mismo
comprobante a la vez" podía dejar un `PaymentProof` `REJECTED` con un
`SaaSPayment`/`Allocation`/`Subscription ACTIVE` ya generados por la
aprobación, un estado contradictorio.

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
días_restantes`; `neto = cargo − crédito`.

- **Neto negativo (downgrade)**: emite una `CreditNote` automáticamente
  (`credit_services.issue_credit_note`).
- **Neto positivo (upgrade) — corregido en FASE DE CORRECCIÓN 3**: antes
  de esta corrección, el cargo solo quedaba en el `metadata` de
  auditoría — nunca se cobraba de verdad en ningún lado (ver
  `KNOWN_ISSUES.md` #133). Ahora `invoicing_services.
  issue_proration_charge_invoice` emite una `SaaSInvoice` INMEDIATA y
  aparte del ciclo normal de renovación, por el monto exacto del
  prorrateo (`period_start=change_date`, misma garantía de
  `UniqueConstraint(subscription, period_start)` de siempre para que un
  doble envío del formulario nunca duplique el cargo) — la factura del
  período vigente, ya emitida, nunca se edita.

Cualquier nota de crédito emitida por un downgrade se aplica
AUTOMÁTICAMENTE a la próxima factura que se genere para esa suscripción
(`credit_services.auto_apply_available_credit_notes`, llamada desde
`generate_invoice_for_subscription`/`issue_proration_charge_invoice`) —
antes de FASE DE CORRECCIÓN 3, `apply_credit_note_to_invoice` existía
pero solo se ejercitaba desde pruebas; ninguna vista ni proceso
automático la invocaba nunca.

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

## Billing recurrente con PayPal (Corrección de Gate Local — "FASE DE CORRECCIÓN 2C")

**Estado**: IMPLEMENTADO y PROBADO EN SANDBOX (vía `FakePayPalProvider`,
el test double ya establecido del proyecto — ver "Localhost" más abajo
para por qué). PREPARADO PARA PRODUCCIÓN en cuanto exista una URL
pública (el checkout síncrono ya funciona igual en local que en
producción; el webhook, indispensable para las renovaciones, exige una
URL HTTPS pública real). NO se ha probado todavía contra un endpoint
real de PayPal Sandbox por HTTP — la validación es de la lógica interna
completa, con la capa de red sustituida por el mismo doble ya usado en
todo `apps.billing` desde FASE 16.

**Arquitectura elegida — PayPal Subscriptions API** (Catalog Products +
Billing Plans + Subscriptions), evaluada oficialmente contra la
alternativa (PayPal Reference Transactions / Vault) antes de escribir
código: Reference Transactions exige aprobación especial de PayPal para
cuentas LIVE (contactar al gestor de cuenta; el error real documentado
por PayPal si no se tiene es `MERCHANT_NOT_ENABLED_FOR_REFERENCE_
TRANSACTION`), mientras que Subscriptions es una API REST estándar sin
aprobación adicional, igual en Sandbox que en Live — la decisión
correcta para no depender de un proceso de aprobación externo fuera de
nuestro control. Fuentes oficiales consultadas: `developer.paypal.com/
docs/subscriptions/integrate/`, `.../subscriptions/webhooks`,
`.../subscriptions/customize/payment-failure-retry/`,
`.../api/nvp-soap/paypal-payments-pro/integration-guide/reference-
transactions` (septiembre 2026).

**Mapeo Budun ↔ PayPal, siempre 1:1 y CENTRALIZADO** (nunca un
producto/plan de PayPal por tenant — la misma `PlanVersion` la
reutilizan todos los tenants que la contraten):
- `PlanVersion.paypal_product_id`/`paypal_plan_id` (campos nuevos,
  vacíos hasta que algún tenant contrate esa versión con cobro
  recurrente) ↔ Producto + Billing Plan de PayPal —
  `apps.billing.services.recurring.ensure_paypal_billing_plan`, creados
  una única vez, inmutables desde entonces (igual que el precio que
  representan: un cambio de precio siempre crea una `PlanVersion` nueva
  con su propio Producto/Plan de PayPal, nunca edita los existentes).
- `Subscription.paypal_subscription_id`/`paypal_subscription_status`
  (campos nuevos) ↔ Subscription de PayPal — una por tenant, creada al
  autorizar el cobro recurrente
  (`recurring.create_recurring_checkout`). `paypal_subscription_status`
  es un espejo informativo del último estado conocido en PayPal
  (visible para el Super Admin, nunca usado para decidir nada de
  negocio por sí solo — la fuente de verdad de negocio sigue siendo
  `Subscription.status`, gobernado exclusivamente por
  `apps.billing.services.subscriptions`).

**Flujo completo**:
1. **Autorización + primer cobro** (`RecurringCheckoutInitiateView` →
   `create_recurring_checkout` → PayPal → `RecurringCheckoutReturnView`
   → `reconcile_recurring_subscription`): reconciliación SÍNCRONA al
   volver del checkout — nunca depende del webhook para la autorización
   inicial (ver "Localhost" abajo). Si PayPal ya reporta `ACTIVE`, se
   confirma el primer cobro contra la factura inicial ya generada por
   `SelectPlanView`/Venta Manual.
2. **Renovación** (`PAYMENT.SALE.COMPLETED`, únicamente por webhook —
   no hay ningún retorno del navegador para un cobro que PayPal ejecuta
   en segundo plano meses después): `confirm_recurring_charge` busca la
   factura `OPEN`/`PARTIALLY_PAID` de la suscripción; si no existe
   todavía (el cron `generate_saas_invoices` no alcanzó a correr antes
   que el webhook), la genera ella misma
   (`invoicing.ensure_next_renewal_invoice`, la misma función que usa
   el cron) — el sistema nunca depende de que el scheduler corra
   primero. El monto/moneda cobrados SIEMPRE respetan la Corrección 2B
   (`SaaSInvoice.total`/`currency`, nunca el precio vigente del plan) —
   y, para el caso recurrente, esto está ADEMÁS estructuralmente
   garantizado por PayPal: el Billing Plan es inmutable, así que ni
   siquiera PayPal podría cobrar un monto distinto del congelado al
   crearlo.
3. **Fallo de cobro** (`BILLING.SUBSCRIPTION.PAYMENT.FAILED`): marca
   `PAST_DUE` (`subscription_services.mark_past_due`, sin cambios).
   **Reintentos**: PayPal reintenta un cobro recurrente fallido POR SU
   CUENTA — `payment_preferences.payment_failure_threshold` (configurado
   al crear el Billing Plan, propuesta de 2 intentos, documentada como
   propuesta y no como política comercial ya decidida por el negocio) —
   Budun NO implementa un scheduler de reintentos propio para PayPal;
   solo reacciona a los webhooks de éxito/fallo que PayPal ya emite. Si
   el reintento tiene éxito, `PAYMENT.SALE.COMPLETED` vuelve la
   suscripción a `ACTIVE`; si se agota el umbral, PayPal emite
   `BILLING.SUBSCRIPTION.SUSPENDED`/`CANCELLED` y Budun sincroniza
   (`suspend_subscription`/`cancel_subscription`, sin cambios).
   `PENDING ≠ SUSPENDED` y `PAST_DUE ≠ SUSPENDED` se mantienen sin
   ninguna excepción para el método recurrente.
4. **Cancelación** (`recurring.cancel_recurring_subscription`): cancela
   AMBOS lados de forma coordinada — primero PayPal (impide cualquier
   cobro futuro), luego Budun (`cancel_subscription`, conserva intacto
   todo el historial de facturas/pagos, nunca los borra). Un cobro
   tardío/fuera de orden que de todas formas llegara después de
   cancelar (`confirm_recurring_charge` sobre una suscripción
   `CANCELLED`/`EXPIRED`) nunca genera una factura nueva — se registra
   como pago sin aplicar (nunca se pierde, mismo criterio que un
   sobrepago) y se audita como anomalía para revisión humana.

**Transferencia bancaria** sigue siendo, deliberadamente, un método
distinto y NO automático — nunca hay una autorización de cobro
recurrente posible sin una cuenta ya vinculada, así que la transferencia
siempre exige comprobante → revisión → aprobación manual (sin cambios).
El Portal distingue explícitamente "PayPal (pago único)", "PayPal
(cobro automático)" y "Transferencia bancaria" como tres opciones
claramente etiquetadas — nunca una sola opción ambigua "PayPal".

**Localhost**: mismo criterio ya documentado para el checkout de pago
único (`docs/paypal.md`) — un webhook de PayPal Sandbox no puede
entregarse a `127.0.0.1`. La autorización INICIAL nunca depende de él
(reconciliación síncrona al volver del checkout); las renovaciones SÍ
dependen exclusivamente del webhook (no hay otra forma de enterarse de
un cobro que PayPal ejecuta sin ningún retorno del navegador) — para
Gate Local, esto se valida con `FakePayPalProvider` + payloads de
webhook realistas construidos a mano (`apps.billing.tests._helpers.
build_webhook_body`, el mismo mecanismo que ya usan los webhooks de
Orders API desde FASE 16) — nunca simulando una entrega real a
`localhost`, que sería fingir una integración que no puede ocurrir de
verdad en este entorno. La prueba de webhook real contra una URL HTTPS
pública queda para la fase de despliegue.

**Seguridad**: nunca se almacena Client Secret/access token/credenciales
(sin cambios respecto a FASE 16 — siguen siendo variables de entorno de
plataforma). Los únicos identificadores nuevos guardados
(`paypal_product_id`/`paypal_plan_id`/`paypal_subscription_id`) son
referencias públicas no sensibles (los mismos IDs que ya aparecen en el
panel de PayPal del propio Super Admin), nunca un secreto ni una
credencial tokenizada — Budun no implementa (ni necesita) tokenización
de medios de pago propia, PayPal la gestiona enteramente de su lado.

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

**Corregido en FASE DE CORRECCIÓN 3**: la distinción de arriba solo se
respetaba en la acción manual del Super Admin — tres caminos
AUTOMÁTICOS de confirmación de pago (`transfers.approve_payment_proof`,
`recurring.confirm_recurring_charge`, `paypal_integration.
_on_payment_confirmed`) llamaban siempre a `activate_subscription`
directo, incluso cuando la suscripción estaba `PAST_DUE`/`SUSPENDED` —
saltándose el guard/auditoría/notificación propios de
`reactivate_subscription`, y (el efecto real, no solo cosmético) sin
restaurar el período si ya había vencido durante la suspensión. Los
tres ahora distinguen: `PENDING` → `activate_subscription`;
`PAST_DUE`/`SUSPENDED` → `reactivate_subscription`. Además,
`reactivate_subscription` ahora restaura el período (le da uno nuevo a
partir de HOY) cuando el vigente ya venció mientras la suscripción
estaba suspendida/en mora — nunca reanuda un período ya vencido, que
dispararía de inmediato una factura de renovación retroactiva por
fechas en las que el tenant no pudo operar (ver `DECISIONS.md` #113).
Si el período vigente todavía no había terminado, se conserva intacto.

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

## Lifecycle integral del SaaS (Corrección de Gate Local — "FASE DE CORRECCIÓN 3")

Auditoría de extremo a extremo del ciclo de vida completo (Tenant/
Subscription/SaaSInvoice/SaaSPayment/Allocation/BillingStatus), sin
tocar la arquitectura ya validada en las correcciones anteriores.
Máquina de estados REAL confirmada por el código (nunca un estado
inventado):

- `Tenant.billing_status`: `PENDING_SETUP` → `PENDING_PAYMENT` →
  `ACTIVE` ⇄ `PAST_DUE` → `SUSPENDED` → `ACTIVE` (reactivación) /
  `CANCELLED`. `EXPIRED` existe en el enum pero ningún flujo real lo
  alcanza todavía (`apps.billing.services.tenants.mark_tenant_expired`
  no tiene ningún llamador) — documentado como pendiente real, nunca
  inventado un disparador nuevo sin que el negocio lo pida.
- `Subscription.Status`: mismo shape (`PENDING`/`ACTIVE`/`PAST_DUE`/
  `SUSPENDED`/`CANCELLED`/`EXPIRED`, este último también sin disparador
  real hoy).

Hallazgos reales corregidos (auditoría antes de tocar nada, por
sección 1 de la corrección):

1. **`ACTIVATE` != `REACTIVATE` no se respetaba en los caminos
   AUTOMÁTICOS** — ver "Alta inicial y activación" arriba.
2. **Reactivación nunca restauraba un período vencido** — ver arriba.
3. **Upgrade con neto positivo nunca cobraba nada** — ver "Cambio de
   plan y prorrateo" arriba.
4. **Notas de crédito nunca se aplicaban automáticamente** — ver
   "Cambio de plan y prorrateo" arriba.
5. **Un reembolso nunca revertía la `SaaSPaymentAllocation` del pago**:
   la factura quedaba `PAID`/`PARTIALLY_PAID` para siempre aunque el
   dinero ya hubiera vuelto al cliente. `refunds._complete_refund`
   ahora revierte las asignaciones activas del pago hasta cubrir el
   monto reembolsado (más recientes primero); si una asignación
   revertida era mayor que lo efectivamente reembolsado, el remanente
   se re-asigna como una asignación NUEVA a la misma factura (reverso +
   reasignación, nunca una edición in-place del ledger).
6. **Dos solicitudes de reembolso simultáneas podían comprometer más de
   lo disponible** — el guard de monto disponible en
   `request_billing_refund` solo contaba reembolsos `COMPLETED`; un
   `BillingRefund` recién creado queda `PENDING` (no completado todavía)
   así que dos solicitudes concurrentes ambas leían "0 ya reembolsado".
   `_comprometido_total` ahora suma `PENDING` + `COMPLETED` (un
   reembolso `FAILED` libera de nuevo su monto).
7. **Notificaciones de PAST_DUE/suspensión/reactivación/renovación
   existían desde FASE 17 pero ningún flujo real las llamaba** —
   conectadas en `mark_past_due`/`suspend_subscription`/
   `reactivate_subscription`/`ensure_next_renewal_invoice`. Las de
   "factura próxima a vencer"/"factura vencida" (`notify_invoice_
   upcoming`/`notify_invoice_overdue`) siguen sin ningún disparador
   real — requerirían un comando de cron nuevo ("N días antes de
   vencer") que no existe hoy; documentado como pendiente real, nunca
   construido sin que el negocio lo pida explícitamente.

**Validado sin necesitar cambios** (auditado, comportamiento ya
correcto): `BillingStatusMiddleware` contra los 7 estados (ninguno deja
al tenant sin poder pagar, activo sin evidencia de pago, o con acceso
ERP indebido); reportes de Super Admin (`apps.billing.services.reports`,
ya distinguen revenue/pending/paid/past-due/suspended/churn/renewal/
refunds/transferencias pendientes/notas de crédito, nunca mezclados con
`apps.reports` tenant-scoped); reconciliación de PayPal recurrente
(nunca crea una segunda `Subscription` de Budun, webhook duplicado/
fuera de orden ya idempotente desde FASE DE CORRECCIÓN 2C); aislamiento
Multi-Tenant (arquitectura de `TenantScopedModel`/`all_objects` ya
suficiente, sin gap nuevo encontrado).

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
comprobante nunca se sirven públicamente — desde FASE DE CORRECCIÓN 4
sí son consultables (antes, ni siquiera el Super Admin podía verlos),
pero exclusivamente vía `FileResponse` a través de
`ProofDownloadView`/`PaymentProofDownloadView`, cada una con su propio
filtro de pertenencia (Super Admin: cualquier tenant; Portal: solo
`tenant=request.tenant`), nunca por `MEDIA_URL` estático. `all_objects`
explícito en
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
`SaaSPayment` creado), dos reactivaciones simultáneas de la misma
suscripción (una gana), dos solicitudes de reembolso simultáneas sobre
el mismo pago (nunca comprometen juntas más de lo disponible — FASE DE
CORRECCIÓN 3), dos emisiones simultáneas de la factura de cargo por
prorrateo de un mismo upgrade (nunca duplica, mismo
`UniqueConstraint(subscription, period_start)`), dos envíos
simultáneos del mismo comprobante de transferencia (uno gana — FASE DE
CORRECCIÓN 4), aprobación y rechazo simultáneos del mismo comprobante
(una única transición consistente, nunca un estado contradictorio),
y una transferencia aprobándose a la vez que un pago de PayPal se
captura sobre la MISMA factura (ambos convergen sin duplicar ni
romperse mutuamente — ver más abajo). Idempotencia real (constraints
de base de datos, nunca solo "el código no se llama dos veces") en:
generación de factura por período, factura de cargo por prorrateo,
aprobación de comprobante (`select_for_update` sobre `PaymentProof`
y, desde FASE DE CORRECCIÓN 4, sobre la propia `SaaSInvoice` antes de
aceptar un comprobante nuevo), renovación recurrente, reactivación.

**Hallazgo real de FASE DE CORRECCIÓN 4**: `auto_apply_payment`
calculaba su plan de asignación leyendo el saldo de cada factura SIN
lock, tomando el lock real recién dentro de `apply_payment_to_invoices`
— si OTRO método de pago independiente cubría la misma factura entre
esas dos lecturas (el caso real: una transferencia aprobándose a la
vez que se captura un pago de PayPal sobre la misma factura, en hilos
distintos), `apply_payment_to_invoices` lanzaba `InvalidPaymentOperation`
sin atrapar — y como `auto_apply_payment` se invoca típicamente desde
dentro de la transacción de OTRA operación (una captura de PayPal, un
webhook), esa excepción revertía la transacción COMPLETA del llamador,
deshaciendo incluso una captura de PayPal ya exitosa. Corregido con un
reintento acotado (una sola vez, recalculando con datos frescos) — si
tras recalcular ya no queda ninguna factura con saldo real, el pago
simplemente queda sin aplicar (saldo a favor), nunca rompe la
operación del llamador.

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
