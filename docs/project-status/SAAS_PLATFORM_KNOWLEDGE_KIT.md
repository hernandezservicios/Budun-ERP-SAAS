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

## SUBSCRIPTION & BILLING LIFECYCLE PATTERNS

Agregado durante "FASE DE CORRECCIÓN 3 — Lifecycle Integral del SaaS"
(ver `KNOWN_ISSUES.md` #133, `DECISIONS.md` #113, `docs/billing.md`
sección "Lifecycle integral del SaaS"). Los 11 patrones reutilizables
que esa corrección exigió documentar explícitamente — varios ya
aparecían implícitos en secciones anteriores de este Kit; aquí quedan
todos con la misma estructura (Problema/Patrón/Solución/Reglas/Errores
comunes/Prevención) para que cualquier dominio futuro con un ciclo de
vida de estados (no solo Billing) pueda reutilizarlos sin releer el
código fuente.

### 1. Subscription State Machine

- **Problema**: un ciclo de vida con varios estados relacionados
  (`Tenant.billing_status` de plataforma + `Subscription.status` de
  negocio) puede divergir entre sí, o alguien puede "inventar" un
  estado nuevo a mitad de una corrección sin darse cuenta de que ya
  existe uno equivalente.
- **Patrón**: DOS máquinas de estados relacionadas pero DISTINTAS, cada
  una con su propio `TextChoices`, sincronizadas en un solo sentido
  (`apps.billing.services.subscriptions` llama a
  `apps.billing.services.tenants`, nunca al revés) por funciones que
  son las ÚNICAS que escriben ese campo en todo el proyecto.
- **Solución**: antes de tocar código, leer el `TextChoices` real de
  AMBOS modelos y listar cada transición que el código realmente
  ejecuta (`grep` de cada función de transición) — nunca asumir la
  máquina de estados a partir de la memoria o de la documentación
  vieja.
- **Reglas**: nunca inventar un estado nuevo sin que el negocio lo pida
  explícitamente; un estado que existe en el enum pero sin ningún
  disparador real (`EXPIRED` en este proyecto) se documenta como
  pendiente, nunca se "completa" solo por prolijidad.
- **Errores comunes**: asumir que dos campos con nombres parecidos
  (`billing_status` del Tenant, `status` de la Subscription) son la
  misma máquina de estados solo porque comparten varios valores.
- **Prevención**: un test explícito por cada valor del enum contra cada
  clase de ruta/comportamiento relevante (ver "PAST_DUE / SUSPENDED"
  abajo y `BillingStatusMiddlewareTests`), nunca solo un subconjunto
  "representativo".

### 2. Billing Lifecycle (visión de punta a punta)

- **Problema**: "existe una función para cada paso" no significa que
  los pasos estén conectados entre sí en el orden real de negocio.
- **Patrón**: alta → activación → período fijo → renovación → pago →
  (fallo → PAST_DUE → gracia → retry → SUSPENDED → reactivación) →
  cancelación, con upgrade/downgrade/crédito/reembolso como ramas
  laterales que nunca alteran una factura ya emitida.
- **Solución**: auditar CADA transición leyendo el código real (nunca
  solo el nombre de la función) antes de corregir nada — de las 6
  correcciones reales de esta fase, ninguna era "falta una función";
  todas eran "la función existe pero un llamador real la usa mal, o
  nadie la llama".
- **Reglas**: cada paso deja evidencia real (factura, pago, allocation)
  antes de avanzar al siguiente estado — nunca una transición "porque
  sí" sin el evento de negocio que la justifica.
- **Errores comunes**: revisar solo las pruebas unitarias existentes
  como prueba de que el flujo completo funciona — 228 tests pasaban en
  verde con los 6 gaps de esta corrección todavía presentes, porque
  ninguno probaba el camino AUTOMÁTICO completo de punta a punta con el
  estado de partida correcto (PAST_DUE/SUSPENDED en vez de PENDING).
- **Prevención**: un smoke manual de ciclo de vida completo (ver
  sección de smoke en `docs/billing.md`) sigue siendo la única prueba
  real de que los pasos individuales, todos correctos por separado,
  también lo son ENCADENADOS.

### 3. Renewal Pattern

- **Problema**: la renovación recurrente puede dispararse desde más de
  un lugar (un cron programado, un webhook reactivo) — coordinarlos
  explícitamente sería frágil y agregaría estado nuevo.
- **Patrón**: una única función idempotente (`ensure_next_renewal_
  invoice`) que cualquiera de los caminos puede llamar sin saber del
  otro; la idempotencia real es un `UniqueConstraint` de base de datos
  (`SaaSInvoice(subscription, period_start)`), nunca una bandera en
  memoria ni "el código no se llama dos veces".
- **Solución**: extraer la función compartida UNA vez (hecho en la
  Corrección 2C) y reutilizarla sin duplicar la lógica de cálculo de
  período en el segundo camino.
- **Reglas**: el período NUNCA avanza dos veces para el mismo ciclo —
  se avanza solo cuando la factura realmente se CREÓ (`creada=True`),
  nunca cuando se recuperó una ya existente.
- **Errores comunes**: asumir que el cron "siempre corre primero" y
  que el webhook solo necesita reaccionar a una factura que ya existe.
- **Prevención**: prueba de concurrencia real con dos hilos generando
  la misma renovación a la vez (`InvoiceGenerationConcurrencyTests`).

### 4. Grace Period

- **Problema**: sin un período de gracia explícito, un fallo de pago
  puntual (tarjeta rechazada por un motivo transitorio) suspendería la
  cuenta de inmediato, una experiencia agresiva e innecesaria.
- **Patrón**: un estado intermedio (`PAST_DUE`) que NO bloquea la
  operación (`billing_status_blocks_operation` es `False` para él),
  gobernado por una política CONFIGURABLE (`BillingPolicy.
  grace_period_days`), nunca un número hardcodeado en el código.
- **Solución**: `apply_billing_past_due_policy` calcula la escalación
  por CALENDARIO (días desde el vencimiento de una factura real),
  determinístico y re-ejecutable sin duplicar transiciones (cada
  función de transición ya es idempotente por sí sola).
- **Reglas**: nunca suspender directo desde `ACTIVE` sin pasar por
  `PAST_DUE` primero; el tiempo de gracia se lee siempre de
  `BillingPolicy`, nunca de una constante en el código.
- **Errores comunes**: confundir el mecanismo de gracia por CALENDARIO
  (Transferencia, sin forma de "reintentar un cobro") con el mecanismo
  de reintento por CANTIDAD DE INTENTOS que un proveedor de cobro
  recurrente puede ofrecer nativamente (ver "PayPal recurrente" abajo)
  — son dos mecanismos DISTINTOS para dos métodos de pago distintos,
  nunca el mismo código.
- **Prevención**: un test por cada combinación de "¿cuántos días de
  atraso?" contra el resultado esperado (`ACTIVE`/`PAST_DUE`/
  `SUSPENDED`), nunca un solo caso feliz.

### 5. PAST_DUE / SUSPENDED (dos estados de mora, deliberadamente distintos)

- **Problema**: tratar "cuenta con problemas de pago" como un único
  estado difuso pierde información real: ¿puede el tenant seguir
  operando mientras regulariza, o ya se le bloqueó por completo?
- **Patrón**: `PAST_DUE` (en gracia, opera con normalidad) y
  `SUSPENDED` (bloqueado, solo puede pagar) son dos estados
  INDEPENDIENTES en el enum, nunca un booleano `is_past_due` sobre un
  único estado "problema de pago".
- **Solución**: `Tenant.billing_status_blocks_operation` es la única
  fuente de verdad de "¿bloquea o no?" — evalúa el valor exacto del
  enum, nunca una heurística sobre otro campo.
- **Reglas**: `PENDING` != `SUSPENDED` != `PAST_DUE` != `CANCELLED` —
  cuatro estados con guardas y significados de negocio distintos,
  ninguno intercambiable con otro aunque el efecto visible ("el tenant
  no puede operar del todo") coincida para dos de ellos.
- **Errores comunes**: implementar una única condición "¿tiene algún
  problema de facturación?" que trate `PAST_DUE` y `SUSPENDED` igual —
  pierde exactamente la distinción de negocio que este patrón exige.
- **Prevención**: `BillingStatusMiddlewareTests` prueba cada estado del
  enum por separado contra el mismo conjunto de rutas, nunca agrupa
  "los estados problemáticos" en un solo caso de prueba.

### 6. Activation vs Reactivation

- **Problema**: dos operaciones que "terminan en el mismo lugar"
  (`Subscription.status = ACTIVE`) pueden tener puntos de partida y
  garantías completamente distintos — tratarlas como intercambiables
  pierde esas garantías.
- **Patrón**: `activate_subscription`/`activate_pending_subscription`
  (exclusivas de `PENDING`, generan evidencia de pago si falta) nunca
  se reutilizan para `reactivate_subscription` (exclusiva de
  `SUSPENDED`/`PAST_DUE`, restaura el período si ya venció) — dos
  funciones con guardas de estado de entrada disjuntas, cada una
  auditando/notificando con su propio significado ("activada" vs.
  "reactivada").
- **Solución real de esta corrección**: el patrón YA estaba correcto en
  la acción manual del Super Admin desde el Gate Local original; el
  gap estaba en que TRES caminos automáticos (aprobación de
  transferencia, confirmación de cobro recurrente, confirmación de
  pago único vía señal) llamaban al primitivo de activación inicial
  incluso para una suscripción `SUSPENDED`/`PAST_DUE` — nunca revisado
  hasta esta auditoría porque cada uno se implementó en una corrección
  distinta, sin volver a comparar contra el patrón ya establecido en la
  primera.
- **Reglas**: antes de llamar a una función de transición de estado,
  el llamador SIEMPRE debe conocer el estado de PARTIDA real (nunca
  "sea cual sea, esta función lo arregla") y elegir la función que
  exige exactamente ese estado de entrada.
- **Errores comunes**: reutilizar el primitivo de activación "porque ya
  hace casi lo mismo" (mismo campo, mismo valor final) sin revisar que
  las garantías adicionales (restauración de período, auditoría/
  notificación correctas) solo viven en la función específica.
- **Prevención**: cuando un patrón de negocio se establece en una
  corrección (aquí, en el Gate Local original de FASE 17), toda
  corrección POSTERIOR que agregue un nuevo camino de confirmación de
  pago debe auditar explícitamente si ese camino respeta el mismo
  patrón — nunca asumir que, por estar descrito en la documentación, ya
  se aplica en todos lados.

### 7. Invoice as Contractual Snapshot

- **Problema**: un valor "vigente" (precio actual de un plan) puede
  cambiar en cualquier momento; una obligación de cobro ya emitida
  nunca debe seguir ese valor cambiante.
- **Patrón**: `SaaSInvoice.total`/`SaaSInvoice.currency`, congelados al
  emitirse, son la ÚNICA fuente de verdad para cualquier cobro
  posterior contra esa factura — nunca se recalculan desde el precio
  vigente del plan/`PlanVersion`.
- **Solución**: toda función que iniciar un cobro contra una factura ya
  existente exige el monto/moneda como parámetros explícitos leídos de
  la factura (`create_checkout_for_invoice`), nunca un identificador de
  plan que otra función podría "resolver" de nuevo.
- **Reglas**: un cargo NUEVO (upgrade a mitad de período) es una
  factura NUEVA y separada — nunca una edición de una factura ya
  emitida, ni siquiera para "corregir" un monto.
- **Errores comunes**: pasar un identificador de negocio (`plan_id`)
  en vez del monto ya congelado, confiando en que la función de destino
  "seguramente" no lo recalcula.
- **Prevención**: un test que cambia el precio vigente DESPUÉS de emitir
  la factura y confirma que el cobro real sigue usando el monto
  original (`test_b_un_cambio_de_precio_del_plan_tras_emitir_la_factura_
  no_afecta_el_monto_cobrado`).

### 8. Recurring Billing

Ver la sección **RECURRING BILLING PATTERN** completa arriba — mismo
patrón, sin cambios en esta corrección. Resumen: la plataforma SaaS
sigue siendo la fuente de verdad de negocio (`Subscription`/
`SaaSInvoice`), el proveedor externo solo autoriza/ejecuta el cobro y
reporta su propio estado (espejo informativo, nunca una entrada a la
lógica de negocio); el proveedor decide el calendario, Budun reacciona
por evento; un fallo de cobro recurrente marca `PAST_DUE`, nunca
suspende directo; el proveedor reutiliza su propio mecanismo nativo de
reintentos si lo ofrece, nunca un scheduler propio en paralelo.

### 9. Payment Reconciliation

- **Problema**: conciliar "dinero recibido" contra "obligación
  pendiente" tiene más casos de los que un primer diseño suele cubrir:
  pago exacto, sobrepago, pago parcial, reembolso total, reembolso
  parcial.
- **Patrón**: un ledger append-only de dos niveles — `SaaSPayment`
  (dinero recibido) + `SaaSPaymentAllocation` (a qué factura se aplicó,
  cuánto) — nunca un campo `paid_amount` desnormalizado en la factura
  ni en el pago; el saldo se calcula siempre sumando el ledger.
- **Solución de esta corrección**: la reconciliación es SIMÉTRICA — así
  como `auto_apply_payment` aplica un pago nuevo a facturas abiertas,
  un reembolso ahora REVIERTE esa aplicación (reverso + reasignación
  del remanente, nunca una edición in-place) para que la factura vuelva
  a reflejar la realidad después de que el dinero salió.
- **Reglas**: una asignación (`SaaSPaymentAllocation`) nunca se edita
  in-place — una corrección real es SIEMPRE un reverso (`status=
  REVERSED`) más, si corresponde, una asignación nueva por el monto
  correcto.
- **Errores comunes**: implementar el camino "aplicar dinero a una
  factura" completo y dar por sentado que el camino inverso (reembolso)
  "ya funciona solo" porque ambos tocan el mismo ledger — son dos
  operaciones independientes que hay que implementar y probar por
  separado.
- **Prevención**: un test que reembolsa un pago que SÍ está aplicado a
  una factura real (no uno recién creado sin aplicar, que es el caso
  que las pruebas anteriores cubrían) — exactamente el gap que esta
  corrección encontró.

### 10. Idempotent Renewal Jobs

- **Problema**: un comando programado (cron) puede ejecutarse dos veces
  por error humano, o competir con un camino reactivo equivalente — sin
  una garantía real, ambos podrían duplicar el efecto.
- **Patrón**: la idempotencia real vive en una restricción de BASE DE
  DATOS (`UniqueConstraint`), nunca en "el comando no se ejecuta dos
  veces" ni en un lock aplicativo separado — cualquier camino que
  intente crear el mismo registro dos veces recibe un `IntegrityError`
  y se resuelve devolviendo el registro ya existente.
- **Solución**: `generate_invoice_for_subscription`/`issue_proration_
  charge_invoice` atrapan `IntegrityError` explícitamente y devuelven
  la fila existente — nunca dejan que la excepción se propague como un
  error real.
- **Reglas**: todo comando pensado para cron real (sin Celery/Redis en
  este proyecto) debe poder ejecutarse dos veces seguidas sin efecto
  adicional — verificado con un test, nunca solo argumentado.
- **Errores comunes**: confiar en un `.exists()` previo para decidir si
  crear una fila — dos procesos concurrentes pueden pasar esa
  comprobación a la vez (ventana de carrera real); solo el
  `UniqueConstraint` cierra la ventana de verdad.
- **Prevención**: `UpgradeProrationInvoiceConcurrencyTests`/
  `InvoiceGenerationConcurrencyTests` — dos hilos reales intentando
  crear el mismo registro a la vez, nunca solo una prueba secuencial
  que llama a la función dos veces en el mismo hilo.

### 11. Safe Cancellation

- **Problema**: cancelar una suscripción puede, si no se diseña con
  cuidado, borrar o corromper el historial que Super Admin/tenant
  necesitan consultar después, o dejar cobros futuros sueltos.
- **Patrón**: cancelar es una TRANSICIÓN DE ESTADO, nunca un borrado —
  el historial completo (facturas, pagos, allocations, notas de
  crédito, reembolsos) permanece intacto y consultable después de
  cancelar, para siempre. Cuando existe un proveedor externo con cobro
  autorizado, se cancela PRIMERO ahí (impide cualquier cobro futuro
  real) y DESPUÉS en Budun — nunca al revés, y nunca solo un lado
  asumiendo que el otro se entera solo.
- **Solución**: `cancel_subscription` soporta inmediata o "al finalizar
  el período" (`cancel_at_period_end`), nunca fuerza una sola semántica;
  `cancel_recurring_subscription` coordina ambos lados explícitamente,
  y si el lado del proveedor falla de forma transitoria, el lado de
  Budun se cancela igual (un tenant nunca debe quedar atrapado por un
  error externo al querer cancelar su propia cuenta).
- **Reglas**: cancelar una suscripción `PENDING` (nunca llegó a
  activarse) sigue siendo una cancelación válida — nunca un caso
  especial no contemplado.
- **Errores comunes**: asumir que cancelar significa "ya no hay nada
  más que hacer con esta suscripción" y dejar de reaccionar a eventos
  tardíos del proveedor (un cobro tardío/fuera de orden sobre una
  suscripción ya `CANCELLED` se registra como pago sin aplicar, nunca
  se descarta ni reactiva nada — ver "RECURRING BILLING PATTERN").
- **Prevención**: un test que cancela y luego simula un evento tardío
  del proveedor, confirmando que el estado cancelado nunca se revierte
  y que el dinero, si llega de todas formas, nunca se pierde.

## BANK TRANSFER & PAYMENT PROOF PATTERNS

Agregado durante "FASE DE CORRECCIÓN 4 — Transferencias, Comprobantes,
Verificación y Notificaciones" (ver `KNOWN_ISSUES.md` #134,
`DECISIONS.md` #114, `docs/billing.md` sección "Transferencia
bancaria"). Ocho patrones reutilizables para cualquier flujo futuro de
"pago manual verificado por un humano" (no solo transferencia bancaria
— el mismo esqueleto sirve para cheques, depósitos, criptomonedas
verificadas manualmente, etc.), cada uno con
Problema/Arquitectura/Solución/Estados/Seguridad/Concurrencia/Errores
comunes/Prevención.

### 1. Bank Transfer Payment Pattern

- **Problema**: un método de pago sin API de confirmación automática
  (nadie nos "avisa" que el dinero llegó) necesita un mecanismo
  completo de evidencia → verificación humana → aplicación, sin
  convertirse en una segunda fuente de verdad de Billing.
- **Arquitectura**: `PaymentProof` (evidencia declarada por el tenant)
  es un documento INTERMEDIO, nunca el pago en sí — el pago real
  (`SaaSPayment`) solo existe después de que un humano (Super Admin)
  confirma la evidencia. `BankAccount` (cuentas de PLATAFORMA, no de
  tenant) es el catálogo de destinos válidos.
- **Solución**: `submit_payment_proof` (tenant) → `approve_payment_
  proof`/`reject_payment_proof` (Super Admin) — dos servicios,
  responsabilidades separadas, ninguno duplica al otro.
- **Estados**: ver "Payment Proof Verification" abajo.
- **Seguridad**: el tenant nunca puede aprobarse a sí mismo (acción
  exclusiva `is_superuser`); el archivo nunca se sirve públicamente.
- **Concurrencia**: ver "Payment Verification Idempotency" abajo.
- **Errores comunes**: activar la suscripción/tenant directamente
  dentro de `submit_payment_proof` "para simplificar" — nunca: la
  activación es SIEMPRE una consecuencia de la APROBACIÓN, jamás de la
  sola existencia de un archivo subido.
- **Prevención**: un test explícito que sube un comprobante y verifica
  que la suscripción/tenant NO cambiaron de estado todavía.

### 2. Payment Proof Verification

- **Problema**: un comprobante de pago necesita un ciclo de vida propio
  (recibido → en revisión → resuelto) sin inventar un estado nuevo por
  cada matiz.
- **Arquitectura**: `PaymentProof.Status` — `SUBMITTED`/`UNDER_REVIEW`
  (dos sabores de "pendiente de revisión", ambos aceptan aprobar/
  rechazar — no hay necesidad de un tercer estado `PENDING_REVIEW`
  genérico), `APPROVED`/`REJECTED` (terminales), `REVERSED` (reservado
  para una reversión administrativa futura, sin disparador todavía).
- **Solución**: el Super Admin ve TODOS los metadatos declarados
  (monto, moneda, cuenta, banco de origen, referencia) Y el archivo
  real (ver "Private Financial Uploads") antes de decidir — nunca una
  decisión basada solo en metadatos sin poder verificar el documento.
- **Estados**: un campo `status` único de `TextChoices` — nunca un
  booleano `is_approved` + otro `is_rejected` (que permitiría el
  estado imposible "ambos true").
- **Seguridad**: `reviewed_by`/`reviewed_at` siempre se registran —
  nunca una aprobación/rechazo anónimo.
- **Concurrencia**: ver "Payment Verification Idempotency".
- **Errores comunes**: mostrar solo el nombre del archivo como texto
  plano sin ningún enlace para verlo — exactamente el hallazgo real de
  esta corrección (ver COMMON FAILURES abajo): el Super Admin decidía
  a ciegas.
- **Prevención**: un test que verifica que la vista de revisión
  Y la de descarga del archivo responden 200 con el contenido real.

### 3. Approval Workflow

- **Problema**: "aprobar" un comprobante en realidad dispara una cadena
  completa de efectos (pago → asignación → factura → suscripción →
  tenant) — hacerlo todo en la vista, o en el modelo, dispersaría esa
  lógica y la haría imposible de reutilizar/probar de forma aislada.
- **Arquitectura**: un único servicio (`approve_payment_proof`)
  orquesta TODA la cadena en una transacción — la vista solo llama al
  servicio y traduce el resultado/excepción a un mensaje.
- **Solución**: `PaymentProof` → `SaaSPayment` (CONFIRMED) →
  `auto_apply_payment` (ledger) → `_recompute_invoice_status` → (si
  corresponde) `activate_subscription`/`reactivate_subscription` →
  `Tenant.billing_status`. Cada paso reutiliza servicios YA existentes
  de otros dominios de Billing — nunca reimplementados aquí.
- **Estados**: el guard de entrada exige `SUBMITTED`/`UNDER_REVIEW` —
  aprobar algo ya `APPROVED` es un no-op idempotente; aprobar algo
  `REJECTED` es un error explícito (nunca "resucita" un rechazo).
- **Seguridad**: exclusivo `is_superuser`, nunca el catálogo de
  `apps.permissions` (que es tenant-scoped, no aplica a un recurso de
  plataforma).
- **Concurrencia**: `select_for_update()` sobre el propio
  `PaymentProof` serializa cualquier operación concurrente sobre el
  mismo comprobante (aprobar dos veces, aprobar+rechazar a la vez).
- **Errores comunes**: no envolver la llamada al servicio en un
  `try/except` en la vista — una transición inválida (comprobante ya
  resuelto por otra pestaña/hilo) produce un 500 sin manejar en vez de
  un mensaje claro (hallazgo real de esta corrección, ver COMMON
  FAILURES).
- **Prevención**: un test HTTP de extremo a extremo (no solo a nivel de
  servicio) que verifica el mensaje de error, no un código 500.

### 4. Rejection + Resubmission

- **Problema**: rechazar un pago no puede ser un callejón sin salida —
  el tenant necesita poder corregir y reenviar, pero el rechazo
  original nunca debe desaparecer ni volverse ambiguo con el reenvío.
- **Arquitectura**: cada envío es un `PaymentProof` NUEVO — nunca se
  edita ni se reutiliza el rechazado. El guard de "un comprobante
  pendiente a la vez" solo mira `SUBMITTED`/`UNDER_REVIEW`, así que un
  `REJECTED` deja de "bloquear" la factura automáticamente.
- **Solución**: `reject_payment_proof` guarda `rejection_reason`
  (texto libre, nunca un código cerrado que limite la explicación real)
  y notifica al tenant por correo con el motivo — la única vía real por
  la que el tenant se entera hoy (sin centro de notificaciones in-app).
- **Estados**: `REJECTED` es terminal para ESE `PaymentProof` — nunca
  transiciona a otro estado; el "reenvío" siempre crea una fila
  distinta con su propia máquina de estados desde cero.
- **Seguridad**: el motivo de rechazo nunca contiene información
  sensible de otro tenant (texto libre escrito por el propio Super
  Admin sobre ESTE comprobante).
- **Concurrencia**: dos reenvíos simultáneos para la misma factura se
  serializan por el mismo lock de "Payment Verification Idempotency".
- **Errores comunes**: permitir "reactivar"/"editar" un comprobante
  rechazado en vez de exigir uno nuevo — reintroduce ambigüedad sobre
  qué evidencia corresponde a qué intento de pago real.
- **Prevención**: un test que rechaza, reenvía, y verifica que EXISTEN
  DOS filas (`REJECTED` + `SUBMITTED`), nunca una sola editada.

### 5. Private Financial Uploads

- **Problema**: un comprobante de transferencia es un documento
  financiero sensible (puede contener datos bancarios del tenant) —
  nunca debe quedar accesible por URL adivinable ni servido como
  contenido estático público.
- **Arquitectura**: `MEDIA_ROOT="media-private/"` (fuera del árbol
  servido por `MEDIA_URL`), nombre de archivo en disco generado
  (`uuid4().hex`, nunca el original ni el ID secuencial), servido
  EXCLUSIVAMENTE por una vista protegida (`FileResponse`) que verifica
  pertenencia (tenant o `is_superuser`) antes de abrir el archivo —
  mismo patrón ya establecido por `apps.customers.
  _ContactDocumentDownloadView` desde FASE 9, reutilizado sin
  reinventar nada.
- **Solución**: dos vistas de descarga (una por tenant, filtrada por
  `tenant=request.tenant`; una para Super Admin, `all_objects` sin
  filtro de tenant) — nunca una sola vista con lógica condicional de
  permisos mezclada, mismo criterio de separación Portal/Super Admin
  de todo el proyecto.
- **Estados**: N/A (el archivo no tiene estados propios, solo el
  `PaymentProof` que lo referencia).
- **Seguridad**: validación de archivo (extensión + firma binaria +
  tamaño + lista negra, ver `apps.customers.file_validation`) ANTES de
  guardar nada; el nombre original solo se usa para MOSTRARSE (nunca
  para la ruta real en disco) — defensa contra path traversal.
- **Concurrencia**: N/A (lectura de archivo, sin escritura concurrente).
- **Errores comunes**: implementar el modelo/servicio de subida
  completo y olvidar la vista de DESCARGA — exactamente el hallazgo
  real más grave de esta corrección: `PaymentProof` funcionaba
  perfectamente de punta a punta, pero nadie podía ver el archivo
  jamás.
- **Prevención**: para todo modelo con un `FileField`/`ImageField`
  sensible, verificar explícitamente que existe una vista de descarga
  protegida — nunca asumir que "subir" implica "también se puede ver".

### 6. Payment Verification Idempotency

- **Problema**: verificar un pago manual involucra al menos dos
  actores humanos potencialmente concurrentes (el tenant reenviando,
  el Super Admin aprobando/rechazando) — sin las garantías correctas,
  un doble clic o dos pestañas pueden duplicar dinero o corromper el
  estado.
- **Arquitectura**: `select_for_update()` sobre la fila que la
  operación en curso NECESITA bloquear — la `SaaSInvoice` para "puedo
  aceptar un comprobante nuevo" (constraint entre FILAS distintas que
  todavía no existen, el clásico problema de "insert race"), el propio
  `PaymentProof` para "puedo transicionar este comprobante".
- **Solución**: nunca un `.exists()` desnudo como única defensa contra
  un duplicado — siempre dentro de un `transaction.atomic()` con el
  lock correcto tomado ANTES de la comprobación.
- **Estados**: cada guard de transición re-verifica el estado ACTUAL
  (post-lock) antes de escribir — un duplicado nunca es un error
  fatal, es un no-op idempotente o un rechazo claro, según corresponda.
- **Seguridad**: N/A (esto es integridad de datos, no autorización).
- **Concurrencia**: verificado con `TransactionTestCase` + hilos reales
  y `threading.Barrier` — nunca solo argumentado, siempre reproducido.
- **Errores comunes** (tres hallazgos reales de esta corrección): (1) el
  guard de "sin comprobante pendiente" en `submit_payment_proof` era un
  `.exists()` sin ningún lock — dos envíos concurrentes podían pasar la
  comprobación antes de que cualquiera comprometiera su fila. (2)
  `reject_payment_proof` no tenía ningún guard contra un comprobante ya
  `APPROVED` — la carrera "aprobar + rechazar a la vez" podía dejar un
  estado contradictorio. (3) `auto_apply_payment` calculaba su plan de
  asignación leyendo el saldo de cada factura SIN lock, y solo tomaba el
  lock real dentro de `apply_payment_to_invoices` — si otro método de
  pago totalmente independiente (transferencia aprobada vs. captura de
  PayPal sobre la MISMA factura, en hilos distintos) cubría la factura
  entre esas dos lecturas, `apply_payment_to_invoices` lanzaba
  `InvalidPaymentOperation` SIN atrapar, y como `auto_apply_payment`
  suele llamarse desde dentro de la transacción de OTRA operación (una
  captura de PayPal, un webhook), esa excepción revertía la transacción
  COMPLETA del llamador — deshaciendo incluso una captura de PayPal ya
  exitosa, solo porque una transferencia ganó la carrera por cubrir la
  misma factura.
- **Prevención**: para cada acción que "crea algo si no existe ya"
  sobre un recurso compartido, preguntar explícitamente "¿qué fila
  bloqueo para que dos intentos concurrentes se serialicen?" antes de
  escribir el `.exists()`/`.filter()` — nunca asumir que alcanza con
  comprobar antes de crear. Para una función que planifica una acción
  leyendo datos SIN lock y luego los aplica CON lock en otra función,
  preguntar explícitamente "¿qué pasa si el plan quedó obsoleto para
  cuando se aplica?" — la respuesta correcta casi nunca es "propagar la
  excepción tal cual" cuando la función existe precisamente para hacer
  "lo mejor posible" (best-effort) en nombre de OTRO llamador que no
  tiene por qué fallar por una carrera ajena y legítima.

### 7. Manual Payment → Billing State Transition

- **Problema**: un pago confirmado MANUALMENTE (por un humano, no por
  un webhook de proveedor) necesita disparar exactamente la misma
  cadena de transiciones que un pago automático — sin un camino
  paralelo que pueda divergir del automático con el tiempo.
- **Arquitectura**: `approve_payment_proof` reutiliza LITERALMENTE los
  mismos servicios que el camino de PayPal (`record_payment`/
  `auto_apply_payment`/`activate_subscription`/`reactivate_
  subscription`) — la única diferencia real es QUIÉN confirma el
  pago (un humano vs. un webhook), nunca QUÉ pasa después.
- **Solución**: la distinción `ACTIVATE != REACTIVATE` (ver "Activation
  vs Reactivation" arriba) se respeta IGUAL en el camino manual que en
  los automáticos — el estado de PARTIDA de la suscripción decide qué
  función llamar, nunca el método de pago usado.
- **Estados**: `PENDING_PAYMENT → proof submitted → SUBMITTED →
  APPROVED → Payment → Allocation → Invoice PAID → Subscription ACTIVE
  → Tenant ACTIVE` es la única cadena válida — nunca "upload →
  ACTIVE" directo.
- **Seguridad**: la confirmación manual exige `is_superuser`
  explícitamente — nunca se automatiza "para simplificar" (la
  verificación humana ES el control de seguridad de este método de
  pago, al no existir una API de confirmación del banco).
- **Concurrencia**: ver "Payment Verification Idempotency".
- **Errores comunes**: crear un camino de activación "simplificado"
  específico para pagos manuales que se salte pasos que el camino
  automático sí hace (p. ej. no restaurar el período al reactivar).
- **Prevención**: cada vez que se agrega un nuevo camino de
  confirmación de pago, auditar explícitamente contra los YA
  existentes — mismo criterio ya aplicado en "Activation vs
  Reactivation".

### 8. Multi-Currency Payment Validation

- **Problema**: sin un motor de conversión de divisas, aceptar un pago
  en una moneda y aplicarlo a una obligación en otra es, en el mejor
  caso, un error de cálculo silencioso, y en el peor, dinero perdido o
  inventado.
- **Arquitectura**: TRES puntos deben coincidir exactamente para un
  pago por transferencia — la moneda de la factura, la de la cuenta
  bancaria receptora, y la declarada por el tenant en el comprobante —
  nunca una conversión implícita entre ellas (mismo criterio ya
  establecido para Cuentas por Cobrar del ERP,
  `apps.sales.services.allocate_payment`, `docs/currency.md`).
- **Solución**: la validación vive en DOS capas — el punto de entrada
  (`submit_payment_proof`, falla rápido, antes de crear ningún
  registro) Y el núcleo del ledger (`apply_payment_to_invoices`/
  `auto_apply_payment`, nunca confía solo en que el punto de entrada
  ya validó) — defensa en profundidad real, no redundancia accidental.
- **Estados**: N/A (esto es una validación de datos, no una máquina de
  estados).
- **Seguridad**: N/A.
- **Concurrencia**: N/A (validación de datos, no de escritura
  concurrente).
- **Errores comunes**: validar la moneda solo contra la cuenta
  bancaria y asumir que eso implica que también coincide con la
  factura — hallazgo real de esta corrección: antes, una cuenta EUR
  real podía "pagar" una factura USD sin ningún rechazo, porque nunca
  se comparaban esas dos monedas entre sí directamente.
- **Prevención**: cuando existan N campos de moneda relacionados
  (factura, comprobante, cuenta, pago...), listarlos TODOS
  explícitamente y verificar que el código realmente compara cada par
  relevante — nunca asumir transitividad sin probarla ("si A quedó
  validado contra B, y B contra C, ¿alguien comparó A contra C?").

## GATE LOCAL SAAS PATTERNS (Corrección 5)

Agregado durante "FASE DE CORRECCIÓN 5 — Gate Local SaaS" (ver
`KNOWN_ISSUES.md` #135, `DECISIONS.md` #115). Tres patrones más,
encontrados auditando las INTERACCIONES entre subsistemas ya
individualmente correctos — el tipo de gap que solo aparece al revisar
cómo dos piezas correctas se combinan, nunca auditando cada una por
separado.

### 1. Cross-Surface Service Reuse for Coordinated Actions

- **Problema**: una operación de negocio "peligrosa si se hace a
  medias" (cancelar un pago recurrente externo Y el registro interno,
  en este orden) se resuelve UNA vez con la función correcta — pero
  nada garantiza que TODAS las superficies reales que exponen esa
  acción (Portal del tenant, Panel de Super Admin, un futuro API)
  terminen usándola.
- **Patrón**: la función coordinada (`recurring.cancel_recurring_
  subscription`) se diseña como un SUPERSET seguro de la función simple
  (`subscriptions.cancel_subscription`) — cuando la condición externa
  no aplica (nunca hubo cobro recurrente autorizado), se comporta
  IDÉNTICO a la simple. Esto permite que CUALQUIER llamador use siempre
  la coordinada sin necesitar lógica condicional propia para decidir
  cuál usar.
- **Solución real de esta corrección**: `recurring.cancel_recurring_
  subscription` ya existía, ya estaba probada, y ya seguía el patrón
  "Safe Cancellation" documentado desde la Corrección 3 — pero NINGUNA
  vista real (`CancelSubscriptionView` del Portal, `TenantDetailView`
  del Super Admin) la llamaba jamás; ambas llamaban a la función simple
  directo. El código "correcto" existía; el código REALMENTE
  ALCANZABLE desde la UI no lo usaba.
- **Reglas**: cuando una acción tiene una versión "coordinada" y una
  "simple", la simple debe quedar como un detalle de implementación
  INTERNO de la coordinada — nunca expuesta como una alternativa que un
  llamador nuevo pueda elegir por error.
- **Errores comunes**: auditar la función coordinada, confirmar que es
  correcta, y detenerse ahí — sin verificar `grep`-eando quién la llama
  realmente en producción (vistas, comandos, señales), no solo en
  pruebas unitarias.
- **Prevención**: para toda función que coordina múltiples sistemas
  (interno + externo), buscar EXPLÍCITAMENTE cada punto de entrada real
  de la acción que representa (cada vista, cada botón) y confirmar que
  TODOS pasan por la versión coordinada — nunca asumirlo por la
  existencia de la función ni por su cobertura de tests unitarios.

### 2. Coupon/Discount Expiration Enforcement

- **Problema**: una condición de vigencia con MÚLTIPLES componentes
  (un interruptor manual + un rango de fechas) puede validarse
  completa en el punto de ENTRADA (la primera vez que algo se aplica) y
  solo parcialmente en cada punto de RENOVACIÓN posterior.
- **Patrón**: una única función booleana de vigencia (`coupons.
  is_coupon_currently_valid`) que evalúa TODOS los componentes de la
  condición — reutilizada tanto en la generación de cada factura
  (`generate_invoice_for_subscription`) como en cualquier reporte que
  necesite saber si un descuento sigue aplicando (`reports.
  _mrr_de_suscripcion`).
- **Solución real de esta corrección**: antes, `generate_invoice_for_
  subscription` solo comprobaba `coupon.is_active` (el interruptor
  manual) en cada renovación — nunca `valid_from`/`valid_until` (las
  fechas) — así que un cupón de duración limitada seguía descontando
  indefinidamente después de su fecha de vencimiento real.
  `_mrr_de_suscripcion` tampoco aplicaba ningún descuento nunca,
  sobreestimando el ingreso recurrente reportado.
- **Reglas**: si una condición de vigencia tiene N componentes,
  CUALQUIER punto del código que decida "¿esto sigue vigente?" debe
  evaluar los N, nunca un subconjunto — y esa evaluación vive en UNA
  función reutilizada, nunca reimplementada en cada punto de uso.
- **Errores comunes**: validar la vigencia completa solo en el
  formulario/acción de aplicación INICIAL (donde el usuario ve un
  mensaje de error si falla) y olvidar que un valor ya persistido
  (`Subscription.coupon`) sigue leyéndose en cada ciclo posterior sin
  pasar por esa misma validación.
- **Prevención**: para cualquier campo que "engancha" una condición de
  negocio a un registro persistente (un cupón, una promoción, un
  descuento), preguntar explícitamente "¿en qué otros puntos del código
  se lee este campo después del momento en que se aplicó, y esos puntos
  revalidan la condición completa?".

### 3. Financial Event Notification Completeness

- **Problema**: un dominio de Billing con varios tipos de eventos
  financieros (pago, factura, nota de crédito, reembolso, cambio de
  estado) puede tener notificaciones bien construidas para ALGUNOS
  eventos y ninguna para otros, sin que ningún test lo detecte (las
  pruebas verifican el efecto en la base de datos, no necesariamente
  que se avisó a alguien).
- **Patrón**: una función de notificación por cada evento financiero
  que afecta directamente el dinero/saldo del tenant — nunca asumir que
  "ya se nota en el Portal" sustituye un aviso proactivo, sobre todo
  para eventos que el tenant no está mirando activamente cuando ocurren
  (una nota de crédito emitida, un reembolso completado).
- **Solución real de esta corrección**: `notify_credit_note_issued`/
  `notify_refund_completed` (nuevas, mismo patrón `_enviar`/
  `_tenant_owner_email` que el resto de `notifications.py`) — antes de
  esta corrección, emitir una nota de crédito o completar un reembolso
  no notificaba absolutamente nada al tenant.
- **Reglas**: toda función de servicio que representa un evento
  financiero real (dinero entra, sale, se acredita, se revierte) evalúa
  explícitamente "¿el tenant necesita enterarse de esto ahora, o le
  basta con verlo la próxima vez que entre?" — la respuesta correcta
  para "recibiste dinero/crédito/reembolso" casi siempre es notificar.
- **Errores comunes**: dar por completo un dominio de notificaciones
  revisando solo la lista de funciones YA escritas en `notifications.py`
  — sin comparar esa lista contra el catálogo REAL de eventos
  financieros del dominio (`apps.billing.models`) para encontrar los
  que nunca tuvieron una función dedicada.
- **Prevención**: mantener (aunque sea informalmente, en la
  documentación) una tabla de "evento financiero → notificación
  correspondiente" y revisarla explícitamente cada vez que se audita el
  dominio — nunca inferir cobertura completa de la sola existencia del
  módulo `notifications.py`.

## FINAL GATE LOCAL PATTERNS (Corrección 6 — última auditoría antes del cierre)

Agregado durante "FASE DE CORRECCIÓN 6 — Gate Local SaaS, última
auditoría funcional antes del cierre integral" (ver `KNOWN_ISSUES.md`
#136, `DECISIONS.md` #116). Dos patrones más, cada uno documentado con
el campo adicional pedido explícitamente para esta corrección —
**Aplicabilidad a futuros proyectos** — porque este Kit debe servir
como base para construir otros SaaS (incluidas plataformas de
préstamos u otros sistemas verticales), no solo para este proyecto.

### 1. Multi-Frequency Proration Normalization

- **Problema**: prorratear un cambio entre dos "planes" que se
  facturan en frecuencias distintas (mensual vs. anual, semanal vs.
  mensual, etc.) exige comparar dos precios que NO son directamente
  comparables entre sí sin normalizarlos primero a una unidad común.
- **Causa raíz**: la fórmula original normalizaba dividiendo AMBOS
  precios entre los días del período VIGENTE (el del plan que se
  abandona) — una simplificación válida solo cuando ambos planes
  comparten esa misma frecuencia; nadie se preguntó explícitamente
  "¿y si el formulario permite además cambiar la frecuencia al mismo
  tiempo?" al escribir la fórmula original.
- **Patrón**: cada precio se normaliza dividiéndolo entre los días
  NOMINALES de SU PROPIA frecuencia (no los del período vigente, no los
  de la frecuencia del otro plan) — el mismo catálogo de "días por
  frecuencia" que ya existe en el sistema para calcular períodos
  (nunca una segunda tabla de conversión).
- **Solución**: `valor_diario_X = precio_X / dias_nominales(frecuencia_X)`
  para cada uno de los dos precios por separado, ANTES de multiplicar
  por los días restantes del período que se abandona.
- **Reglas**: cualquier fórmula que compare dos "tarifas periódicas"
  debe declarar explícitamente en qué UNIDAD normaliza cada una, y esa
  unidad debe derivarse de la frecuencia de CADA tarifa individualmente
  — nunca asumir que ambas comparten la misma frecuencia solo porque
  eso fue cierto en los casos probados hasta ahora.
- **Errores comunes**: probar la fórmula solo con pares del mismo tipo
  (mensual→mensual, anual→anual) porque son los casos "obvios" de
  upgrade/downgrade, y nunca ejercitar el caso donde el formulario real
  permite ADEMÁS cambiar la frecuencia — el bug pasó 3 correcciones
  completas sin detectarse porque ningún test cruzaba frecuencias.
- **Prevención**: para cualquier formulario de "cambiar de X a otro X"
  donde X tiene un atributo variable (aquí, frecuencia), preguntar
  explícitamente "¿el formulario permite que ese atributo también
  cambie a la vez?", y si la respuesta es sí, escribir al menos un test
  que ejercite ese cambio combinado con un valor numérico fácil de
  verificar a mano.
- **Aplicabilidad a futuros proyectos**: cualquier dominio con
  "planes"/"tarifas"/"tasas" periódicas en más de una frecuencia
  (una plataforma de préstamos con cuotas semanales/quincenales/
  mensuales, un SaaS con planes mensuales/anuales/trimestrales) debe
  aplicar este mismo principio de normalización — nunca comparar dos
  tarifas periódicas directamente sin normalizar cada una a su propia
  unidad de tiempo nominal primero.

### 2. Best-Effort Sweep Resilience Under Concurrency

- **Problema**: una función de "barrido automático" (aplicar lo que se
  pueda de un recurso compartido — saldo de un pago, saldo de una nota
  de crédito — contra una lista de obligaciones abiertas) calcula su
  plan de acción leyendo datos SIN lock, y solo toma el lock real en el
  momento de aplicar cada paso individual — dejando una ventana real
  donde el plan calculado puede quedar obsoleto antes de ejecutarse.
- **Causa raíz**: el mismo patrón (leer sin lock para planificar, lockear
  solo para ejecutar) se implementó DOS veces en este proyecto
  (`payments.auto_apply_payment` en la Corrección 4,
  `credits.auto_apply_available_credit_notes` en la Corrección 3) sin
  que la primera corrección hiciera evidente que la segunda tenía
  exactamente el mismo problema — cada función se auditó de forma
  aislada, nunca comparándola contra otras funciones con la misma FORMA
  estructural.
- **Patrón**: toda función de "barrido best-effort" que se invoca desde
  DENTRO de la transacción de otra operación (una captura de pago, la
  generación de una factura) debe considerarse una función que "nunca
  debe fallar de forma que rompa a su llamador" — cualquier excepción
  de una carrera real en un paso individual se atrapa y el barrido
  continúa (o termina limpio), nunca se propaga hacia arriba.
- **Solución**: `try/except` alrededor de cada aplicación individual
  dentro del bucle del barrido, capturando específicamente la excepción
  de "ya no hay suficiente saldo/cupo" (nunca un `except Exception`
  genérico) — y, cuando sea barato hacerlo, refrescar el dato que causó
  el fallo (releer el saldo real) antes de continuar con el siguiente
  paso, para que el resto del barrido en la misma llamada aproveche lo
  que de verdad quede disponible.
- **Reglas**: un barrido best-effort NUNCA deja que el recurso se
  pierda — si un paso falla por una carrera, el recurso permanece
  disponible para el PRÓXIMO barrido (nunca se descarta, nunca se
  marca como "ya intentado y fallido" de forma permanente).
- **Errores comunes**: corregir esta clase de bug una vez y no volver a
  revisar el resto del código en busca de la MISMA forma estructural
  (leer-sin-lock-para-planificar + lockear-solo-para-ejecutar) en otras
  funciones — exactamente lo que pasó aquí: la Corrección 4 arregló
  `auto_apply_payment` sin que nadie buscara su gemelo estructural
  (`auto_apply_available_credit_notes`) hasta la Corrección 6.
- **Prevención**: cuando se corrija un bug de concurrencia con una
  FORMA reconocible (plan sin lock + ejecución con lock, en un bucle),
  buscar explícitamente (`grep` por la firma del problema: bucles que
  llaman a una función con su propio `transaction.atomic()`/
  `select_for_update()` interno) otras funciones del mismo dominio con
  la misma forma, en la MISMA corrección — nunca asumir que el problema
  era exclusivo de la función recién arreglada.
- **Aplicabilidad a futuros proyectos**: cualquier sistema financiero
  con más de un "ledger de saldo disponible" que se reparte
  automáticamente contra obligaciones abiertas (pagos anticipados,
  créditos, garantías, líneas de crédito parcialmente desembolsadas en
  una plataforma de préstamos) tendrá, casi con certeza, más de una
  función con esta misma forma — auditarlas TODAS juntas la primera vez
  que se encuentra una, en vez de una por una en correcciones separadas.

## SAAS VISUAL SHELL PATTERNS (FASE DE REDISEÑO VISUAL SaaS)

Cuatro patrones nuevos, esta vez de identidad visual/navegación en vez
de lógica financiera — nacen de la misma disciplina de auditoría real
antes de corregir que el resto de este Knowledge Kit.

### 1. SaaS Visual Shell Separation

- **Problema**: cuando una plataforma SaaS tiene DOS audiencias reales
  con necesidades completamente distintas — el cliente final operando
  su propio negocio (tenant) y el equipo que opera la plataforma
  (Super Admin) — reutilizar el mismo shell de navegación para ambas
  hace que cada una vea menús que no le pertenecen.
- **Causa raíz**: las plantillas de administración de plataforma se
  crearon extendiendo el mismo layout que ya existía (el del tenant),
  porque funcionaba y ya tenía sidebar/navbar/toasts resueltos — nadie
  se preguntó si ese sidebar debía mostrar los mismos enlaces para las
  dos audiencias.
- **Patrón**: un segundo shell (`layout_saas_admin.html`) que reutiliza
  la MISMA estructura de grid/JS del primero (mismo `.shell`, mismo
  `ui.js`, mismo mecanismo de colapso responsive) pero con su propio
  contenido de navegación — nunca un shell reescrito desde cero, y
  nunca condicionales `{% if es_super_admin %}` dentro de un único
  shell compartido (esa alternativa es más frágil: un enlace nuevo del
  ERP olvidado dentro del `{% if %}` equivocado vuelve a filtrar menús
  entre audiencias).
- **Solución**: cada superficie de plataforma (namespaces
  `billing_admin`/`billing_platform`) extiende el shell nuevo; la
  superficie que SÍ pertenece al tenant (`billing_portal`, el tenant
  viendo su propia facturación) se deja intencionalmente en el shell
  original — la regla no es "toda vista de Billing usa el shell nuevo",
  es "toda vista de PLATAFORMA usa el shell nuevo".
- **Reglas**: antes de crear una vista nueva de administración de
  plataforma, preguntar explícitamente a qué audiencia pertenece
  (tenant operando su negocio vs. equipo operando la plataforma) y
  elegir el shell según esa respuesta, nunca por conveniencia de copiar
  una plantilla existente.
- **Errores comunes**: verificar la separación solo mirando el CSS/HTML
  de una página aislada — el bug real solo es visible navegando o
  inspeccionando la respuesta HTTP completa de una vista de plataforma
  real (un test que busca la ausencia de textos exclusivos del otro
  shell, no solo la presencia de los propios, es la única forma de
  detectar una fuga real).
- **Prevención**: un test de "smoke de shell" por cada nueva superficie
  de plataforma que verifique tanto la PRESENCIA de la marca/menú
  propios como la AUSENCIA de textos exclusivos del shell del tenant.
- **Aplicabilidad a futuros proyectos**: cualquier SaaS con un panel de
  operación interna (soporte, ventas, finanzas) además del panel del
  cliente final — incluida una plataforma de préstamos con un panel de
  originación/cobranza interno separado del portal del prestatario —
  debe aplicar esta misma separación de shells desde el primer día,
  nunca como una fase de "pulido" posterior.

### 2. SaaS Design Token Pattern

- **Problema**: una identidad visual "azul + verde" documentada como
  regla fija (FASE 5) puede volverse inapropiada para una superficie
  nueva (una consola de operación de plataforma) sin que eso signifique
  que la decisión original estuviera mal para su contexto original (el
  ERP del tenant).
- **Causa raíz**: los tokens de color (`--color-primario`,
  `--color-secundario`) se definieron con roles genéricos
  ("primario"/"secundario") en vez de roles semánticos explícitos
  ("brand"/"success") — un color con rol "secundario" termina
  reutilizándose como si fuera parte de la identidad estructural en vez
  de reservarse para un significado semántico concreto.
- **Patrón**: mantener TODOS los tokens existentes (nunca romper una
  superficie que ya depende de ellos) y agregar tokens NUEVOS con un
  rol semántico explícito y acotado a la superficie nueva
  (`--color-saas-sidebar-*`), en vez de redefinir el significado de un
  token ya usado en producción.
- **Solución**: documentar explícitamente, por token, si su rol es
  brand/primary/success/warning/danger/info/neutral — y para la
  superficie nueva, usar SOLO azul+neutrales+semánticos, dejando verde
  reservado exclusivamente para éxito (nunca un botón "secundario"
  estructural verde en la superficie nueva).
- **Reglas**: verde (o cualquier color que solo debería significar
  "éxito"/"aprobado"/"positivo") nunca se usa como color estructural
  de marca/navegación — si una superficie necesita un segundo tono de
  marca, debe ser una variante del color primario (más oscura/clara),
  nunca el color de éxito.
- **Errores comunes**: eliminar o redefinir un token existente
  "para simplificar", sin verificar primero en cuántas plantillas ya
  vive ese token — romper silenciosamente una superficie que no forma
  parte del trabajo actual.
- **Prevención**: antes de tocar cualquier token de color existente,
  hacer un `grep` de su uso real en todo el proyecto (CSS y templates)
  y confirmar que ninguna superficie fuera de alcance depende de su
  significado actual.
- **Aplicabilidad a futuros proyectos**: cualquier proyecto con más de
  una superficie de usuario (portal de cliente vs. consola interna,
  o en una plataforma de préstamos: portal del prestatario vs. consola
  de originación/cobranza) debe decidir explícitamente, por superficie,
  si comparte identidad de marca o si cada una necesita su propia
  variante — y documentar esa decisión como aquí, no dejarla implícita.

### 3. SaaS Navigation Pattern

- **Problema**: una consola de administración con muchas secciones
  reales (aquí: Tenants, Clientes, Planes, Suscripciones, Facturas,
  Pagos, Transferencias, Notas de crédito, Reembolsos, Reportes,
  Configuración) necesita una navegación que escale, no una lista plana
  ni un menú de botones que solo aparece en una página.
- **Causa raíz**: la navegación se agregó incrementalmente, una sección
  a la vez, cada vez añadiendo "un botón más" a una fila que vivía
  únicamente en la página de inicio — nadie se detuvo a agruparla
  cuando pasó de 3 a 13 destinos.
- **Patrón**: sidebar vertical persistente (visible en TODAS las
  páginas de la superficie, vía el shell compartido, nunca duplicado
  por plantilla), agrupado por dominio de negocio real —nunca por orden
  de creación— y con el estado activo resuelto por
  `request.resolver_match` (mismo mecanismo que el sidebar del ERP,
  nunca un mecanismo nuevo).
- **Solución**: grupos derivados de los namespaces/URLs REALES
  existentes (nunca enlaces a una ruta que no existe todavía) — un
  grupo sin al menos un destino real no se crea solo para "llenar
  espacio".
- **Reglas**: cada nueva vista de administración debe agregarse al
  grupo del sidebar que le corresponde en el MISMO commit que la crea
  — un sidebar que se actualiza "después" es la forma más común de que
  una vista se vuelva inalcanzable salvo escribiendo la URL a mano.
- **Errores comunes**: agregar una acción de navegación solo en la
  página desde la que "tiene sentido" llegar hoy, en vez del sidebar
  persistente — funciona hasta que se agrega una segunda forma real de
  llegar a esa misma página y la navegación queda inconsistente.
- **Prevención**: un test que enumere TODOS los nombres de URL
  reales del namespace de administración y verifique que cada uno
  aparece enlazado desde el sidebar (o está documentado como
  intencionalmente no-listado, p. ej. una página de detalle).
- **Aplicabilidad a futuros proyectos**: cualquier consola
  administrativa que crecerá por fases (un back-office de préstamos con
  Solicitudes/Desembolsos/Cobranza/Mora/Reportes) debe adoptar desde el
  principio un sidebar agrupado por dominio con este mismo mecanismo de
  estado activo, en vez de una navegación ad-hoc que "ya se ordenará
  después".
- **Addendum (Revisión visual SaaS, Bloque B) — reutilización de una
  vista de detalle adyacente**: cuando un modelo B (aquí, `Subscription`)
  no tiene una página de detalle propia pero SIEMPRE pertenece 1:1 (o
  1:N con "el vigente" bien definido) a un modelo A que SÍ la tiene
  (aquí, `Tenant`), la vista de detalle de A ya es, en la práctica, el
  detalle real de B — la solución correcta es enlazar el listado de B
  hacia el detalle de A (agregando solo el campo id que falte al
  reporte, nunca lógica nueva), NUNCA construir una página de detalle
  nueva y duplicada para B. Invertir esta regla (crear SubscriptionDetail
  cuando TenantDetail ya muestra todo lo relevante de la suscripción
  vigente) sería exactamente el tipo de "segunda fuente de verdad"/
  funcionalidad duplicada que el proyecto evita en todo lo demás.

### 4. Human-readable SaaS Status Pattern

- **Problema**: un estado interno del dominio (`past_due`, `suspended`,
  `void`) es vocabulario de implementación — mostrarlo directo al
  usuario (o mostrarlo ya traducido pero sin ninguna señal visual de si
  es bueno o malo) le exige interpretar el sistema en vez de leerlo.
- **Causa raíz**: el texto SÍ estaba bien resuelto desde el modelo
  (`TextChoices` con labels en español reales, ver
  `Tenant.BillingStatus`/`Subscription.Status`/etc.) — el gap real
  estaba en el COLOR: cada badge de estado se renderizaba con la misma
  clase neutra sin importar el estado, porque nadie conectó el color al
  significado del estado de forma sistemática.
- **Patrón**: separar las dos responsabilidades — el TEXTO lo resuelve
  siempre `get_..._display()` (una sola fuente de verdad, nunca un
  texto duplicado a mano por plantilla) y el COLOR lo resuelve un único
  filtro de presentación (`estado_badge`) con un mapa código-crudo→color
  verificado contra los `TextChoices` reales de cada modelo del
  dominio.
- **Solución**: `{{ objeto.status|estado_badge }}` para la clase +
  `{{ objeto.get_status_display }}` para el texto, siempre juntos —
  nunca un estado visible sin las dos partes.
- **Reglas**: ningún estado interno (`.status`, `.billing_status`) se
  imprime crudo en una plantilla bajo ninguna circunstancia; un
  vocabulario externo ajeno al dominio (aquí, los códigos de la
  Subscriptions API de PayPal) se traduce con su PROPIO filtro
  (`estado_paypal`), nunca mezclado con el mapa de estados propios del
  dominio.
- **Errores comunes**: asumir que "el texto ya está en español" es
  suficiente y que el color es solo decoración — un estado urgente
  (pago atrasado, suscripción suspendida) sin ninguna señal de color es
  fácil de pasar por alto en una lista larga, incluso con el texto
  correcto.
- **Prevención**: al agregar un `TextChoices` nuevo a cualquier modelo
  del dominio, agregar en el MISMO commit su entrada correspondiente al
  mapa de `estado_badge` — un código no mapeado cae a "neutro" (nunca
  rompe el render), pero un test que enumere los `TextChoices` reales
  contra las claves del mapa detecta el olvido antes de que llegue a
  producción.
- **Aplicabilidad a futuros proyectos**: cualquier dominio con estados
  de ciclo de vida (una plataforma de préstamos con
  `pending`/`approved`/`disbursed`/`delinquent`/`written_off`/`paid_off`)
  debe aplicar este mismo patrón de dos fuentes de verdad separadas
  (texto desde el modelo, color desde un mapa único) desde el primer
  estado que se muestre a un usuario — nunca decidir el color caso por
  caso en cada plantilla.

## SaaS Visual Design Pattern (FASE DE REDISEÑO VISUAL SaaS 2.0)

Continuación directa de "SAAS VISUAL SHELL PATTERNS": una vez separado
el shell y establecida la identidad de color, este patrón cubre cómo
*elevar* ese sistema a un lenguaje visual premium consistente sin
tocar el ERP ni reescribir cada plantilla individualmente.

- **Problema**: un sistema de diseño puede tener los componentes
  correctos (shell separado, badges semánticos, botones consistentes)
  y aun así sentirse "genérico" o incompleto frente a una referencia
  visual real (un mockup aprobado) — faltan los detalles de
  refinamiento (iconografía, jerarquía tipográfica explícita,
  scrollbar, espaciado generoso) que hacen que una plataforma se
  sienta terminada y no una colección de componentes sueltos.
- **Causa raíz**: varios de estos detalles nunca se decidieron
  explícitamente porque nunca se necesitaron hasta que hubo una
  referencia visual concreta que compararlos — p. ej. `h1`/`h2`/`h3`
  nunca tuvieron un tamaño de fuente propio del sistema de diseño
  (dependían del tamaño por defecto del navegador), y el sidebar nunca
  tuvo iconos porque nadie los pidió hasta ahora.
- **Patrón**: refinar el sistema en la capa de COMPONENTES/TOKENS
  compartidos (`design-system.css`, un puñado de plantillas de shell),
  nunca vista por vista — cualquier plantilla que ya consume
  `.tarjeta`/`.kpi`/`.badge`/`.tabla` recibe el refinamiento
  automáticamente la próxima vez que se renderiza, sin tocar su propio
  archivo. Cuando el refinamiento es "de identidad" (tamaños de
  encabezado, espaciado del `.main`) y el selector es compartido con
  el ERP (`h1`, `h2`, `.main`), se acota con un modificador
  (`.shell--saas`) en vez de cambiar el selector global — el mismo
  principio ya usado para el color del sidebar en la fase anterior,
  aplicado ahora a la tipografía.
- **Solución**: (1) tipografía — escala explícita de tamaños
  (`--texto-*`) para `h1`/`h2`/`h3`, acotada a `.shell--saas`; (2)
  iconografía — emoji consistentes (mismo criterio ya usado en
  `estado-vacio__icono`/`kpi-grupo__titulo` desde fases anteriores,
  nunca una librería de iconos SVG/fuente nueva) en sidebar y KPIs;
  (3) scrollbar fina (`scrollbar-width: thin` + `::-webkit-scrollbar`)
  y `overflow-x: hidden` en `body` — estas dos SÍ se dejan globales
  (nunca acotadas a `.shell--saas`) porque son mejoras neutras de
  plataforma de navegador, no cambios de identidad visual, y benefician
  también al ERP sin alterarlo; (4) espaciado más generoso
  (`.shell--saas .main`) para la sensación "premium" pedida.
- **Reglas**: antes de decidir si un refinamiento va acotado o global,
  preguntar "¿esto cambia la IDENTIDAD visual (color, tipografía,
  layout) o es una mejora NEUTRA de plataforma (scrollbar, prevención
  de overflow)?" — la primera se acota con un modificador, la segunda
  puede aplicarse globalmente con una nota explícita documentando por
  qué se consideró segura.
- **Errores comunes**: sobre-corregir aplicando CADA refinamiento vista
  por vista (25 archivos) cuando el mismo resultado se logra con 3-4
  cambios en los componentes/shell compartidos — además de ser mucho
  más trabajo, introduce inconsistencias reales entre vistas que se
  tocaron y las que no.
- **Prevención**: antes de tocar una plantilla individual para un
  cambio "visual", preguntar primero si el mismo resultado se logra
  extendiendo la clase/componente ya compartido por todas — solo bajar
  a nivel de plantilla cuando el cambio es específico de ESA vista
  (un texto, un dato real).
- **Aplicabilidad a futuros proyectos**: cualquier plataforma que reciba
  una referencia visual aprobada (un mockup, una guía de marca) después
  de que el sistema base ya existe debe traducir esa referencia a
  tokens/componentes primero, y aplicarla como una actualización de
  la capa compartida — nunca como 20+ ediciones de plantilla
  individuales que terminan divergiendo entre sí con el tiempo.

## Conditional Severity Indicator Pattern (Revisión visual SaaS, Bloque A)

- **Problema**: un indicador visual de severidad (color de advertencia
  o peligro en un KPI/badge) que se aplica de forma INCONDICIONAL —
  sin importar si el valor real es 0 — muestra una señal de alarma
  falsa constantemente, entrenando al usuario a ignorarla (la clásica
  "fatiga de alertas").
- **Causa raíz**: al construir un panel de KPIs con varias métricas de
  "problema" (pagos atrasados, suspensiones, cancelaciones), es fácil
  fijar el color de severidad de cada tarjeta como parte de su
  definición estática, en vez de derivarlo del valor real que esa
  tarjeta va a mostrar — el propio dashboard de esta plataforma tenía
  2 KPIs ya condicionales (Transferencias pendientes, Facturas
  vencidas) y 3 sin condicionar (Pagos atrasados, Suspendidas,
  Cancelaciones este mes), una inconsistencia real dentro de la MISMA
  pantalla que nadie había notado.
- **Patrón**: separar el CONTEO (siempre se muestra, sea 0 o no) del
  COLOR DE SEVERIDAD (solo se aplica cuando el conteo indica un
  problema real) — `{% if resumen.valor %}kpi--advertencia{% endif %}`,
  nunca la clase fija.
- **Solución**: para cada indicador que representa "algo va mal si
  este número es mayor que 0", la clase de color se calcula desde el
  valor, nunca se asigna en la plantilla como si fuera parte fija del
  diseño de esa tarjeta.
- **Reglas**: distinguir dos categorías de KPI antes de decidir el
  color: "indicador de problema" (0 = bien, código neutro; >0 = alerta,
  color condicional) vs. "indicador de crecimiento/categoría" (ingresos,
  suscripciones activas — el color puede ser fijo porque representa la
  categoría del dato, no un juicio sobre si el valor actual es bueno o
  malo).
- **Errores comunes**: copiar y pegar el modificador de color de un KPI
  ya existente al crear uno nuevo sin verificar si ese KPI en concreto
  debería ser condicional — así fue exactamente como surgió la
  inconsistencia real encontrada aquí.
- **Prevención**: al agregar cualquier KPI/badge de "problema" nuevo,
  preguntar explícitamente "¿este color debe desaparecer cuando el
  valor sea 0?" antes de fijar la clase.
- **Aplicabilidad a futuros proyectos**: cualquier dashboard con
  indicadores de "cosas que requieren atención" (una plataforma de
  préstamos con "cuotas vencidas", "solicitudes rechazadas",
  "clientes en mora") debe aplicar este mismo criterio — el color de
  alarma se deriva siempre del valor real, nunca se fija como parte
  del diseño estático de la tarjeta.

## SaaS Master Visual Language Patterns (FASE — Rediseño Visual Maestro)

Cuatro patrones nuevos a partir de la implementación del Design System
SaaS basado en una imagen de referencia maestra — la primera vez que
este proyecto trabaja desde una referencia visual concreta en vez de
una descripción textual.

### 1. Inline SVG Icon System (sin dependencia externa)

- **Problema**: la interfaz necesitaba iconografía consistente
  (sidebar, KPI, estados vacíos) pero el proyecto no tenía ningún
  sistema de iconos — solo emoji, explícitamente rechazados por no
  transmitir una identidad de "producto SaaS comercial" profesional.
- **Causa raíz**: nunca se necesitó iconografía real hasta que una
  referencia visual concreta la exigió — el emoji era la opción "cero
  esfuerzo" disponible desde el primer día del shell SaaS.
- **Patrón**: un pequeño diccionario Python de trazos SVG (24×24,
  outline, `stroke="currentColor"`) servido por un `simple_tag` de
  Django (`{% icono "home" %}`) — el HTML final es un `<svg>` inline,
  nunca una petición de red, un sprite externo ni una fuente de
  iconos.
- **Solución**: `apps/core/templatetags/ui_icons.py`, un solo
  diccionario `_ICONOS` (nombre → contenido interior del `<svg>`) y
  una función `icono()` que arma el `<svg>` completo con los atributos
  comunes (`viewBox`, `stroke-width`, accesibilidad) una sola vez.
- **Reglas**: nunca instalar una librería de iconos (Font Awesome,
  Feather-as-a-package, un sprite SVG externo) mientras el catálogo
  necesario siga siendo pequeño (aquí, ~25 iconos) — CLAUDE.md exige
  justificar cualquier dependencia nueva, y un diccionario de 25
  entradas no la justifica. Cada icono decorativo (acompañado de texto
  visible) es `aria-hidden="true"`; un icono que es el ÚNICO contenido
  de un control usa `titulo=` para un `<title>` accesible real.
- **Errores comunes**: usar un símbolo tipográfico Unicode (✓, →, ×)
  como si fuera parte del "sistema de iconos" — son texto, no iconos,
  y está bien seguir usándolos como texto (ver "Ver todas →", "←
  Volver") mientras no se confundan con la iconografía SVG real.
- **Prevención**: antes de agregar un icono nuevo, revisar primero si
  ya existe uno semánticamente equivalente en `_ICONOS` — nunca crear
  una entrada casi duplicada (dos variantes del mismo concepto) solo
  porque el trazo exacto no coincide pixel a pixel con la referencia.
- **Aplicabilidad a futuros proyectos**: cualquier plataforma con un
  presupuesto de iconos moderado (decenas, no cientos) puede evitar
  una dependencia de iconos externa por completo con este mismo
  patrón — reservar una librería real solo cuando el catálogo
  necesario crezca a un tamaño que un diccionario a mano ya no pueda
  mantener cómodamente.

### 2. Component Namespace Isolation (prefijo `saas-`)

- **Problema**: el dashboard necesitaba un componente de KPI card
  completamente distinto (icono circular, tendencia) del `.kpi`/
  `.kpi-grid` ya existente — pero `.kpi` resultó estar en uso activo
  en TODO el ERP (dashboard, detalle de producto, POS, ventas,
  compras), no solo en el dashboard SaaS como se asumía inicialmente.
- **Causa raíz**: nunca se había necesitado verificar el alcance real
  de un componente "genérico" del Design System antes de esta fase —
  ninguna corrección visual anterior había necesitado reescribir uno.
- **Patrón**: cuando un componente compartido necesita una versión
  visualmente distinta para UNA superficie, se crea un componente
  NUEVO con un prefijo de espacio de nombres (`saas-kpi-card`, nunca
  `kpi-card-v2`/`kpi-nuevo`) — el componente compartido original
  permanece exactamente igual, para siempre, mientras algo más lo siga
  usando.
- **Solución**: `grep` del nombre de clase en TODO el proyecto (no
  solo `apps/billing`) antes de decidir si modificar un componente
  existente o crear uno nuevo — la regla operativa: si aparece en un
  template fuera de la superficie que se está rediseñando, se crea un
  componente nuevo, sin excepción.
- **Reglas**: todo componente nuevo exclusivo de la plataforma SaaS
  lleva el prefijo `saas-` (`saas-kpi-card`, `saas-dona`,
  `saas-linea-chart`, `saas-actividad-item`) — nunca reutilizar el
  nombre corto de un componente ya existente aunque el nuevo se sienta
  como "la versión mejorada" de aquel.
- **Errores comunes**: asumir que un componente vive "solo en el
  dashboard" porque es ahí donde se lo está mirando en este momento —
  la verificación real es siempre un `grep`, nunca una suposición
  basada en dónde se originó el componente.
- **Prevención**: antes de MODIFICAR (no crear) cualquier clase CSS ya
  documentada como parte del Design System base (FASE 5/7), buscar su
  uso en todo el proyecto — el mismo hábito que ya se aplicaba a nivel
  de plantilla (`layout_app.html` nunca se toca) debe aplicarse
  también a nivel de clase CSS individual.
- **Aplicabilidad a futuros proyectos**: cualquier proyecto con más de
  una superficie de producto compartiendo un Design System base
  (portal de cliente + panel interno, app móvil + web) debe adoptar un
  prefijo de espacio de nombres por superficie desde el principio —
  mucho más barato que descubrir la colisión después de que ambas
  superficies ya dependen del mismo nombre de clase.

### 3. Real-Data Chart Rendering Without a Charting Library

- **Problema**: la referencia visual pedía una gráfica de línea
  (ingresos) y una de dona (estado de suscripciones) — sin ninguna
  librería de gráficas ya presente en el proyecto, y CLAUDE.md exige
  no introducir una sin necesidad real.
- **Causa raíz**: dos gráficas simples (6 puntos, ≤6 segmentos) no
  justifican el peso de una librería completa (Chart.js/D3) — el caso
  de uso real es mucho más pequeño que el problema que esas librerías
  resuelven.
- **Patrón**: SVG inline con la geometría calculada en Python
  (`apps/core/templatetags/ui_charts.py`), nunca en JavaScript ni en
  el propio template — Django ya sabe hacer aritmética de coordenadas
  mejor que un template de por sí limitado para eso. La dona reutiliza
  literalmente el mismo mapa de color semántico que los badges
  (`estado_badge`), nunca una paleta paralela.
- **Solución**: dos `simple_tag` puros (`linea_chart_datos`,
  `dona_chart_segmentos`) que reciben datos YA agregados por
  `apps.billing.services.reports` (nunca consultan la base de datos
  ellos mismos — separación estricta entre "de dónde viene el dato" y
  "cómo se dibuja") y devuelven coordenadas/arcos listos para
  interpolar en el SVG.
- **Reglas**: un helper de geometría de gráfica nunca decide QUÉ datos
  mostrar (eso es responsabilidad exclusiva del servicio de reportes)
  — solo CÓMO posicionarlos. Un mes sin actividad aparece con valor 0
  en la gráfica, nunca se omite (el punto debe existir para que la
  línea no se distorsione).
- **Errores comunes**: intentar hacer la aritmética de escalado
  (mín/máx/normalización) dentro del propio template de Django — los
  templates no tienen operadores aritméticos completos, y forzarlo
  lleva a lógica de presentación duplicada y difícil de probar.
- **Prevención**: cualquier gráfica nueva que se necesite en el
  futuro, evaluar primero si su complejidad real (número de series,
  interactividad necesaria) sigue estando por debajo del punto donde
  una librería se vuelve la opción más simple — y documentar esa
  evaluación explícitamente si se decide agregar una.
- **Aplicabilidad a futuros proyectos**: cualquier dashboard con un
  puñado de gráficas simples y bien definidas (línea de tendencia,
  dona de distribución, barras comparativas) puede evitar una
  dependencia de gráficas completa con este mismo patrón — reservarla
  para cuando se necesite algo que SVG a mano ya no pueda resolver
  razonablemente (zoom, tooltips interactivos ricos, series grandes).

### 4. Honest Trend Indicators (nunca fabricar una comparación)

- **Problema**: la referencia visual muestra una flecha ↑/↓ con
  porcentaje "vs. mes anterior" en cada KPI — pero varias métricas del
  panel (MRR, suscripciones activas, pagos atrasados) son fotografías
  de un instante (el valor ahora mismo), no flujos con un "mes
  anterior" real y reconstruible sin una tabla de historial dedicada.
- **Causa raíz**: la tentación real frente a una referencia visual
  detallada es replicar CADA elemento visible, incluso cuando el dato
  real que lo alimentaría no existe todavía — CLAUDE.md y esta fase
  son explícitos: la imagen define el lenguaje visual, nunca los
  datos.
- **Patrón**: distinguir explícitamente "métrica de flujo" (tiene un
  valor real para "el mes pasado", agregable sobre un rango de
  fechas — altas, cancelaciones, ingresos, reembolsos, notas de
  crédito) de "métrica de estado" (una foto del ahora, sin historial
  reconstruible sin una tabla de snapshots que no existe — MRR/ARR,
  activas, atrasadas, suspendidas, transferencias pendientes,
  facturas vencidas). Solo las primeras muestran tendencia.
- **Solución**: `_variacion_porcentual(actual, anterior)` devuelve
  `None` (nunca 0 ni un string vacío) cuando no hay base real de
  comparación; la plantilla omite la línea de tendencia por completo
  ante `None` — nunca renderiza un "0%"/"sin cambios" fabricado.
  Cuando SÍ hay un valor real de 0% (se comparó y de verdad no hubo
  cambio), eso sí se muestra, porque es un hecho real, no inventado.
- **Reglas**: ninguna KPI card muestra una tendencia a menos que exista
  una función real que calcule esa comparación específica — "se ve
  vacío sin la tercera línea" nunca es razón suficiente para inventar
  un número.
- **Errores comunes**: rellenar con "— sin cambios" cualquier métrica
  sin tendencia calculada, asumiendo que es una forma "neutra" de
  completar el diseño — sigue siendo una afirmación falsa (dice "lo
  comparamos y no cambió" cuando en realidad nunca se comparó nada).
- **Prevención**: al conectar cualquier elemento visual de la
  referencia a datos reales, preguntar explícitamente "¿existe hoy una
  consulta real que produzca este número, o lo estoy completando para
  que se parezca a la imagen?" — si la respuesta es la segunda, se
  omite el elemento (o se dice explícitamente que está preparado pero
  no conectado, como el buscador del navbar) en vez de inventarlo.
- **Aplicabilidad a futuros proyectos**: cualquier dashboard que
  muestre indicadores de tendencia debe clasificar cada métrica como
  "flujo" o "estado" antes de decidir si puede llevar una comparación
  — una plataforma de préstamos podría comparar "desembolsos este
  mes" (flujo, real) pero no "cartera vigente ahora mismo" (estado,
  sin snapshot histórico) sin construir antes una tabla de snapshots
  dedicada.

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
- **#113**: reactivar una suscripción con el período ya vencido le da
  un período NUEVO a partir de HOY (nunca reanuda el vencido, que
  facturaría retroactivamente tiempo bloqueado). El cargo de un upgrade
  se cobra con una factura inmediata y separada, en vez de esperar a la
  renovación siguiente (evitaba sistemáticamente cobrar el resto del
  período actual al precio nuevo). Un reembolso `PENDING` cuenta como
  monto comprometido para el guard de sobre-reembolso (no solo los
  `COMPLETED`) — cierra una ventana de doble-solicitud concurrente. La
  nota de crédito de un downgrade se aplica automáticamente a la
  próxima factura (no existe ninguna pantalla manual para eso, así que
  dejarlo manual equivalía a nunca aplicarla). `EXPIRED` se deja sin
  disparador explícitamente — existe en el enum pero ningún flujo real
  lo pide todavía.
- **#114**: la moneda de una transferencia debe coincidir EXACTAMENTE
  con la factura Y con la cuenta receptora (nunca conversión implícita,
  mismo criterio ya usado en Cuentas por Cobrar del ERP) — validado en
  dos capas (punto de entrada + núcleo del ledger), nunca solo una. Las
  dos nuevas vistas de descarga de comprobante (Portal/Super Admin) se
  implementaron como vistas SEPARADAS, nunca una sola con lógica
  condicional de permisos — mismo criterio de separación Portal/Super
  Admin ya aplicado en todo `apps.billing`. El guard de "sin
  comprobante pendiente" se movió detrás de un `select_for_update()`
  sobre la `SaaSInvoice` (no sobre `PaymentProof`, que todavía no
  existe en el momento de la comprobación) — el mismo patrón ya usado
  por `create_checkout_for_invoice` para el problema equivalente del
  lado de PayPal. Se descartó agregar un nuevo estado `PENDING_REVIEW`
  explícito: `SUBMITTED`/`UNDER_REVIEW` ya cubren exactamente ese
  significado, y el enum ya lo distingue de los estados terminales.
- **#115** (FASE DE CORRECCIÓN 5 — Gate Local SaaS, ver `KNOWN_ISSUES.md`
  #135): `cancel_recurring_subscription` se convirtió en el ÚNICO
  camino real de cancelación desde las vistas (Portal y Super Admin) —
  se descartó mantener `cancel_subscription` como opción alternativa en
  algún caso, precisamente porque es un superset seguro y no hay ningún
  escenario real donde la versión simple sea preferible desde una
  vista. El reembolso automático de un cobro recurrente de PayPal vía
  API se deja explícitamente SIN construir (requeriría un método nuevo
  del provider, `POST /v1/payments/sale/{sale_id}/refund` de la API de
  Pagos clásica) — el camino manual ya existente (`complete_manual_
  refund`) cubre el caso real sin necesitar esa decisión arquitectónica
  todavía; documentado como pendiente real, no como omisión silenciosa.
- **#116** (FASE DE CORRECCIÓN 6 — Gate Local SaaS, última auditoría
  antes del cierre, ver `KNOWN_ISSUES.md` #136): el prorrateo normaliza
  cada precio con los días nominales de SU PROPIA frecuencia
  (reutilizando `_DIAS_POR_FRECUENCIA`) en vez de "convertir" un precio
  a un equivalente en la otra frecuencia antes de comparar — misma
  matemática, más simple de leer y de auditar. `días_restantes` se
  mantiene sobre el período vigente que se abandona, nunca sobre el
  nuevo. La corrección de concurrencia de `auto_apply_available_
  credit_notes` reutiliza el mismo criterio ya decidido para
  `auto_apply_payment` (Corrección 4) — capturar y continuar, nunca
  propagar — con la mejora de refrescar el saldo disponible tras cada
  fallo para que el resto del barrido en la misma llamada aproveche lo
  que de verdad queda.
- **#117** (FASE DE REDISEÑO VISUAL SaaS, ver `KNOWN_ISSUES.md` #137):
  shell nuevo y separado (`layout_saas_admin.html`) en vez de
  parametrizar el shell del ERP — estructuralmente imposible que un
  cambio futuro filtre menús entre audiencias. Identidad azul+neutrales
  para la plataforma (verde reservado a éxito), decisión explícita del
  usuario que NO se propaga al ERP existente. Color de estado resuelto
  por un único mapa (`estado_badge`), nunca una clase condicional por
  plantilla. `BankAccount` gana editar+desactivar, nunca un botón
  "Eliminar" (protegida por `on_delete=PROTECT` desde FASE 17). Los
  `style=` inline se reemplazan por un conjunto pequeño y cerrado de
  utilidades CSS, nunca un framework de utilidades completo.
- **#118** (FASE — REDISEÑO VISUAL INTEGRAL SaaS 2.0, ver
  `KNOWN_ISSUES.md` #138): refinamientos de identidad (tipografía de
  encabezados, espaciado del `.main`) acotados a `.shell--saas`,
  siguiendo al pie de la letra la instrucción explícita de crear una
  variante SaaS específica en vez de asumir que un cambio al selector
  global era "seguro" para el ERP. Scrollbar fina y `overflow-x:
  hidden` SÍ se dejan globales, documentado explícitamente como la
  excepción (mejora neutra de plataforma, no de identidad). Iconos con
  emoji, nunca una librería SVG/fuente de iconos nueva. Sin tipografía
  de Google Fonts — la pila `system-ui` ya es moderna y no introduce
  una dependencia de red nueva sin aprobación explícita.

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
- 228 tests en verde NO significan que el ciclo de vida completo esté
  conectado — cada corrección anterior probó su propio camino nuevo
  correctamente, pero ninguna volvió a probar los caminos YA existentes
  con el estado de partida que su propio cambio hacía posible por
  primera vez (un pago confirmándose sobre una suscripción `SUSPENDED`,
  no solo `PENDING`). Una auditoría de "¿todos los caminos hacia esta
  función usan la función correcta?" (`grep` de cada llamador real,
  nunca solo releer la función en sí) encontró 3 de los 6 gaps de esta
  corrección.
- Un guard de concurrencia que solo cuenta filas en un estado TERMINAL
  (`COMPLETED`) dentro de una tabla cuyo primer estado real es
  intermedio (`PENDING`) tiene una ventana real: dos solicitudes que
  todavía no llegaron al estado terminal se ven ambas como "no cuentan
  todavía" — el `select_for_update()` sobre la fila padre (aquí,
  `SaaSPayment`) serializa el ORDEN de ejecución, pero no arregla un
  cálculo que ignora los intentos ya en curso. La corrección fue sumar
  también el estado intermedio al cálculo, nunca cambiar el mecanismo
  de lock (que ya era correcto).
- Cuando dos operaciones "terminan en el mismo lugar" (mismo campo,
  mismo valor final), la pregunta correcta nunca es "¿puedo reutilizar
  la más simple de las dos?" sino "¿desde qué estado de PARTIDA se
  permite llegar aquí, y qué garantías adicionales (auditoría,
  notificación, restauración de estado relacionado) solo tiene la
  función más específica?".
- Un modelo puede estar "completo" en su servicio de escritura (crear,
  aprobar, rechazar, todas las validaciones correctas) y aun así ser
  COMPLETAMENTE inútil en la práctica si nadie construyó la vía de
  LECTURA correspondiente — un `FileField` sensible sin ninguna vista
  de descarga es la forma más severa de este gap, porque el flujo
  "funciona" de punta a punta en las pruebas (que llaman al servicio
  directamente) sin que nadie note que la UI real nunca expuso el
  archivo. Antes de dar por completo un dominio con archivos adjuntos,
  preguntar explícitamente "¿cómo se ve/descarga esto después de
  subirlo?", nunca asumir que "se guarda" implica "se puede consultar".
- Un guard de "no permitir un duplicado" implementado como
  `.filter(...).exists()` sin ningún `select_for_update()` es
  correcto para el caso SECUENCIAL (dos llamadas una tras otra) pero
  tiene una ventana de carrera real para el caso CONCURRENTE (dos
  llamadas literalmente al mismo tiempo) — los tests secuenciales
  (`TestCase`, sin hilos) nunca la detectan; hace falta una prueba de
  concurrencia real (`TransactionTestCase` + hilos) para exponerla.
- Un formulario que ofrece "elegir cualquier valor vigente de X" (aquí,
  cualquier `PlanVersion` actual) hereda implícitamente TODAS las
  combinaciones posibles del atributo variable de X (aquí, la
  frecuencia) — una fórmula escrita pensando solo en el caso "obvio"
  (mismo tipo de X) puede llevar 3 correcciones completas sin que nadie
  note que también acepta silenciosamente el caso cruzado.
- Cuando se corrige un bug de concurrencia con una FORMA reconocible
  (planificar sin lock + ejecutar con lock, dentro de un bucle), esa
  MISMA forma puede repetirse en otras funciones del mismo dominio que
  nadie volvió a mirar — corregir una instancia no garantiza que se
  haya buscado su gemela estructural en el resto del código.
- Copiar un shell/layout existente para una superficie nueva porque "ya
  funciona" es exactamente cómo dos audiencias con necesidades
  distintas terminan compartiendo la misma navegación — la pregunta
  correcta antes de copiar un layout no es "¿renderiza bien?" sino
  "¿a quién le pertenece este menú?".
- Un texto de estado ya traducido correctamente (`get_..._display()`
  con labels en español reales desde el modelo) puede seguir siendo un
  gap de UX real si nunca se le asocia una señal de color — el texto
  resuelve el idioma, el color resuelve la urgencia, y son dos
  responsabilidades distintas que hay que verificar por separado.
- Un modelo con `on_delete=PROTECT` en sus relaciones inversas ya tomó
  la decisión de "nunca borrado físico" en el momento en que se
  diseñó — cuando la UI llega después a esa misma entidad, la pregunta
  no es "¿cómo implemento eliminar?" sino "¿qué patrón ya eligió el
  modelo?", y la respuesta correcta suele ser activar/desactivar, no
  un manejo de excepción alrededor de un borrado que se sabe de
  antemano que puede fallar.
- Un selector CSS "global" (`h1`, `.main`) compartido entre dos
  superficies con identidades distintas (ERP y SaaS) es exactamente el
  tipo de cambio donde "probablemente sea seguro" no es suficiente —
  la regla explícita de crear una variante acotada (`.shell--saas`)
  cuando existe riesgo, en vez de decidir unilateralmente que el
  cambio es inofensivo, es la que hay que seguir incluso cuando el
  cambio parece trivial (un tamaño de fuente menor rara vez rompe un
  layout, pero "rara vez" no es "nunca").
- No todo refinamiento visual nuevo necesita acotarse por shell:
  cuando el cambio es una mejora neutra de plataforma/navegador
  (scrollbar, prevención de overflow horizontal) que no altera ninguna
  identidad visual, aplicarlo globalmente es correcto y más simple —
  la clave es distinguir explícitamente "cambio de identidad" de
  "mejora neutra" antes de decidir el alcance, nunca por defecto
  acotar (o generalizar) todo por igual.
- Una vista puede pasar un `ModelForm` ya validado al contexto de la
  plantilla (`context["version_form"] = PlanVersionForm()`) y la
  plantilla puede simplemente IGNORARLO, usando `<input>`/`<select>`
  sueltos con los mismos `name=` — el POST sigue funcionando (los
  nombres de campo coinciden) así que nada se rompe funcionalmente,
  pero se pierden los labels/help_text/errores por campo que el form
  ya sabía renderizar. Auditar un formulario no es solo mirar la
  plantilla: hay que confirmar que la plantilla REALMENTE usa el form
  que la vista le da, no solo que el nombre del campo coincide.

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
- **Síntoma**: aprobar un comprobante de transferencia (o confirmar un
  cobro de PayPal, único o recurrente) sobre una suscripción
  `SUSPENDED`/`PAST_DUE` la reactivaba correctamente en apariencia
  (`status` volvía a `ACTIVE`), pero el período seguía siendo el
  vencido de antes de la suspensión. → **Causa real**: los tres caminos
  automáticos de confirmación de pago llamaban a `activate_subscription`
  (el primitivo de activación INICIAL) en vez de `reactivate_
  subscription` — funcionalmente parecido (mismo campo, mismo valor
  final) pero sin la lógica de restauración de período que solo vive en
  la segunda función. → **Corrección**: los tres caminos ahora
  distinguen el estado de partida (`PENDING` → activar; `PAST_DUE`/
  `SUSPENDED` → reactivar) y `reactivate_subscription` restaura el
  período cuando ya venció.
- **Síntoma**: un upgrade de plan a mitad de período nunca aparecía
  cobrado en ningún lado — ni una factura nueva, ni una línea en la
  siguiente, solo un registro en el `metadata` de auditoría. → **Causa
  real**: `change_plan` solo tenía una rama para el caso "hay que
  acreditar" (downgrade); el caso "hay que cobrar" (upgrade) nunca se
  implementó, pese a que el propio docstring de la función lo prometía.
  → **Corrección**: `issue_proration_charge_invoice` emite una factura
  inmediata y separada por el cargo exacto.
- **Síntoma**: una nota de crédito emitida por un downgrade nunca se
  veía reflejada en ninguna factura futura, ni automática ni
  manualmente (no existe ninguna pantalla para "aplicar" una). → **Causa
  real**: `apply_credit_note_to_invoice` existía desde FASE 17 pero
  ningún llamador real (vista o proceso automático) la invocaba —
  código completamente alcanzable solo desde pruebas. → **Corrección**:
  `auto_apply_available_credit_notes`, invocada automáticamente al
  generar cualquier factura nueva para la suscripción.
- **Síntoma**: reembolsar un pago que SÍ estaba aplicado a una factura
  dejaba esa factura marcada `PAID` para siempre, aunque el dinero ya
  hubiera vuelto al cliente. → **Causa real**: `_complete_refund`
  cambiaba el estado del `SaaSPayment` pero nunca tocaba la
  `SaaSPaymentAllocation` correspondiente — los 11 tests de reembolso
  existentes nunca lo detectaron porque ninguno reembolsaba un pago
  realmente aplicado (todos usaban un pago recién creado, sin aplicar).
  → **Corrección**: revertir las asignaciones activas del pago hasta
  cubrir el monto reembolsado, reasignando el remanente si la
  asignación revertida era mayor que lo efectivamente devuelto.
- **Síntoma** (encontrado por la prueba de concurrencia nueva del punto
  anterior, no por auditoría de código): dos solicitudes de reembolso
  simultáneas de 30.00 cada una sobre un pago de 50.00 pasaban AMBAS. →
  **Causa real**: el guard de monto disponible contaba solo reembolsos
  `COMPLETED`; un `BillingRefund` recién creado queda `PENDING`, así
  que ambos hilos, aunque serializados por el lock sobre `SaaSPayment`,
  veían igualmente "0 ya reembolsado" uno después del otro. →
  **Corrección**: sumar también `PENDING` al cálculo del monto ya
  comprometido.
- **Síntoma** (hallazgo más grave de "FASE DE CORRECCIÓN 4 —
  Transferencias, Comprobantes, Verificación y Notificaciones"): el
  Super Admin no tenía NINGUNA forma de ver el contenido real de un
  comprobante de transferencia subido — la pantalla de revisión solo
  mostraba el nombre de archivo como texto plano, sin ningún enlace. →
  **Causa real**: `proof_detail.html` se construyó mostrando metadatos
  (monto, moneda, cuenta, referencia) pero nunca se agregó una vista de
  descarga del archivo — el modelo/servicio de subida estaba completo,
  la vía de lectura del archivo real simplemente nunca se construyó. →
  **Corrección**: dos vistas nuevas de descarga protegida (`FileResponse`,
  mismo patrón que `apps.customers._ContactDocumentDownloadView`) — una
  para el Super Admin (cualquier tenant) y otra para el propio tenant
  (filtrada por `tenant=request.tenant`), enlazadas desde ambas
  pantallas de revisión/historial.
- **Síntoma**: una transferencia declarada en una moneda que coincidía
  con la cuenta bancaria receptora, pero NO con la factura que
  supuestamente pagaba, se aceptaba sin ningún rechazo. → **Causa
  real**: `submit_payment_proof` solo comparaba la moneda declarada
  contra la de la cuenta receptora — nunca contra la de la factura. →
  **Corrección**: validación adicional exigiendo que las tres
  coincidan exactamente, reforzada también en el núcleo del ledger
  (`apply_payment_to_invoices`/`auto_apply_payment`, que ahora nunca
  aplican un pago a una factura en otra moneda, sin importar por qué
  camino haya entrado ese pago al sistema).
- **Síntoma**: dos envíos concurrentes del mismo formulario de subida
  de comprobante (doble clic, dos pestañas) podían crear DOS
  `PaymentProof` `SUBMITTED` para la misma factura, pese a que una
  prueba secuencial ya verificaba que un segundo envío se rechazaba. →
  **Causa real**: el guard de "sin comprobante pendiente" era un
  `.filter(...).exists()` sin ningún `select_for_update()` — dos
  transacciones concurrentes podían pasar esa comprobación ANTES de que
  cualquiera comprometiera su propia fila. → **Corrección**:
  `select_for_update()` sobre la `SaaSInvoice` (mismo patrón ya usado
  por `create_checkout_for_invoice`) antes de comprobar/crear.
- **Síntoma**: rechazar un comprobante que YA había sido aprobado (una
  carrera real entre dos acciones del Super Admin, o dos pestañas)
  dejaba un estado contradictorio — `PaymentProof` `REJECTED` con un
  `SaaSPayment` `CONFIRMED`/`Subscription ACTIVE` ya generados por la
  aprobación previa, sin revertir nada. → **Causa real**:
  `reject_payment_proof` solo comprobaba "¿ya está `REJECTED`?" (no-op
  idempotente) pero nunca "¿ya está `APPROVED`?" (transición inválida).
  → **Corrección**: guard explícito que rechaza intentar rechazar
  cualquier estado que no sea `SUBMITTED`/`UNDER_REVIEW`, con su propio
  mensaje de error atrapado en la vista (nunca un 500 sin manejar).
- **Síntoma** (encontrado por la propia prueba de concurrencia nueva
  escrita para probar que "transferencia + PayPal sobre la misma
  factura" converge de forma segura, no por auditoría de código): una
  captura de PayPal exitosa quedaba REVERTIDA por completo (el
  `PayPalTransaction` volvía a su estado previo, ni siquiera quedaba
  `CONFIRMED`) cuando, al mismo tiempo, una transferencia distinta
  terminaba de cubrir la MISMA factura primero. → **Causa real**:
  `auto_apply_payment` calculaba cuánto aplicar a cada factura leyendo
  el saldo SIN ningún lock, y recién tomaba el lock real dentro de
  `apply_payment_to_invoices` — si la factura ya estaba cubierta para
  cuando ese lock se obtenía, `apply_payment_to_invoices` lanzaba
  `InvalidPaymentOperation` sin que nadie la atrapara, y esa excepción
  se propagaba hacia arriba a través de la señal `payment_confirmed`
  hasta la propia transacción de `capture_checkout`, revirtiéndola
  entera. → **Corrección**: `auto_apply_payment` ahora recalcula su
  plan de asignación UNA vez más si la primera aplicación falla por
  esta razón (reintento acotado, nunca indefinido) — si tras
  recalcular ya no queda ninguna factura con saldo real, el pago
  simplemente queda sin aplicar (saldo a favor), nunca rompe la
  operación del llamador.
- **Síntoma** (el hallazgo más severo de "FASE DE CORRECCIÓN 5 — Gate
  Local SaaS"): un tenant con cobro recurrente de PayPal ya autorizado
  que cancelaba su suscripción — desde su propio Portal, o desde el
  Panel de Super Admin — seguía siendo cobrado automáticamente cada
  período, pese a que `Subscription.status` ya mostraba `CANCELLED` en
  Budun. → **Causa real**: `CancelSubscriptionView` (Portal) y
  `TenantDetailView.post()` (Super Admin, acción "cancelar") llamaban a
  `subscriptions.cancel_subscription` directo — la función coordinada
  `recurring.cancel_recurring_subscription` (que SÍ cancela también el
  lado de PayPal) ya existía y ya estaba probada desde FASE DE
  CORRECCIÓN 2C, pero ningún camino real de la aplicación la invocaba
  jamás, solo los tests unitarios la llamaban de forma directa. →
  **Corrección**: ambas vistas ahora llaman a `cancel_recurring_
  subscription`, que se comporta exactamente igual que la función
  simple cuando nunca hubo autorización de PayPal — nunca hace falta
  distinguir el caso en el llamador.
- **Síntoma**: un cupón de duración limitada (p. ej. una promoción de 3
  meses) seguía descontando indefinidamente en cada renovación
  posterior a su fecha de vencimiento real, y el MRR/ARR del dashboard
  de Super Admin nunca reflejaba ningún descuento por cupón. → **Causa
  real**: `generate_invoice_for_subscription` solo comprobaba `coupon.
  is_active` (un interruptor manual) en cada renovación — nunca
  `valid_from`/`valid_until` (las fechas reales de vigencia); `reports.
  _mrr_de_suscripcion` nunca aplicaba ningún descuento de cupón en
  absoluto, usando siempre el precio de lista. → **Corrección**: nueva
  `coupons.is_coupon_currently_valid` (fecha + interruptor manual),
  reutilizada por ambos puntos.
- **Síntoma**: emitir una nota de crédito o completar un reembolso
  nunca notificaba nada al tenant — se enteraba solo si entraba por su
  cuenta a revisar su Portal de Facturación. → **Causa real**:
  `notifications.py` nunca tuvo funciones dedicadas para estos dos
  eventos financieros, a diferencia de pago/factura/PAST_DUE/
  suspensión/reactivación/renovación, que ya estaban cubiertos. →
  **Corrección**: `notify_credit_note_issued`/`notify_refund_completed`,
  mismo patrón que el resto del módulo.
- **Síntoma**: emitir una nota de crédito para un `SaaSCustomer` sin
  ningún `Tenant` asociado todavía producía un `IntegrityError` sin
  manejar (500) — el formulario nunca lo impedía. → **Causa real**:
  `IssueCreditNoteView` pasaba `tenant=customer.tenants.first()`
  (potencialmente `None`) directo a `issue_credit_note`, cuyo campo
  `tenant` no es nulo (`CreditNote` hereda `TenantScopedModel`). →
  **Corrección**: guard explícito en la vista con un mensaje claro.
- **Síntoma** (el hallazgo financiero más significativo de "FASE DE
  CORRECCIÓN 6 — Gate Local SaaS"): cambiar de un plan mensual a uno
  anual (o viceversa) a mitad de período producía un cargo o crédito
  varias veces mayor al correcto (~12× de magnitud). → **Causa real**:
  `calculate_proration` dividía TANTO el precio actual COMO el precio
  nuevo entre los días del período VIGENTE (p. ej. 30, mensual) sin
  importar que el plan NUEVO tuviera una frecuencia distinta (365 días,
  anual) — `ChangePlanForm`/`portal_change_plan.html` permiten elegir
  cualquier `PlanVersion` vigente sin ninguna restricción de
  frecuencia, así que el caso era completamente alcanzable desde el
  propio Portal del tenant. → **Corrección**: cada precio se divide
  entre los días NOMINALES de SU PROPIA frecuencia
  (`_DIAS_POR_FRECUENCIA`), nunca entre los días del período vigente.
- **Síntoma** (encontrado por la propia prueba de concurrencia nueva
  escrita para el hallazgo anterior, no por auditoría de código): dos
  facturas de la MISMA suscripción generándose casi a la vez (el cron
  de renovación y una reconciliación reactiva de PayPal disparándose
  juntos) podían hacer que la generación de una de ellas fallara con
  una excepción sin atrapar. → **Causa real**: `credits.auto_apply_
  available_credit_notes` tenía EXACTAMENTE el mismo problema
  estructural que `payments.auto_apply_payment` (ya corregido en la
  Corrección 4) — calculaba su plan de aplicación sin lock y solo
  tomaba el lock real dentro de `apply_credit_note_to_invoice`; nadie
  había buscado esta gemela estructural al corregir la primera. →
  **Corrección**: mismo `try/except` ya aplicado a `auto_apply_payment`,
  con la mejora de refrescar el saldo disponible tras cada fallo.
- **Síntoma**: el Super Admin, administrando Tenants/Facturas/PayPal de
  toda la plataforma, veía el sidebar completo del ERP (Inventario,
  Ventas, Compras, POS, RRHH, Nómina, Contabilidad...) en cada página
  de administración. → **Causa real**: las 21 plantillas de
  `billing_admin`/`billing_platform` extendían `layout_app.html` — el
  mismo shell del ERP tenant — porque ya existía y funcionaba, sin que
  nadie se preguntara si ambas audiencias debían compartir la misma
  navegación. → **Corrección**: shell nuevo y separado
  (`layout_saas_admin.html`, sidebar azul profundo agrupado por
  sección); el Portal del tenant se dejó intencionalmente en el shell
  original.
- **Síntoma**: el dashboard de Billing SaaS mostraba "MRR"/"ARR"/
  "PAST_DUE" como etiquetas de KPI, y cada badge de estado
  (`ACTIVE`/`SUSPENDED`/`PAID`/`PENDING`) se veía idéntico, en gris
  neutro. → **Causa real**: las etiquetas de KPI eran texto fijo
  hardcodeado en el template (nunca conectadas a un vocabulario
  humano); el texto de cada badge SÍ venía correctamente traducido
  desde `get_..._display()`, pero ningún badge tenía nunca un
  modificador de color — se renderizaban con `class="badge"` a secas
  en absolutamente todas las plantillas. → **Corrección**: dashboard
  reescrito con etiquetas humanas agrupadas en 3 secciones; nuevo
  filtro `estado_badge` con un único mapa código-crudo→color aplicado
  de forma consistente en las 21 plantillas de plataforma.
- **Síntoma**: frente a un mockup visual aprobado por el usuario, la
  plataforma ya tenía el shell separado y los badges semánticos
  correctos, pero se sentía incompleta — sin iconos, con encabezados
  de tamaño inconsistente (heredado del navegador, nunca del sistema
  de diseño), con una scrollbar pesada por defecto. → **Causa real**:
  ninguno de estos detalles se había necesitado hasta que hubo una
  referencia visual concreta contra la cual compararlos — el sistema
  de componentes era correcto pero incompleto en su capa de
  refinamiento. → **Corrección**: iconos con emoji (mismo mecanismo ya
  establecido, nunca una librería nueva), tamaños de encabezado
  explícitos acotados a `.shell--saas`, scrollbar fina y `overflow-x:
  hidden` globales (documentados como la excepción segura) — todo
  aplicado en la capa de componentes/shell compartidos, nunca vista
  por vista.
