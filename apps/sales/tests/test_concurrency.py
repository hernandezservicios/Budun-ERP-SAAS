"""
Pruebas de concurrencia real (FASE 10, requisito explícito del
usuario): dos operaciones simultáneas sobre el mismo recurso nunca deben
producir un resultado inconsistente (doble venta, sobre-reserva). Se
usa `TransactionTestCase` (no `TestCase`, que envuelve todo en una única
transacción que nunca hace commit real) + hilos reales, para que el
`select_for_update()` de `services.py`/`apps.inventory.services`
realmente sirva de barrera entre conexiones concurrentes distintas,
como ocurriría con dos requests HTTP simultáneas en producción.
"""

import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from apps.customers.models import Customer
from apps.inventory import services as inv_services
from apps.inventory.models import Product
from apps.sales import services
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class ReservationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrencia Ventas", slug="concurrencia-ventas")
        self.user = User.objects.create_user(email="concurrencia@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)
        self.customer = Customer.objects.create(tenant=self.tenant, first_name="Cliente Concurrencia")

        self.producto_cantidad = Product.objects.create(
            tenant=self.tenant, name="Producto Concurrente", sku="CONC-1", sale_price=Decimal("10")
        )
        inv_services.register_stock_in(product=self.producto_cantidad, quantity=Decimal("50"), user=self.user)

        self.producto_serial = Product.objects.create(
            tenant=self.tenant, name="Unidad Concurrente", sku="CONC-2", sale_price=Decimal("500"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.unidad = inv_services.register_serialized_unit(product=self.producto_serial, user=self.user, imei_1="000111222333444")

    def test_dos_reservas_concurrentes_de_la_misma_unidad_serializada_solo_una_gana(self):
        resultados = []
        barrera = threading.Barrier(2)

        def intentar():
            barrera.wait()
            try:
                services.create_reservation(self.tenant, product=self.producto_serial, user=self.user, inventory_unit=self.unidad)
                resultados.append("ok")
            except services.InvalidSalesOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=intentar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1, "Exactamente una de las dos reservas concurrentes debe ganar.")
        self.assertEqual(resultados.count("rechazado"), 1)

    def test_dos_ventas_concurrentes_de_la_misma_unidad_serializada_no_permiten_doble_venta(self):
        resultados = []
        barrera = threading.Barrier(2)

        def intentar_vender():
            barrera.wait()
            try:
                connection.close()  # asegurar una conexión fresca por hilo
                venta = services.create_sale(self.tenant, user=self.user)
                services.add_sale_item(venta, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
                services.confirm_sale(venta, self.user)
                resultados.append("ok")
            except services.InvalidSalesOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=intentar_vender) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1, "Nunca debe poder venderse la misma unidad dos veces.")
        self.assertEqual(resultados.count("rechazado"), 1)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.status, "vendido")

    def test_dos_reservas_concurrentes_que_exceden_el_stock_combinado_solo_una_gana(self):
        """Stock = 50. Dos hilos reservan 30 cada uno (60 en total,
        supera el stock): solo una debe tener éxito."""
        resultados = []
        barrera = threading.Barrier(2)

        def intentar_reservar():
            barrera.wait()
            try:
                connection.close()
                services.create_reservation(self.tenant, product=self.producto_cantidad, user=self.user, quantity=Decimal("30"))
                resultados.append("ok")
            except services.InvalidSalesOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=intentar_reservar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1)
        self.assertEqual(resultados.count("rechazado"), 1)
        self.assertEqual(services.get_reserved_quantity(self.producto_cantidad), Decimal("30"))
