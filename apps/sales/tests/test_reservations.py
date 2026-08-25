from decimal import Decimal

from django.urls import reverse

from apps.inventory.models import InventoryUnit
from apps.sales import services
from apps.sales.models import Reservation

from ._helpers import SalesTestCase


class ReservationServiceTests(SalesTestCase):
    def test_reservar_cantidad(self):
        reserva = services.create_reservation(self.tenant, product=self.producto_cantidad, user=self.user, quantity=Decimal("10"))
        self.assertEqual(reserva.status, Reservation.Status.ACTIVE)
        self.assertEqual(services.get_reserved_quantity(self.producto_cantidad), Decimal("10"))

    def test_reservar_mas_de_lo_disponible_es_rechazado(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.create_reservation(self.tenant, product=self.producto_cantidad, user=self.user, quantity=Decimal("999"))

    def test_reservar_cantidad_cero_o_negativa_es_rechazado(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.create_reservation(self.tenant, product=self.producto_cantidad, user=self.user, quantity=Decimal("0"))

    def test_reservar_ambos_cantidad_y_unidad_es_rechazado(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.create_reservation(
                self.tenant, product=self.producto_cantidad, user=self.user, quantity=Decimal("1"), inventory_unit=self.unidad
            )

    def test_reservar_ninguno_es_rechazado(self):
        with self.assertRaises(services.InvalidSalesOperation):
            services.create_reservation(self.tenant, product=self.producto_cantidad, user=self.user)

    def test_reservar_unidad_serializada_transiciona_a_reservado(self):
        services.create_reservation(self.tenant, product=self.producto_serial, user=self.user, inventory_unit=self.unidad)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.status, InventoryUnit.Status.RESERVADO)

    def test_reservar_unidad_ya_reservada_es_rechazado(self):
        services.create_reservation(self.tenant, product=self.producto_serial, user=self.user, inventory_unit=self.unidad)
        with self.assertRaises(services.InvalidSalesOperation):
            services.create_reservation(self.tenant, product=self.producto_serial, user=self.user, inventory_unit=self.unidad)

    def test_liberar_reserva_de_cantidad(self):
        reserva = services.create_reservation(self.tenant, product=self.producto_cantidad, user=self.user, quantity=Decimal("10"))
        services.release_reservation(reserva, self.user)
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reservation.Status.RELEASED)
        self.assertEqual(services.get_reserved_quantity(self.producto_cantidad), Decimal("0"))

    def test_liberar_reserva_de_unidad_serializada_restaura_en_stock(self):
        reserva = services.create_reservation(self.tenant, product=self.producto_serial, user=self.user, inventory_unit=self.unidad)
        services.release_reservation(reserva, self.user)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.status, InventoryUnit.Status.EN_STOCK)

    def test_liberar_reserva_ya_liberada_es_idempotente(self):
        reserva = services.create_reservation(self.tenant, product=self.producto_cantidad, user=self.user, quantity=Decimal("1"))
        services.release_reservation(reserva, self.user)
        reserva_repetida = services.release_reservation(reserva, self.user)
        self.assertEqual(reserva_repetida.status, Reservation.Status.RELEASED)

    def test_disponible_para_prometer_serializado_no_resta_dos_veces(self):
        """Para SERIALIZED, `get_current_stock` ya excluye unidades
        RESERVADO — `get_available_to_promise` no debe restar de nuevo."""
        services.create_reservation(self.tenant, product=self.producto_serial, user=self.user, inventory_unit=self.unidad)
        self.assertEqual(services.get_available_to_promise(self.producto_serial), 0)


class ReservationHttpViewTests(SalesTestCase):
    def test_listado_de_reservas_via_http(self):
        services.create_reservation(self.tenant, product=self.producto_cantidad, user=self.user, quantity=Decimal("5"))
        respuesta = self.client.get(reverse("sales:reservation_list"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.producto_cantidad.name)

    def test_liberar_reserva_via_http(self):
        reserva = services.create_reservation(self.tenant, product=self.producto_cantidad, user=self.user, quantity=Decimal("5"))
        respuesta = self.client.post(reverse("sales:reservation_release", args=[reserva.pk]))
        self.assertRedirects(respuesta, reverse("sales:reservation_list"))
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, Reservation.Status.RELEASED)
