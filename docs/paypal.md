# PayPal (`apps.billing`)

> **Estado: CONSTRUIDO en FASE 16** (ver `docs/phases/PHASE-16-paypal-sandbox.md`
> para el checklist completo). Reemplaza la especificación anterior de
> este documento — todo lo descrito aquí abajo ya existe en el código,
> no es un plan. Sigue existiendo `docs/phases/PHASE-16-paypal-sandbox.md`
> (checklist/criterios de aceptación) y `docs/billing.md` (alcance
> todavía pendiente de FASE 17 — Billing SaaS completo).

## 1. PayPal es un provider de Billing SaaS, no del ERP del tenant

```text
Billing SaaS (apps.billing)
    ↓
Payment Provider Interface (apps.billing.providers.base.PaymentProvider)
    ↓
PayPal Provider (apps.billing.providers.paypal.PayPalProvider)
    ↓
PayPal (Orders API v2 + Payments v2 + Webhooks v1)
```

PayPal **nunca** se conecta a `apps.sales.Payment`/`PaymentAllocation`/
`Refund` (el motor de cuentas por cobrar de cada tenant, FASE 10/11) —
esos modelos siguen siendo exclusivamente del ERP operativo del
tenant. Todo pago confirmado por PayPal termina en `apps.billing.
PayPalTransaction` (ver sección 3) — el registro propio de Billing
SaaS, nunca un `Payment` de `apps.sales`.

La única superposición legítima entre "PayPal" y `apps.sales` es
distinta y ya existía antes de esta fase: un tenant puede registrar
manualmente que un cliente suyo le pagó por PayPal fuera del sistema
(`Payment.method` extensible) — una entrada manual del cajero, sin
ninguna relación con esta integración.

## 2. Alcance de FASE 16 vs. FASE 17

FASE 16 construye el **mecanismo** de PayPal (Orders API v2 completo:
crear orden, capturar, reembolsar; OAuth2; webhooks verificados;
idempotencia; concurrencia) y una herramienta de plataforma para
operarlo/probarlo. **No** construye:

- El flujo de autoservicio Landing → Pricing → Plan → Suscripción
  (eso es FASE 17 — `docs/billing.md`).
- `Plan`/`Subscription`/`SaaS Invoice`/`SaaS Payment` como modelos de
  base de datos — `apps.core.pricing.PLANS` (FASE 6) se extendió con
  `price_amount`/`price_currency` (el mínimo necesario para poder
  crear una orden real con un monto Decimal exacto), pero sigue sin
  ser un modelo de Plan real.
- Transferencia bancaria, comprobantes, verificación manual, notas de
  crédito, creación/administración de tenants — todo FASE 17.

## 3. Modelos (`apps.billing.models`)

Ninguno de estos modelos hereda `TenantScopedModel` — el actor es el
Super Admin de la PLATAFORMA (que opera sobre transacciones de
cualquier tenant), no un tenant operando sobre sus propios datos.
Mismo principio ya usado por `apps.audit.AuditLog`/`apps.tenants.
Membership`.

- **`PayPalGatewayStatus`** (fila única, `pk=1`): estado operativo del
  gateway — `is_enabled` (interruptor administrativo reversible del
  checkout), `last_tested_at`/`last_test_ok`/`last_test_error`/
  `last_tested_environment`. Las credenciales (`PAYPAL_CLIENT_ID`/
  `PAYPAL_CLIENT_SECRET`/`PAYPAL_ENVIRONMENT`/`PAYPAL_WEBHOOK_ID`)
  **nunca** viven aquí ni en ninguna tabla — son variables de entorno
  de la plataforma, mismo criterio que `DJANGO_SECRET_KEY`/
  `DB_PASSWORD` (ver sección 4).
- **`PayPalTransaction`**: un intento de cobro vía Orders API v2 (alta
  o renovación de la suscripción de un tenant al SaaS). `environment`
  es un snapshot (nunca cambia con la configuración posterior, mismo
  principio que `SaleItem`). Identificadores externos SEPARADOS entre
  sí y del estado interno: `external_order_id`/`external_capture_id`/
  `external_refund_id` nunca se confunden con `status`. `amount`/
  `currency` (lo que decidimos cobrar) se conservan SIEMPRE separados
  de `provider_amount`/`provider_currency` (lo que PayPal reportó al
  capturar) — nunca se mezclan/sobrescriben entre sí. Máquina de
  estados: `CREATED → {PENDING_CAPTURE|CONFIRMED|FAILED|CANCELLED}`,
  `CONFIRMED → {REFUND_PENDING|REFUNDED}`, `REFUND_PENDING →
  {REFUNDED|REFUND_FAILED}` — validada en `apps.billing.services`,
  nunca en la vista ni en el modelo.
- **`PayPalWebhookEvent`**: ledger/registro de idempotencia de
  webhooks. `event_id` (el `id` que PayPal asigna a cada evento) tiene
  `UniqueConstraint` — la barrera real de idempotencia a nivel de base
  de datos (ver sección 8). `summary` guarda solo un subconjunto
  mínimo y seguro (tipo de evento, id/estado/monto del recurso) —
  nunca el payload completo ni datos del pagador.

No existe ningún campo de stock/saldo desnormalizado ni una segunda
fuente de verdad: `PayPalTransaction.status` es siempre la única
fuente de "en qué estado está este cobro".

## 4. Credenciales y configuración

Variables de entorno de PLATAFORMA (`.env`, nunca en base de datos ni
en Git, mismo criterio que `DJANGO_SECRET_KEY`/`DB_PASSWORD`):

```text
PAYPAL_ENVIRONMENT=SANDBOX   # o LIVE
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_WEBHOOK_ID=
```

`PAYPAL_WEBHOOK_ID` es el ID que PayPal asigna al registrar la URL de
webhook (`/webhooks/paypal/`) en el dashboard del desarrollador —
necesario para la verificación oficial de firma. **Se retiró**
`PAYPAL_ACCESS_TOKEN` de `.env.example` (existía desde antes de esta
fase): guardar un access token violaría la regla de la sección 10 de
`docs/phases/PHASE-16-paypal-sandbox.md` ("no registrar access
tokens") — el token se pide en vivo (OAuth2 `client_credentials`) y se
cachea solo en el cache de Django (`LocMemCache`), nunca en disco/BD.

## 5. Decisión: Orders API v2, no Subscriptions API

Se evaluaron **PayPal Orders API** vs. **PayPal Subscriptions API**
(sección 5 de la fase). Se eligió **Orders API v2** exclusivamente:

- Subscriptions API exige crear `Product`/`Plan` del LADO DE PAYPAL,
  espejando el futuro `Plan` interno de FASE 17 antes de que ese
  modelo exista — habría sido construir Billing SaaS por la puerta de
  atrás, exactamente lo que la fase prohíbe.
- Con Orders API, cada cobro (alta o renovación) es una orden
  independiente, capturada explícitamente por nuestro propio servicio
  — la periodicidad/renovación queda como una decisión de FASE 17
  (cuándo disparar la siguiente orden), nunca delegada a PayPal.
- Refund es igual de completo en ambos flujos (Payments v2 API sobre
  la captura), así que Orders API cubre pago inicial, renovación (una
  orden más) y refund sin ninguna limitación real.

Ver `DECISIONS.md` para el registro formal de esta decisión.

## 6. Provider abstraction (`apps.billing.providers`)

`PaymentProvider` (`.base`) es la interfaz abstracta: `create_order`/
`capture_order`/`get_order`/`refund_capture`/`verify_webhook_signature`/
`test_connection`. `PayPalProvider` (`.paypal`) es la única
implementación real hoy; `get_default_provider()` (`.__init__`) es el
único punto de construcción — nunca se instancia `PayPalProvider`
directamente desde `services.py`/vistas. Esto deja espacio explícito
para Transferencia Bancaria (FASE 17) u otro proveedor sin rehacer
`apps.billing.services`.

**Endpoints oficiales usados** (consultados en `developer.paypal.com`
durante esta fase, no una documentación antigua):

| Operación | Método | Path |
|---|---|---|
| OAuth2 (client credentials) | POST | `/v1/oauth2/token` |
| Crear orden | POST | `/v2/checkout/orders` |
| Capturar orden | POST | `/v2/checkout/orders/{id}/capture` |
| Consultar orden | GET | `/v2/checkout/orders/{id}` |
| Reembolsar captura | POST | `/v2/payments/captures/{id}/refund` |
| Verificar firma de webhook | POST | `/v1/notifications/verify-webhook-signature` |

Sandbox: `api-m.sandbox.paypal.com`; Live: `api-m.paypal.com` (elegido
por `PAYPAL_ENVIRONMENT`). La verificación de firma de webhook usa el
método oficial recomendado (reenviar transmission-id/time/cert-url/
auth-algo/transmission-sig + `webhook_id` + el evento al propio
endpoint de PayPal) en vez de reimplementar la verificación
criptográfica de certificados — más simple y más confiable.

**Decisión de dependencias**: se usa `urllib` (librería estándar) para
las llamadas HTTP, **no** se agrega `requests` ni el SDK oficial de
PayPal como dependencia nueva — mismo criterio de mínima dependencia
que ya rigió `reportlab`/`openpyxl`/`Pillow` (cada dependencia se
justifica explícitamente; el volumen de llamadas HTTP que esta
integración necesita no lo justifica). Ver `DECISIONS.md`.

## 7. Idempotencia y reconciliación

Dos niveles, nunca confundidos:

1. **Hacia PayPal**: cada operación que crea/modifica dinero
   (crear orden, capturar, reembolsar) envía `PayPal-Request-Id`
   derivado de `PayPalTransaction.client_reference` (UUID fijo por
   fila) — un reintento nuestro con la misma fila nunca duplica la
   operación del lado de PayPal.
2. **Hacia nosotros mismos**: `PayPalWebhookEvent.event_id` tiene
   `UniqueConstraint` — dos entregas del mismo evento (reintento de
   PayPal, o dos procesos) nunca se procesan dos veces; la segunda
   entrega encuentra la fila ya creada (`IntegrityError` capturado) y
   nunca vuelve a aplicar la transición.

Cada transición de estado (`apps.billing.services._apply_webhook_event`)
vuelve a verificar el estado ACTUAL antes de escribir (dentro de
`transaction.atomic()` + `select_for_update()`) — un evento que
describe una transición ya alcanzada (duplicado, o fuera de orden
porque llegó tarde) es un no-op idempotente, nunca un error ni una
doble aplicación. Ejemplo probado: un `PAYMENT.CAPTURE.COMPLETED`
tardío que llega DESPUÉS de que la transacción ya se reembolsó nunca
la regresa a `CONFIRMED`.

## 8. Webhooks (`/webhooks/paypal/`, `apps.billing.webhook_views`)

Endpoint público, sin autenticación por sesión/API key (PayPal no
puede enviar un Bearer token nuestro) — la seguridad reside
enteramente en la verificación oficial de firma, nunca en confiar en
el remitente. La vista solo captura headers/cuerpo crudo y delega a
`apps.billing.services.process_webhook_event` — nunca toca el ORM
directamente. Throttle básico por IP (60/min, cache de Django) como
defensa en profundidad. Firma inválida → 400 (PayPal puede reintentar,
pero un evento con firma inválida nunca se acepta); cualquier otro
resultado (procesado/duplicado/ignorado/error interno ya registrado) →
200, porque la idempotencia real vive en la base de datos, nunca en
si PayPal reintenta o no.

Eventos manejados: `CHECKOUT.ORDER.APPROVED` (informativo — nuestro
propio flujo ya captura sincrónicamente al volver del checkout),
`PAYMENT.CAPTURE.COMPLETED`/`CHECKOUT.ORDER.COMPLETED` (confirma),
`PAYMENT.CAPTURE.DENIED`/`DECLINED` (falla), `PAYMENT.CAPTURE.REFUNDED`
(reembolso completado, incluso si el reembolso se originó fuera de
banda, directamente en el panel de PayPal), `PAYMENT.REFUND.PENDING`/
`FAILED`. Un evento reconocido por PayPal pero fuera del alcance de
esta fase (p. ej. disputas) se marca procesado sin cambiar estado —
nunca un error.

## 9. Refunds

`apps.billing.services.request_refund`: solo desde `CONFIRMED`
(rechaza explícitamente un segundo reembolso o un reembolso sobre una
transacción no confirmada). Ciclo `PENDING → COMPLETED`/`PENDING →
FAILED` soportado, sin borrar historial — mismo principio de
inmutabilidad que `Return`/`PaymentAllocation` revertida en el resto
del proyecto.

## 10. Multi-moneda

`PayPalTransaction.currency`/`amount` (interno, lo que decidimos
cobrar) y `provider_currency`/`provider_amount` (lo que PayPal
reportó al capturar) se guardan SIEMPRE por separado — nunca se
mezclan. `apps.core.pricing.PLANS` fija `price_currency` por plan
(hoy todos en `USD`); no hay conversión automática en ningún punto.

## 11. Permisos y auditoría

**Desviación deliberada de la sugerencia literal de permisos**
(`billing.paypal.view/configure/test/refund`): estas vistas son
exclusivas de PLATAFORMA, no de ningún tenant — el motor de
`apps.permissions` resuelve permisos POR TENANT (`RolePermission` es
"qué puede hacer el rol X en el tenant Y"), lo cual no aplica a un
recurso que no pertenece a ningún tenant. En vez de forzar esas 4
acciones dentro de ese catálogo, se agregó `require_superuser`/
`SuperuserRequiredMixin` (`apps.tenants.permissions`, junto a
`require_tenant`/`require_role`) — exactamente el mismo criterio que
YA usa `apps.permissions.services.has_permission` en su primer
escalón ("OWNER/superusuario → siempre autorizado"), aplicado aquí
como la única condición porque no hay tenant del que depender. Ver
`DECISIONS.md`.

Toda operación se audita vía `apps.audit` (dominio `"billing_paypal"`,
`tenant` puede ser `None` en operaciones de plataforma sin tenant
asociado): `PAYPAL_CONFIG_TESTED`, `PAYPAL_CHECKOUT_CREATED`,
`PAYPAL_PAYMENT_CONFIRMED`/`FAILED`, `PAYPAL_CHECKOUT_CANCELLED`,
`PAYPAL_REFUND_REQUESTED`/`COMPLETED`/`FAILED`,
`PAYPAL_WEBHOOK_PROCESSED` (`AuditLog.Action`, nuevos). Nunca se audita
el client secret, el access token, ni la firma cruda del webhook —
verificado con tests dedicados que inspeccionan el contenido
serializado de cada `AuditLog` del dominio.

## 12. Preparación para FASE 17 (`apps.billing.signals`)

`payment_confirmed`/`payment_failed`/`checkout_cancelled`/
`refund_requested`/`refund_completed`/`refund_failed` (señales de
Django) son el contrato estable que FASE 17 conectará para actualizar
su futura `Subscription`/`SaaS Invoice` (ninguno de esos modelos
existe todavía). `SUBSCRIPTION_ACTIVATED`/`SUBSCRIPTION_CANCELLED`
(mencionados como ejemplo en la instrucción de FASE 16) **no** se
modelan — no existe ningún concepto de `Subscription` al que
asociarlos; inventarlas ahora habría sido el "segundo sistema de
Billing" que la fase prohíbe.

## 13. UI de plataforma (`apps.billing.platform_views`, `/plataforma/billing/paypal/`)

Exclusiva del Super Admin — nunca parte del hub «Configuración» del
tenant (`apps.core`, que es tenant-scoped): estado del gateway +
Probar Conexión + habilitar/deshabilitar checkout, iniciar un cobro
real (elige tenant + plan con precio + propósito, redirige a PayPal),
retorno/cancelación, detalle de transacción con sus eventos de
webhook y botón de reembolso. Es una herramienta de
**operación/prueba del mecanismo**, no el flujo de venta de
autoservicio (Landing → Pricing) ni la administración completa de
Billing — ambos FASE 17. No existe todavía una navegación/hub de
"Panel de Plataforma" formal (gap conocido, documentado para que FASE
17 lo formalice) — la URL se documenta aquí como punto de entrada
directo.

## 14. Qué NO se construyó en FASE 16

`Plan`/`Subscription`/`SaaS Invoice`/`SaaS Payment` como modelos de
base de datos; Landing → Pricing → checkout de autoservicio para un
tenant real; transferencia bancaria/comprobantes/verificación manual;
notas de crédito de Billing; creación/administración de tenants;
contabilidad del operador SaaS; soporte para `OTHER_ERP`/otro
proveedor de pagos. Todo eso es FASE 17 (`docs/billing.md`).
