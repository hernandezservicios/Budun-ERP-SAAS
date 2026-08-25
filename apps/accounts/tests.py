"""
Tests de autenticación y onboarding (FASE 4).

Incluye, además de los flujos propios de esta fase, una prueba de
regresión de aislamiento Multi-Tenant que ejercita el registro/login/
onboarding REAL vía HTTP (a diferencia de `apps/tenants/tests.py`, que
construye los objetos directamente) — ver
`test_regresion_dos_usuarios_registrados_quedan_aislados`.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.tenants.models import Membership, Tenant
from apps.tenants.services import create_isolation_sample
from apps.tenants.scoping import tenant_context

User = get_user_model()


class RegistrationTests(TestCase):
    def test_registro_crea_usuario_lo_autentica_y_redirige_a_onboarding(self):
        respuesta = self.client.post(
            reverse("accounts:registro"),
            {
                "email": "nueva@example.com",
                "first_name": "Ana",
                "last_name": "Pérez",
                "password1": "una-clave-larga-987",
                "password2": "una-clave-larga-987",
            },
        )
        self.assertRedirects(respuesta, reverse("accounts:onboarding"))
        self.assertTrue(User.objects.filter(email="nueva@example.com").exists())

        respuesta_perfil = self.client.get(reverse("accounts:perfil"))
        self.assertEqual(respuesta_perfil.status_code, 200)  # la sesión ya está autenticada

    def test_registro_normaliza_email_a_minusculas(self):
        self.client.post(
            reverse("accounts:registro"),
            {
                "email": "MAYUS@Example.COM",
                "first_name": "Ana",
                "last_name": "Pérez",
                "password1": "una-clave-larga-987",
                "password2": "una-clave-larga-987",
            },
        )
        self.assertTrue(User.objects.filter(email="mayus@example.com").exists())

    def test_registro_rechaza_email_duplicado(self):
        User.objects.create_user(email="dup@example.com", password="una-clave-larga-987")
        respuesta = self.client.post(
            reverse("accounts:registro"),
            {
                "email": "dup@example.com",
                "first_name": "Ana",
                "last_name": "Pérez",
                "password1": "una-clave-larga-987",
                "password2": "una-clave-larga-987",
            },
        )
        self.assertEqual(respuesta.status_code, 200)  # vuelve a mostrar el formulario
        self.assertFalse(respuesta.context["form"].is_valid())
        self.assertEqual(User.objects.filter(email="dup@example.com").count(), 1)

    def test_registro_rechaza_contrasenas_no_coincidentes(self):
        respuesta = self.client.post(
            reverse("accounts:registro"),
            {
                "email": "otra@example.com",
                "first_name": "Ana",
                "last_name": "Pérez",
                "password1": "una-clave-larga-987",
                "password2": "otra-clave-distinta",
            },
        )
        self.assertFalse(respuesta.context["form"].is_valid())
        self.assertFalse(User.objects.filter(email="otra@example.com").exists())

    def test_registro_rechaza_contrasena_debil(self):
        respuesta = self.client.post(
            reverse("accounts:registro"),
            {
                "email": "debil@example.com",
                "first_name": "Ana",
                "last_name": "Pérez",
                "password1": "12345678",
                "password2": "12345678",
            },
        )
        self.assertFalse(respuesta.context["form"].is_valid())
        self.assertFalse(User.objects.filter(email="debil@example.com").exists())


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="login@example.com", password="una-clave-larga-987")

    def test_login_correcto_redirige_a_onboarding_si_no_tiene_tenant(self):
        respuesta = self.client.post(
            reverse("accounts:login"),
            {"username": "login@example.com", "password": "una-clave-larga-987"},
        )
        self.assertRedirects(respuesta, reverse("accounts:onboarding"))

    def test_login_correcto_redirige_a_perfil_si_ya_tiene_tenant(self):
        tenant = Tenant.objects.create(name="Empresa X", slug="empresa-x")
        Membership.objects.create(user=self.user, tenant=tenant, role=Membership.Role.OWNER)

        respuesta = self.client.post(
            reverse("accounts:login"),
            {"username": "login@example.com", "password": "una-clave-larga-987"},
        )
        self.assertRedirects(respuesta, reverse("accounts:perfil"))

    def test_login_con_contrasena_incorrecta_muestra_error_generico(self):
        respuesta = self.client.post(
            reverse("accounts:login"),
            {"username": "login@example.com", "password": "contraseña-incorrecta"},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["form"].is_valid())
        # No debe revelar si el email existe o no (mismo mensaje genérico).
        self.assertContains(respuesta, "incorrectos")

    def test_logout_cierra_sesion_y_bloquea_perfil(self):
        self.client.login(username="login@example.com", password="una-clave-larga-987")
        self.client.post(reverse("accounts:logout"))

        respuesta = self.client.get(reverse("accounts:perfil"))
        self.assertRedirects(
            respuesta, f"{reverse('accounts:login')}?next={reverse('accounts:perfil')}"
        )


class OnboardingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="onboard@example.com", password="una-clave-larga-987")
        self.client.login(username="onboard@example.com", password="una-clave-larga-987")

    def test_onboarding_crea_tenant_y_membership_owner(self):
        respuesta = self.client.post(
            reverse("accounts:onboarding"), {"company_name": "Mi Empresa"}
        )
        self.assertRedirects(respuesta, reverse("accounts:perfil"))

        tenant = Tenant.objects.get(slug="mi-empresa")
        self.assertEqual(tenant.name, "Mi Empresa")

        membership = Membership.objects.get(user=self.user, tenant=tenant)
        self.assertEqual(membership.role, Membership.Role.OWNER)

    def test_onboarding_genera_slug_unico_si_hay_colision(self):
        Tenant.objects.create(name="Otra empresa", slug="mi-empresa")
        self.client.post(reverse("accounts:onboarding"), {"company_name": "Mi Empresa"})
        self.assertTrue(Tenant.objects.filter(slug="mi-empresa-2").exists())

    def test_onboarding_ya_completado_redirige_sin_duplicar(self):
        tenant = Tenant.objects.create(name="Ya existente", slug="ya-existente")
        Membership.objects.create(user=self.user, tenant=tenant, role=Membership.Role.OWNER)

        respuesta = self.client.get(reverse("accounts:onboarding"))
        self.assertRedirects(respuesta, reverse("accounts:perfil"))
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 1)

    def test_tenant_context_disponible_inmediatamente_tras_onboarding(self):
        self.client.post(reverse("accounts:onboarding"), {"company_name": "Mi Empresa"})
        respuesta = self.client.get(reverse("accounts:perfil"))
        self.assertContains(respuesta, "Mi Empresa")


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="perfil@example.com",
            password="una-clave-larga-987",
            first_name="Nombre",
            last_name="Apellido",
        )
        self.client.login(username="perfil@example.com", password="una-clave-larga-987")

    def test_perfil_requiere_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("accounts:perfil"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("accounts:login"), respuesta.url)

    def test_perfil_muestra_datos_actuales(self):
        respuesta = self.client.get(reverse("accounts:perfil"))
        self.assertContains(respuesta, "Nombre")
        self.assertContains(respuesta, "Apellido")

    def test_perfil_sin_tenant_muestra_aviso_de_onboarding(self):
        respuesta = self.client.get(reverse("accounts:perfil"))
        self.assertContains(respuesta, "Todavía no has configurado tu empresa")

    def test_perfil_permite_editar_nombre(self):
        respuesta = self.client.post(
            reverse("accounts:perfil"),
            {"first_name": "Nuevo", "last_name": "Apellido", "email": "perfil@example.com"},
        )
        self.assertRedirects(respuesta, reverse("accounts:perfil"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Nuevo")

    def test_perfil_rechaza_email_duplicado(self):
        User.objects.create_user(email="ocupado@example.com", password="una-clave-larga-987")
        respuesta = self.client.post(
            reverse("accounts:perfil"),
            {"first_name": "Nombre", "last_name": "Apellido", "email": "ocupado@example.com"},
        )
        self.assertFalse(respuesta.context["form"].is_valid())


class MultiTenantRegressionTests(TestCase):
    """Regresión explícita pedida por el usuario: el aislamiento
    Multi-Tenant (FASE 3) debe seguir intacto cuando se llega a él a
    través del flujo REAL de registro/login/onboarding de FASE 4, no solo
    creando los objetos directamente."""

    def _registrar_y_onboardear(self, email, empresa):
        client = self.client_class()
        client.post(
            reverse("accounts:registro"),
            {
                "email": email,
                "first_name": "Persona",
                "last_name": "Prueba",
                "password1": "una-clave-larga-987",
                "password2": "una-clave-larga-987",
            },
        )
        client.post(reverse("accounts:onboarding"), {"company_name": empresa})
        return client

    def test_dos_usuarios_registrados_quedan_completamente_aislados(self):
        cliente_a = self._registrar_y_onboardear("regresion.a@example.com", "Empresa A")
        cliente_b = self._registrar_y_onboardear("regresion.b@example.com", "Empresa B")

        tenant_a = Tenant.objects.get(slug="empresa-a")
        tenant_b = Tenant.objects.get(slug="empresa-b")

        with tenant_context(tenant_a):
            create_isolation_sample(tenant_a, "secreto-de-A")
        with tenant_context(tenant_b):
            create_isolation_sample(tenant_b, "secreto-de-B")

        respuesta_a = cliente_a.get(reverse("accounts:perfil"))
        respuesta_b = cliente_b.get(reverse("accounts:perfil"))

        self.assertContains(respuesta_a, "Empresa A")
        self.assertNotContains(respuesta_a, "Empresa B")
        self.assertContains(respuesta_b, "Empresa B")
        self.assertNotContains(respuesta_b, "Empresa A")

    def test_sesion_de_un_cliente_no_permite_ver_tenant_del_otro_manipulando_la_sesion(self):
        cliente_a = self._registrar_y_onboardear("manip.a@example.com", "Empresa Manip A")
        self._registrar_y_onboardear("manip.b@example.com", "Empresa Manip B")
        tenant_b = Tenant.objects.get(slug="empresa-manip-b")

        session = cliente_a.session
        session["active_tenant_id"] = tenant_b.id
        session.save()

        respuesta = cliente_a.get(reverse("accounts:perfil"))
        self.assertContains(respuesta, "Empresa Manip A")
        self.assertNotContains(respuesta, "Empresa Manip B")


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="reset@example.com", password="clave-original-987"
        )

    def test_solicitar_reset_envia_correo_y_no_revela_si_el_email_no_existe(self):
        respuesta = self.client.post(
            reverse("accounts:password_reset"), {"email": "reset@example.com"}
        )
        self.assertRedirects(respuesta, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset@example.com", mail.outbox[0].to)

        mail.outbox.clear()
        respuesta_inexistente = self.client.post(
            reverse("accounts:password_reset"), {"email": "no-existe@example.com"}
        )
        # Misma redirección de "éxito" aunque el correo no exista: Django
        # no revela si una cuenta existe o no.
        self.assertRedirects(respuesta_inexistente, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_flujo_completo_de_reset_permite_iniciar_sesion_con_la_nueva_contrasena(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        # Django exige visitar primero la URL con el token "crudo" (la que
        # llega por correo); redirige a una segunda URL con un token
        # provisional guardado en sesión, desde donde ya se puede postear.
        url_inicial = reverse(
            "accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token}
        )
        respuesta_inicial = self.client.get(url_inicial)
        self.assertEqual(respuesta_inicial.status_code, 302)

        respuesta_form = self.client.get(respuesta_inicial.url)
        self.assertEqual(respuesta_form.status_code, 200)

        respuesta_post = self.client.post(
            respuesta_inicial.url,
            {"new_password1": "clave-nueva-987!", "new_password2": "clave-nueva-987!"},
        )
        self.assertRedirects(respuesta_post, reverse("accounts:password_reset_complete"))

        self.assertFalse(
            self.client.login(username="reset@example.com", password="clave-original-987")
        )
        self.assertTrue(
            self.client.login(username="reset@example.com", password="clave-nueva-987!")
        )

    def test_token_invalido_no_permite_cambiar_la_contrasena(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        url = reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": uid, "token": "token-invalido-000"},
        )
        respuesta = self.client.get(url, follow=True)
        self.assertContains(respuesta, "no es válido")


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="cambio@example.com", password="clave-original-987"
        )
        self.client.login(username="cambio@example.com", password="clave-original-987")

    def test_requiere_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(respuesta.status_code, 302)

    def test_cambio_exitoso_mantiene_la_sesion_activa(self):
        respuesta = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "clave-original-987",
                "new_password1": "clave-nueva-2024!",
                "new_password2": "clave-nueva-2024!",
            },
        )
        self.assertRedirects(respuesta, reverse("accounts:password_change_done"))

        # La sesión sigue activa (Django actualiza el hash de sesión tras
        # el cambio, en vez de forzar un logout).
        respuesta_perfil = self.client.get(reverse("accounts:perfil"))
        self.assertEqual(respuesta_perfil.status_code, 200)

    def test_rechaza_contrasena_actual_incorrecta(self):
        respuesta = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "esta-no-es-la-actual",
                "new_password1": "clave-nueva-2024!",
                "new_password2": "clave-nueva-2024!",
            },
        )
        self.assertFalse(respuesta.context["form"].is_valid())
