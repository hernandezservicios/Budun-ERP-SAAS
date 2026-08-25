from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tenants.models import Membership, Tenant

User = get_user_model()


class ApprovalsTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Autorizaciones", slug="empresa-autorizaciones")
        self.owner = User.objects.create_user(email="owner.approvals@example.com", password="clave-de-prueba-987")
        self.member = User.objects.create_user(email="member.approvals@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.member, tenant=self.tenant, role=Membership.Role.MEMBER)
        self.client.login(username="member.approvals@example.com", password="clave-de-prueba-987")
        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.approvals@example.com", password="clave-de-prueba-987")
