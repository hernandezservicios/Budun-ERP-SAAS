"""ALLOW/DENY del enforcement real de permisos en `apps.sales`
(FASE 7 — ETAPA 7 — BLOQUE 8). Verificación en servidor vía HTTP real
— nunca se asume que ocultar un botón en la UI sea suficiente.

Roles reales usados (ver `apps.permissions.catalog.DEFAULT_ROLE_PERMISSIONS`):
- OWNER: siempre autorizado (regla permanente de `has_permission`).
- CASHIER: tiene `sales.view`/`sales.create`/`payments.create`, pero
  NO `sales.update`/`sales.cancel`/`sales.refund`/`payments.reverse`
  — diferenciación deliberada del catálogo (vender es una cosa, poder
  editar/cancelar/reembolsar/revertir un pago ya registrado es otra).
- EMPLOYEE: solo lectura (`sales.view`), ninguna acción de escritura.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.sales import services as sales_services
from apps.sales.models import PaymentAllocation
from apps.tenants.models import Membership

from ._helpers import SalesTestCase

User = get_user_model()


class SalesPermissionTests(SalesTestCase):
    def setUp(self):
        super().setUp()
        self.empleado = User.objects.create_user(email="empleado.ventas@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.empleado, tenant=self.tenant, role=Membership.Role.EMPLOYEE)
        self.empleado_client = self.client_class()
        self.empleado_client.login(username="empleado.ventas@example.com", password="clave-de-prueba-987")

        self.cajero = User.objects.create_user(email="cajero.ventas@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.cajero, tenant=self.tenant, role=Membership.Role.CASHIER)
        self.cajero_client = self.client_class()
        self.cajero_client.login(username="cajero.ventas@example.com", password="clave-de-prueba-987")

    def _venta_draft(self):
        return sales_services.create_sale(self.tenant, user=self.user, customer=self.customer)

    def _venta_confirmada(self):
        venta = self._venta_draft()
        sales_services.add_sale_item(venta, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        return sales_services.confirm_sale(venta, self.user)

    # ------------------------------------------------------------
    # sales.create
    # ------------------------------------------------------------

    def test_empleado_sin_sales_create_no_puede_crear_venta(self):
        respuesta = self.empleado_client.post(reverse("sales:sale_create"), {
            "customer": self.customer.pk, "currency": "USD", "payment_terms": "contado",
            "notes": "", "terms": "", "global_discount_percent": "0", "global_discount_amount": "0", "issue_date": "",
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_cajero_con_sales_create_puede_crear_venta(self):
        respuesta = self.cajero_client.post(reverse("sales:sale_create"), {
            "customer": self.customer.pk, "currency": "USD", "payment_terms": "contado",
            "notes": "", "terms": "", "global_discount_percent": "0", "global_discount_amount": "0", "issue_date": "",
        })
        venta = self._ultima_venta()
        self.assertIsNotNone(venta)
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[venta.pk]))

    def _ultima_venta(self):
        from apps.sales.models import Sale

        return Sale.all_objects.filter(tenant=self.tenant).order_by("-id").first()

    # ------------------------------------------------------------
    # sales.update (agregar/eliminar línea, confirmar)
    # ------------------------------------------------------------

    def test_empleado_sin_sales_update_no_puede_agregar_linea(self):
        venta = self._venta_draft()
        respuesta = self.empleado_client.post(reverse("sales:sale_item_add", args=[venta.pk]), {
            "product": self.producto_cantidad.pk, "quantity": "1", "unit_identifier": "",
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_cajero_sin_sales_update_no_puede_confirmar_venta(self):
        venta = self._venta_draft()
        sales_services.add_sale_item(venta, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        respuesta = self.cajero_client.post(reverse("sales:sale_confirm", args=[venta.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_owner_con_sales_update_puede_confirmar_venta(self):
        venta = self._venta_draft()
        sales_services.add_sale_item(venta, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        respuesta = self.client.post(reverse("sales:sale_confirm", args=[venta.pk]))
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[venta.pk]))

    # ------------------------------------------------------------
    # sales.cancel
    # ------------------------------------------------------------

    def test_cajero_sin_sales_cancel_no_puede_cancelar_venta(self):
        venta = self._venta_draft()
        respuesta = self.cajero_client.post(reverse("sales:sale_cancel", args=[venta.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_owner_con_sales_cancel_puede_cancelar_venta(self):
        venta = self._venta_draft()
        respuesta = self.client.post(reverse("sales:sale_cancel", args=[venta.pk]))
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[venta.pk]))

    # ------------------------------------------------------------
    # sales.refund (devolución de mercancía)
    # ------------------------------------------------------------

    def test_cajero_sin_sales_refund_no_puede_iniciar_devolucion(self):
        venta = self._venta_confirmada()
        respuesta = self.cajero_client.post(reverse("sales:sale_return_create", args=[venta.pk]), {})
        self.assertEqual(respuesta.status_code, 403)

    def test_empleado_sin_sales_refund_no_puede_iniciar_devolucion(self):
        venta = self._venta_confirmada()
        respuesta = self.empleado_client.post(reverse("sales:sale_return_create", args=[venta.pk]), {})
        self.assertEqual(respuesta.status_code, 403)

    # ------------------------------------------------------------
    # payments.create
    # ------------------------------------------------------------

    def test_empleado_sin_payments_create_no_puede_registrar_pago(self):
        venta = self._venta_confirmada()
        respuesta = self.empleado_client.post(reverse("sales:sale_payment_add", args=[venta.pk]), {
            "method": "cash", "amount": "5",
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_cajero_con_payments_create_puede_registrar_pago(self):
        venta = self._venta_confirmada()
        respuesta = self.cajero_client.post(reverse("sales:sale_payment_add", args=[venta.pk]), {
            "method": "cash", "amount": "5",
        })
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[venta.pk]))

    # ------------------------------------------------------------
    # payments.reverse — el cajero NO lo tiene por catálogo (diseño
    # real: revertir un pago ya registrado requiere un rol superior)
    # ------------------------------------------------------------

    def test_cajero_sin_payments_reverse_no_puede_revertir_pago(self):
        venta = self._venta_confirmada()
        sales_services.record_payment_for_sale(venta, user=self.user, method="cash", amount=Decimal("5"))
        # `all_objects` + filtro explícito de tenant: fuera de una
        # request real no hay `ContextVar` de tenant activo para que el
        # manager por defecto (`objects`) resuelva nada (mismo bug-class
        # documentado en CLAUDE.md/KNOWN_ISSUES.md).
        allocation = PaymentAllocation.all_objects.filter(tenant=self.tenant, sale=venta).first()
        respuesta = self.cajero_client.post(reverse("sales:sale_payment_reverse", args=[venta.pk, allocation.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_owner_con_payments_reverse_puede_revertir_pago(self):
        venta = self._venta_confirmada()
        sales_services.record_payment_for_sale(venta, user=self.user, method="cash", amount=Decimal("5"))
        allocation = PaymentAllocation.all_objects.filter(tenant=self.tenant, sale=venta).first()
        respuesta = self.client.post(reverse("sales:sale_payment_reverse", args=[venta.pk, allocation.pk]))
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[venta.pk]))

    # ------------------------------------------------------------
    # Tenant isolation — el permiso nunca sustituye el filtro de tenant
    # ------------------------------------------------------------

    def test_permiso_no_rompe_aislamiento_de_tenant(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra empresa", slug="otra-empresa-permisos")
        otro_owner = User.objects.create_user(email="otro.owner@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=otro_owner, tenant=otro_tenant, role=Membership.Role.OWNER)
        venta_ajena = sales_services.create_sale(self.tenant, user=self.user)

        otro_client = self.client_class()
        otro_client.login(username="otro.owner@example.com", password="clave-de-prueba-987")
        respuesta = otro_client.post(reverse("sales:sale_cancel", args=[venta_ajena.pk]))
        # OWNER siempre tiene el permiso — el rechazo real debe venir
        # del filtro de tenant (404), nunca del permiso (403).
        self.assertEqual(respuesta.status_code, 404)
