"""
Utilidades compartidas por los tests de inventario (no es un módulo de
tests en sí: no empieza con "test", así que Django no lo ejecuta
directamente, solo se importa desde los demás archivos)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tenants.models import Membership, Tenant

User = get_user_model()


class InventoryTestCase(TestCase):
    """Crea un tenant con un usuario dueño ya autenticado, listo para
    probar cualquier vista de inventario."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Inventario", slug="empresa-inventario")
        self.user = User.objects.create_user(
            email="inventario@example.com", password="clave-de-prueba-987"
        )
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)
        self.client.login(username="inventario@example.com", password="clave-de-prueba-987")
