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
