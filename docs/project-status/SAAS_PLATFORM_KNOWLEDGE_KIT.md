# SaaS Platform Knowledge Kit

Base de conocimiento viva, específica de la plataforma SaaS (Billing,
alta de tenants, identidad y ciclo de vida del Owner) — **complementa,
nunca reemplaza**, `KNOWN_ISSUES.md`/`DECISIONS.md`/`PHASE_HISTORY.md`
(la fuente de verdad completa y cronológica del proyecto). Aquí se
consolidan, por tema, los patrones que se repetirán en futuras
correcciones del Gate Local y en fases posteriores, para no tener que
redescubrirlos cada vez. Se agrega, nunca se reescribe: cada entrada
nueva es un párrafo adicional bajo su sección, citando el
commit/`KNOWN_ISSUES`/`DECISIONS` real donde se implementó — nunca una
afirmación sin evidencia.

Creado durante "FASE DE CORRECCIÓN 1B — Activación de cuenta desde
Registro/Login" (posterior a FASE 20, Gate Local). Primeras entradas:
identidad del Owner y activación de cuenta.

## ACCOUNT ACTIVATION

**Patrón reusable — Identity Creation vs. Account Activation son dos
eventos distintos, nunca uno solo.** Cuando un Tenant se crea o se
comercializa automáticamente (hoy: Venta Manual desde Super Admin,
`apps.billing.admin_views.ManualTenantSaleView`; cualquier flujo futuro
de alta que reserve un Owner por adelantado debe seguir el mismo
patrón) hay dos eventos que el sistema separa a propósito:

1. **Identity Creation** — el `User` + `Membership` OWNER se crean de
   inmediato, con `set_unusable_password()` (identidad reservada, sin
   acceso posible todavía).
2. **Account Activation** — el dueño real de esa identidad la reclama
   después, estableciendo su propia contraseña por primera vez, vía un
   token de un solo uso enviado a su correo.

El Owner creado así **nunca debe registrarse de nuevo**: Registro/Login
reconocen el correo como "identidad ya creada, pendiente de
activación" y ofrecen activar — nunca un mensaje genérico que no dice
qué hacer, y nunca, bajo ninguna circunstancia, un segundo `User` para
el mismo correo (`apps.accounts.forms.RegistrationForm.clean_email`
sigue siendo la única puerta, sin excepción, desde FASE 4).

Mecánica completa (ver `KNOWN_ISSUES.md` #128/#129, `DECISIONS.md`
#108/#109, `docs/authentication.md`):

- **Enlace inicial**: se genera y envía automáticamente en el momento
  de la creación (`apps.accounts.services.send_account_activation_email`,
  llamado justo después de que la transacción de alta ya confirmó).
- **Reenvío**: self-service, disparado desde Registro ("Activar mi
  cuenta"), Login ("Reenviar enlace de activación") o la pantalla de
  enlace expirado ("Solicitar nuevo enlace") — los tres apuntan al
  mismo formulario (`accounts:activacion_reenviar`), que localiza el
  `User` existente por correo y NUNCA crea uno nuevo.
- **Expiración**: pantalla específica ("Este enlace de activación ha
  expirado") en vez del mensaje genérico de "inválido" — solo cuando la
  causa real es el tiempo transcurrido
  (`apps.accounts.services.classify_activation_token`); un token
  adulterado o emitido para otro usuario sigue mostrando el mensaje
  genérico, sin darle a un atacante ninguna pista sobre cuál fue el
  problema exacto.
- **Invalidación del enlace anterior**: cada reenvío invalida
  FUNCIONALMENTE cualquier token emitido antes (el del alta original y
  cualquier reenvío previo) llamando de nuevo a `set_unusable_password()`
  — que genera un valor aleatorio distinto cada vez que se llama — antes
  de emitir el nuevo token. Sin este paso, "reenviar" solo agregaría un
  enlace más, válido en paralelo, en vez de reemplazar al anterior.
- **Cuenta ya activada**: si el correo pertenece a un Owner que ya
  activó (`has_usable_password() == True`), Registro muestra "Ya existe
  una cuenta... Inicia sesión" (nunca el flujo de activación), y el
  reenvío no hace nada — ni envía correo ni revela el estado real, mismo
  criterio anti-enumeración que la recuperación de contraseña estándar.
- **Separación entre Identity Creation y Account Activation**: ningún
  paso de la activación (confirmar el token, establecer la contraseña)
  vuelve a tocar `Tenant`/`Membership`/`Subscription` — esos ya existen
  desde la Identity Creation. Activar una cuenta es exclusivamente un
  cambio de `User.password`; nunca recrea ni modifica el resto del
  estado de negocio ya creado.

## AUTHENTICATION

Ver `docs/authentication.md` (documento completo y autoritativo del
subsistema: login por correo, registro, recuperación/cambio de
contraseña, perfil, onboarding, y la sección "Activación de cuenta para
Owners creados automáticamente"). Puntos que otras fases deben conocer
sin releer el documento completo:

- `USERNAME_FIELD = "email"`, sin `username`; `AUTHENTICATION_BACKENDS`
  es el `ModelBackend` por defecto de Django, sin backends propios.
- Un Super Admin de plataforma (`is_superuser=True`) se evalúa ANTES
  que la pertenencia a un tenant en todo punto de decisión post-login
  (`EmailLoginView.get_success_url`, `OnboardingView.dispatch`) — nunca
  comparte código de decisión con "usuario sin tenant todavía".
- Throttling de login/recuperación de contraseña/reenvío de activación
  son tres ejes de `apps.accounts.rate_limit` completamente
  independientes (agotar uno nunca agota los otros).

## SAAS BILLING & PAYMENT PROVIDERS

Primeras entradas agregadas durante "FASE DE CORRECCIÓN 2 — Billing del
Tenant + PayPal + Transferencia" (ver `KNOWN_ISSUES.md` #130,
`DECISIONS.md` #110, `docs/billing.md`/`docs/paypal.md`).

- **SaaS Billing separado del ERP Operational Payments**: `apps.billing`
  (`Subscription`/`SaaSInvoice`/`SaaSPayment`/`SaaSPaymentAllocation`)
  es lo que un Tenant paga a Budun ERP por usar la plataforma;
  `apps.sales.Payment`/`PaymentAllocation` es el motor de cuentas por
  cobrar de CADA TENANT hacia SUS PROPIOS clientes — dominios
  ortogonales que nunca se mezclan, ni siquiera comparten tabla aunque
  su forma sea casi idéntica (mismo principio que
  `Payment`/`SupplierPayment` desde FASE 10/12). Ninguna integración de
  Billing SaaS (PayPal, transferencia) escribe jamás en `apps.sales`.
- **Payment Methods configurables**: ningún método de pago se
  hardcodea en una plantilla o formulario — cada uno expone una función
  `is_X_available()` (`apps.billing.services.is_paypal_available`,
  `apps.billing.services.transfers.is_bank_transfer_available`) que el
  Portal consulta en cada request; nunca una lista fija de opciones en
  el código de la plantilla/formulario.
- **PayPal como provider**: `apps.billing.providers.base.PaymentProvider`
  es la interfaz; `PayPalProvider` es la única implementación real hoy.
  Disponibilidad = `PayPalGatewayStatus.is_enabled` (un interruptor
  único de PLATAFORMA, no por tenant) — el backend (`create_checkout`)
  ya rechazaba un checkout con el gateway deshabilitado antes de esta
  corrección; lo que faltaba era que la UI también lo consultara.
- **Bank Transfer como provider** (conceptual — no hay una llamada a un
  servicio externo, así que no tiene una interfaz `PaymentProvider`
  formal): disponibilidad = "¿existe al menos una `BankAccount`
  activa?" — nunca tuvo un interruptor único como PayPal porque nunca
  lo necesitó.
- **Invoice → Payment → Allocation**: un método de pago NUNCA marca una
  factura como pagada directamente — siempre crea un `SaaSPayment`
  (registrado y confirmado) que luego se APLICA a la factura vía
  `SaaSPaymentAllocation` (`record_payment` + `auto_apply_payment`), y
  solo entonces el saldo de la factura (recalculado del ledger, nunca
  un campo cacheado) llega a cero y el estado pasa a `PAID`. Los dos
  caminos reales (PayPal síncrono vía `_on_payment_confirmed`,
  transferencia vía `approve_payment_proof`) convergen en el MISMO par
  de funciones — nunca dos implementaciones paralelas de "aplicar un
  pago".
- **Patrón reusable — una factura emitida es un snapshot contractual**
  (agregado en "FASE DE CORRECCIÓN 2B", ver `KNOWN_ISSUES.md` #131,
  `DECISIONS.md` #111): *"Una factura SaaS emitida es un snapshot
  contractual del importe y moneda. Los pagos posteriores deben cobrar
  exactamente ese snapshot y nunca recalcular el precio vigente del
  plan."* Ningún proveedor de pago (PayPal hoy; cualquiera futuro) debe
  recibir jamás un monto derivado de "cuánto cuesta el plan ahora" para
  cobrar una factura YA EMITIDA — siempre `invoice.total`/
  `invoice.currency`, nunca `resolve_plan_pricing`/equivalente. La
  única excepción legítima es un flujo que genuinamente NO tiene
  factura todavía (alta nueva vía "elegir plan", o la herramienta de
  prueba de plataforma) — ahí SÍ corresponde resolver el precio
  vigente, porque no hay ningún snapshot que respetar todavía.
  `apps.billing.services.create_checkout_for_invoice` es la
  implementación de referencia de este patrón para PayPal.
- **Subscription lifecycle**: un pago confirmado (por cualquier
  método) dispara `activate_subscription` — el mismo primitivo de bajo
  nivel que usan tanto la activación inicial
  (`activate_pending_subscription`, exclusiva de `PENDING`) como la
  reactivación (`reactivate_subscription`, exclusiva de
  `SUSPENDED`/`PAST_DUE`); el propio evento de pago real ya es la
  evidencia que esos dos guardas exigen para una acción administrativa
  manual, así que la señal puede llamar al primitivo directamente sin
  pasar por ninguno de los dos guardas — `PENDING` sigue sin ser
  `SUSPENDED`, "Activar" y "Reactivar" siguen siendo operaciones
  distintas para el Super Admin (sin cambios de la corrección
  anterior).
- **Payment method availability** es una decisión de PLATAFORMA
  (PayPal) o de CONFIGURACIÓN COMPARTIDA (cuentas bancarias, no por
  tenant) — nunca algo que un tenant individual activa/desactiva para
  sí mismo.
- **Separación entre provider y dominio de negocio**:
  `apps.billing.providers` (PayPal) no sabe qué es una
  `Subscription`/`SaaSInvoice` — solo sabe crear/capturar/reembolsar
  órdenes. Toda la lógica de negocio (qué factura se paga, cuándo se
  activa una suscripción) vive en `apps.billing.services`, nunca en el
  provider ni en la vista.
- **Limitaciones de webhook en localhost**: un webhook de PayPal
  Sandbox no puede llegar a `127.0.0.1` — el flujo real de este
  proyecto NUNCA depende de él para confirmar un pago (la captura es
  SÍNCRONA en el `return_url` al volver de PayPal); el webhook es solo
  una confirmación redundante para cuando el navegador no vuelve. Para
  el Gate Local, validar el flujo síncrono contra Sandbox real (o
  contra `FakePayPalProvider` en un smoke automatizado) es suficiente y
  correcto — nunca simular una entrega de webhook que no podría ocurrir
  de verdad en ese entorno.

## RECURRING BILLING PATTERN

Primeras entradas agregadas durante "FASE DE CORRECCIÓN 2C — PayPal
Recurring Billing / Cobro Automático Mensual" (ver `KNOWN_ISSUES.md`
#132, `DECISIONS.md` #112, `docs/billing.md` sección "Billing
recurrente con PayPal").

**Patrón reusable**: *"La plataforma SaaS mantiene la Subscription y
las Invoices como fuente de verdad. El proveedor externo ejecuta el
cobro recurrente. El estado externo se reconcilia mediante eventos
idempotentes."* Ningún proveedor de cobro recurrente futuro (PayPal
Subscriptions hoy; cualquier otro mañana) debe convertirse jamás en una
segunda fuente de verdad de negocio — `Subscription.status`/
`SaaSInvoice.status` siguen siendo lo único que Budun consulta para
decidir si un tenant opera o no; el estado del proveedor externo
(`Subscription.paypal_subscription_status` hoy) es SIEMPRE un espejo
informativo, nunca una entrada a la lógica de negocio.

- **Autorización inicial**: un flujo de aprobación por redirect (el
  mismo patrón que el checkout de pago único: crear → `approve_url` →
  el cliente aprueba en el sitio del proveedor → retorno) que autoriza
  cobros FUTUROS, sin cobrar nada todavía por sí solo — el primer cobro
  se confirma aparte (síncronamente al volver, en este proyecto).
- **Renewal**: nunca depende de que un scheduler propio calcule "cuándo
  cobrar" — el PROVEEDOR decide el calendario (su propio Billing Plan/
  ciclo de facturación) y notifica el resultado por evento. El sistema
  reacciona generando/reconciliando la factura correspondiente,
  reactivamente si hace falta, nunca esperando pasivamente a que su
  propio cron adivine el momento correcto primero.
- **Payment failure / grace period / PAST_DUE**: un fallo de cobro
  recurrente reportado por el proveedor marca el estado de gracia
  (`PAST_DUE`) — nunca se salta directo a suspender. `PAST_DUE` es
  siempre un estado DISTINTO de `SUSPENDED`, sin excepciones ni atajos.
- **SUSPENDED / retry**: si el proveedor tiene su propio mecanismo de
  reintentos configurable (como `payment_failure_threshold` de PayPal),
  reutilizarlo — nunca construir un scheduler de reintentos propio en
  paralelo al que el proveedor ya ofrece nativamente para esto mismo.
  Budun solo reacciona a los webhooks de resultado (éxito → vuelve a
  `ACTIVE`; agotado el umbral → `SUSPENDED`/`CANCELLED`).
- **Cancellation**: coordinada en AMBOS lados explícitamente (proveedor
  primero — impide cualquier cobro futuro real — luego el sistema
  propio) — nunca cancelar solo un lado y asumir que el otro se entera
  solo. El historial (facturas, pagos) NUNCA se borra al cancelar.
- **Webhook reconciliation**: cada evento re-verifica el estado ACTUAL
  antes de escribir (nunca asume que llega en el orden correcto ni que
  es la primera vez que se ve) — un evento duplicado o tardío/fuera de
  orden (p. ej. un cobro confirmado que llega DESPUÉS de una
  cancelación) es siempre un no-op idempotente, nunca reactiva ni
  duplica nada. El dinero que un evento tardío reporte como cobrado, si
  ya no hay nada válido a lo que aplicarlo, se registra igual como pago
  sin aplicar — nunca se descarta ni se pierde.
- **Price snapshot**: el mismo principio de la Corrección 2B
  ("`SaaSInvoice.total`/`currency` son el snapshot contractual") se
  extiende al cobro recurrente con una garantía ADICIONAL: si el propio
  objeto de facturación del proveedor externo es inmutable una vez
  creado (el Billing Plan de PayPal lo es), el proveedor mismo refuerza
  la regla — ni siquiera él podría cobrar un monto distinto del
  congelado al crearlo. Un cambio de precio siempre crea una versión
  contractual NUEVA (`PlanVersion` nueva) con su propio objeto de
  facturación nuevo del lado del proveedor — nunca se edita el
  existente.

## DECISIONS LOG

Registro narrativo — el detalle completo y versionado vive en
`docs/project-status/DECISIONS.md`; aquí solo el resumen navegable de
las decisiones de esta familia de correcciones:

- **#108**: reutilizar `default_token_generator` (el mismo mecanismo de
  la recuperación de contraseña) en vez de un modelo de token nuevo
  para la activación inicial — ya resuelve un solo uso efectivo,
  expiración, atado a usuario y detección de adulteración sin código
  adicional.
- **#109**: `resend_activation_email` invalida el token anterior
  reutilizando `set_unusable_password()` (genera un hash aleatorio
  nuevo cada vez) en vez de un campo de versión/nonce nuevo en el
  modelo `User`; `classify_activation_token` distingue "expirado" de
  "inválido" reutilizando el método de extensión que Django expone
  (`_make_token_with_timestamp`) en vez de un segundo generador de
  tokens; el reenvío es anti-enumeración por diseño (misma respuesta
  exista o no la cuenta, esté o no ya activada), igual criterio que
  `AccountPasswordResetView` desde FASE 18.
- **#110**: la disponibilidad de un método de pago se calcula desde la
  configuración real en cada request (`is_paypal_available`/
  `is_bank_transfer_available`), nunca cacheada ni hardcodeada en el
  formulario/plantilla. Se descartó unificar ambos métodos detrás de
  una interfaz común tipo "PaymentMethodProvider": PayPal y
  transferencia tienen semánticas de disponibilidad genuinamente
  distintas (un interruptor único de plataforma vs. "¿existe al menos
  una fila activa?") y forzarlas a la misma forma habría sido una
  abstracción prematura sin un tercer método real que la necesite
  todavía — mismo criterio de "no generalizar sin un segundo caso real"
  ya aplicado repetidas veces en este proyecto.
- **#111**: `create_checkout_for_invoice` como función NUEVA en vez de
  modificar el comportamiento por defecto de `create_checkout` — su
  único otro llamador real (la herramienta de prueba de plataforma, sin
  ninguna factura) sigue necesitando resolver el precio vigente del
  plan, así que cambiarle el comportamiento por defecto para arreglar
  el Portal habría sido tocar un llamador que funciona correctamente
  hoy. La concurrencia se cerró bloqueando SOLO la `SaaSInvoice` en
  cuestión (`select_for_update()`), no la `Subscription` entera —
  suficiente para el escenario real (dos clics sobre la MISMA factura)
  sin ampliar el lock a operaciones administrativas no relacionadas
  sobre la misma suscripción. Se descartó explícitamente inventar una
  lista de monedas soportadas por PayPal sin poder verificarla contra
  documentación oficial — la validación de moneda se limitó a una
  comprobación de buena formación, y la lista real queda como pendiente
  documentado, nunca como una suposición.
- **#112**: PayPal Subscriptions API sobre Reference Transactions/Vault
  — decisión tomada solo después de verificar oficialmente que Reference
  Transactions exige aprobación especial de PayPal para cuentas LIVE
  (bloqueo externo fuera de nuestro control), mientras que Subscriptions
  no la necesita. Reintentos de cobro delegados enteramente al
  `payment_failure_threshold` nativo de PayPal — nunca un scheduler de
  reintentos propio compitiendo con uno que el proveedor ya ofrece. La
  generación de la factura de renovación es reactiva (desde el webhook)
  ADEMÁS de programada (desde el cron existente) — ambos caminos usan la
  misma función idempotente, así que cualquiera de los dos que llegue
  primero resuelve, sin necesitar coordinación explícita entre ellos.

## LESSONS LEARNED

- `django.contrib.auth.forms.PasswordResetForm.get_users()` excluye a
  propósito cualquier cuenta con `has_usable_password() == False` — es
  imposible usar "¿Olvidaste tu contraseña?" como flujo de activación
  para una cuenta creada sin contraseña. Cualquier patrón futuro de
  "crear una identidad por adelantado, dejar que su dueño la reclame
  después" necesita su PROPIO flujo de confirmación (puede reutilizar
  `default_token_generator`, pero nunca el formulario completo de
  recuperación de contraseña).
- `User.set_unusable_password()` genera un valor aleatorio NUEVO cada
  vez que se llama (`make_password(None)`) — es una forma gratuita, sin
  infraestructura nueva, de invalidar cualquier token que dependa del
  hash de la contraseña (todo lo que use `default_token_generator`),
  siempre que la cuenta siga sin contraseña utilizable real.
- `PasswordResetTokenGenerator.check_token` solo devuelve un booleano —
  no distingue "expiró" de "es inválido por cualquier otra razón".
  Mostrarle al usuario un mensaje específico de expiración exige
  reimplementar esa distinción reutilizando el propio método de
  extensión de Django (`_make_token_with_timestamp`), no inventar un
  mecanismo de expiración paralelo.
- Un backend correcto (`create_checkout` ya rechazaba un checkout de
  PayPal con el gateway deshabilitado) no implica una UI correcta — la
  ausencia de una prueba end-to-end contra la PLANTILLA renderizada (no
  solo contra la vista/servicio a nivel de API) dejó pasar un botón que
  nunca se mostraba, con el backend detrás funcionando perfectamente
  todo el tiempo. Una prueba que solo llama al servicio/vista
  directamente no habría detectado este hallazgo — hacía falta
  `assertContains`/`assertNotContains` sobre el HTML real.
- Antes de replicar el patrón de disponibilidad de un método de pago en
  otro ("¿tiene un booleano `is_enabled` como PayPal?"), preguntar
  primero cuál es la señal REAL de disponibilidad de ESE método
  específico — la transferencia nunca necesitó un interruptor propio
  porque su señal real ya existía (`BankAccount.objects.filter(
  is_active=True)`).
- Un identificador de negocio (`plan_id`/slug) que sirve para "resolver
  cuánto cuesta esto" en un contexto (alta nueva, sin factura) puede
  dejar de ser la fuente de verdad correcta en otro contexto (pagar una
  factura YA EMITIDA) — antes de reutilizar una función que resuelve un
  monto a partir de un identificador, preguntar explícitamente "¿ya
  existe un snapshot congelado del monto real, o esta operación
  necesita calcularlo desde cero?".

## COMMON FAILURES

- **Síntoma**: el registro rechaza un correo con un mensaje genérico
  ("Ya existe una cuenta...") que no le dice al usuario qué hacer. →
  **Causa real**: el correo pertenece a un `User` con contraseña
  inutilizable creado por Venta Manual. → **Corrección**: distinguir el
  caso con un código de error propio (`pending_activation` vs.
  `account_exists`) y ofrecer la acción correcta en cada uno.
- **Síntoma**: "Reenviar activación" no invalida el enlace anterior —
  ambos enlaces (el viejo y el nuevo) siguen funcionando. → **Causa
  real**: generar un token nuevo con `default_token_generator.make_token`
  no invalida uno anterior por sí solo; ambos son válidos mientras no
  expiren y la contraseña no cambie. → **Corrección**: llamar
  `set_unusable_password()` de nuevo (nunca activar la cuenta) antes de
  emitir el nuevo token.
- **Síntoma**: "¿Olvidaste tu contraseña?" no envía nada para el Owner
  recién creado por Venta Manual, ni siquiera un error visible. →
  **Causa real**: `PasswordResetForm.get_users()` filtra en silencio
  cualquier cuenta con `has_usable_password() == False`. → **Corrección**:
  no es un bug a arreglar en ese flujo — es el motivo por el que existe
  un flujo de activación dedicado, separado de la recuperación de
  contraseña.
- **Síntoma**: "El Portal de Billing del tenant solo muestra
  Transferencia bancaria, nunca PayPal", pese a que PayPal está
  habilitado y el checkout funciona perfectamente si se llega a él por
  otra vía. → **Causa real**: la plantilla de la tabla de facturas
  (`portal_status.html`) enlazaba EXCLUSIVAMENTE a
  `transfer_instructions` — nunca existía ningún enlace a
  `checkout_paypal_initiate` desde ahí, ni ninguna condición que lo
  bloqueara; el backend nunca tuvo el problema. → **Corrección**:
  exponer ambos métodos de pago en la tabla de facturas, cada uno
  condicionado a su disponibilidad real
  (`is_paypal_available`/`is_bank_transfer_available`).
- **Síntoma**: PayPal aparece como opción para elegir plan incluso con
  el gateway deshabilitado por el Super Admin. → **Causa real**:
  `SelectPlanForm.payment_method` tenía las `choices` hardcodeadas en
  la definición de la clase (`[("paypal", "PayPal"), ("bank_transfer",
  ...)]`), nunca calculadas contra la configuración real. →
  **Corrección**: calcular `choices` dinámicamente en `__init__` a
  partir de `is_paypal_available()`/`is_bank_transfer_available()` —
  `create_checkout` sigue siendo, además, la segunda defensa real en el
  backend si de todos modos llegara un valor inválido.
- **Síntoma**: un tenant podría, en teoría, subir dos comprobantes de
  transferencia para la misma factura, o uno para una factura ya
  pagada, o declarar un monto de cero o una moneda que no coincide con
  la cuenta receptora — ninguno de estos casos estaba validado. →
  **Causa real**: `submit_payment_proof` solo validaba el archivo
  adjunto; nunca el estado de la factura, la existencia de un
  comprobante pendiente previo, el monto ni la moneda declarados. →
  **Corrección**: cuatro validaciones nuevas en el servicio (único
  punto de entrada real del dominio), nunca duplicadas en la vista.
- **Síntoma**: si el precio de un plan cambia DESPUÉS de que una
  factura ya fue emitida, PayPal podría terminar cobrando un monto
  distinto del que la propia factura dice deber. → **Causa real**:
  `CheckoutPayPalInitiateView` pasaba `plan_id` a `create_checkout`,
  que recalculaba el monto/moneda desde el precio VIGENTE del plan
  (`resolve_plan_pricing`) en vez de usar el snapshot ya congelado en
  `invoice.total`/`invoice.currency`. → **Corrección**:
  `create_checkout_for_invoice` exige el monto/moneda de la factura
  explícitamente; `create_checkout` gana parámetros opcionales que,
  cuando se pasan, desactivan el recálculo — su otro llamador (la
  herramienta de plataforma, sin factura) sigue igual.
- **Síntoma**: dos clics rápidos en "Pagar con PayPal" (o dos pestañas)
  sobre la misma factura podrían crear dos órdenes de PayPal en
  paralelo. → **Causa real**: nada bloqueaba un segundo intento de
  checkout mientras el primero seguía sin resolverse. → **Corrección**:
  `select_for_update()` sobre la `SaaSInvoice` + comprobación de que no
  exista ya un `PayPalTransaction` `CREATED`/`PENDING_CAPTURE` para la
  misma suscripción antes de crear uno nuevo — verificado con un test
  de concurrencia real (`TransactionTestCase` + hilos).
- **Síntoma**: nunca existía ningún cobro automático real para una
  suscripción recurrente — solo se generaba la factura del período
  siguiente, sin ningún intento de cobrarla. → **Causa real**: FASE 16
  conectó PayPal únicamente vía Orders API v2 (pago único) porque en ese
  momento el `Plan`/`Subscription` real de FASE 17 todavía no existía;
  nunca se volvió a conectar un mecanismo de cobro recurrente después de
  que FASE 17 sí los construyera. → **Corrección**: PayPal Subscriptions
  API completa (autorización, confirmación, renovación por webhook,
  fallo/PAST_DUE, cancelación coordinada).
- **Síntoma**: un webhook de Subscriptions procesado en un smoke manual
  quedaba silenciosamente marcado `ERROR` (`TransactionManagementError:
  select_for_update cannot be used outside a transaction`), pese a que
  los 24 tests unitarios nuevos pasaban en verde. → **Causa real**: la
  función que aplicaba la transición (`apply_subscription_webhook_
  event`) usaba `select_for_update()` sin su propio `transaction.
  atomic()` — funcionaba en los tests SOLO porque `TestCase` ya envuelve
  cada prueba en una transacción ambiente, ocultando el error. →
  **Corrección**: `transaction.atomic()` explícito alrededor de esa
  lectura+escritura. **Lección**: un test que pasa dentro de `TestCase`
  no prueba que el código funcione FUERA de una transacción ya
  existente — cualquier función que use `select_for_update()` debe
  abrir su PROPIA transacción, nunca asumir que el llamador ya abrió
  una; un smoke manual ejecutado fuera del framework de tests es lo que
  expuso este caso real.
