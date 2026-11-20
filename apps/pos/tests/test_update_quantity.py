"""HTTP — edición de cantidad de línea en el carrito POS (FASE 7 —
BLOQUE A). Prueba únicamente la capa HTTP (permiso `pos.use`, tenant,
estado de venta, validación de entrada, línea serializada) — el
comportamiento matemático de `update_sale_item_quantity` (incluido el
clamp heredado de A0.1) ya está cubierto en
`apps/sales/tests/test_sales.py::SaleItemQuantityUpdateTests`."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.pos import services
from apps.sales import services as sales_services
from apps.sales.models import Sale
from apps.tenants.models import Membership, Tenant

from ._helpers import PosTestCase

User = get_user_model()


class UpdateItemQuantityHttpTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = User.objects.create_user(email="empleado.cantidad@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.empleado, tenant=self.tenant, role=Membership.Role.EMPLOYEE)
        self.empleado_client = self.client_class()
        self.empleado_client.login(username="empleado.cantidad@example.com", password="clave-de-prueba-987")

    def test_post_exitoso_actualiza_la_cantidad(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("2"), user=self.cajero, tenant=self.tenant)
        respuesta = self.client.post(reverse("pos:update_item_quantity", args=[sale.pk, item.pk]), {"quantity": "5"})
        self.assertRedirects(respuesta, reverse("pos:terminal_detail", args=[sale.pk]))
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("5.000"))

    def test_empleado_sin_pos_use_no_puede_editar_cantidad(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("2"), user=self.cajero, tenant=self.tenant)
        respuesta = self.empleado_client.post(reverse("pos:update_item_quantity", args=[sale.pk, item.pk]), {"quantity": "5"})
        self.assertEqual(respuesta.status_code, 403)
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("2.000"))

    def test_tenant_incorrecto_no_puede_editar_cantidad(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("2"), user=self.cajero, tenant=self.tenant)

        otro_tenant = Tenant.objects.create(name="Otra empresa cantidad", slug="otra-empresa-cantidad")
        otro_owner = User.objects.create_user(email="otro.owner.cantidad@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=otro_owner, tenant=otro_tenant, role=Membership.Role.OWNER)
        otro_client = self.client_class()
        otro_client.login(username="otro.owner.cantidad@example.com", password="clave-de-prueba-987")

        respuesta = otro_client.post(reverse("pos:update_item_quantity", args=[sale.pk, item.pk]), {"quantity": "9"})
        self.assertEqual(respuesta.status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("2.000"))

    def test_venta_no_editable_rechaza_la_edicion(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("2"), user=self.cajero, tenant=self.tenant)
        sales_services.confirm_sale(sale, self.cajero)
        respuesta = self.client.post(reverse("pos:update_item_quantity", args=[sale.pk, item.pk]), {"quantity": "9"})
        self.assertEqual(respuesta.status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("2.000"))

    def test_cantidad_invalida_es_rechazada(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("2"), user=self.cajero, tenant=self.tenant)
        for valor in ("0", "-1", "abc"):
            respuesta = self.client.post(reverse("pos:update_item_quantity", args=[sale.pk, item.pk]), {"quantity": valor})
            self.assertRedirects(respuesta, reverse("pos:terminal_detail", args=[sale.pk]))
            item.refresh_from_db()
            self.assertEqual(item.quantity, Decimal("2.000"))

    def test_linea_serializada_rechaza_la_edicion(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(
            sale, product=self.producto_serial, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
            inventory_unit=self.unidad,
        )
        respuesta = self.client.post(reverse("pos:update_item_quantity", args=[sale.pk, item.pk]), {"quantity": "2"})
        self.assertRedirects(respuesta, reverse("pos:terminal_detail", args=[sale.pk]))
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("1.000"))
        self.assertEqual(item.inventory_unit_id, self.unidad.pk)

    def test_terminal_muestra_el_control_editable_solo_para_linea_por_cantidad(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item_cantidad = services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("2"), user=self.cajero, tenant=self.tenant)
        item_serial = services.add_item_to_cart(
            sale, product=self.producto_serial, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
            inventory_unit=self.unidad,
        )
        respuesta = self.client.get(reverse("pos:terminal_detail", args=[sale.pk]))
        url_cantidad = reverse("pos:update_item_quantity", args=[sale.pk, item_cantidad.pk])
        url_serial = reverse("pos:update_item_quantity", args=[sale.pk, item_serial.pk])
        self.assertContains(respuesta, f'action="{url_cantidad}"')
        self.assertNotContains(respuesta, f'action="{url_serial}"')

    def test_checkout_recibe_el_total_ya_recalculado_tras_editar_cantidad(self):
        services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("2"), user=self.cajero, tenant=self.tenant)
        self.client.post(reverse("pos:update_item_quantity", args=[sale.pk, item.pk]), {"quantity": "5"})
        sale.refresh_from_db()
        total_esperado = sale.total  # 5 x 20.00 con 18% de impuesto, sin descuento

        respuesta = self.client.post(reverse("pos:checkout", args=[sale.pk]), {
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "0", "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-method": "transfer", "form-0-amount": str(total_esperado),
        })
        self.assertRedirects(respuesta, reverse("sales:sale_receipt", args=[sale.pk]))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)
        self.assertEqual(sale.total, total_esperado)
