import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.billing.models import BankAccount, PaymentProof, Plan, PlanVersion, SaaSInvoice, SaaSPayment, SaaSPaymentAllocation, Subscription, Tenant
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import subscriptions as subscription_services
from apps.billing.services import transfers as transfer_services
from apps.tenants.models import Membership

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner

User = get_user_model()


class AdminAccessTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.superadmin = User.objects.create_superuser(email="super.admin.billing@example.com", password="clave-de-prueba-987")

    def test_owner_normal_no_puede_ver_el_dashboard_de_plataforma(self):
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        self.assertEqual(respuesta.status_code, 403)

    def test_superadmin_ve_el_dashboard(self):
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        self.assertEqual(respuesta.status_code, 200)


class ManualTenantSaleViewTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.venta@example.com", password="clave-de-prueba-987")
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_venta_manual_crea_tenant_membresia_y_suscripcion_pendiente(self):
        respuesta = self.client.post(reverse("billing_admin:manual_sale"), {
            "customer_name": "Cliente Manual", "customer_email": "cliente.manual@example.com",
            "tenant_name": "Empresa Manual", "plan_version": self.version.pk,
            "owner_email": "owner.manual@example.com",
        })
        tenant = Tenant.objects.get(slug="empresa-manual")
        # Gate Local (KNOWN_ISSUES.md): la venta manual deja al tenant en
        # PENDING_PAYMENT (ya existe una factura real esperando pago),
        # nunca en PENDING_SETUP a secas ni en ACTIVE sin pago aprobado.
        self.assertEqual(tenant.billing_status, Tenant.BillingStatus.PENDING_PAYMENT)
        subscription = Subscription.all_objects.get(tenant=tenant)
        self.assertEqual(subscription.status, Subscription.Status.PENDING)
        self.assertRedirects(respuesta, reverse("billing_admin:tenant_detail", args=[tenant.pk]))

    def test_venta_manual_genera_la_primera_saasinvoice(self):
        """Hallazgo real del Gate Local: ManualTenantSaleView creaba la
        Subscription pero nunca generaba su primera SaaSInvoice — el
        tenant quedaba "pendiente de pago" sin ninguna factura real."""
        self.client.post(reverse("billing_admin:manual_sale"), {
            "customer_name": "Cliente Manual 2", "customer_email": "cliente.manual2@example.com",
            "tenant_name": "Empresa Manual Dos", "plan_version": self.version.pk,
            "owner_email": "owner.manual2@example.com",
        })
        tenant = Tenant.objects.get(slug="empresa-manual-dos")
        subscription = Subscription.all_objects.get(tenant=tenant)
        facturas = SaaSInvoice.all_objects.filter(subscription=subscription)
        self.assertEqual(facturas.count(), 1)
        factura = facturas.first()
        self.assertEqual(factura.status, SaaSInvoice.Status.OPEN)
        self.assertEqual(factura.total, Decimal("29.00"))

    def test_owner_creado_con_password_inutilizable_y_recibe_correo_de_activacion(self):
        """FASE DE CORRECCIÓN 1 (Acceso del Owner y ciclo de vida del
        Tenant): el Owner que Venta Manual crea automáticamente no debe
        poder iniciar sesión hasta activar su cuenta, y debe recibir un
        correo real con el enlace de activación."""
        mail.outbox.clear()
        self.client.post(reverse("billing_admin:manual_sale"), {
            "customer_name": "Cliente Manual 3", "customer_email": "cliente.manual3@example.com",
            "tenant_name": "Empresa Manual Tres", "plan_version": self.version.pk,
            "owner_email": "owner.manual3@example.com",
        })
        owner = User.objects.get(email="owner.manual3@example.com")
        self.assertFalse(owner.has_usable_password())

        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertIn("owner.manual3@example.com", correo.to)
        self.assertRegex(correo.body, r"https?://\S+/cuentas/activacion/\S+/\S+/")


class OwnerActivationFlowTests(TestCase):
    """FASE DE CORRECCIÓN 1 — Acceso del Owner y ciclo de vida del
    Tenant: cierra el flujo completo "Super Admin crea Tenant → Owner
    activa su cuenta → Owner inicia sesión → Owner accede a SU Tenant",
    de punta a punta vía HTTP real (incluido el correo real enviado por
    `ManualTenantSaleView`), sin crear nunca un segundo `User`."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            email="super.activacion@example.com", password="clave-de-prueba-987"
        )
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

        mail.outbox.clear()
        self.client.post(reverse("billing_admin:manual_sale"), {
            "customer_name": "Cliente Activación", "customer_email": "cliente.activacion@example.com",
            "tenant_name": "Empresa Activación", "plan_version": self.version.pk,
            "owner_email": "owner.activacion@example.com",
        })
        self.tenant = Tenant.objects.get(slug="empresa-activacion")
        self.owner = User.objects.get(email="owner.activacion@example.com")
        self.activation_url = re.search(r"https?://\S+/cuentas/activacion/\S+/\S+/", mail.outbox[0].body).group(0)
        self.client.logout()

    def _seguir_hasta_formulario(self, url):
        """Reproduce el patrón real de `PasswordResetConfirmView`: la
        primera visita con el token "crudo" redirige a una segunda URL
        con un token provisional guardado en sesión, desde donde ya se
        puede postear la nueva contraseña."""
        respuesta_inicial = self.client.get(url)
        self.assertEqual(respuesta_inicial.status_code, 302)
        return respuesta_inicial.url

    def test_activacion_valida_permite_iniciar_sesion_y_acceder_al_tenant_correcto(self):
        url_formulario = self._seguir_hasta_formulario(self.activation_url)
        respuesta_form = self.client.get(url_formulario)
        self.assertEqual(respuesta_form.status_code, 200)

        respuesta_post = self.client.post(url_formulario, {
            "new_password1": "clave-owner-activada-1!", "new_password2": "clave-owner-activada-1!",
        })
        self.assertRedirects(respuesta_post, reverse("accounts:activacion_completada"))

        self.owner.refresh_from_db()
        self.assertTrue(self.owner.has_usable_password())

        # Login posterior con la contraseña recién elegida.
        self.assertTrue(self.client.login(
            username="owner.activacion@example.com", password="clave-owner-activada-1!"
        ))

        # Acceso al Tenant correcto (no a otro, no a ninguno): una URL
        # bajo /cuentas/ (fuera del alcance de BillingStatusMiddleware,
        # que solo bloquea rutas operativas del ERP cuando el tenant no
        # está ACTIVE/PAST_DUE — no es lo que se corrige en esta fase)
        # confirma que TenantMiddleware resolvió exactamente ESTE
        # Tenant vía la Membership OWNER real.
        respuesta_perfil = self.client.get(reverse("accounts:perfil"))
        self.assertEqual(respuesta_perfil.status_code, 200)
        self.assertEqual(respuesta_perfil.context["tenant"], self.tenant)
        self.assertEqual(respuesta_perfil.context["membership"].role, Membership.Role.OWNER)
        self.assertEqual(respuesta_perfil.context["membership"].tenant_id, self.tenant.pk)

    def test_token_expirado_no_permite_activar(self):
        # PASSWORD_RESET_TIMEOUT negativo: cualquier token, sin importar
        # qué tan reciente, queda fuera de ventana — misma mecánica que
        # Django usa internamente (segundos transcurridos > TIMEOUT),
        # sin necesitar viajar en el tiempo de verdad.
        #
        # FASE DE CORRECCIÓN 1B: desde esta corrección, un token expirado
        # muestra una pantalla ESPECÍFICA ("...ha expirado") en vez del
        # genérico "no es válido" que sigue cubriendo el resto de los
        # casos (adulterado, de otro usuario, ya usado) — ver
        # `apps.accounts.services.classify_activation_token`.
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            respuesta = self.client.get(self.activation_url, follow=True)
        self.assertContains(respuesta, "ha expirado")
        self.assertContains(respuesta, reverse("accounts:activacion_reenviar"))
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.has_usable_password())

    def test_token_reutilizado_tras_activar_ya_no_funciona(self):
        url_formulario = self._seguir_hasta_formulario(self.activation_url)
        self.client.post(url_formulario, {
            "new_password1": "clave-owner-activada-1!", "new_password2": "clave-owner-activada-1!",
        })

        # Reutilizar el enlace ORIGINAL (el que llegó por correo) tras
        # ya haber activado la cuenta: cambiar la contraseña cambió el
        # hash del que depende el token, así que el mismo enlace nunca
        # vuelve a funcionar.
        respuesta = self.client.get(self.activation_url, follow=True)
        self.assertContains(respuesta, "no es válido")

    def test_token_invalido_no_permite_activar(self):
        base, _token_real = self.activation_url.rstrip("/").rsplit("/", 1)
        url_con_token_invalido = f"{base}/token-invalido-000/"
        respuesta = self.client.get(url_con_token_invalido, follow=True)
        self.assertContains(respuesta, "no es válido")

    def test_password_corta_es_rechazada_en_activacion(self):
        url_formulario = self._seguir_hasta_formulario(self.activation_url)
        respuesta = self.client.post(url_formulario, {
            "new_password1": "corta1", "new_password2": "corta1",
        })
        self.assertFalse(respuesta.context["form"].is_valid())
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.has_usable_password())

    def test_no_se_duplica_el_user_al_reintentar_registro_publico_con_el_mismo_correo(self):
        respuesta = self.client.post(reverse("accounts:registro"), {
            "email": "owner.activacion@example.com", "first_name": "Owner", "last_name": "Duplicado",
            "password1": "otra-clave-cualquiera-1!", "password2": "otra-clave-cualquiera-1!",
        })
        self.assertFalse(respuesta.context["form"].is_valid())
        self.assertEqual(User.objects.filter(email="owner.activacion@example.com").count(), 1)
        # Sigue sin poder iniciar sesión: el intento de registro público
        # nunca le puso una contraseña utilizable a escondidas.
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.has_usable_password())


class OwnerRegistroLoginResendUxTests(TestCase):
    """FASE DE CORRECCIÓN 1B — Activación desde Registro/Login: los
    mismos escenarios de `OwnerActivationFlowTests`, pero llegando por
    las pantallas normales de Registro/Login en vez del correo original
    de Venta Manual, y con DOS tenants/Owners reales para probar
    aislamiento (Escenario 6)."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            email="super.registro.login@example.com", password="clave-de-prueba-987"
        )
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

        mail.outbox.clear()
        self.client.post(reverse("billing_admin:manual_sale"), {
            "customer_name": "Cliente Uno", "customer_email": "cliente.uno.rlu@example.com",
            "tenant_name": "Empresa RLU Uno", "plan_version": self.version.pk,
            "owner_email": "owner.uno.rlu@example.com",
        })
        self.client.post(reverse("billing_admin:manual_sale"), {
            "customer_name": "Cliente Dos", "customer_email": "cliente.dos.rlu@example.com",
            "tenant_name": "Empresa RLU Dos", "plan_version": self.version.pk,
            "owner_email": "owner.dos.rlu@example.com",
        })
        self.tenant_uno = Tenant.objects.get(slug="empresa-rlu-uno")
        self.tenant_dos = Tenant.objects.get(slug="empresa-rlu-dos")
        self.owner_uno = User.objects.get(email="owner.uno.rlu@example.com")
        self.owner_dos = User.objects.get(email="owner.dos.rlu@example.com")
        self.client.logout()
        mail.outbox.clear()

    def _activar(self, client, email, password):
        client.post(reverse("accounts:activacion_reenviar"), {"email": email})
        url = re.search(r"https?://\S+/cuentas/activacion/\S+/\S+/", mail.outbox[-1].body).group(0)
        respuesta_inicial = client.get(url)
        client.post(respuesta_inicial.url, {"new_password1": password, "new_password2": password})

    def test_registro_con_email_de_owner_de_venta_manual_ofrece_activar_sin_duplicar_user(self):
        respuesta = self.client.post(reverse("accounts:registro"), {
            "email": "owner.uno.rlu@example.com", "first_name": "Owner", "last_name": "Duplicado",
            "password1": "otra-clave-cualquiera-1!", "password2": "otra-clave-cualquiera-1!",
        })
        self.assertFalse(respuesta.context["form"].is_valid())
        self.assertContains(respuesta, "Activa tu cuenta")
        self.assertContains(respuesta, reverse("accounts:activacion_reenviar"))
        self.assertEqual(User.objects.filter(email="owner.uno.rlu@example.com").count(), 1)

    def test_login_con_email_de_owner_de_venta_manual_ofrece_reenviar_activacion(self):
        respuesta = self.client.post(reverse("accounts:login"), {
            "username": "owner.uno.rlu@example.com", "password": "lo-que-sea",
        })
        self.assertContains(respuesta, "todavía no activó")
        self.assertContains(respuesta, "Reenviar enlace de activación")

    def test_reenvio_tras_venta_manual_permite_activar_y_acceder_solo_a_su_propio_tenant(self):
        respuesta_reenvio = self.client.post(
            reverse("accounts:activacion_reenviar"), {"email": "owner.uno.rlu@example.com"}
        )
        self.assertRedirects(respuesta_reenvio, reverse("accounts:activacion_reenviada"))
        self.assertEqual(len(mail.outbox), 1)

        match = re.search(r"https?://\S+/cuentas/activacion/\S+/\S+/", mail.outbox[0].body)
        respuesta_inicial = self.client.get(match.group(0))
        self.client.post(respuesta_inicial.url, {
            "new_password1": "clave-rlu-uno-987!", "new_password2": "clave-rlu-uno-987!",
        })

        self.assertTrue(self.client.login(username="owner.uno.rlu@example.com", password="clave-rlu-uno-987!"))
        respuesta_perfil = self.client.get(reverse("accounts:perfil"))
        self.assertEqual(respuesta_perfil.context["tenant"], self.tenant_uno)
        self.assertEqual(respuesta_perfil.context["membership"].role, Membership.Role.OWNER)

    def test_dos_owners_de_venta_manual_activados_quedan_completamente_aislados_entre_si(self):
        cliente_uno = Client()
        cliente_dos = Client()
        self._activar(cliente_uno, "owner.uno.rlu@example.com", "clave-rlu-uno-987!")
        self._activar(cliente_dos, "owner.dos.rlu@example.com", "clave-rlu-dos-987!")

        self.assertTrue(cliente_uno.login(username="owner.uno.rlu@example.com", password="clave-rlu-uno-987!"))
        self.assertTrue(cliente_dos.login(username="owner.dos.rlu@example.com", password="clave-rlu-dos-987!"))

        perfil_uno = cliente_uno.get(reverse("accounts:perfil"))
        perfil_dos = cliente_dos.get(reverse("accounts:perfil"))
        self.assertEqual(perfil_uno.context["tenant"], self.tenant_uno)
        self.assertEqual(perfil_dos.context["tenant"], self.tenant_dos)
        self.assertNotEqual(perfil_uno.context["tenant"], perfil_dos.context["tenant"])

        # Ningún Membership cruzó de un Owner al otro.
        self.assertEqual(Membership.objects.filter(user=self.owner_uno, tenant=self.tenant_dos).count(), 0)
        self.assertEqual(Membership.objects.filter(user=self.owner_dos, tenant=self.tenant_uno).count(), 0)


class TenantLifecycleAdminViewTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.lifecycle@example.com", password="clave-de-prueba-987")
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_suspender_desde_admin(self):
        self.client.post(reverse("billing_admin:tenant_detail", args=[self.tenant.pk]), {"accion": "suspender"})
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.SUSPENDED)

    def test_reactivar_desde_admin(self):
        self.client.post(reverse("billing_admin:tenant_detail", args=[self.tenant.pk]), {"accion": "suspender"})
        self.client.post(reverse("billing_admin:tenant_detail", args=[self.tenant.pk]), {"accion": "reactivar"})
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)


class ActivateVsReactivateAdminViewTests(TestCase):
    """Gate Local (KNOWN_ISSUES.md): ACTIVATE != REACTIVATE — dos
    acciones distintas, con guardas distintas, nunca intercambiables."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.activar@example.com", password="clave-de-prueba-987")
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def _post_accion(self, accion):
        return self.client.post(reverse("billing_admin:tenant_detail", args=[self.tenant.pk]), {"accion": accion})

    def test_activar_desde_admin_activa_subscription_y_tenant_con_evidencia_real(self):
        respuesta = self._post_accion("activar")
        self.assertRedirects(respuesta, reverse("billing_admin:tenant_detail", args=[self.tenant.pk]))

        self.subscription.refresh_from_db()
        self.tenant.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(self.subscription.current_period_start)
        self.assertIsNotNone(self.subscription.current_period_end)
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)

        # "Activar" nunca activa sin dejar evidencia real de pago.
        factura = SaaSInvoice.all_objects.get(subscription=self.subscription)
        self.assertEqual(factura.status, SaaSInvoice.Status.PAID)
        pago = SaaSPayment.all_objects.get(subscription=self.subscription)
        self.assertEqual(pago.method, SaaSPayment.Method.MANUAL_OTHER)
        self.assertEqual(pago.status, SaaSPayment.Status.CONFIRMED)
        self.assertEqual(SaaSPaymentAllocation.all_objects.filter(payment=pago).count(), 1)

    def test_activar_es_idempotente_ante_doble_clic(self):
        self._post_accion("activar")
        self._post_accion("activar")
        self.assertEqual(SaaSInvoice.all_objects.filter(subscription=self.subscription).count(), 1)
        self.assertEqual(SaaSPayment.all_objects.filter(subscription=self.subscription).count(), 1)
        self.assertEqual(SaaSPaymentAllocation.all_objects.filter(payment__subscription=self.subscription).count(), 1)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)

    def test_activar_sin_subscription_muestra_error_amigable_no_500(self):
        tenant_sin_subscription, _owner = crear_tenant_con_owner(name="Sin Suscripción", slug="sin-suscripcion", email="sin.sub@example.com")
        respuesta = self.client.post(
            reverse("billing_admin:tenant_detail", args=[tenant_sin_subscription.pk]), {"accion": "activar"}
        )
        self.assertEqual(respuesta.status_code, 302)  # nunca un 500
        respuesta_seguida = self.client.get(respuesta.url)
        self.assertContains(respuesta_seguida, "no tiene ninguna suscripción")

    def test_reactivar_sobre_subscription_pending_muestra_error_amigable_no_500(self):
        """Hallazgo real del Gate Local: antes de este fix, "Reactivar"
        sobre una Subscription PENDING lanzaba InvalidSubscriptionOperation
        sin capturar -> error 500 sin manejar."""
        respuesta = self._post_accion("reactivar")
        self.assertEqual(respuesta.status_code, 302)  # nunca un 500
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.PENDING)
        respuesta_seguida = self.client.get(respuesta.url)
        self.assertContains(respuesta_seguida, "Solo se puede reactivar")

    def test_activar_no_reutiliza_reactivar_para_suspendida(self):
        """Lo inverso también debe respetarse: una Subscription SUSPENDED
        no se "activa" con la acción activar (que exige PENDING) — debe
        usarse reactivar."""
        subscription_services.activate_subscription(self.subscription)
        subscription_services.suspend_subscription(self.subscription)
        respuesta = self._post_accion("activar")
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.SUSPENDED)
        respuesta_seguida = self.client.get(respuesta.url)
        self.assertContains(respuesta_seguida, "Solo se puede ACTIVAR una suscripción pendiente")


class ProofApprovalAdminViewTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.proof@example.com", password="clave-de-prueba-987")
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        self.subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        self.bank_account = BankAccount.objects.create(
            bank_name="Banco X", country="RD", currency="USD", account_holder="Budun ERP", account_number="0000",
        )
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.proof = transfer_services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD",
            file=SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_aprobar_desde_admin_activa_todo(self):
        respuesta = self.client.post(reverse("billing_admin:proof_detail", args=[self.proof.pk]), {"accion": "aprobar"})
        self.assertRedirects(respuesta, reverse("billing_admin:proof_detail", args=[self.proof.pk]))
        self.proof.refresh_from_db()
        self.assertEqual(self.proof.status, PaymentProof.Status.APPROVED)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)

    def test_rechazar_desde_admin(self):
        respuesta = self.client.post(reverse("billing_admin:proof_detail", args=[self.proof.pk]), {"accion": "rechazar", "reason": "no coincide"})
        self.assertEqual(respuesta.status_code, 302)
        self.proof.refresh_from_db()
        self.assertEqual(self.proof.status, PaymentProof.Status.REJECTED)


class PlanManagementViewTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.plans@example.com", password="clave-de-prueba-987")
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_crear_plan_y_version(self):
        self.client.post(reverse("billing_admin:plans_list"), {
            "name": "Plan Nuevo", "slug": "plan-nuevo", "description": "", "is_active": "on", "sort_order": 0,
            "max_users": "", "max_products": "", "features": "[]",
        })
        plan = Plan.objects.get(slug="plan-nuevo")
        self.client.post(reverse("billing_admin:plan_version_create", args=[plan.pk]), {
            "frequency": "monthly", "price_amount": "15.00", "price_currency": "USD",
        })
        self.assertTrue(PlanVersion.objects.filter(plan=plan, is_current=True).exists())
