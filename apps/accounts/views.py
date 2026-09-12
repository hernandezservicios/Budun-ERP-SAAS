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

from apps.core.utils import get_client_ip
from apps.tenants.models import Membership, Tenant

from . import rate_limit
from .forms import EmailAuthenticationForm, OnboardingForm, ProfileForm, RegistrationForm

# Throttling de recuperación de contraseña (FASE 18 — Security
# Hardening): límites independientes de los de login
# (`apps.accounts.forms`, scopes "login_email"/"login_ip") — un
# atacante que agota el límite de login nunca agota, de paso, el de
# recuperación de contraseña ni viceversa. Ventana más amplia (1 hora)
# porque el abuso aquí no es "adivinar una contraseña" sino "bombardear
# de correos" o forzar el costo de una consulta a la base de datos por
# cada intento.
PASSWORD_RESET_MAX_ATTEMPTS_PER_EMAIL = 5
PASSWORD_RESET_MAX_ATTEMPTS_PER_IP = 10
PASSWORD_RESET_THROTTLE_WINDOW_SECONDS = 60 * 60


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
        # Super Admin de plataforma (FASE 15/16: `is_superuser`, ver
        # `apps.tenants.permissions.require_superuser`) NUNCA pasa por
        # el flujo de tenant — se evalúa ANTES que la pertenencia a un
        # tenant a propósito: un Super Admin real y un usuario que
        # simplemente "todavía no tiene tenant" comparten el mismo
        # hecho observable (cero Membership), pero significan cosas
        # opuestas, y solo el primero existe fuera del concepto de
        # tenant por diseño (ver docstring de `OnboardingView`, que
        # aplica exactamente el mismo criterio).
        if self.request.user.is_superuser:
            return str(reverse_lazy("billing_admin:dashboard"))

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
            # FASE 7: el Panel es ahora el destino real tras iniciar
            # sesión (antes, en FASE 4, era el perfil).
            return str(reverse_lazy("dashboard:panel"))
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
    desde aquí (esa gestión multi-empresa no es alcance de FASE 4). Un
    Super Admin de plataforma (`is_superuser`) NUNCA llega a esta vista,
    tenga o no Membership — se redirige de inmediato al panel de
    plataforma (bug real corregido: antes se le trataba igual que a un
    usuario "todavía sin tenant", creándole un Tenant real por accidente).
    """

    form_class = OnboardingForm
    template_name = "accounts/onboarding.html"
    # FASE 17 (Billing SaaS, ver docs/billing.md sección 15): un tenant
    # nuevo ya no llega directo al Panel — queda PENDING_SETUP hasta
    # elegir un plan y completar el pago. Cambio de comportamiento
    # deliberado respecto a FASE 4/7 (ver `apps/accounts/tests.py`,
    # actualizado en el mismo commit).
    success_url = reverse_lazy("billing_portal:select_plan")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            # Mismo criterio que `EmailLoginView.get_success_url`: un
            # Super Admin de plataforma nunca debe poder crear un
            # Tenant "para sí mismo" — ni siquiera navegando directo a
            # esta URL (marcador, enlace viejo, botón atrás). Se
            # evalúa antes que la Membership, nunca después.
            if request.user.is_superuser:
                return redirect("billing_admin:dashboard")
            if Membership.objects.filter(user=request.user, is_active=True).exists():
                return redirect("dashboard:panel")
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
            # billing_status=PENDING_SETUP explícito (FASE 17): el
            # default del campo es ACTIVE por compatibilidad con
            # tenants preexistentes, pero un tenant NUEVO siempre debe
            # pasar por Billing antes de operar por completo — ver
            # `apps.billing.middleware.BillingStatusMiddleware`.
            tenant = Tenant.objects.create(name=company_name, slug=slug, billing_status=Tenant.BillingStatus.PENDING_SETUP)
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
    """FASE 18 (Security Hardening): además de lo que Django ya cubre
    (token de un solo uso con expiración, y una respuesta idéntica
    exista o no la cuenta — Django nunca revela existencia de email),
    se añade throttling real por IP y por email para cerrar el abuso
    de bombardeo de correos / consultas repetidas a la base de datos
    (hallazgo documentado desde FASE 4/`docs/security.md`, mismo eje
    que el login pero con scopes y ventana propios — ver
    `PASSWORD_RESET_MAX_ATTEMPTS_PER_*` arriba)."""

    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        email = (form.cleaned_data.get("email") or "").strip().lower()
        ip = get_client_ip(self.request)

        if rate_limit.is_blocked(
            "pwreset_email", email, max_attempts=PASSWORD_RESET_MAX_ATTEMPTS_PER_EMAIL
        ) or rate_limit.is_blocked(
            "pwreset_ip", ip, max_attempts=PASSWORD_RESET_MAX_ATTEMPTS_PER_IP
        ):
            self._auditar_bloqueo(email, ip)
            # Misma página de "listo" que un envío real: nunca revela,
            # con una respuesta distinta, que la causa fue el límite de
            # tasa — igual criterio que Django ya aplica para no
            # revelar si el email existe o no.
            return redirect(self.get_success_url())

        rate_limit.register_attempt(
            "pwreset_email", email, window_seconds=PASSWORD_RESET_THROTTLE_WINDOW_SECONDS
        )
        rate_limit.register_attempt(
            "pwreset_ip", ip, window_seconds=PASSWORD_RESET_THROTTLE_WINDOW_SECONDS
        )
        return super().form_valid(form)

    def _auditar_bloqueo(self, email, ip):
        # Import diferido + resiliente — mismo criterio que
        # `EmailAuthenticationForm._auditar_bloqueo` / el resto de
        # integraciones automáticas del proyecto.
        try:
            from apps.audit.models import AuditLog
            from apps.audit.services import log_event

            log_event(
                None, action=AuditLog.Action.PASSWORD_RESET_THROTTLED, domain="auth",
                ip_address=ip, metadata={"email": email} if email else {},
            )
        except Exception:  # noqa: BLE001
            pass


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
