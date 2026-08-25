"""Utilidades compartidas por los tests de FASE 12 (Compras) — mismo
patrón que `apps/pos/tests/_helpers.py`/`apps/sales/tests/_helpers.py`."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.models import Supplier
from apps.inventory.models import Product
from apps.pos.models import CashRegister
from apps.pos.services import open_cash_session
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class PurchasesTestCase(TestCase):
    """Tenant con un propietario, un comprador (MEMBER sin política de
    autorización especial), un proveedor, un producto por CANTIDAD y un
    producto SERIALIZADO — listo para probar cualquier flujo de Compras."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Compras", slug="empresa-compras")
        self.owner = User.objects.create_user(email="owner.compras@example.com", password="clave-de-prueba-987")
        self.comprador = User.objects.create_user(email="comprador@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.comprador, tenant=self.tenant, role=Membership.Role.MEMBER)

        self.supplier = Supplier.objects.create(
            tenant=self.tenant, legal_name="Proveedor Central SRL", currency="USD",
        )

        self.producto = Product.objects.create(
            tenant=self.tenant, name="Cable HDMI", sku="TST-COMP-CABLE",
            sale_price=Decimal("20.00"), purchase_price=Decimal("10.00"), tax_rate=Decimal("18"),
        )
        self.producto_serial = Product.objects.create(
            tenant=self.tenant, name="iPhone Compras", sku="TST-COMP-TEL",
            sale_price=Decimal("800.00"), purchase_price=Decimal("500.00"), tax_rate=Decimal("18"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )

        self.caja = CashRegister.all_objects.create(tenant=self.tenant, name="Caja Principal", code="CAJA-01")
        self.caja.authorized_users.add(self.owner, self.comprador)

        self.client.login(username="comprador@example.com", password="clave-de-prueba-987")
        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.compras@example.com", password="clave-de-prueba-987")

    def abrir_caja(self, user):
        return open_cash_session(self.tenant, cash_register=self.caja, user=user, opening_amount=Decimal("100"))
