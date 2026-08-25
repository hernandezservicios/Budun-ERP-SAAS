from decimal import Decimal

from apps.approvals.services import resolve_approval, set_tenant_default_policy
from apps.inventory.models import InventoryUnit
from apps.inventory.services import get_current_stock
from apps.purchases import services
from apps.purchases.models import PurchaseOrder

from ._helpers import PurchasesTestCase


def _orden_enviada_cantidad(self, cantidad=Decimal("10")):
    orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
    item = services.add_purchase_order_item(
        orden, product=self.producto, quantity=cantidad, user=self.owner, unit_cost=Decimal("10"),
    )
    services.send_purchase_order(orden, self.owner, tenant=self.tenant)
    return orden, item


def _orden_enviada_serializada(self, cantidad=Decimal("3")):
    orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
    item = services.add_purchase_order_item(
        orden, product=self.producto_serial, quantity=cantidad, user=self.owner, unit_cost=Decimal("500"),
    )
    services.send_purchase_order(orden, self.owner, tenant=self.tenant)
    return orden, item


class ReceivingQuantityTests(PurchasesTestCase):
    def test_recepcion_parcial_luego_completa(self):
        orden, item = _orden_enviada_cantidad(self, Decimal("10"))
        stock_antes = get_current_stock(self.producto)

        services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("6")}],
            user=self.owner, tenant=self.tenant,
        )
        orden.refresh_from_db()
        self.assertEqual(orden.status, PurchaseOrder.Status.PARTIALLY_RECEIVED)
        self.assertEqual(services.get_purchase_order_item_pending_quantity(item), Decimal("4"))
        self.assertEqual(get_current_stock(self.producto), stock_antes + Decimal("6"))

        services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("4")}],
            user=self.owner, tenant=self.tenant,
        )
        orden.refresh_from_db()
        self.assertEqual(orden.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(services.get_purchase_order_item_pending_quantity(item), Decimal("0"))
        self.assertEqual(get_current_stock(self.producto), stock_antes + Decimal("10"))

    def test_unit_cost_none_explicito_usa_el_costo_de_la_orden(self):
        """Regresión: la vista siempre incluye la clave "unit_cost" en el
        dict de línea (con valor `None` cuando el campo se deja en
        blanco) — `dict.get(clave, default)` NO usa `default` si la
        clave está presente con valor `None`, solo si falta por
        completo. Encontrado por el smoke test HTTP: `PurchaseReceiptItem.unit_cost`
        llegaba `None` y violaba su `NOT NULL`."""
        orden, item = _orden_enviada_cantidad(self, Decimal("10"))
        recepcion = services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("6"), "unit_cost": None}],
            user=self.owner, tenant=self.tenant,
        )
        receipt_item = services.get_receipt_items(recepcion).first()
        self.assertEqual(receipt_item.unit_cost, item.unit_cost)

    def test_no_se_puede_recibir_contra_orden_en_borrador(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        item = services.add_purchase_order_item(orden, product=self.producto, quantity=Decimal("5"), user=self.owner, unit_cost=Decimal("10"))
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.receive_purchase_order(
                orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("1")}],
                user=self.owner, tenant=self.tenant,
            )

    def test_sobre_recepcion_rechazada_por_defecto(self):
        orden, item = _orden_enviada_cantidad(self, Decimal("10"))
        with self.assertRaises(services.OverReceivingRequiresApproval):
            services.receive_purchase_order(
                orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("15")}],
                user=self.comprador, tenant=self.tenant,
            )

    def test_sobre_recepcion_autorizada_por_propietario(self):
        orden, item = _orden_enviada_cantidad(self, Decimal("10"))
        recepcion = services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("12")}],
            user=self.owner, tenant=self.tenant,
        )
        self.assertEqual(services.get_purchase_order_item_received_quantity(item), Decimal("12"))
        self.assertTrue(recepcion.number.startswith("REC-"))

    def test_sobre_recepcion_con_flujo_de_autorizacion(self):
        set_tenant_default_policy(
            self.tenant, max_discount_percent=Decimal("0"), max_discount_amount=Decimal("0"),
            max_credit_overage=Decimal("0"), max_purchase_order_amount=Decimal("0"), max_over_receiving_percent=Decimal("0"),
        )
        orden, item = _orden_enviada_cantidad(self, Decimal("10"))
        with self.assertRaises(services.OverReceivingRequiresApproval) as ctx:
            services.receive_purchase_order(
                orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("15")}],
                user=self.comprador, tenant=self.tenant,
            )
        solicitud = services.request_over_receiving_approval(
            self.tenant, orden, self.comprador,
            limite_percent=ctx.exception.limit_percent, exceso_percent=ctx.exception.requested_percent,
        )
        resolve_approval(solicitud, approved=True, user=self.owner)
        # No se pasa `use_approval`: `receive_purchase_order` debe encontrar
        # la solicitud aprobada por sí solo, igual que en el flujo real de
        # la vista.
        recepcion = services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("15")}],
            user=self.comprador, tenant=self.tenant,
        )
        self.assertIsNotNone(recepcion.pk)


class ReceivingSerializedTests(PurchasesTestCase):
    def test_unit_cost_none_explicito_usa_el_costo_de_la_orden(self):
        """Mismo caso de regresión que en QUANTITY, para la rama SERIALIZED."""
        orden, item = _orden_enviada_serializada(self, Decimal("1"))
        recepcion = services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "units": [{"imei_1": "555444333222111", "unit_cost": None}]}],
            user=self.owner, tenant=self.tenant,
        )
        receipt_item = services.get_receipt_items(recepcion).first()
        self.assertEqual(receipt_item.unit_cost, item.unit_cost)
        self.assertEqual(receipt_item.inventory_unit.unit_cost, item.unit_cost)

    def test_recepcion_serializada_crea_una_unidad_por_imei(self):
        orden, item = _orden_enviada_serializada(self, Decimal("2"))
        services.receive_purchase_order(
            orden,
            lines=[{
                "purchase_order_item": item,
                "units": [
                    {"imei_1": "111111111111111", "unit_cost": Decimal("500")},
                    {"imei_1": "222222222222222", "unit_cost": Decimal("510")},
                ],
            }],
            user=self.owner, tenant=self.tenant,
        )
        unidades = InventoryUnit.all_objects.filter(tenant=self.tenant, product=self.producto_serial)
        self.assertEqual(unidades.count(), 2)
        self.assertTrue(all(u.status == InventoryUnit.Status.EN_STOCK for u in unidades))
        orden.refresh_from_db()
        self.assertEqual(orden.status, PurchaseOrder.Status.RECEIVED)

    def test_imei_duplicado_en_el_mismo_tenant_es_rechazado(self):
        orden, item = _orden_enviada_serializada(self, Decimal("3"))
        services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "units": [{"imei_1": "333333333333333"}]}],
            user=self.owner, tenant=self.tenant,
        )
        with self.assertRaises(Exception):
            services.receive_purchase_order(
                orden, lines=[{"purchase_order_item": item, "units": [{"imei_1": "333333333333333"}]}],
                user=self.owner, tenant=self.tenant,
            )

    def test_unidad_sin_ningun_identificador_es_rechazada(self):
        orden, item = _orden_enviada_serializada(self, Decimal("1"))
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.receive_purchase_order(
                orden, lines=[{"purchase_order_item": item, "units": [{}]}],
                user=self.owner, tenant=self.tenant,
            )

    def test_recepcion_serializada_registra_costo_y_trazabilidad(self):
        orden, item = _orden_enviada_serializada(self, Decimal("1"))
        services.receive_purchase_order(
            orden,
            lines=[{"purchase_order_item": item, "units": [{"imei_1": "444444444444444", "unit_cost": Decimal("515")}]}],
            user=self.owner, tenant=self.tenant,
        )
        unidad = InventoryUnit.all_objects.get(tenant=self.tenant, imei_1="444444444444444")
        self.assertEqual(unidad.unit_cost, Decimal("515"))
        self.assertIn(orden.number, unidad.purchase_origin)
