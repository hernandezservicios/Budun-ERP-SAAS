from decimal import Decimal

from django.urls import reverse

from apps.pos import services
from apps.pos.models import CashMovement, CashRegister, CashSession

from ._helpers import PosTestCase


class CashSessionServiceTests(PosTestCase):
    def test_abrir_caja_crea_sesion_y_movimiento_de_apertura(self):
        sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("500"))
        self.assertEqual(sesion.status, CashSession.Status.OPEN)
        self.assertEqual(sesion.opening_amount, Decimal("500"))
        movimiento = CashMovement.all_objects.get(tenant=self.tenant, cash_session=sesion)
        self.assertEqual(movimiento.movement_type, CashMovement.MovementType.OPENING)
        self.assertEqual(movimiento.amount, Decimal("500"))

    def test_abrir_caja_con_fondo_cero_es_valido(self):
        sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("0"))
        self.assertEqual(sesion.opening_amount, Decimal("0"))

    def test_abrir_caja_con_fondo_negativo_es_rechazado(self):
        with self.assertRaises(services.InvalidPosOperation):
            services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("-1"))

    def test_usuario_no_autorizado_no_puede_abrir_caja(self):
        otro = self.owner.__class__.objects.create_user(email="no.autorizado@example.com", password="clave-de-prueba-987")
        from apps.tenants.models import Membership

        Membership.objects.create(user=otro, tenant=self.tenant, role=Membership.Role.MEMBER)
        with self.assertRaises(services.InvalidPosOperation):
            services.open_cash_session(self.tenant, cash_register=self.caja, user=otro, opening_amount=Decimal("100"))

    def test_propietario_siempre_autorizado_para_cualquier_caja(self):
        sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.owner, opening_amount=Decimal("100"))
        self.assertEqual(sesion.user, self.owner)

    def test_no_se_puede_abrir_dos_sesiones_en_la_misma_caja(self):
        services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("100"))
        with self.assertRaises(services.InvalidPosOperation):
            services.open_cash_session(self.tenant, cash_register=self.caja, user=self.owner, opening_amount=Decimal("100"))

    def test_un_usuario_no_puede_tener_dos_sesiones_activas(self):
        otra_caja = CashRegister.all_objects.create(tenant=self.tenant, name="Caja 2", code="CAJA-02")
        services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("100"))
        with self.assertRaises(services.InvalidPosOperation):
            services.open_cash_session(self.tenant, cash_register=otra_caja, user=self.cajero, opening_amount=Decimal("100"))

    def test_caja_inactiva_no_se_puede_abrir(self):
        self.caja.status = CashRegister.Status.INACTIVE
        self.caja.save(update_fields=["status"])
        with self.assertRaises(services.InvalidPosOperation):
            services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("100"))

    def test_efectivo_esperado_suma_movimientos_correctamente(self):
        sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("500"))
        services.record_cash_movement(sesion, movement_type=CashMovement.MovementType.CASH_IN, amount=Decimal("100"), user=self.cajero)
        services.record_cash_movement(sesion, movement_type=CashMovement.MovementType.CASH_OUT, amount=Decimal("50"), user=self.cajero)
        # 500 + 100 - 50 = 550
        self.assertEqual(services.get_expected_cash(sesion), Decimal("550"))

    def test_cerrar_caja_calcula_esperado_contado_y_diferencia(self):
        sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("500"))
        cerrada = services.close_cash_session(sesion, self.cajero, counted_cash=Decimal("510"))
        self.assertEqual(cerrada.expected_cash, Decimal("500"))
        self.assertEqual(cerrada.counted_cash, Decimal("510"))
        self.assertEqual(cerrada.difference, Decimal("10"))
        self.assertEqual(cerrada.status, CashSession.Status.CLOSED)

    def test_cerrar_una_sesion_ya_cerrada_es_un_error_no_un_no_op(self):
        sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("500"))
        services.close_cash_session(sesion, self.cajero, counted_cash=Decimal("500"))
        with self.assertRaises(services.InvalidPosOperation):
            services.close_cash_session(sesion, self.cajero, counted_cash=Decimal("999"))
        sesion.refresh_from_db()
        self.assertEqual(sesion.counted_cash, Decimal("500"))  # el resultado histórico no cambió

    def test_no_se_pueden_registrar_movimientos_en_sesion_cerrada(self):
        sesion = services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("500"))
        services.close_cash_session(sesion, self.cajero, counted_cash=Decimal("500"))
        with self.assertRaises(services.InvalidPosOperation):
            services.record_cash_movement(sesion, movement_type=CashMovement.MovementType.CASH_IN, amount=Decimal("10"), user=self.cajero)

    def test_ensure_open_session_for_checkout_lanza_sin_sesion(self):
        with self.assertRaises(services.InvalidPosOperation):
            services.ensure_open_session_for_checkout(self.tenant, self.cajero)


class CashSessionHttpViewTests(PosTestCase):
    def test_abrir_caja_via_http(self):
        respuesta = self.client.post(reverse("pos:session_open"), {
            "cash_register": self.caja.pk, "opening_amount": "500", "notes": "",
        })
        # `pos:terminal_start` es en sí mismo un redirect (crea/reutiliza
        # el carrito), así que no se sigue la cadena completa aquí.
        self.assertRedirects(respuesta, reverse("pos:terminal_start"), target_status_code=302)
        self.assertTrue(CashSession.all_objects.filter(tenant=self.tenant, user=self.cajero, status=CashSession.Status.OPEN).exists())

    def test_cerrar_caja_via_http(self):
        services.open_cash_session(self.tenant, cash_register=self.caja, user=self.cajero, opening_amount=Decimal("500"))
        respuesta = self.client.post(reverse("pos:session_close"), {"counted_cash": "500", "closing_notes": ""})
        self.assertEqual(respuesta.status_code, 302)
        sesion = CashSession.all_objects.get(tenant=self.tenant, user=self.cajero)
        self.assertEqual(sesion.status, CashSession.Status.CLOSED)

    def test_crear_caja_requiere_ser_propietario(self):
        respuesta = self.client.post(reverse("pos:register_list"), {"name": "Nueva", "code": "CAJA-99", "terminal": ""})
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(CashRegister.all_objects.filter(tenant=self.tenant, code="CAJA-99").exists())

    def test_propietario_puede_crear_caja(self):
        respuesta = self.owner_client.post(reverse("pos:register_list"), {"name": "Nueva", "code": "CAJA-99", "terminal": ""})
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(CashRegister.all_objects.filter(tenant=self.tenant, code="CAJA-99").exists())
