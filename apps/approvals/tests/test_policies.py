from decimal import Decimal

from apps.approvals import services
from apps.approvals.models import ApprovalPolicy

from ._helpers import ApprovalsTestCase


class PolicyHierarchyTests(ApprovalsTestCase):
    def test_sin_ninguna_politica_devuelve_none(self):
        self.assertIsNone(services.get_effective_policy(self.tenant, self.member))

    def test_politica_de_rol_se_usa_cuando_no_hay_politica_de_usuario(self):
        politica = ApprovalPolicy.all_objects.create(
            tenant=self.tenant, scope=ApprovalPolicy.Scope.ROLE, role="member",
            max_discount_percent=Decimal("10"), max_discount_amount=Decimal("100"), max_credit_overage=Decimal("0"),
        )
        self.assertEqual(services.get_effective_policy(self.tenant, self.member), politica)

    def test_politica_de_usuario_tiene_prioridad_sobre_la_de_rol(self):
        ApprovalPolicy.all_objects.create(
            tenant=self.tenant, scope=ApprovalPolicy.Scope.ROLE, role="member",
            max_discount_percent=Decimal("10"), max_discount_amount=Decimal("100"), max_credit_overage=Decimal("0"),
        )
        politica_usuario = ApprovalPolicy.all_objects.create(
            tenant=self.tenant, scope=ApprovalPolicy.Scope.USER, user=self.member,
            max_discount_percent=Decimal("25"), max_discount_amount=Decimal("500"), max_credit_overage=Decimal("0"),
        )
        self.assertEqual(services.get_effective_policy(self.tenant, self.member), politica_usuario)

    def test_politica_de_tenant_se_usa_cuando_no_hay_rol_ni_usuario(self):
        politica_tenant = ApprovalPolicy.all_objects.create(
            tenant=self.tenant, scope=ApprovalPolicy.Scope.TENANT,
            max_discount_percent=Decimal("2"), max_discount_amount=Decimal("20"), max_credit_overage=Decimal("0"),
        )
        self.assertEqual(services.get_effective_policy(self.tenant, self.member), politica_tenant)

    def test_propietario_no_necesita_politica_para_estar_autorizado(self):
        autorizado, limite_percent, limite_amount = services.check_discount_authorization(
            self.tenant, self.owner, percent=Decimal("100"), amount=Decimal("999999")
        )
        self.assertTrue(autorizado)

    def test_can_user_approve_propietario_siempre_true(self):
        self.assertTrue(services.can_user_approve(self.tenant, self.owner))

    def test_can_user_approve_miembro_sin_politica_false(self):
        self.assertFalse(services.can_user_approve(self.tenant, self.member))

    def test_can_user_approve_miembro_con_politica_can_approve(self):
        ApprovalPolicy.all_objects.create(
            tenant=self.tenant, scope=ApprovalPolicy.Scope.ROLE, role="member",
            max_discount_percent=Decimal("0"), max_discount_amount=Decimal("0"), max_credit_overage=Decimal("0"),
            can_approve=True,
        )
        self.assertTrue(services.can_user_approve(self.tenant, self.member))

    def test_set_role_policy_es_upsert(self):
        services.set_role_policy(
            self.tenant, role="member", max_discount_percent=Decimal("5"), max_discount_amount=Decimal("50"),
            max_credit_overage=Decimal("0"), can_approve=False,
        )
        services.set_role_policy(
            self.tenant, role="member", max_discount_percent=Decimal("15"), max_discount_amount=Decimal("150"),
            max_credit_overage=Decimal("0"), can_approve=True,
        )
        self.assertEqual(ApprovalPolicy.all_objects.filter(tenant=self.tenant, scope="role", role="member").count(), 1)
        politica = ApprovalPolicy.all_objects.get(tenant=self.tenant, scope="role", role="member")
        self.assertEqual(politica.max_discount_percent, Decimal("15.00"))
        self.assertTrue(politica.can_approve)
