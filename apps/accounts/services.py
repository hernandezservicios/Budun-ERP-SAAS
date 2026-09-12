"""
Activación de cuentas creadas automáticamente (FASE DE CORRECCIÓN 1 —
Acceso del Owner y ciclo de vida del Tenant).

Cuando Super Admin da de alta un Tenant vía Venta Manual
(`apps.billing.admin_views.ManualTenantSaleView`), el `User` Owner se
crea automáticamente con `set_unusable_password()` — no puede iniciar
sesión todavía, pero el `User`/`Membership` OWNER ya existen (nunca se
crea un segundo `User` para el mismo correo, ver
`apps.accounts.forms.RegistrationForm.clean_email`). Este módulo genera
y envía el enlace que le permite establecer su propia contraseña por
primera vez.

Reutiliza deliberadamente el mismo mecanismo de token que la
recuperación de contraseña ya usa en producción
(`django.contrib.auth.tokens.default_token_generator`, una instancia de
`PasswordResetTokenGenerator`): el token incorpora el pk del usuario, un
hash derivado de su contraseña actual y una marca de tiempo, así que ya
resuelve, sin ningún modelo nuevo, las cuatro propiedades de seguridad
pedidas: de un solo uso EFECTIVO (establecer la contraseña cambia el
hash del que depende el token, invalidando cualquier reintento del mismo
enlace), expirable (`settings.PASSWORD_RESET_TIMEOUT`, 3 días por
defecto de Django), ligado a un usuario específico (`uidb64`) y con
detección de token inválido/adulterado.

Deliberadamente NO se reutiliza `django.contrib.auth.forms.
PasswordResetForm` para esto: su `get_users()` EXCLUYE a propósito
cualquier usuario con `has_usable_password() == False` (para que nadie
pueda usar "¿Olvidaste tu contraseña?" como puerta trasera para
apoderarse de una cuenta sin contraseña de otra persona) — exactamente
el caso del Owner recién creado por Venta Manual. Por eso este módulo
construye el token directamente para el `User` ya conocido (el propio
Owner que la vista acaba de crear), sin pasar por ese filtro.

FASE DE CORRECCIÓN 1B añade `classify_activation_token` (distingue
"expiró" de "inválido", para un mensaje específico) y
`resend_activation_email` (reenvío self-service desde Registro/Login,
ver `AccountActivationResendView`), completando la experiencia cuando
el cliente llega por las pantallas normales en vez del correo de Alta
Manual.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.utils.encoding import force_bytes
from django.utils.http import base36_to_int, urlsafe_base64_encode

User = get_user_model()


def build_activation_url(user, *, request=None):
    """URL absoluta de activación para `user`. Con `request` disponible
    (caso real: Super Admin completando el formulario de Venta Manual)
    se construye a partir de la request real (dominio/esquema
    correctos); si no (uso desde shell/comandos/tests), se usa
    `settings.APP_BASE_URL` con `http://localhost:8000` como último
    recurso de desarrollo."""
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("accounts:activacion_confirmar", kwargs={"uidb64": uidb64, "token": token})
    if request is not None:
        return request.build_absolute_uri(path)
    base = getattr(settings, "APP_BASE_URL", "http://localhost:8000")
    return f"{base.rstrip('/')}{path}"


def send_account_activation_email(user, *, request=None):
    """Envía el correo de activación. Nunca lanza: un fallo de envío
    (SMTP caído, backend mal configurado, etc.) nunca debe poder
    revertir ni bloquear la creación real del Tenant/Owner — mismo
    criterio de resiliencia que el resto de integraciones automáticas
    del proyecto (`apps.accounting.services.try_record_*`, las
    auditorías `try/except` de `apps.audit`). Devuelve
    `(enviado: bool, activation_url: str)` para que el llamador pueda
    mostrarle el enlace directamente al Super Admin si el envío
    falla."""
    activation_url = build_activation_url(user, request=request)
    contexto = {"user": user, "activation_url": activation_url}
    try:
        asunto = render_to_string("accounts/activation_email_subject.txt", contexto)
        asunto = "".join(asunto.splitlines()).strip()
        mensaje = render_to_string("accounts/activation_email.html", contexto)
        send_mail(asunto, mensaje, None, [user.email])
        return True, activation_url
    except Exception:  # noqa: BLE001
        return False, activation_url


def classify_activation_token(user, token):
    """Clasifica un token de activación como `"valid"`, `"expired"` o
    `"invalid"` (FASE DE CORRECCIÓN 1B, Escenario 4).

    `PasswordResetTokenGenerator.check_token` (Django) solo devuelve un
    booleano — no distingue "la firma es correcta pero venció el plazo"
    de "la firma es incorrecta" (adulterado, de otro usuario, o ya
    invalidado porque la contraseña/estado del usuario cambió desde que
    se emitió). Para poder mostrarle al Owner un mensaje específico de
    expiración (en vez de "inválido" a secas) se reutiliza el mismo
    `default_token_generator`, recalculando la firma esperada para el
    timestamp que el propio token declara — con el mismo método
    (`_make_token_with_timestamp`) que Django factoriza precisamente
    para que un generador se pueda reutilizar/extender así — y solo se
    ignora el chequeo de expiración. Si la firma coincide, la única
    razón por la que `check_token` igual devolvió `False` es el tiempo
    transcurrido: expiró. Ninguna otra información nueva se expone (no
    se revela nada que `check_token` no revele ya)."""
    if user is None or not token:
        return "invalid"
    if default_token_generator.check_token(user, token):
        return "valid"
    try:
        ts_b36, _hash = token.split("-")
        ts = base36_to_int(ts_b36)
    except (ValueError, TypeError):
        return "invalid"
    firma_valida = any(
        constant_time_compare(
            default_token_generator._make_token_with_timestamp(user, ts, secret), token
        )
        for secret in [default_token_generator.secret, *default_token_generator.secret_fallbacks]
    )
    return "expired" if firma_valida else "invalid"


def resend_activation_email(email, *, request=None):
    """Reenvía el enlace de activación (FASE DE CORRECCIÓN 1B, Escenario
    3). Localiza el `User` existente por correo — NUNCA crea uno nuevo
    — y, si (y solo si) sigue pendiente de activación
    (`has_usable_password() == False`), invalida FUNCIONALMENTE
    cualquier token anterior (el emitido en el alta original y
    cualquier reenvío previo) antes de emitir y enviar uno nuevo.

    La invalidación no requiere ningún modelo de token nuevo: el token
    de `default_token_generator` depende del hash de `user.password"
    (ver `PasswordResetTokenGenerator._make_hash_value`), y
    `set_unusable_password()` genera un valor aleatorio NUEVO cada vez
    que se llama (`django.contrib.auth.hashers.make_password(None)`) —
    volver a llamarlo cambia ese hash sin volver la cuenta utilizable,
    lo que invalida cualquier token calculado contra el valor anterior
    exactamente igual que un cambio de contraseña real invalidaría un
    token de recuperación.

    Deliberadamente NO revela nada por su valor de retorno ni lanza
    ante un correo inexistente o ya activado — mismo criterio
    anti-enumeración que `AccountPasswordResetView`/`PasswordResetForm`:
    el llamador (la vista) siempre muestra la misma respuesta de
    "listo" sin importar el resultado real."""
    email_normalizado = (email or "").strip().lower()
    if not email_normalizado:
        return
    user = User.objects.filter(email=email_normalizado).first()
    if user is None or user.has_usable_password():
        return
    user.set_unusable_password()
    user.save(update_fields=["password"])
    send_account_activation_email(user, request=request)
