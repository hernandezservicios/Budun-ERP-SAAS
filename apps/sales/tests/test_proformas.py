from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.inventory.models import InventoryUnit
from apps.sales import services
from apps.sales.models import ProformaInvoice, Reservation, Sale

from ._helpers import SalesTestCase


class ProformaServiceTests(SalesTestCase):
    def test_crear_proforma_standalone(self):
        proforma = services.create_proforma(self.tenant, user=self.user, customer=self.customer)
        self.assertTrue(proforma.number.startswith("PRO-"))
        self.assertEqual(proforma.status, ProformaInvoice.Status.DRAFT)

    def test_no_se_puede_reservar_stock_sin_emitir(self):
        proforma = services.create_proforma(self.tenant, user=self.user)
        services.add_proforma_item(proforma, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.reserve_stock_for_proforma(proforma, self.user)

    def test_reservar_stock_producto_cantidad(self):
        proforma = services.create_proforma(self.tenant, user=self.user)
        services.add_proforma_item(proforma, product=self.producto_cantidad, quantity=Decimal("10"), user=self.user)
        services.transition_proforma_status(proforma, ProformaInvoice.Status.ISSUED, self.user)
        reservas = services.reserve_stock_for_proforma(proforma, self.user)
        self.assertEqual(len(reservas), 1)
        self.assertEqual(services.get_reserved_quantity(self.producto_cantidad), Decimal("10"))
        self.assertEqual(services.get_available_to_promise(self.producto_cantidad), Decimal("40"))

    def test_reservar_mas_de_lo_disponible_es_rechazado(self):
        proforma = services.create_proforma(self.tenant, user=self.user)
        services.add_proforma_item(proforma, product=self.producto_cantidad, quantity=Decimal("999"), user=self.user)
        services.transition_proforma_status(proforma, ProformaInvoice.Status.ISSUED, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.reserve_stock_for_proforma(proforma, self.user)

    def test_reservar_stock_producto_serializado_transiciona_unidad(self):
        proforma = services.create_proforma(self.tenant, user=self.user)
        services.add_proforma_item(proforma, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
        services.transition_proforma_status(proforma, ProformaInvoice.Status.ISSUED, self.user)
        services.reserve_stock_for_proforma(proforma, self.user)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.status, InventoryUnit.Status.RESERVADO)

    def test_cancelar_proforma_libera_reservas(self):
        proforma = services.create_proforma(self.tenant, user=self.user)
        services.add_proforma_item(proforma, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
        services.transition_proforma_status(proforma, ProformaInvoice.Status.ISSUED, self.user)
        services.reserve_stock_for_proforma(proforma, self.user)
        services.transition_proforma_status(proforma, ProformaInvoice.Status.CANCELED, self.user)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.status, InventoryUnit.Status.EN_STOCK)
        reserva = Reservation.all_objects.get(inventory_unit=self.unidad)
        self.assertEqual(reserva.status, Reservation.Status.RELEASED)

    def test_vencer_proforma_via_expire_due_proformas(self):
        proforma = services.create_proforma(self.tenant, user=self.user, expiry_date=timezone.localdate().replace(year=2000))
        services.transition_proforma_status(proforma, ProformaInvoice.Status.ISSUED, self.user)
        vencidas = services.expire_due_proformas(self.tenant)
        self.assertEqual(len(vencidas), 1)
        proforma.refresh_from_db()
        self.assertEqual(proforma.status, ProformaInvoice.Status.EXPIRED)

    def test_convertir_proforma_a_venta(self):
        proforma = services.create_proforma(self.tenant, user=self.user, customer=self.customer)
        services.add_proforma_item(proforma, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        services.transition_proforma_status(proforma, ProformaInvoice.Status.ISSUED, self.user)
        sale = services.convert_proforma_to_sale(proforma, self.user)
        self.assertEqual(sale.status, Sale.Status.DRAFT)
        self.assertEqual(sale.source_proforma_id, proforma.pk)
        proforma.refresh_from_db()
        self.assertEqual(proforma.status, ProformaInvoice.Status.CONVERTED)


class ProformaHttpViewTests(SalesTestCase):
    def test_crear_proforma_via_http(self):
        respuesta = self.client.post(reverse("sales:proforma_create"), {
            "customer": self.customer.pk, "currency": "USD", "payment_terms": "contado",
            "notes": "", "terms": "", "global_discount_percent": "0", "global_discount_amount": "0",
            "issue_date": "", "expiry_date": "",
        })
        proforma = ProformaInvoice.all_objects.filter(tenant=self.tenant).first()
        self.assertRedirects(respuesta, reverse("sales:proforma_detail", args=[proforma.pk]))

    def test_reservar_stock_via_http(self):
        proforma = services.create_proforma(self.tenant, user=self.user)
        services.add_proforma_item(proforma, product=self.producto_cantidad, quantity=Decimal("5"), user=self.user)
        services.transition_proforma_status(proforma, ProformaInvoice.Status.ISSUED, self.user)
        respuesta = self.client.post(reverse("sales:proforma_reserve_stock", args=[proforma.pk]))
        self.assertRedirects(respuesta, reverse("sales:proforma_detail", args=[proforma.pk]))
        self.assertTrue(Reservation.all_objects.filter(tenant=self.tenant, product=self.producto_cantidad).exists())

    def test_convertir_a_venta_via_http(self):
        proforma = services.create_proforma(self.tenant, user=self.user)
        services.transition_proforma_status(proforma, ProformaInvoice.Status.ISSUED, self.user)
        respuesta = self.client.post(reverse("sales:proforma_convert_sale", args=[proforma.pk]))
        sale = Sale.all_objects.filter(tenant=self.tenant).first()
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))
