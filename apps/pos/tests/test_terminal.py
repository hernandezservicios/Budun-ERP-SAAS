from decimal import Decimal

from django.urls import reverse

from apps.inventory.models import InventoryUnit
from apps.pos import services
from apps.pos.models import CashMovement
from apps.sales.models import Sale

from ._helpers import PosTestCase


class TerminalServiceTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))

    def test_search_delega_en_inventory_services(self):
        resultados = services.search(self.tenant, "Cable")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].product, self.producto)

    def test_start_cart_crea_venta_draft(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        self.assertEqual(sale.status, Sale.Status.DRAFT)

    def test_agregar_producto_por_cantidad(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("2"), user=self.cajero, tenant=self.tenant)
        self.assertEqual(item.quantity, Decimal("2"))
        sale.refresh_from_db()
        self.assertEqual(sale.total, (Decimal("2") * Decimal("20.00") * Decimal("1.18")).quantize(Decimal("0.01")))

    def test_agregar_producto_serializado_con_unidad(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(
            sale, product=self.producto_serial, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
            inventory_unit=self.unidad,
        )
        self.assertEqual(item.inventory_unit, self.unidad)

    def test_quitar_linea_recalcula_totales(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        item = services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant)
        services.remove_cart_item(item)
        sale.refresh_from_db()
        self.assertEqual(sale.total, Decimal("0"))

    def test_set_cart_customer(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        services.set_cart_customer(sale, self.customer)
        sale.refresh_from_db()
        self.assertEqual(sale.customer, self.customer)

    def test_checkout_sale_sin_sesion_abierta_es_rechazado(self):
        services.close_cash_session(self.sesion, self.cajero, counted_cash=Decimal("0"))
        sale = services.start_cart(self.tenant, user=self.cajero)
        services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant)
        with self.assertRaises(services.InvalidPosOperation):
            services.checkout_sale(sale, user=self.cajero, tenant=self.tenant, payments=[{"method": "cash", "amount": sale.total}])

    def test_checkout_sale_confirma_y_paga(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant)
        sale.refresh_from_db()
        venta, pagos = services.checkout_sale(sale, user=self.cajero, tenant=self.tenant, payments=[{"method": "cash", "amount": sale.total}])
        self.assertEqual(venta.status, Sale.Status.CONFIRMED)
        self.assertEqual(venta.payment_status, Sale.PaymentStatus.PAID)
        self.assertEqual(len(pagos), 1)

    def test_checkout_sale_multipago_efectivo_y_tarjeta(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        services.add_item_to_cart(sale, product=self.producto_serial, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant, inventory_unit=self.unidad)
        sale.refresh_from_db()
        mitad = (sale.total / 2).quantize(Decimal("0.01"))
        resto = sale.total - mitad
        venta, pagos = services.checkout_sale(
            sale, user=self.cajero, tenant=self.tenant,
            payments=[{"method": "cash", "amount": mitad}, {"method": "card", "amount": resto}],
        )
        self.assertEqual(venta.payment_status, Sale.PaymentStatus.PAID)
        self.assertEqual(len(pagos), 2)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.status, InventoryUnit.Status.VENDIDO)
        movimiento_cash = CashMovement.all_objects.filter(tenant=self.tenant, cash_session=self.sesion, movement_type="sale_cash").first()
        self.assertEqual(movimiento_cash.amount, mitad)

    def test_checkout_sale_venta_parcial_deja_estado_credito(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        services.set_cart_customer(sale, self.customer)
        services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant)
        sale.refresh_from_db()
        venta, _pagos = services.checkout_sale(sale, user=self.cajero, tenant=self.tenant, payments=[{"method": "cash", "amount": Decimal("5")}])
        self.assertEqual(venta.payment_status, Sale.PaymentStatus.PARTIALLY_PAID)

    def test_cancelar_carrito(self):
        from apps.sales import services as sales_services

        sale = services.start_cart(self.tenant, user=self.cajero)
        sales_services.cancel_sale(sale, self.cajero, reason="prueba")
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CANCELED)


class TerminalHttpViewTests(PosTestCase):
    def setUp(self):
        super().setUp()
        services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))

    def test_flujo_completo_via_http(self):
        respuesta = self.client.get(reverse("pos:terminal_start"))
        self.assertEqual(respuesta.status_code, 302)
        sale = Sale.all_objects.get(tenant=self.tenant, salesperson=self.cajero, status=Sale.Status.DRAFT)

        respuesta = self.client.get(reverse("pos:terminal_detail", args=[sale.pk]), {"q": "Cable"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cable HDMI")

        respuesta = self.client.post(reverse("pos:add_item", args=[sale.pk]), {
            "product_id": self.producto.pk, "quantity": "1", "unit_identifier": "", "discount_percent": "", "discount_amount": "",
        })
        self.assertRedirects(respuesta, reverse("pos:terminal_detail", args=[sale.pk]))
        sale.refresh_from_db()
        self.assertEqual(sale.total, (Decimal("20.00") * Decimal("1.18")).quantize(Decimal("0.01")))

        respuesta = self.client.post(reverse("pos:checkout", args=[sale.pk]), {
            "form-TOTAL_FORMS": "2", "form-INITIAL_FORMS": "0", "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-method": "cash", "form-0-amount": str(sale.total), "form-1-method": "", "form-1-amount": "",
        })
        self.assertRedirects(respuesta, reverse("sales:sale_receipt", args=[sale.pk]))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)

    def test_tenant_a_no_puede_ver_carrito_de_tenant_b(self):
        from apps.tenants.models import Membership, Tenant
        from django.contrib.auth import get_user_model

        User = get_user_model()
        tenant_b = Tenant.objects.create(name="Otro tenant", slug="otro-tenant-pos")
        user_b = User.objects.create_user(email="otro@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=user_b, tenant=tenant_b, role=Membership.Role.OWNER)
        from apps.sales import services as sales_services

        sale_b = sales_services.create_sale(tenant_b, user=user_b)

        respuesta = self.client.get(reverse("pos:terminal_detail", args=[sale_b.pk]))
        self.assertEqual(respuesta.status_code, 404)
