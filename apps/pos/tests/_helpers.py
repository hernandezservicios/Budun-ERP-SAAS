"""Utilidades compartidas por los tests de FASE 11 (POS/Caja/Cobros/
Autorizaciones) — mismo patrón que `apps/sales/tests/_helpers.py`."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.models import Customer
from apps.inventory import services as inv_services
from apps.inventory.models import Product
from apps.pos.models import CashRegister
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class PosTestCase(TestCase):
    """Tenant con un propietario, un cajero (MEMBER autorizado en la
    caja principal), un cliente, un producto por CANTIDAD con stock, un
    producto SERIALIZADO con una unidad EN_STOCK, y una caja activa —
    listo para probar cualquier flujo de POS/Caja."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa POS", slug="empresa-pos")
        self.owner = User.objects.create_user(email="owner.pos@example.com", password="clave-de-prueba-987")
        self.cajero = User.objects.create_user(email="cajero.pos@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        # CASHIER (FASE 15): antes de los roles granulares, "cajero" solo
        # podía expresarse como MEMBER — CASHIER es el rol que realmente
        # describe a este usuario (trae `cash.open`/`cash.close`/
        # `cash.move`/`pos.use`/`sales.create` por defecto, ver
        # `apps.permissions.catalog`), así que se usa aquí.
        Membership.objects.create(user=self.cajero, tenant=self.tenant, role=Membership.Role.CASHIER)

        self.customer = Customer.objects.create(
            tenant=self.tenant, first_name="Cliente", last_name="POS",
            credit_enabled=True, credit_limit=Decimal("10000"),
        )

        self.producto = Product.objects.create(
            tenant=self.tenant, name="Cable HDMI", sku="TST-POS-CABLE", sale_price=Decimal("20.00"), tax_rate=Decimal("18"),
        )
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("100"), user=self.owner)

        self.producto_serial = Product.objects.create(
            tenant=self.tenant, name="iPhone POS", sku="TST-POS-TEL", sale_price=Decimal("800.00"), tax_rate=Decimal("18"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.unidad = inv_services.register_serialized_unit(
            product=self.producto_serial, user=self.owner, imei_1="111222333444555"
        )

        self.caja = CashRegister.all_objects.create(tenant=self.tenant, name="Caja Principal", code="CAJA-01")
        self.caja.authorized_users.add(self.cajero)

        self.client.login(username="cajero.pos@example.com", password="clave-de-prueba-987")
        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.pos@example.com", password="clave-de-prueba-987")
