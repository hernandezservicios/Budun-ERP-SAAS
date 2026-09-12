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
"""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


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
