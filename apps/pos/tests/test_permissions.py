"""ALLOW/DENY del enforcement real de permisos en `apps.pos`
(FASE 7 — ETAPA 7 — BLOQUE 8). Verificación en servidor vía HTTP real
— nunca se asume que ocultar un botón en la UI sea suficiente.

Roles reales usados (ver `apps.permissions.catalog.DEFAULT_ROLE_PERMISSIONS`):
- OWNER: siempre autorizado (regla permanente de `has_permission`).
- CASHIER: tiene `pos.use`/`cash.*`/`payments.create`/`credit.view`/
  `credit_note.view`+`apply`, pero NO `credit.apply` ni
  `credit_note.create` — diferenciación deliberada del catálogo
  (vender/cobrar es una cosa, aplicar saldo a favor o emitir una nota
  de crédito es una operación de mayor confianza reservada a MANAGER).
- MANAGER: tiene el conjunto completo de permisos POS/Cobros.
- EMPLOYEE: sin ningún permiso de POS/Cobros por defecto.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.pos import services
from apps.sales import services as sales_services
from apps.tenants.models import Membership

from ._helpers import PosTestCase

User = get_user_model()


class PosPermissionTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = User.objects.create_user(email="empleado.pos@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.empleado, tenant=self.tenant, role=Membership.Role.EMPLOYEE)
        self.empleado_client = self.client_class()
        self.empleado_client.login(username="empleado.pos@example.com", password="clave-de-prueba-987")

        self.gerente = User.objects.create_user(email="gerente.pos@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.gerente, tenant=self.tenant, role=Membership.Role.MANAGER)
        self.gerente_client = self.client_class()
        self.gerente_client.login(username="gerente.pos@example.com", password="clave-de-prueba-987")

        self.sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))

    def _venta_confirmada(self, total_deseado):
        from apps.inventory import services as inv_services

        inv_services.register_stock_in(product=self.producto, quantity=total_deseado, user=self.owner)
        venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.customer)
        sales_services.add_sale_item(
            venta, product=self.producto, quantity=total_deseado, user=self.owner,
            unit_price=Decimal("1"), tax_rate=Decimal("0"),
        )
        return sales_services.confirm_sale(venta, self.owner)

    # ------------------------------------------------------------
    # pos.use — Terminal
    # ------------------------------------------------------------

    def test_cajero_con_pos_use_puede_iniciar_terminal(self):
        respuesta = self.client.get(reverse("pos:terminal_start"))
        self.assertEqual(respuesta.status_code, 302)

    def test_empleado_sin_pos_use_no_puede_iniciar_terminal(self):
        respuesta = self.empleado_client.get(reverse("pos:terminal_start"))
        self.assertEqual(respuesta.status_code, 403)

    def test_empleado_sin_pos_use_no_puede_agregar_producto(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        respuesta = self.empleado_client.post(reverse("pos:add_item", args=[sale.pk]), {
            "product_id": self.producto.pk, "quantity": "1", "unit_identifier": "", "discount_percent": "", "discount_amount": "",
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_empleado_sin_pos_use_no_puede_cobrar(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        services.add_item_to_cart(sale, product=self.producto, quantity=Decimal("1"), user=self.cajero, tenant=self.tenant)
        respuesta = self.empleado_client.post(reverse("pos:checkout", args=[sale.pk]), {
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "0", "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-method": "cash", "form-0-amount": str(sale.total),
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_empleado_sin_pos_use_no_puede_cancelar_carrito(self):
        sale = services.start_cart(self.tenant, user=self.cajero)
        respuesta = self.empleado_client.post(reverse("pos:cancel_cart", args=[sale.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_owner_siempre_autorizado_para_pos_use(self):
        respuesta = self.owner_client.get(reverse("pos:terminal_start"))
        self.assertEqual(respuesta.status_code, 302)

    # ------------------------------------------------------------
    # cash.view — Resumen de sesión
    # ------------------------------------------------------------

    def test_cajero_con_cash_view_puede_ver_resumen_de_sesion(self):
        cerrada = services.close_cash_session(self.sesion, self.cajero, counted_cash=Decimal("0"))
        respuesta = self.client.get(reverse("pos:session_summary", args=[cerrada.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_empleado_sin_cash_view_no_puede_ver_resumen_de_sesion(self):
        cerrada = services.close_cash_session(self.sesion, self.cajero, counted_cash=Decimal("0"))
        respuesta = self.empleado_client.get(reverse("pos:session_summary", args=[cerrada.pk]))
        self.assertEqual(respuesta.status_code, 403)

    # ------------------------------------------------------------
    # payments.create — Cobros (cobrar factura, registrar anticipo)
    # ------------------------------------------------------------

    def test_cajero_con_payments_create_puede_registrar_anticipo(self):
        respuesta = self.client.post(reverse("pos:register_advance", args=[self.customer.pk]), {
            "method": "cash", "amount": "50", "reference": "", "notes": "",
        })
        self.assertRedirects(respuesta, reverse("pos:customer_collections", args=[self.customer.pk]))

    def test_empleado_sin_payments_create_no_puede_registrar_anticipo(self):
        respuesta = self.empleado_client.post(reverse("pos:register_advance", args=[self.customer.pk]), {
            "method": "cash", "amount": "50", "reference": "", "notes": "",
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_empleado_sin_payments_create_no_puede_cobrar_factura(self):
        factura = self._venta_confirmada(Decimal("100"))
        respuesta = self.empleado_client.post(reverse("pos:collect_payment", args=[self.customer.pk]), {
            "sale_ids": [str(factura.pk)], "method": "cash", "amount": "100", "reference": "",
        })
        self.assertEqual(respuesta.status_code, 403)

    # ------------------------------------------------------------
    # credit.apply — el cajero NO lo tiene por catálogo (diseño real)
    # ------------------------------------------------------------

    def test_cajero_sin_credit_apply_no_puede_aplicar_saldo_a_favor(self):
        services.register_customer_advance(self.tenant, customer=self.customer, method="transfer", amount=Decimal("100"), user=self.owner)
        factura = self._venta_confirmada(Decimal("150"))
        respuesta = self.client.post(reverse("pos:apply_credit", args=[self.customer.pk, factura.pk]), {"amount": "50"})
        self.assertEqual(respuesta.status_code, 403)

    def test_gerente_con_credit_apply_puede_aplicar_saldo_a_favor(self):
        services.register_customer_advance(self.tenant, customer=self.customer, method="transfer", amount=Decimal("100"), user=self.owner)
        factura = self._venta_confirmada(Decimal("150"))
        respuesta = self.gerente_client.post(reverse("pos:apply_credit", args=[self.customer.pk, factura.pk]), {"amount": "50"})
        self.assertRedirects(respuesta, reverse("pos:customer_collections", args=[self.customer.pk]))

    # ------------------------------------------------------------
    # credit_note.create — el cajero NO lo tiene por catálogo
    # ------------------------------------------------------------

    def test_cajero_sin_credit_note_create_no_puede_emitir_nota_de_credito(self):
        respuesta = self.client.post(reverse("pos:issue_credit_note", args=[self.customer.pk]), {
            "amount": "40", "reason": "cortesía",
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_gerente_con_credit_note_create_puede_emitir_nota_de_credito(self):
        respuesta = self.gerente_client.post(reverse("pos:issue_credit_note", args=[self.customer.pk]), {
            "amount": "40", "reason": "cortesía",
        })
        self.assertRedirects(respuesta, reverse("pos:customer_collections", args=[self.customer.pk]))

    # ------------------------------------------------------------
    # payments.reverse (Refund) — el cajero NO lo tiene por catálogo
    # ------------------------------------------------------------

    def test_cajero_sin_payments_reverse_no_puede_reembolsar(self):
        pago = sales_services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("300"), user=self.owner)
        respuesta = self.client.post(reverse("pos:refund_payment", args=[self.customer.pk, pago.pk]), {
            "mode": "cash", "amount": "100", "reason": "",
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_gerente_con_payments_reverse_puede_reembolsar(self):
        pago = sales_services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("300"), user=self.owner)
        respuesta = self.gerente_client.post(reverse("pos:refund_payment", args=[self.customer.pk, pago.pk]), {
            "mode": "credit", "amount": "100", "reason": "",
        })
        self.assertRedirects(respuesta, reverse("pos:customer_collections", args=[self.customer.pk]))

    # ------------------------------------------------------------
    # cash.open / cash.close / cash.move — ya estaban correctamente
    # protegidos antes de este bloque; se reconfirma aquí que el
    # bloque no los alteró.
    # ------------------------------------------------------------

    def test_empleado_sin_cash_open_no_puede_abrir_caja(self):
        respuesta = self.empleado_client.post(reverse("pos:session_open"), {
            "cash_register": self.caja.pk, "opening_amount": "0", "notes": "",
        })
        self.assertEqual(respuesta.status_code, 403)

    # ------------------------------------------------------------
    # Tenant isolation — el permiso nunca sustituye el filtro de tenant
    # ------------------------------------------------------------

    def test_permiso_no_rompe_aislamiento_de_tenant(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra empresa POS", slug="otra-empresa-pos")
        otro_owner = User.objects.create_user(email="otro.owner.pos@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=otro_owner, tenant=otro_tenant, role=Membership.Role.OWNER)
        carrito_ajeno = sales_services.create_sale(self.tenant, user=self.owner)

        otro_client = self.client_class()
        otro_client.login(username="otro.owner.pos@example.com", password="clave-de-prueba-987")
        respuesta = otro_client.post(reverse("pos:cancel_cart", args=[carrito_ajeno.pk]))
        # OWNER siempre tiene pos.use — el rechazo real debe venir del
        # filtro de tenant (404), nunca del permiso (403).
        self.assertEqual(respuesta.status_code, 404)
