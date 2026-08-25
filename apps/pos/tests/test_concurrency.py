"""Concurrencia real de FASE 11 (requisito explícito del usuario): dos
aperturas simultáneas de la misma caja nunca deben crear dos sesiones
activas, y un usuario nunca debe poder tener dos sesiones activas a la
vez, ni siquiera bajo una carrera real entre hilos — mismo patrón que
`apps.sales.tests.test_concurrency` (`TransactionTestCase` + hilos +
`connection.close()` por hilo)."""

import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from apps.pos import services
from apps.pos.models import CashRegister, CashSession
from apps.tenants.models import Membership, Tenant

User = get_user_model()


class CashSessionConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrencia POS", slug="concurrencia-pos")
        self.owner = User.objects.create_user(email="concurrencia.pos@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner, tenant=self.tenant, role=Membership.Role.OWNER)
        self.caja = CashRegister.all_objects.create(tenant=self.tenant, name="Caja Concurrente", code="CAJA-CONC")

    def test_dos_aperturas_concurrentes_de_la_misma_caja_solo_una_gana(self):
        usuarios = [
            User.objects.create_user(email=f"concurrencia.pos.{i}@example.com", password="clave-de-prueba-987")
            for i in range(2)
        ]
        for usuario in usuarios:
            Membership.objects.create(user=usuario, tenant=self.tenant, role=Membership.Role.OWNER)

        resultados = []
        barrera = threading.Barrier(2)

        def intentar_abrir(usuario):
            barrera.wait()
            try:
                connection.close()
                services.open_cash_session(self.tenant, cash_register=self.caja, user=usuario, opening_amount=Decimal("100"))
                resultados.append("ok")
            except services.InvalidPosOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=intentar_abrir, args=(usuario,)) for usuario in usuarios]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1, "Exactamente una apertura debe ganar sobre la misma caja.")
        self.assertEqual(resultados.count("rechazado"), 1)
        self.assertEqual(CashSession.all_objects.filter(tenant=self.tenant, cash_register=self.caja, status=CashSession.Status.OPEN).count(), 1)

    def test_dos_aperturas_concurrentes_del_mismo_usuario_solo_una_gana(self):
        cajas = [
            CashRegister.all_objects.create(tenant=self.tenant, name=f"Caja {i}", code=f"CAJA-U{i}")
            for i in range(2)
        ]
        resultados = []
        barrera = threading.Barrier(2)

        def intentar_abrir(caja):
            barrera.wait()
            try:
                connection.close()
                services.open_cash_session(self.tenant, cash_register=caja, user=self.owner, opening_amount=Decimal("100"))
                resultados.append("ok")
            except services.InvalidPosOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=intentar_abrir, args=(caja,)) for caja in cajas]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(resultados.count("ok"), 1, "El mismo usuario nunca debe terminar con dos sesiones activas.")
        self.assertEqual(CashSession.all_objects.filter(tenant=self.tenant, user=self.owner, status=CashSession.Status.OPEN).count(), 1)
