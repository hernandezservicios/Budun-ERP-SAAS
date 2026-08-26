from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.api import services
from apps.inventory import services as inv_services
from apps.inventory.models import Category, Product
from apps.tenants.models import Membership, Tenant

User = get_user_model()

TODOS_LOS_SCOPES = [
    "health:read", "products:read", "categories:read",
    "inventory:read", "inventory_movements:read", "serialized_inventory:read",
]


class ApiTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa API", slug="empresa-api")
        self.owner = User.objects.create_user(email="owner.api@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)

        self.categoria = Category.objects.create(tenant=self.tenant, name="Categoría API")
        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto API", sku="API-1", barcode="7501234567890",
            category=self.categoria, sale_price=Decimal("25.00"), tax_rate=Decimal("18"), min_stock=Decimal("5"),
        )
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner)

        self.api_key, self.secreto = services.generate_api_key(self.tenant, user=self.owner, scopes=TODOS_LOS_SCOPES)

        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.api@example.com", password="clave-de-prueba-987")

    def auth_headers(self, secreto=None):
        return {"HTTP_AUTHORIZATION": f"Bearer {secreto if secreto is not None else self.secreto}"}
