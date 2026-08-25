from django.contrib.auth import login as auth_login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeDoneView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.text import slugify
from django.views.generic import CreateView, FormView, UpdateView

from apps.tenants.models import Membership, Tenant

from .forms import EmailAuthenticationForm, OnboardingForm, ProfileForm, RegistrationForm


class RegisterView(CreateView):
    """Registro (FASE 4). Crea el `User` y lo autentica inmediatamente
    (sin verificación de email por ahora: no está en el alcance explícito
    de esta fase; ver docs/authentication.md)."""

    form_class = RegistrationForm
    template_name = "accounts/registro.html"

    def get_success_url(self):
        return reverse_lazy("accounts:onboarding")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Login explícito con el backend por defecto (evita ambigüedad si
        # en el futuro se agregan varios backends de autenticación).
        auth_login(self.request, self.object, backend="django.contrib.auth.backends.ModelBackend")
        return response


class EmailLoginView(LoginView):
    """Login por correo electrónico (FASE 4)."""

    form_class = EmailAuthenticationForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        # No se puede usar `self.request.tenant` aquí: TenantMiddleware ya
        # calculó ese valor ANTES de que esta misma vista autenticara al
        # usuario (login() ocurre dentro de form_valid, en esta request),
        # así que request.tenant todavía reflejaría el estado anterior
        # (anónimo). Se resuelve con una consulta fresca a Membership,
        # nunca a partir de un valor enviado por el cliente.
        tiene_tenant = Membership.objects.filter(
            user=self.request.user, is_active=True, tenant__is_active=True
        ).exists()
        if tiene_tenant:
            return str(reverse_lazy("accounts:perfil"))
        return str(reverse_lazy("accounts:onboarding"))


class AccountLogoutView(LogoutView):
    """Logout (FASE 4). Django invalida la sesión del lado del servidor."""

    next_page = reverse_lazy("core:home")


class OnboardingView(LoginRequiredMixin, FormView):
    """Creación transaccional de User (ya existente) + Tenant + Membership
    OWNER (FASE 4).

    Deliberadamente NO usa `TenantRequiredMixin`: el propósito de esta
    vista es precisamente crear el primer tenant de un usuario que todavía
    no tiene ninguno. Si el usuario ya tiene una membresía activa, se
    redirige a su perfil en vez de permitir crear tenants adicionales
    desde aquí (esa gestión multi-empresa no es alcance de FASE 4).
    """

    form_class = OnboardingForm
    template_name = "accounts/onboarding.html"
    success_url = reverse_lazy("accounts:perfil")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and Membership.objects.filter(
            user=request.user, is_active=True
        ).exists():
            return redirect("accounts:perfil")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        company_name = form.cleaned_data["company_name"].strip()
        base_slug = slugify(company_name) or "empresa"
        slug = base_slug
        suffix = 1
        while Tenant.objects.filter(slug=slug).exists():
            suffix += 1
            slug = f"{base_slug}-{suffix}"

        with transaction.atomic():
            tenant = Tenant.objects.create(name=company_name, slug=slug)
            Membership.objects.create(
                user=self.request.user, tenant=tenant, role=Membership.Role.OWNER
            )

        return super().form_valid(form)


class ProfileView(LoginRequiredMixin, UpdateView):
    """Perfil del usuario autenticado (FASE 4).

    No exige tenant activo (`TenantRequiredMixin`): un usuario recién
    registrado que aún no completó el onboarding debe poder ver/editar su
    propia cuenta. Si tiene un tenant activo, el template muestra el
    nombre de la empresa y el rol — nunca datos de otro tenant (fail
    closed: si `request.tenant` es None, el template simplemente no
    muestra esa sección).
    """

    form_class = ProfileForm
    template_name = "accounts/perfil.html"
    success_url = reverse_lazy("accounts:perfil")

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tenant"] = getattr(self.request, "tenant", None)
        context["membership"] = getattr(self.request, "membership", None)
        return context


# ----------------------------------------------------------------------
# Recuperación y cambio de contraseña.
#
# Se reutilizan las vistas integradas de Django (ya cubren generación de
# token seguro de un solo uso con expiración, invalidación tras el uso,
# y — en PasswordChangeView — mantener la sesión viva tras el cambio
# mediante `update_session_auth_hash`). Solo se personalizan plantillas y
# URLs de redirección.
# ----------------------------------------------------------------------


class AccountPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class AccountPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class AccountPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class AccountPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


class AccountPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = "accounts/password_change_form.html"
    success_url = reverse_lazy("accounts:password_change_done")


class AccountPasswordChangeDoneView(LoginRequiredMixin, PasswordChangeDoneView):
    template_name = "accounts/password_change_done.html"
