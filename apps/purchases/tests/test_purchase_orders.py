from decimal import Decimal

from apps.approvals.services import resolve_approval, set_tenant_default_policy
from apps.purchases import services
from apps.purchases.models import PurchaseOrder, PurchasesActivityLog

from ._helpers import PurchasesTestCase


class PurchaseOrderCrudTests(PurchasesTestCase):
    def test_crear_orden_genera_numero_secuencial_oc(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.comprador)
        self.assertTrue(orden.number.startswith("OC-"))
        self.assertEqual(orden.status, PurchaseOrder.Status.DRAFT)

    def test_agregar_linea_calcula_totales(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.comprador)
        services.add_purchase_order_item(
            orden, product=self.producto, quantity=Decimal("10"), user=self.comprador, unit_cost=Decimal("10.00"),
        )
        orden.refresh_from_db()
        self.assertEqual(orden.subtotal, Decimal("100.00"))
        self.assertEqual(orden.tax_total, Decimal("18.00"))
        self.assertEqual(orden.total, Decimal("118.00"))

    def test_no_se_puede_enviar_orden_sin_lineas(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.comprador)
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.send_purchase_order(orden, self.comprador, tenant=self.tenant)

    def test_enviar_orden_cambia_estado_y_audita(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        services.add_purchase_order_item(orden, product=self.producto, quantity=Decimal("5"), user=self.owner, unit_cost=Decimal("10"))
        enviada = services.send_purchase_order(orden, self.owner, tenant=self.tenant)
        self.assertEqual(enviada.status, PurchaseOrder.Status.SENT)
        self.assertIsNotNone(enviada.sent_at)
        self.assertTrue(
            PurchasesActivityLog.all_objects.filter(
                tenant=self.tenant, entity_type="purchase_order", entity_id=orden.pk,
                action=PurchasesActivityLog.Action.SENT,
            ).exists()
        )

    def test_no_se_puede_agregar_linea_a_orden_ya_enviada(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        services.add_purchase_order_item(orden, product=self.producto, quantity=Decimal("5"), user=self.owner, unit_cost=Decimal("10"))
        services.send_purchase_order(orden, self.owner, tenant=self.tenant)
        with self.assertRaises(services.InvalidPurchaseOperation):
            services.add_purchase_order_item(orden, product=self.producto, quantity=Decimal("1"), user=self.owner)

    def test_cancelar_orden_en_borrador(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        cancelada = services.cancel_purchase_order(orden, self.owner, reason="ya no se necesita")
        self.assertEqual(cancelada.status, PurchaseOrder.Status.CANCELED)

    def test_propietario_no_requiere_autorizacion_de_compra_sobre_el_limite(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        services.add_purchase_order_item(
            orden, product=self.producto, quantity=Decimal("1000"), user=self.owner, unit_cost=Decimal("500"),
        )
        enviada = services.send_purchase_order(orden, self.owner, tenant=self.tenant)
        self.assertEqual(enviada.status, PurchaseOrder.Status.SENT)

    def test_compra_sobre_el_limite_exige_autorizacion(self):
        set_tenant_default_policy(
            self.tenant, max_discount_percent=Decimal("0"), max_discount_amount=Decimal("0"),
            max_credit_overage=Decimal("0"), max_purchase_order_amount=Decimal("100"),
        )
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.comprador)
        services.add_purchase_order_item(
            orden, product=self.producto, quantity=Decimal("10"), user=self.comprador, unit_cost=Decimal("50"),
        )
        with self.assertRaises(services.PurchaseOverThresholdRequiresApproval) as ctx:
            services.send_purchase_order(orden, self.comprador, tenant=self.tenant)

        # `ctx.exception.total` (no `orden.total`): `orden` en memoria
        # sigue con `.total = 0`, el valor por defecto en la creación —
        # `add_purchase_order_item` actualiza el total en una COPIA
        # bloqueada distinta, nunca refresca este objeto Python (mismo
        # patrón ya documentado en apps.sales.services). La excepción sí
        # trae el total real, calculado dentro del servicio.
        solicitud = services.request_purchase_approval(self.tenant, orden, self.comprador, limite=ctx.exception.limit)
        resolve_approval(solicitud, approved=True, user=self.owner, approved_value=ctx.exception.total)
        # No se pasa `use_approval`: `send_purchase_order` debe encontrar la
        # solicitud aprobada por sí solo (`get_usable_approved_request`),
        # igual que en el flujo real de la vista.
        enviada = services.send_purchase_order(orden, self.comprador, tenant=self.tenant)
        self.assertEqual(enviada.status, PurchaseOrder.Status.SENT)

    def test_cerrar_orden_parcialmente_recibida(self):
        orden = services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        item = services.add_purchase_order_item(orden, product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=Decimal("10"))
        services.send_purchase_order(orden, self.owner, tenant=self.tenant)
        services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("6")}],
            user=self.owner, tenant=self.tenant,
        )
        cerrada = services.close_purchase_order(orden, self.owner)
        self.assertEqual(cerrada.status, PurchaseOrder.Status.CLOSED)
