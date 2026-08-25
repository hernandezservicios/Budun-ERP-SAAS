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


class PaymentAllocationConcurrencyTests(TransactionTestCase):
    """Extensión obligatoria "Payment / PaymentAllocation": el monto
    aplicado nunca puede exceder el saldo disponible del pago ni el
    saldo pendiente de la factura, ni siquiera bajo dos solicitudes
    simultáneas — `allocate_payment` bloquea (`select_for_update`) tanto
    el `Payment` como el `Sale` antes de validar, igual que el resto del
    módulo."""

    reset_sequences = True

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrencia Pagos", slug="concurrencia-pagos")
        self.user = User.objects.create_user(email="concurrencia-pagos@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)
        self.customer = Customer.objects.create(tenant=self.tenant, first_name="Cliente Concurrencia Pagos")

        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto Pagos", sku="CONC-PAY-1", sale_price=Decimal("1")
        )
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("100000"), user=self.user)

    def _crear_venta_confirmada(self, total):
        venta = services.create_sale(self.tenant, user=self.user, customer=self.customer)
        services.add_sale_item(venta, product=self.producto, quantity=total, user=self.user, tax_rate=Decimal("0"))
        return services.confirm_sale(venta, self.user)

    def test_dos_asignaciones_concurrentes_del_mismo_pago_no_exceden_lo_disponible(self):
        """Pago de 100 disponible. Dos hilos intentan aplicar 60 cada uno
        (120 en total, supera lo disponible) a dos facturas distintas:
        solo uno debe tener éxito."""
        pago = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("100"), user=self.user)
        factura_1 = self._crear_venta_confirmada(Decimal("60"))
        factura_2 = self._crear_venta_confirmada(Decimal("60"))
        resultados = []
        barrera = threading.Barrier(2)

        def intentar(factura):
            barrera.wait()
            try:
                connection.close()
                services.allocate_payment(pago, factura, Decimal("60"), self.user)
                resultados.append("ok")
            except services.InvalidSalesOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=intentar, args=(f,)) for f in (factura_1, factura_2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1, "El total aplicado nunca debe exceder el saldo disponible del pago.")
        self.assertEqual(resultados.count("rechazado"), 1)
        self.assertEqual(services.get_unallocated_payment_amount(pago), Decimal("40"))

    def test_dos_asignaciones_concurrentes_a_la_misma_factura_no_exceden_el_saldo_pendiente(self):
        """Factura de 100. Dos pagos distintos de 80 cada uno intentan
        aplicarse simultáneamente a la misma factura (160 en total,
        supera el saldo pendiente): solo uno debe tener éxito."""
        factura = self._crear_venta_confirmada(Decimal("100"))
        pago_1 = services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("80"), user=self.user)
        pago_2 = services.create_payment(self.tenant, customer=self.customer, method="card", amount=Decimal("80"), user=self.user)
        resultados = []
        barrera = threading.Barrier(2)

        def intentar(pago):
            barrera.wait()
            try:
                connection.close()
                services.allocate_payment(pago, factura, Decimal("80"), self.user)
                resultados.append("ok")
            except services.InvalidSalesOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=intentar, args=(p,)) for p in (pago_1, pago_2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1, "El saldo pendiente de la factura nunca debe sobre-aplicarse.")
        self.assertEqual(resultados.count("rechazado"), 1)
        self.assertEqual(services.get_sale_balance_due(factura), Decimal("20"))
