from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.approvals import services
from apps.approvals.models import ApprovalRequest
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class ApprovalsIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Approvals Tenant A", slug="approvals-tenant-a")
        self.tenant_b = Tenant.objects.create(name="Approvals Tenant B", slug="approvals-tenant-b")
        self.owner_a = User.objects.create_user(email="appr.a@example.com", password="clave-de-prueba-987")
        self.owner_b = User.objects.create_user(email="appr.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner_a, tenant=self.tenant_a, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.owner_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

        self.solicitud_a = services.request_approval(
            self.tenant_a, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.owner_a, requested_value=Decimal("10"),
        )
        self.client_b = self.client_class()
        self.client_b.login(username="appr.b@example.com", password="clave-de-prueba-987")

    def test_tenant_b_no_puede_resolver_solicitud_de_tenant_a(self):
        respuesta = self.client_b.post(reverse("approvals:approval_resolve", args=[self.solicitud_a.pk]), {"decision": "approve"})
        self.assertEqual(respuesta.status_code, 404)
        self.solicitud_a.refresh_from_db()
        self.assertEqual(self.solicitud_a.status, ApprovalRequest.Status.PENDING)

    def test_pending_list_no_mezcla_tenants(self):
        pendientes_b = services.get_pending_requests(self.tenant_b)
        self.assertNotIn(self.solicitud_a, list(pendientes_b))

    def test_get_effective_policy_no_cruza_tenants(self):
        services.set_role_policy(
            self.tenant_a, role="owner", max_discount_percent=Decimal("50"), max_discount_amount=Decimal("500"),
            max_credit_overage=Decimal("0"), can_approve=True,
        )
        # owner_b es OWNER de tenant_b, no debe heredar la política de tenant_a.
        politica_b = services.get_effective_policy(self.tenant_b, self.owner_b)
        self.assertIsNone(politica_b)
