from decimal import Decimal

from apps.approvals import services as approvals_services
from apps.approvals.models import ApprovalPolicy, ApprovalRequest
from apps.pos import services

from ._helpers import PosTestCase


class DiscountAuthorizationTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))
        self.sale = services.start_cart(self.tenant, user=self.cajero)
        # `self.cajero` (`PosTestCase`) es rol CASHIER desde FASE 15 (antes
        # de los roles granulares, "cajero" solo podía expresarse como
        # MEMBER) — la política debe quedar keyed al rol real del usuario
        # que hace el descuento, o `ApprovalPolicy` no la encuentra.
        ApprovalPolicy.all_objects.create(
            tenant=self.tenant, scope=ApprovalPolicy.Scope.ROLE, role="cashier",
            max_discount_percent=Decimal("10"), max_discount_amount=Decimal("50"), max_credit_overage=Decimal("0"),
        )

    def test_descuento_dentro_de_ambos_limites_no_requiere_autorizacion(self):
        item = services.add_item_to_cart(
            self.sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
            discount_percent=Decimal("5"),
        )
        self.assertEqual(item.discount_percent, Decimal("5.00"))

    def test_porcentaje_dentro_pero_monto_excedido_requiere_autorizacion(self):
        # 10% de un carrito grande puede superar el tope de $50 en monto.
        with self.assertRaises(services.DiscountRequiresApproval):
            services.add_item_to_cart(
                self.sale, product=self.producto_serial, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
                discount_percent=Decimal("10"),
            )

    def test_monto_dentro_pero_porcentaje_excedido_requiere_autorizacion(self):
        with self.assertRaises(services.DiscountRequiresApproval):
            services.add_item_to_cart(
                self.sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
                discount_amount=Decimal("15"),  # 20.00 de precio, 15 de descuento = 75% > 10%
            )

    def test_propietario_nunca_requiere_autorizacion(self):
        item = services.add_item_to_cart(
            self.sale, product=self.producto_serial, quantity=Decimal("1"), user=self.owner, tenant=self.tenant,
            discount_percent=Decimal("90"),
        )
        self.assertEqual(item.discount_percent, Decimal("90.00"))

    def test_reintento_con_aprobacion_valida_aplica_el_descuento(self):
        with self.assertRaises(services.DiscountRequiresApproval) as contexto:
            services.add_item_to_cart(
                self.sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
                discount_amount=Decimal("15"),
            )
        error = contexto.exception
        solicitud = services.request_discount_approval(
            self.tenant, self.sale, self.cajero,
            percent_solicitado=error.requested_percent, amount_solicitado=error.requested_amount,
            limite_percent=error.limit_percent, limite_amount=error.limit_amount,
        )
        approvals_services.resolve_approval(solicitud, approved=True, user=self.owner, approved_value=Decimal("15"))

        item = services.add_item_to_cart(
            self.sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
            discount_amount=Decimal("15"),
        )
        self.assertEqual(item.discount_amount, Decimal("15.00"))
        solicitud.refresh_from_db()
        self.assertIsNotNone(solicitud.consumed_at)

    def test_una_aprobacion_no_puede_reutilizarse_dos_veces(self):
        solicitud = approvals_services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.cajero,
            requested_value=Decimal("15"), allowed_limit=Decimal("50"),
            document_type="sale", document_id=self.sale.pk,
        )
        approvals_services.resolve_approval(solicitud, approved=True, user=self.owner, approved_value=Decimal("15"))

        services.add_item_to_cart(
            self.sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
            discount_amount=Decimal("15"),
        )
        solicitud.refresh_from_db()
        self.assertIsNotNone(solicitud.consumed_at)

        # Un segundo descuento igual, sin nueva aprobación, debe volver a bloquear.
        with self.assertRaises(services.DiscountRequiresApproval):
            services.add_item_to_cart(
                self.sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
                discount_amount=Decimal("15"),
            )

    def test_descuento_global_tambien_requiere_autorizacion(self):
        services.add_item_to_cart(self.sale, product=self.producto_serial, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant)
        with self.assertRaises(services.DiscountRequiresApproval):
            services.set_cart_global_discount(self.sale, user=self.cajero, tenant=self.tenant, percent=Decimal("50"))

    def test_sin_ninguna_politica_configurada_cualquier_descuento_requiere_autorizacion(self):
        ApprovalPolicy.all_objects.all().delete()
        with self.assertRaises(services.DiscountRequiresApproval):
            services.add_item_to_cart(
                self.sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant,
                discount_percent=Decimal("1"),
            )
