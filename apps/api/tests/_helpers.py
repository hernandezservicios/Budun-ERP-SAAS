from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.api import integration_services, services
from apps.api.models import Integration
from apps.inventory import services as inv_services
from apps.inventory.models import Category, Product
from apps.tenants.models import Membership, Tenant

User = get_user_model()

TODOS_LOS_SCOPES = [
    "health:read", "products:read", "categories:read",
    "inventory:read", "inventory_movements:read", "serialized_inventory:read",
]

TODOS_LOS_SCOPES_CATALOG = ["catalog:read", "catalog:availability:read", "catalog:media:read"]


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


class IntegrationTestCase(TestCase):
    """Fixture para la Catalog API (ampliación final de FASE 15) — un
    tenant con un producto (con marca/modelo/variantes) y una
    `Integration` ya creada con todos los scopes de catálogo."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Catalog", slug="empresa-catalog")
        self.owner = User.objects.create_user(email="owner.catalog@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)

        self.categoria = Category.objects.create(tenant=self.tenant, name="Categoría Catalog")
        self.producto = Product.objects.create(
            tenant=self.tenant, name="Teléfono Catalog", sku="CAT-1", barcode="7509876543210",
            category=self.categoria, sale_price=Decimal("500.00"), tax_rate=Decimal("18"),
            brand="Marca", model_name="Modelo X", variant_attributes={"color": "Negro"},
        )
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("7"), user=self.owner)

        self.integration, self.secreto = integration_services.create_integration(
            self.tenant, user=self.owner, name="Integración de prueba",
            provider=Integration.Provider.BUDUN, scopes=TODOS_LOS_SCOPES_CATALOG,
        )

        self.owner_client = self.client_class()
        self.owner_client.login(username="owner.catalog@example.com", password="clave-de-prueba-987")

    def auth_headers(self, secreto=None):
        return {"HTTP_AUTHORIZATION": f"Bearer {secreto if secreto is not None else self.secreto}"}
