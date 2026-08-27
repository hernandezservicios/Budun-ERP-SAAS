from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from apps.core.utils import get_client_ip

from . import rate_limit
from .models import User

# Throttling de login (FASE 18 — Security Hardening): dos ejes
# independientes, ver `apps.accounts.rate_limit`. Valores conservadores
# — no bloquean un uso legítimo normal (nadie falla 5 veces seguidas
# su propia contraseña en 15 minutos) pero cierran fuerza bruta y
# credential stuffing.
LOGIN_MAX_ATTEMPTS_PER_EMAIL = 5
LOGIN_MAX_ATTEMPTS_PER_IP = 20
LOGIN_THROTTLE_WINDOW_SECONDS = 15 * 60


class RegistrationForm(forms.ModelForm):
    """Formulario de registro (FASE 4). Crea el `User`; la creación del
    Tenant/Membership ocurre después, en el onboarding (ver views.py)."""

    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name"]
        labels = {
            "email": "Correo electrónico",
            "first_name": "Nombre",
            "last_name": "Apellido",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo electrónico.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        return password2

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password2") or cleaned_data.get("password1")
        if password:
            # Reutiliza AUTH_PASSWORD_VALIDATORS (ver config/settings.py).
            password_validation.validate_password(password)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    """`AuthenticationForm` de Django, solo con las etiquetas en español
    (el campo ya se llama `username` internamente, pero como
    `USERNAME_FIELD = "email"`, Django lo valida correctamente contra el
    email)."""

    username = forms.CharField(label="Correo electrónico")

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": (
            "Correo electrónico o contraseña incorrectos. Verifica ambos "
            "datos e inténtalo de nuevo."
        ),
    }

    def clean(self):
        """Throttling de fuerza bruta (FASE 18 — Security Hardening,
        hallazgo ya documentado desde FASE 4). Se verifica ANTES de
        `authenticate()` (evita incluso el costo de hashear la
        contraseña una vez bloqueado) y se registra un intento fallido
        DESPUÉS solo si las credenciales resultan inválidas — un
        bloqueo nunca revela, con un mensaje distinto, que la causa es
        el límite de tasa en vez de una contraseña incorrecta."""
        email = (self.data.get("username") or "").strip().lower()
        ip = get_client_ip(self.request) if self.request is not None else None

        if rate_limit.is_blocked(
            "login_email", email, max_attempts=LOGIN_MAX_ATTEMPTS_PER_EMAIL
        ) or rate_limit.is_blocked(
            "login_ip", ip, max_attempts=LOGIN_MAX_ATTEMPTS_PER_IP
        ):
            self._auditar_bloqueo(email, ip)
            raise forms.ValidationError(self.error_messages["invalid_login"], code="invalid_login")

        try:
            cleaned_data = super().clean()
        except forms.ValidationError:
            rate_limit.register_attempt(
                "login_email", email, window_seconds=LOGIN_THROTTLE_WINDOW_SECONDS
            )
            rate_limit.register_attempt(
                "login_ip", ip, window_seconds=LOGIN_THROTTLE_WINDOW_SECONDS
            )
            raise

        # Login exitoso: limpia cualquier intento fallido previo para
        # que un usuario legítimo nunca quede penalizado por errores
        # de tecleo anteriores una vez que ya demostró su contraseña.
        rate_limit.reset("login_email", email)
        rate_limit.reset("login_ip", ip)
        return cleaned_data

    def _auditar_bloqueo(self, email, ip):
        # Import diferido + resiliente — mismo criterio que el resto de
        # integraciones automáticas del proyecto (`apps.reports._audit_export`,
        # `apps.audit.signals`): la auditoría nunca debe poder romper ni
        # bloquear el login que está auditando.
        try:
            from apps.audit.models import AuditLog
            from apps.audit.services import log_event

            log_event(
                None, action=AuditLog.Action.LOGIN_THROTTLED, domain="auth",
                ip_address=ip, metadata={"email": email} if email else {},
            )
        except Exception:  # noqa: BLE001
            pass


class ProfileForm(forms.ModelForm):
    """Edición del perfil propio (FASE 4). No incluye contraseña ni
    tenant: la contraseña se cambia en su propio flujo (ver
    PasswordChangeView) y el tenant no es editable desde aquí."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Correo electrónico",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise forms.ValidationError("Ya existe otra cuenta con este correo electrónico.")
        return email


class OnboardingForm(forms.Form):
    """Primer paso tras el registro: nombre de la empresa (Tenant). La
    creación real (Tenant + Membership OWNER) es transaccional y ocurre en
    la vista (ver views.OnboardingView)."""

    company_name = forms.CharField(
        label="Nombre de tu empresa",
        max_length=150,
        min_length=2,
    )
