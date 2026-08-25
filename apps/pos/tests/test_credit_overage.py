from decimal import Decimal

from apps.approvals import services as approvals_services
from apps.pos import services
from apps.sales.models import Sale

from ._helpers import PosTestCase


class CreditOverageTests(PosTestCase):
    """`self.customer` tiene credit_enabled=True, credit_limit=10000
    (ver `_helpers.PosTestCase`)."""

    def setUp(self):
        super().setUp()
        services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))

    def test_venta_a_credito_dentro_del_limite_no_requiere_autorizacion(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        services.set_cart_customer(sale, self.customer)
        from apps.inventory import services as inv_services

        inv_services.register_stock_in(product=self.producto, quantity=Decimal("100"), user=self.owner)
        services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("100"), user=self.cajero, tenant=self.tenant, discount_percent=Decimal("0"))
        sale.refresh_from_db()
        # Total ~= 100*20*1.18 = 2360, muy por debajo del límite de 10000; sin pago -> pendiente 2360 < 10000.
        venta, _pagos = services.checkout_sale(sale, user=self.cajero, tenant=self.tenant, payments=[{"method": "cash", "amount": Decimal("1")}])
        self.assertEqual(venta.status, Sale.Status.CONFIRMED)

    def test_venta_a_credito_que_excede_el_limite_requiere_autorizacion(self):
        from apps.inventory import services as inv_services

        sale = services.start_cart(self.tenant, user=self.cajero)
        services.set_cart_customer(sale, self.customer)
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("500"), user=self.owner)
        services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("500"), user=self.cajero, tenant=self.tenant)
        sale.refresh_from_db()
        # Total ~= 500*20*1.18 = 11,800 > límite 10,000.
        with self.assertRaises(services.CreditOverageRequiresApproval):
            services.checkout_sale(sale, user=self.cajero, tenant=self.tenant, payments=[{"method": "cash", "amount": Decimal("1")}])

    def test_propietario_no_requiere_autorizacion_de_credito(self):
        from apps.inventory import services as inv_services
        from apps.pos.models import CashRegister

        caja_owner = CashRegister.all_objects.create(tenant=self.tenant, name="Caja Owner", code="CAJA-OWNER")
        services.open_cash_session(self.tenant, cash_register=caja_owner, user=self.owner, opening_amount=Decimal("0"))

        sale = services.start_cart(self.tenant, user=self.owner)
        services.set_cart_customer(sale, self.customer)
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("500"), user=self.owner)
        services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("500"), user=self.owner, tenant=self.tenant)
        sale.refresh_from_db()
        venta, _pagos = services.checkout_sale(sale, user=self.owner, tenant=self.tenant, payments=[{"method": "cash", "amount": Decimal("1")}])
        self.assertEqual(venta.status, Sale.Status.CONFIRMED)

    def test_reintento_tras_aprobacion_de_credito_excedido(self):
        from apps.inventory import services as inv_services

        sale = services.start_cart(self.tenant, user=self.cajero)
        services.set_cart_customer(sale, self.customer)
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("500"), user=self.owner)
        services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("500"), user=self.cajero, tenant=self.tenant)
        sale.refresh_from_db()

        with self.assertRaises(services.CreditOverageRequiresApproval) as contexto:
            services.checkout_sale(sale, user=self.cajero, tenant=self.tenant, payments=[{"method": "cash", "amount": Decimal("1")}])
        error = contexto.exception
        solicitud = services.request_credit_overage_approval(self.tenant, sale, self.cajero, excedente=error.overage_amount, limite=error.limit)
        approvals_services.resolve_approval(solicitud, approved=True, user=self.owner, approved_value=error.overage_amount)

        venta, _pagos = services.checkout_sale(sale, user=self.cajero, tenant=self.tenant, payments=[{"method": "cash", "amount": Decimal("1")}])
        self.assertEqual(venta.status, Sale.Status.CONFIRMED)
        solicitud.refresh_from_db()
        self.assertIsNotNone(solicitud.consumed_at)

    def test_cliente_sin_credito_habilitado_nunca_requiere_autorizacion_de_credito(self):
        from apps.inventory import services as inv_services

        self.customer.credit_enabled = False
        self.customer.save(update_fields=["credit_enabled"])
        sale = services.start_cart(self.tenant, user=self.cajero)
        services.set_cart_customer(sale, self.customer)
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("500"), user=self.owner)
        services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("500"), user=self.cajero, tenant=self.tenant)
        sale.refresh_from_db()
        venta, _pagos = services.checkout_sale(sale, user=self.cajero, tenant=self.tenant, payments=[{"method": "cash", "amount": Decimal("1")}])
        self.assertEqual(venta.status, Sale.Status.CONFIRMED)
