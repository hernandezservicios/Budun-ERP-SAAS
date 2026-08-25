"""Concurrencia real (hilos + conexiones reales de PostgreSQL, no
`TestCase`, que nunca hace commit real) para los 5 escenarios exigidos
en FASE 12: recepción simultánea de la misma orden, intentos
simultáneos de sobre-recepción, registro simultáneo del mismo serial/
IMEI, devolución simultánea de la misma unidad, y cambios simultáneos
que juntos completan exactamente una orden (sin doble-conteo). Mismo
patrón que `apps/pos/tests/test_concurrency.py` (FASE 11)."""

import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from apps.approvals.services import resolve_approval, request_approval
from apps.approvals.models import ApprovalRequest
from apps.customers.models import Supplier
from apps.inventory.models import InventoryUnit, Product
from apps.purchases import services
from apps.purchases.models import PurchaseOrder
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class PurchaseConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Concurrencia", slug="empresa-concurrencia")
        self.owner = User.objects.create_user(email="owner.conc@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        # Usuario NO propietario: el propietario siempre está autorizado
        # a sobre-recibir sin aprobación (regla de negocio deliberada,
        # ver apps.approvals.services.is_owner) — los escenarios de
        # sobre-recepción necesitan un usuario sujeto a la política
        # (límite 0% por defecto) para ejercer realmente esa ruta.
        self.comprador = User.objects.create_user(email="comprador.conc@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.comprador, tenant=self.tenant, role=Membership.Role.MEMBER)
        self.supplier = Supplier.objects.create(tenant=self.tenant, legal_name="Proveedor Concurrencia")
        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto Concurrencia", sku="TST-CONC-001",
            sale_price=Decimal("20"), purchase_price=Decimal("10"),
        )
        self.producto_serial = Product.objects.create(
            tenant=self.tenant, name="Serial Concurrencia", sku="TST-CONC-SER",
            sale_price=Decimal("500"), purchase_price=Decimal("300"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )

    def _orden_enviada(self, product, cantidad):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        item = services.add_purchase_order_item(orden, product=product, quantity=cantidad, user=self.owner, unit_cost=Decimal("10"))
        services.send_purchase_order(orden, self.owner, tenant=self.tenant)
        return orden, item

    def _correr_en_hilos(self, funciones):
        resultados = {}

        def envoltura(nombre, funcion):
            try:
                funcion()
                resultados[nombre] = "ok"
            except Exception as error:  # noqa: BLE001 — se captura para inspección del test
                resultados[nombre] = error
            finally:
                connection.close()

        hilos = [threading.Thread(target=envoltura, args=(nombre, funcion)) for nombre, funcion in funciones]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        return resultados

    def test_recepcion_simultanea_de_la_misma_orden_no_duplica_ni_excede(self):
        """Dos hilos reciben 6 unidades cada uno contra una orden de 10:
        exactamente uno debe tener éxito (6 recibidas); el otro, al ver
        que solo quedan 4 pendientes, debe requerir autorización de
        sobre-recepción — nunca los dos aplicando 6+6=12 sin más."""
        orden, item = self._orden_enviada(self.producto, Decimal("10"))
        barrera = threading.Barrier(2)

        def recibir():
            barrera.wait(timeout=5)
            # Usuario NO propietario a propósito: el propietario está
            # siempre autorizado a sobre-recibir (ver setUp), lo que
            # dejaría este escenario sin ejercer la ruta de autorización.
            services.receive_purchase_order(
                orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("6")}],
                user=self.comprador, tenant=self.tenant,
            )

        resultados = self._correr_en_hilos([("A", recibir), ("B", recibir)])
        exitos = [r for r in resultados.values() if r == "ok"]
        rechazos = [r for r in resultados.values() if r != "ok"]
        self.assertEqual(len(exitos), 1)
        self.assertEqual(len(rechazos), 1)
        self.assertIsInstance(rechazos[0], services.OverReceivingRequiresApproval)
        item.refresh_from_db()
        self.assertEqual(services.get_purchase_order_item_received_quantity(item), Decimal("6"))

    def test_intentos_simultaneos_de_sobre_recepcion_consumen_la_aprobacion_una_sola_vez(self):
        orden, item = self._orden_enviada(self.producto, Decimal("10"))
        solicitud = request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.OVER_RECEIVING, requested_by=self.comprador,
            requested_value=Decimal("50"), allowed_limit=Decimal("0"),
            document_type="purchase_order", document_id=orden.pk,
        )
        solicitud = resolve_approval(solicitud, approved=True, user=self.owner)
        barrera = threading.Barrier(2)

        def recibir_con_exceso():
            barrera.wait(timeout=5)
            # Usuario NO propietario a propósito (ver test anterior) — de
            # lo contrario el propietario bypassa por completo la
            # consulta/consumo de `use_approval` y el test no ejercería
            # la ruta que dice probar.
            services.receive_purchase_order(
                orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("15")}],
                user=self.comprador, tenant=self.tenant, use_approval=solicitud,
            )

        resultados = self._correr_en_hilos([("A", recibir_con_exceso), ("B", recibir_con_exceso)])
        exitos = [r for r in resultados.values() if r == "ok"]
        self.assertEqual(len(exitos), 1, "Solo una recepción debió poder consumir la misma aprobación.")

    def test_registro_simultaneo_del_mismo_imei_en_ordenes_distintas(self):
        """Dos hilos reciben el MISMO IMEI contra dos órdenes distintas
        (sin ningún lock de fila en común): la unicidad de FASE 8 a
        nivel de base de datos debe rechazar exactamente una de las
        dos, nunca crear dos InventoryUnit con el mismo IMEI."""
        orden_a, item_a = self._orden_enviada(self.producto_serial, Decimal("1"))
        orden_b, item_b = self._orden_enviada(self.producto_serial, Decimal("1"))
        barrera = threading.Barrier(2)
        imei = "123123123123123"

        def recibir(orden, item):
            barrera.wait(timeout=5)
            services.receive_purchase_order(
                orden, lines=[{"purchase_order_item": item, "units": [{"imei_1": imei}]}],
                user=self.owner, tenant=self.tenant,
            )

        resultados = self._correr_en_hilos([
            ("A", lambda: recibir(orden_a, item_a)), ("B", lambda: recibir(orden_b, item_b)),
        ])
        exitos = [r for r in resultados.values() if r == "ok"]
        self.assertEqual(len(exitos), 1)
        self.assertEqual(InventoryUnit.all_objects.filter(tenant=self.tenant, imei_1=imei).count(), 1)

    def test_devolucion_simultanea_de_la_misma_unidad(self):
        orden, item = self._orden_enviada(self.producto_serial, Decimal("1"))
        recepcion = services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "units": [{"imei_1": "444555666777888"}]}],
            user=self.owner, tenant=self.tenant,
        )
        receipt_item = services.get_receipt_items(recepcion).first()
        barrera = threading.Barrier(2)

        def devolver():
            barrera.wait(timeout=5)
            services.create_supplier_return(orden, items=[{"receipt_item": receipt_item}], user=self.owner)

        resultados = self._correr_en_hilos([("A", devolver), ("B", devolver)])
        exitos = [r for r in resultados.values() if r == "ok"]
        self.assertEqual(len(exitos), 1, "Solo una devolución debió poder transicionar la misma unidad.")
        unidad = InventoryUnit.all_objects.get(pk=receipt_item.inventory_unit_id)
        self.assertEqual(unidad.status, InventoryUnit.Status.DEVUELTO_PROVEEDOR)

    def test_dos_recepciones_concurrentes_que_juntas_completan_la_orden_sin_doble_conteo(self):
        orden, item = self._orden_enviada(self.producto, Decimal("10"))
        barrera = threading.Barrier(2)

        def recibir(cantidad):
            barrera.wait(timeout=5)
            services.receive_purchase_order(
                orden, lines=[{"purchase_order_item": item, "quantity_received": cantidad}],
                user=self.owner, tenant=self.tenant,
            )

        resultados = self._correr_en_hilos([
            ("A", lambda: recibir(Decimal("5"))), ("B", lambda: recibir(Decimal("5"))),
        ])
        exitos = [r for r in resultados.values() if r == "ok"]
        self.assertEqual(len(exitos), 2)
        self.assertEqual(services.get_purchase_order_item_received_quantity(item), Decimal("10"))
        orden.refresh_from_db()
        self.assertEqual(orden.status, PurchaseOrder.Status.RECEIVED)
