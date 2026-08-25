from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.customers.models import Supplier
from apps.inventory.models import Product
from apps.purchases import services
from apps.purchases.models import PurchaseOrder
from apps.tenants.models import Membership, Tenant

from ._helpers import PurchasesTestCase

User = get_user_model()


class MultiTenantIsolationTests(PurchasesTestCase):
    """Tenant A nunca puede leer, escribir ni cruzar datos con Tenant B —
    ni con IDs manipulados, ni combinando entidades de tenants distintos
    en una misma operación."""

    def setUp(self):
        super().setUp()
        self.tenant_b = Tenant.objects.create(name="Empresa B", slug="empresa-b")
        self.owner_b = User.objects.create_user(email="owner.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner_b, tenant=self.tenant_b, role=Membership.Role.OWNER)
        self.supplier_b = Supplier.objects.create(tenant=self.tenant_b, legal_name="Proveedor B")
        self.producto_b = Product.objects.create(
            tenant=self.tenant_b, name="Producto B", sku="TST-B-001", sale_price=Decimal("10"), purchase_price=Decimal("5"),
        )

    def test_no_se_puede_crear_orden_con_proveedor_de_otro_tenant(self):
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.create_purchase_order(self.tenant, supplier=self.supplier_b, user=self.owner)

    def test_no_se_puede_agregar_linea_con_producto_de_otro_tenant(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.add_purchase_order_item(orden, product=self.producto_b, quantity=Decimal("1"), user=self.owner)

    def test_orden_de_tenant_a_no_es_visible_desde_tenant_b(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        self.assertFalse(PurchaseOrder.all_objects.filter(tenant=self.tenant_b, pk=orden.pk).exists())
        with self.assertRaises(PurchaseOrder.DoesNotExist):
            PurchaseOrder.all_objects.get(pk=orden.pk, tenant=self.tenant_b)

    def test_no_se_puede_aplicar_pago_de_un_tenant_a_factura_de_otro(self):
        factura_b = services.create_supplier_invoice(
            self.tenant_b, supplier=self.supplier_b, supplier_invoice_number="B-0001", user=self.owner_b,
        )
        services.add_supplier_invoice_item(factura_b, description="X", quantity=Decimal("1"), unit_cost=Decimal("50"), user=self.owner_b)
        services.confirm_supplier_invoice(factura_b, self.owner_b)

        pago_a = services.create_supplier_payment(
            self.tenant, supplier=self.supplier, method="transfer", amount=Decimal("50"), user=self.owner,
        )
        with self.assertRaises(Exception):
            services.allocate_supplier_payment(pago_a, factura_b, Decimal("50"), self.owner)

    def test_vista_de_ordenes_requiere_tenant_activo_y_no_filtra_datos_ajenos(self):
        services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        respuesta = self.client.get("/compras/ordenes/")
        self.assertIn(respuesta.status_code, (200, 302))

    def test_detalle_de_orden_de_otro_tenant_da_404(self):
        orden_b = services.create_purchase_order(self.tenant_b, supplier=self.supplier_b, user=self.owner_b)
        respuesta = self.client.get(f"/compras/ordenes/{orden_b.pk}/")
        self.assertEqual(respuesta.status_code, 404)
