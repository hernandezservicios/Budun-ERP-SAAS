# Authentication (FASE 4)

Registro, login, logout, recuperación/cambio de contraseña, perfil y
onboarding. Este documento describe lo implementado en FASE 4 y cómo se
integra con el Multi-Tenancy de FASE 3 (ver `docs/multi-tenancy.md`), sin
modificar ninguna de sus protecciones.

## Login por correo electrónico

`accounts.User` ya no tiene `username` (se eliminó en FASE 4; `AUTH_USER_MODEL`
se había fijado en FASE 3). `USERNAME_FIELD = "email"`, con un
`UserManager` propio (`apps/accounts/models.py`) siguiendo el patrón
oficial de Django para modelos de usuario sin username. Se verificó que
no existía ningún usuario real antes de aplicar la migración que elimina
la columna (0 filas).

## Flujos implementados

| Flujo | Vista | Notas |
|---|---|---|
| Registro | `RegisterView` (`/cuentas/registro/`) | Crea el usuario, valida email único y `AUTH_PASSWORD_VALIDATORS`, autentica inmediatamente y redirige a onboarding. Sin verificación de email (no es alcance explícito de esta fase). |
| Login | `EmailLoginView` (`/cuentas/login/`) | `AuthenticationForm` de Django con mensaje de error genérico (no revela si el email existe). Redirige a onboarding o a perfil según si el usuario YA tiene una membresía activa (consulta fresca a `Membership`, no `request.tenant` — ver nota técnica abajo). |
| Logout | `AccountLogoutView` (`/cuentas/logout/`) | `LogoutView` estándar de Django: invalida la sesión del lado del servidor. |
| Recuperar contraseña | `AccountPasswordReset*View` (`/cuentas/password/reset/...`) | Vistas integradas de Django: token de un solo uso con expiración. Mismo mensaje de "correo enviado" exista o no la cuenta. `EMAIL_BACKEND=console` en desarrollo (se imprime en el log, no se envía nada real); un proveedor SMTP real es decisión de FASE 21. |
| Cambiar contraseña | `AccountPasswordChangeView` (`/cuentas/password/cambiar/`) | `PasswordChangeView` estándar: exige la contraseña actual, mantiene la sesión activa tras el cambio (`update_session_auth_hash`, incorporado por Django). |
| Perfil | `ProfileView` (`/cuentas/perfil/`) | Edita nombre/apellido/email. No exige tenant activo (ver "Fail-closed" abajo). Muestra la empresa y el rol si el usuario ya tiene un tenant. |
| Onboarding | `OnboardingView` (`/cuentas/onboarding/`) | Creación **transaccional** (`transaction.atomic()`) de `Tenant` + `Membership` con rol `OWNER`. Si el usuario ya tiene una membresía activa, redirige a perfil sin crear un tenant adicional (gestión multi-empresa no es alcance de FASE 4). |
| Activar cuenta | `AccountActivation*View` (`/cuentas/activacion/...`) | Para el `User` Owner que `apps.billing.admin_views.ManualTenantSaleView` crea automáticamente con `set_unusable_password()` (FASE DE CORRECCIÓN 1 del Gate Local, ver sección al final de este documento). |

## Nota técnica: por qué el redirect post-login NO usa `request.tenant`

`TenantMiddleware` calcula `request.tenant` **antes** de que la vista se
ejecute. En la request del login, el usuario todavía es anónimo en ese
momento (la autenticación ocurre dentro de `LoginView.form_valid`, más
tarde en la misma request), así que `request.tenant` seguiría siendo
`None` incluso si el usuario recién autenticado sí tiene un tenant. Por
eso `EmailLoginView.get_success_url()` hace una consulta directa y fresca
a `Membership` en vez de leer `request.tenant`. Esto se descubrió con un
test que falló durante el desarrollo (ver historial de Git) y quedó
cubierto por `LoginLogoutTests.test_login_correcto_redirige_a_perfil_si_ya_tiene_tenant`.

## Cómo se preservan las protecciones Multi-Tenant de FASE 3

Ninguna de las siguientes reglas (ya establecidas en FASE 3) se modificó:

- **Tenant Context** (`apps/tenants/scoping.py`) sigue siendo la única
  fuente de verdad del tenant activo; FASE 4 no lo reemplaza ni lo evita.
- **Managers/QuerySets tenant-aware** (`TenantScopedModel`/`TenantManager`)
  no se tocaron. Ninguna vista de `accounts` consulta modelos tenant-aware
  directamente (perfil y onboarding solo tocan `User`, `Tenant` y
  `Membership`, que no heredan de `TenantScopedModel` — ver
  `docs/multi-tenancy.md`).
- **Selección de tenant**: ningún formulario ni endpoint de FASE 4 acepta
  un `tenant_id` del cliente. El único tenant que se crea es el de
  onboarding, y queda ligado al `request.user` autenticado por el
  backend, nunca a un valor enviado por el navegador.
- **Autorización**: `require_tenant`/`require_role` (FASE 3) no se
  modificaron; FASE 4 no los necesitó todavía porque no hay vistas de
  negocio protegidas por rol aún (eso llega con los módulos de FASE 8+).
- **Fail-closed**: se mantiene para datos tenant-scoped. La única
  vista que NO exige tenant activo es `ProfileView`, deliberadamente: un
  usuario que aún no completó el onboarding debe poder ver/editar su
  propia cuenta (nombre, email, contraseña) sin quedar bloqueado; esto no
  es una excepción al fail-closed de datos de negocio, porque `User` no
  es un modelo tenant-scoped y la vista no muestra ningún dato de ningún
  tenant salvo el propio (`request.tenant`, ya resuelto de forma segura
  por el middleware).
- **`all_objects`**: ninguna vista o endpoint de `accounts` lo usa
  (solo lo usa `apps/tenants/admin.py`, ya revisado y aceptado en FASE 3
  como herramienta interna de staff, no un endpoint de negocio).
- **`IsolationSample`**: sigue siendo exclusivamente el soporte de las
  pruebas de aislamiento (FASE 3 y las nuevas de regresión de FASE 4); no
  se usó en ninguna vista real.
- **Pruebas de FASE 3**: `apps/tenants/tests.py` (16 tests) se mantuvo
  intacto en su lógica; solo se ajustaron las llamadas a
  `create_user(username=...)` porque ese parámetro ya no existe en el
  modelo (ver `docs/project-status/KNOWN_ISSUES.md`). Los 16 tests siguen
  verificando exactamente lo mismo que en FASE 3 y siguen en verde.

## Regresión Multi-Tenant vía HTTP real (nuevo en FASE 4)

Además de mantener los 16 tests de FASE 3, se agregaron 2 pruebas de
regresión en `apps/accounts/tests.py::MultiTenantRegressionTests` que
ejercitan el aislamiento a través del flujo **real** de registro → login
→ onboarding (no solo creando objetos directamente, como en FASE 3):

- Dos usuarios se registran y completan onboarding con empresas distintas;
  cada uno ve únicamente su propia empresa y sus propios datos
  (`IsolationSample`) al visitar su perfil.
- Un intento de manipular la sesión de un usuario para apuntar al tenant
  del otro es descartado por `TenantMiddleware` (ya probado a nivel
  unitario en FASE 3; aquí se confirma también a nivel HTTP completo).

## Validaciones implementadas
- Email único (normalizado a minúsculas) en registro y en edición de perfil.
- Confirmación de contraseña + `AUTH_PASSWORD_VALIDATORS` (longitud
  mínima, no numérica, no común, no similar a los datos del usuario) en
  registro y en cambio/recuperación de contraseña (los validadores de
  Django se aplican automáticamente en `SetPasswordForm`/`PasswordChangeForm`).
- Nombre de empresa (onboarding): longitud mínima; slug generado
  automáticamente y desambiguado si ya existe (nunca falla por colisión).
- Mensajes de error genéricos en login (no se revela si un email existe).

## Pendiente deliberadamente fuera de alcance de FASE 4
- **Verificación de email** al registrarse: no estaba en los objetivos
  explícitos de la fase; se puede agregar más adelante si se decide.
- **Rate limiting / bloqueo por intentos fallidos de login**: es alcance
  natural de FASE 18 — Security Hardening, no de esta fase.
- **Selector de tenant / multi-empresa por usuario**: el modelo
  `Membership` ya soporta que un usuario pertenezca a varios tenants
  (FASE 3), pero no hay todavía UI para cambiar entre ellos ni para crear
  tenants adicionales desde una cuenta existente.
- **Proveedor SMTP real**: se usa el backend de consola en desarrollo;
  la configuración de producción es decisión de FASE 21.

## Activación de cuenta para Owners creados automáticamente (Corrección de Gate Local — "FASE DE CORRECCIÓN 1")

`apps.billing.admin_views.ManualTenantSaleView` (FASE 17, Super Admin,
`/plataforma/billing/admin/venta-manual/`) crea el `Tenant` y el `User`
Owner de una vez, con `owner.set_unusable_password()` — correcto para que
nadie pueda autenticarse con una contraseña adivinada, pero antes de esta
corrección no existía ningún flujo real para que ese Owner estableciera
su propia contraseña. Ver `KNOWN_ISSUES.md` #128 y `DECISIONS.md` #108
para el hallazgo completo y la justificación de diseño.

- **`apps.accounts.services`** (nuevo): `build_activation_url`/
  `send_account_activation_email` generan el enlace y envían el correo.
  Reutilizan `django.contrib.auth.tokens.default_token_generator` —
  el mismo mecanismo de la fila "Recuperar contraseña" de arriba — pero
  construyen el token directamente para el `User` ya conocido, sin pasar
  por `PasswordResetForm.get_users()` (que excluye a propósito cualquier
  cuenta con `has_usable_password() == False`, precisamente este caso).
- **`AccountActivationConfirmView`/`AccountActivationCompleteView`**
  (`apps/accounts/views.py`) son subclases mínimas de
  `PasswordResetConfirmView`/`PasswordResetCompleteView` de Django —
  mismo `SetPasswordForm` (valida `AUTH_PASSWORD_VALIDATORS`, incluida la
  longitud mínima), solo cambian plantilla y URL de éxito.
- `ManualTenantSaleView.post()` envía el correo de activación justo
  DESPUÉS de que la transacción de alta ya confirmó — nunca dentro de su
  `with transaction.atomic()` — y nunca bloquea la venta si el envío
  falla (se le muestra el enlace directamente al Super Admin).
- `RegistrationForm.clean_email()` sigue rechazando siempre un correo ya
  existente (nunca crea un segundo `User`, sin cambios en esa regla); si
  la cuenta existente tiene `has_usable_password() == False`, el mensaje
  ahora señala el correo de activación en vez de sugerir "inicia sesión".
- Tests: `apps/billing/tests/test_admin_views.py::OwnerActivationFlowTests`
  (7 tests HTTP end-to-end: activación válida + login + acceso al tenant
  correcto, token expirado, token reutilizado tras activar, token
  inválido, contraseña corta rechazada, sin duplicar `User` al reintentar
  `/cuentas/registro/`) más `ManualTenantSaleViewTests` extendida.
