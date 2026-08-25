"""Aislamiento Multi-Tenant de FASE 11 (POS/Caja/Cobros/Autorizaciones):
Tenant A nunca debe poder leer, modificar, abrir/cerrar caja, cobrar o
resolver autorizaciones de Tenant B, ni siquiera manipulando IDs."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.approvals import services as approvals_services
from apps.approvals.models import ApprovalRequest
from apps.customers.models import Customer
from apps.inventory import services as inv_services
from apps.inventory.models import Product
from apps.pos import services
from apps.pos.models import CashRegister, CashSession
from apps.sales import services as sales_services
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class PosIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="POS Tenant A", slug="pos-tenant-a")
        self.tenant_b = Tenant.objects.create(name="POS Tenant B", slug="pos-tenant-b")
        self.user_a = User.objects.create_user(email="pos.a@example.com", password="clave-de-prueba-987")
        self.user_b = User.objects.create_user(email="pos.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user_a, tenant=self.tenant_a, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.user_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

        self.producto_a = Product.objects.create(tenant=self.tenant_a, name="Producto A", sku="POS-ISO-A", sale_price=Decimal("10"))
        inv_services.register_stock_in(product=self.producto_a, quantity=Decimal("20"), user=self.user_a)
        self.customer_a = Customer.objects.create(tenant=self.tenant_a, first_name="Cliente A")

        self.caja_a = CashRegister.all_objects.create(tenant=self.tenant_a, name="Caja A", code="CAJA-A1")
        self.sesion_a = services.open_cash_session(self.tenant_a, cash_register=self.caja_a, user=self.user_a, opening_amount=Decimal("100"))
        self.sale_a = services.start_cart(self.tenant_a, user=self.user_a)
        services.add_item_to_cart(self.sale_a, product=self.producto_a, quantity=Decimal("1"), user=self.user_a, tenant=self.tenant_a)

        self.client_b = self.client_class()
        self.client_b.login(username="pos.b@example.com", password="clave-de-prueba-987")

    def test_tenant_b_no_ve_carrito_de_tenant_a(self):
        respuesta = self.client_b.get(reverse("pos:terminal_detail", args=[self.sale_a.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_tenant_b_no_puede_agregar_items_al_carrito_de_tenant_a(self):
        respuesta = self.client_b.post(reverse("pos:add_item", args=[self.sale_a.pk]), {
            "product_id": self.producto_a.pk, "quantity": "1", "unit_identifier": "", "discount_percent": "", "discount_amount": "",
        })
        self.assertEqual(respuesta.status_code, 404)

    def test_tenant_b_no_puede_cobrar_carrito_de_tenant_a(self):
        respuesta = self.client_b.post(reverse("pos:checkout", args=[self.sale_a.pk]), {
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "0", "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-method": "cash", "form-0-amount": "10",
        })
        self.assertEqual(respuesta.status_code, 404)

    def test_tenant_b_no_puede_ver_cobros_de_cliente_de_tenant_a(self):
        respuesta = self.client_b.get(reverse("pos:customer_collections", args=[self.customer_a.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_allocate_credit_note_rechaza_cross_tenant_a_nivel_de_servicio(self):
        nota_a = sales_services.create_credit_note(self.tenant_a, customer=self.customer_a, amount=Decimal("10"), user=self.user_a)
        nota_a = sales_services.issue_credit_note(nota_a, self.user_a)

        venta_b = sales_services.create_sale(self.tenant_b, user=self.user_b)
        with self.assertRaises(sales_services.InvalidSalesOperation):
            sales_services.apply_credit_note(nota_a, venta_b, Decimal("1"), self.user_b)

    def test_approval_request_de_tenant_a_no_resoluble_por_tenant_b(self):
        solicitud = approvals_services.request_approval(
            self.tenant_a, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.user_a,
            requested_value=Decimal("10"), document_type="sale", document_id=self.sale_a.pk,
        )
        # can_user_approve exige tenant explícito — un usuario de otro tenant nunca "puede aprobar" en el tenant ajeno.
        self.assertFalse(approvals_services.can_user_approve(self.tenant_a, self.user_b))

    def test_tenant_b_no_puede_abrir_sesion_en_caja_de_tenant_a(self):
        respuesta = self.client_b.post(reverse("pos:session_open"), {
            "cash_register": self.caja_a.pk, "opening_amount": "50", "notes": "",
        })
        # El formulario filtra las cajas por tenant, así que la caja de A
        # no aparece en el queryset del usuario B -> formulario inválido.
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(CashSession.all_objects.filter(tenant=self.tenant_a, cash_register=self.caja_a, user=self.user_b).exists())
