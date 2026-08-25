from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User


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
