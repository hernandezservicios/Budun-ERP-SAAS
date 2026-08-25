"""
Aislamiento Multi-Tenant del motor comercial (FASE 10, objetivo
explícito del usuario): Tenant A nunca debe poder leer, modificar,
eliminar, buscar, filtrar, pagar, reservar, devolver ni descargar
adjuntos de datos de Tenant B, ni siquiera manipulando IDs/URLs.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.inventory import services as inv_services
from apps.inventory.models import Product
from apps.sales import services
from apps.sales.models import ProformaInvoice, Reservation, Sale
from apps.tenants.models import Membership, Tenant

from ._helpers import MEDIA_ROOT_TEMPORAL_TESTS

User = get_user_model()


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TEMPORAL_TESTS)
class SalesIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Ventas Tenant A", slug="ventas-tenant-a")
        self.tenant_b = Tenant.objects.create(name="Ventas Tenant B", slug="ventas-tenant-b")

        self.user_a = User.objects.create_user(email="ventas.a@example.com", password="clave-de-prueba-987")
        self.user_b = User.objects.create_user(email="ventas.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user_a, tenant=self.tenant_a, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.user_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

        self.producto_a = Product.objects.create(tenant=self.tenant_a, name="Producto A", sku="ISO-A", sale_price=Decimal("10"))
        inv_services.register_stock_in(product=self.producto_a, quantity=Decimal("20"), user=self.user_a)
        self.producto_b = Product.objects.create(tenant=self.tenant_b, name="Producto B", sku="ISO-B", sale_price=Decimal("10"))
        inv_services.register_stock_in(product=self.producto_b, quantity=Decimal("20"), user=self.user_b)

        self.quotation_a = services.create_quotation(self.tenant_a, user=self.user_a)
        self.quotation_b = services.create_quotation(self.tenant_b, user=self.user_b)

        self.sale_a = services.create_sale(self.tenant_a, user=self.user_a)
        services.add_sale_item(self.sale_a, product=self.producto_a, quantity=Decimal("2"), user=self.user_a)
        self.sale_a = services.confirm_sale(self.sale_a, self.user_a)
        self.payment_a = services.record_payment(self.sale_a, method="cash", amount=self.sale_a.total, user=self.user_a)

        self.sale_b = services.create_sale(self.tenant_b, user=self.user_b)
        services.add_sale_item(self.sale_b, product=self.producto_b, quantity=Decimal("2"), user=self.user_b)
        self.sale_b = services.confirm_sale(self.sale_b, self.user_b)

        self.reservation_a = services.create_reservation(self.tenant_a, product=self.producto_a, user=self.user_a, quantity=Decimal("5"))

        self.client_a = self.client_class()
        self.client_a.login(username="ventas.a@example.com", password="clave-de-prueba-987")
        self.client_b = self.client_class()
        self.client_b.login(username="ventas.b@example.com", password="clave-de-prueba-987")

    # --- Lectura -----------------------------------------------------------

    def test_tenant_a_no_puede_leer_cotizacion_de_tenant_b(self):
        respuesta = self.client_a.get(reverse("sales:quotation_detail", args=[self.quotation_b.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_tenant_a_no_puede_leer_venta_de_tenant_b(self):
        respuesta = self.client_a.get(reverse("sales:sale_detail", args=[self.sale_b.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_listados_no_mezclan_tenants(self):
        # Los números comerciales son por-tenant (dos tenants distintos
        # pueden coincidir en "COT-000001", cada uno con su propia
        # secuencia) — comparar por URL de detalle (que sí codifica el
        # PK real, único) en vez de por número, para no dar un falso
        # negativo cuando ambos números coinciden por diseño.
        respuesta = self.client_a.get(reverse("sales:quotation_list"))
        self.assertContains(respuesta, reverse("sales:quotation_detail", args=[self.quotation_a.pk]))
        self.assertNotContains(respuesta, reverse("sales:quotation_detail", args=[self.quotation_b.pk]))

        respuesta = self.client_a.get(reverse("sales:sale_list"))
        self.assertContains(respuesta, reverse("sales:sale_detail", args=[self.sale_a.pk]))
        self.assertNotContains(respuesta, reverse("sales:sale_detail", args=[self.sale_b.pk]))

    # --- Servicios: nunca mezclan tenants ------------------------------------

    def test_service_get_reserved_quantity_no_mezcla_tenants(self):
        # Mismo SKU/nombre en ambos tenants no debería importar: se filtra por instancia de producto real.
        self.assertEqual(services.get_reserved_quantity(self.producto_a), Decimal("5"))
        self.assertEqual(services.get_reserved_quantity(self.producto_b), Decimal("0"))

    def test_activity_log_no_mezcla_tenants(self):
        eventos_b = services.get_activity_log(self.tenant_b, entity_type="sale", entity_id=self.sale_b.pk)
        eventos_a_sobre_b = services.get_activity_log(self.tenant_a, entity_type="sale", entity_id=self.sale_b.pk)
        self.assertTrue(len(list(eventos_b)) >= 1)
        self.assertEqual(len(list(eventos_a_sobre_b)), 0)

    # --- Modificación / acciones ---------------------------------------------

    def test_tenant_a_no_puede_confirmar_venta_de_tenant_b(self):
        respuesta = self.client_a.post(reverse("sales:sale_confirm", args=[self.sale_b.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_tenant_a_no_puede_cancelar_venta_de_tenant_b(self):
        sale_b_borrador = services.create_sale(self.tenant_b, user=self.user_b)
        respuesta = self.client_a.post(reverse("sales:sale_cancel", args=[sale_b_borrador.pk]))
        self.assertEqual(respuesta.status_code, 404)
        sale_b_borrador.refresh_from_db()
        self.assertEqual(sale_b_borrador.status, Sale.Status.DRAFT)

    def test_tenant_a_no_puede_registrar_pago_sobre_venta_de_tenant_b(self):
        respuesta = self.client_a.post(reverse("sales:sale_payment_add", args=[self.sale_b.pk]), {
            "method": "cash", "amount": "5", "reference": "", "notes": "",
        })
        self.assertEqual(respuesta.status_code, 404)

    def test_tenant_a_no_puede_anular_pago_de_tenant_b(self):
        pago_b = services.record_payment(self.sale_b, method="cash", amount=Decimal("1"), user=self.user_b)
        respuesta = self.client_a.post(reverse("sales:sale_payment_void", args=[self.sale_b.pk, pago_b.pk]))
        self.assertEqual(respuesta.status_code, 404)
        pago_b.refresh_from_db()
        self.assertNotEqual(pago_b.status, "voided")

    def test_tenant_a_no_puede_liberar_reserva_de_tenant_b(self):
        reserva_b = services.create_reservation(self.tenant_b, product=self.producto_b, user=self.user_b, quantity=Decimal("1"))
        respuesta = self.client_a.post(reverse("sales:reservation_release", args=[reserva_b.pk]))
        self.assertEqual(respuesta.status_code, 404)
        reserva_b.refresh_from_db()
        self.assertEqual(reserva_b.status, Reservation.Status.ACTIVE)

    def test_tenant_a_no_puede_convertir_cotizacion_de_tenant_b(self):
        respuesta = self.client_a.post(reverse("sales:quotation_convert_proforma", args=[self.quotation_b.pk]))
        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(ProformaInvoice.all_objects.filter(source_quotation=self.quotation_b).exists())

    def test_tenant_a_no_puede_registrar_devolucion_sobre_venta_de_tenant_b(self):
        respuesta = self.client_a.get(reverse("sales:sale_return_create", args=[self.sale_b.pk]))
        self.assertEqual(respuesta.status_code, 404)

    # --- IDs manipulados -----------------------------------------------------

    def test_ids_manipulados_en_urls_de_venta_devuelven_404(self):
        urls_con_id_ajeno = [
            reverse("sales:sale_detail", args=[self.sale_b.pk]),
            reverse("sales:sale_receipt", args=[self.sale_b.pk]),
            reverse("sales:sale_return_create", args=[self.sale_b.pk]),
        ]
        for url in urls_con_id_ajeno:
            with self.subTest(url=url):
                self.assertEqual(self.client_a.get(url).status_code, 404)

    def test_ids_manipulados_en_urls_de_cotizacion_devuelven_404(self):
        urls_con_id_ajeno = [
            reverse("sales:quotation_detail", args=[self.quotation_b.pk]),
            reverse("sales:quotation_print", args=[self.quotation_b.pk]),
        ]
        for url in urls_con_id_ajeno:
            with self.subTest(url=url):
                self.assertEqual(self.client_a.get(url).status_code, 404)

    def test_manipular_sesion_hacia_otro_tenant_no_filtra_ventas(self):
        # Comparar por URL de detalle, no por número: los números
        # comerciales son por-tenant y pueden coincidir legítimamente
        # entre tenants (ver test_listados_no_mezclan_tenants).
        session = self.client_a.session
        session["active_tenant_id"] = self.tenant_b.id
        session.save()
        respuesta = self.client_a.get(reverse("sales:sale_list"))
        self.assertNotContains(respuesta, reverse("sales:sale_detail", args=[self.sale_b.pk]))
