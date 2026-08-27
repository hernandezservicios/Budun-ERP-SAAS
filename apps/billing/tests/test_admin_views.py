from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.billing.models import BankAccount, PaymentProof, Plan, PlanVersion, Subscription, Tenant
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import subscriptions as subscription_services
from apps.billing.services import transfers as transfer_services

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
        self.assertEqual(tenant.billing_status, Tenant.BillingStatus.PENDING_SETUP)
        subscription = Subscription.all_objects.get(tenant=tenant)
        self.assertEqual(subscription.status, Subscription.Status.PENDING)
        self.assertRedirects(respuesta, reverse("billing_admin:tenant_detail", args=[tenant.pk]))


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
