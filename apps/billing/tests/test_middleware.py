from django.test import TestCase
from django.urls import reverse

from apps.tenants.models import Tenant

from ._helpers_saas import crear_tenant_con_owner


class BillingStatusMiddlewareTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_tenant_activo_por_defecto_no_es_redirigido(self):
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertEqual(respuesta.status_code, 200)

    def test_tenant_suspendido_es_redirigido_al_portal_de_billing(self):
        self.tenant.billing_status = Tenant.BillingStatus.SUSPENDED
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertRedirects(respuesta, reverse("billing_portal:status"))

    def test_tenant_pending_payment_es_redirigido(self):
        self.tenant.billing_status = Tenant.BillingStatus.PENDING_PAYMENT
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertRedirects(respuesta, reverse("billing_portal:status"))

    def test_past_due_no_bloquea_operacion(self):
        self.tenant.billing_status = Tenant.BillingStatus.PAST_DUE
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertEqual(respuesta.status_code, 200)

    def test_tenant_bloqueado_puede_ver_su_propio_portal_de_billing(self):
        self.tenant.billing_status = Tenant.BillingStatus.SUSPENDED
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertEqual(respuesta.status_code, 200)

    def test_tenant_bloqueado_puede_ver_su_perfil_de_cuenta(self):
        self.tenant.billing_status = Tenant.BillingStatus.SUSPENDED
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("accounts:perfil"))
        self.assertEqual(respuesta.status_code, 200)

    def test_tenant_pending_setup_es_redirigido(self):
        # FASE DE CORRECCIÓN 3 (Lifecycle integral, sección "BillingStatusMiddleware"):
        # probar CADA estado explícitamente, no solo un subconjunto —
        # PENDING_SETUP nunca se había probado antes de esta corrección.
        self.tenant.billing_status = Tenant.BillingStatus.PENDING_SETUP
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertRedirects(respuesta, reverse("billing_portal:status"))

    def test_tenant_cancelado_es_redirigido(self):
        self.tenant.billing_status = Tenant.BillingStatus.CANCELLED
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertRedirects(respuesta, reverse("billing_portal:status"))

    def test_tenant_expirado_es_redirigido(self):
        self.tenant.billing_status = Tenant.BillingStatus.EXPIRED
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertRedirects(respuesta, reverse("billing_portal:status"))

    def test_tenant_bloqueado_puede_ver_el_formulario_de_cambio_de_plan(self):
        # Ningún estado debe dejar al tenant sin poder pagar/gestionar su
        # Billing — el propio Portal siempre queda accesible.
        self.tenant.billing_status = Tenant.BillingStatus.PAST_DUE
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertEqual(respuesta.status_code, 200)
        self.tenant.billing_status = Tenant.BillingStatus.SUSPENDED
        self.tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertEqual(respuesta.status_code, 200)

    def test_usuario_sin_tenant_nunca_es_redirigido_por_este_middleware(self):
        client = self.client_class()
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_user(email="sin.tenant@example.com", password="clave-de-prueba-987")
        client.login(username="sin.tenant@example.com", password="clave-de-prueba-987")
        respuesta = client.get(reverse("accounts:perfil"))
        self.assertEqual(respuesta.status_code, 200)
