"""Punto de entrada visual de movimientos manuales de caja (FASE 7 —
ETAPA 7 — BLOQUE F). El backend (`CashMovementCreateView`,
`CashMovementForm`, `services.record_cash_movement`, `cash.move`) ya
existía y ya estaba probado antes de este bloque — estos tests
verifican específicamente el nuevo punto de entrada HTTP real desde
`terminal.html`, nunca una segunda implementación."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.pos import services
from apps.pos.models import CashMovement
from apps.tenants.models import Membership, Tenant

from ._helpers import PosTestCase

User = get_user_model()


class CashMovementHttpViewTests(PosTestCase):
    def setUp(self):
        super().setUp()
        self.sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("100"))

        self.empleado = User.objects.create_user(email="empleado.movimiento@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.empleado, tenant=self.tenant, role=Membership.Role.EMPLOYEE)
        self.empleado_client = self.client_class()
        self.empleado_client.login(username="empleado.movimiento@example.com", password="clave-de-prueba-987")

    # 1-3. Los 3 tipos manuales, registrables por un usuario con cash.move
    def test_cajero_con_cash_move_puede_registrar_entrada_de_efectivo(self):
        respuesta = self.client.post(reverse("pos:cash_movement_create"), {
            "movement_type": "cash_in", "amount": "50", "reason": "Dotación de cambio",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("pos:terminal_start"))
        movimiento = CashMovement.all_objects.get(tenant=self.tenant, cash_session=self.sesion, movement_type="cash_in")
        self.assertEqual(movimiento.amount, Decimal("50"))

    def test_cajero_con_cash_move_puede_registrar_salida_de_efectivo(self):
        respuesta = self.client.post(reverse("pos:cash_movement_create"), {
            "movement_type": "cash_out", "amount": "20", "reason": "Compra de suministros",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("pos:terminal_start"))
        movimiento = CashMovement.all_objects.get(tenant=self.tenant, cash_session=self.sesion, movement_type="cash_out")
        self.assertEqual(movimiento.amount, Decimal("20"))

    def test_cajero_con_cash_move_puede_registrar_retiro(self):
        respuesta = self.client.post(reverse("pos:cash_movement_create"), {
            "movement_type": "withdrawal", "amount": "30", "reason": "Retiro a caja fuerte",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("pos:terminal_start"))
        movimiento = CashMovement.all_objects.get(tenant=self.tenant, cash_session=self.sesion, movement_type="withdrawal")
        self.assertEqual(movimiento.amount, Decimal("30"))

    # 4. Sin cash.move -> denegación ya existente (403)
    def test_empleado_sin_cash_move_no_puede_registrar_movimiento(self):
        respuesta = self.empleado_client.post(reverse("pos:cash_movement_create"), {
            "movement_type": "cash_in", "amount": "50", "reason": "",
        })
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(CashMovement.all_objects.filter(tenant=self.tenant, cash_session=self.sesion, movement_type="cash_in").exists())

    # 5. El movimiento se registra en la sesión correcta del cajero que lo hizo
    def test_movimiento_se_registra_en_la_sesion_del_cajero(self):
        self.client.post(reverse("pos:cash_movement_create"), {
            "movement_type": "cash_in", "amount": "15", "reason": "",
        })
        movimiento = CashMovement.all_objects.get(tenant=self.tenant, movement_type="cash_in")
        self.assertEqual(movimiento.cash_session_id, self.sesion.pk)
        self.assertEqual(movimiento.user_id, self.cajero.pk)

    # 6. get_expected_cash refleja el movimiento
    def test_get_expected_cash_refleja_el_movimiento_manual(self):
        esperado_antes = services.get_expected_cash(self.sesion)
        self.client.post(reverse("pos:cash_movement_create"), {
            "movement_type": "cash_out", "amount": "25", "reason": "",
        })
        esperado_despues = services.get_expected_cash(self.sesion)
        self.assertEqual(esperado_despues, esperado_antes - Decimal("25"))

    # 7. Sin sesión abierta -> comportamiento ya existente (rechazo, sin crear movimiento)
    def test_sin_sesion_abierta_no_se_puede_registrar_movimiento(self):
        services.close_cash_session(self.sesion, self.cajero, counted_cash=Decimal("100"))
        respuesta = self.client.post(reverse("pos:cash_movement_create"), {
            "movement_type": "cash_in", "amount": "10", "reason": "",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("pos:terminal_start"))
        self.assertFalse(CashMovement.all_objects.filter(tenant=self.tenant, movement_type="cash_in", amount=Decimal("10")).exists())

    # 8. ADJUSTMENT no es un tipo aceptado por este punto de entrada
    def test_adjustment_no_es_un_tipo_valido_para_este_formulario(self):
        respuesta = self.client.post(reverse("pos:cash_movement_create"), {
            "movement_type": "adjustment", "amount": "10", "reason": "",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("pos:terminal_start"))
        self.assertFalse(CashMovement.all_objects.filter(tenant=self.tenant, movement_type="adjustment").exists())

    def test_terminal_no_incluye_adjustment_como_opcion(self):
        respuesta = self.client.get(reverse("pos:terminal_start"))
        respuesta = self.client.get(respuesta.url)
        self.assertNotContains(respuesta, "adjustment")

    # 9. Aislamiento de tenant — la sesión activa se resuelve siempre
    # dentro del tenant/usuario de la request, nunca de otro tenant.
    def test_usuario_de_otro_tenant_sin_sesion_propia_no_afecta_la_sesion_de_este_tenant(self):
        otro_tenant = Tenant.objects.create(name="Otra empresa movimiento", slug="otra-empresa-movimiento")
        otro_owner = User.objects.create_user(email="otro.owner.movimiento@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=otro_owner, tenant=otro_tenant, role=Membership.Role.OWNER)

        otro_client = self.client_class()
        otro_client.login(username="otro.owner.movimiento@example.com", password="clave-de-prueba-987")
        respuesta = otro_client.post(reverse("pos:cash_movement_create"), {
            "movement_type": "cash_in", "amount": "999", "reason": "",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("pos:terminal_start"))
        # Ningún movimiento se creó en la sesión del tenant original.
        self.assertFalse(CashMovement.all_objects.filter(tenant=self.tenant, amount=Decimal("999")).exists())
        # Tampoco se creó nada en el otro tenant (no tiene sesión abierta).
        self.assertFalse(CashMovement.all_objects.filter(tenant=otro_tenant).exists())

    # Tarjeta visible únicamente con sesión abierta
    def test_tarjeta_de_movimiento_visible_con_sesion_abierta(self):
        respuesta = self.client.get(reverse("pos:terminal_start"))
        respuesta = self.client.get(respuesta.url)
        self.assertContains(respuesta, "Movimiento de caja")

    def test_tarjeta_de_movimiento_no_aparece_sin_sesion_abierta(self):
        services.close_cash_session(self.sesion, self.cajero, counted_cash=Decimal("100"))
        respuesta = self.client.get(reverse("pos:terminal_start"))
        respuesta = self.client.get(respuesta.url)
        self.assertNotContains(respuesta, "Movimiento de caja")
