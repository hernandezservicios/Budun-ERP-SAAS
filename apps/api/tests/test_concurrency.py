"""
FASE 18 — Security Hardening. Cierra un hallazgo de cobertura ya
documentado en `docs/security.md` ("Pendiente en FASE 18: cobertura
sistemática de rotación de credenciales (ApiKey/Integration) bajo
concurrencia, no probada explícitamente todavía"): dos solicitudes de
rotación simultáneas de la MISMA `ApiKey` (ej. doble clic en "Rotar",
o dos pestañas de administración abiertas a la vez) nunca deben dejar
el sistema en un estado inconsistente (fila duplicada, tenant sin
ninguna clave activa, excepción no manejada). Mismo patrón
(`TransactionTestCase` + hilos reales) que `apps.billing.tests.
test_concurrency`/`apps.sales.tests.test_concurrency` desde FASE 8/10.

Resultado esperado y aceptado (documentado, no un hallazgo a corregir):
`rotate_api_key` no usa `select_for_update()` porque no lo necesita
para su única garantía real — "nunca dos claves activas a la vez" —
que ya cumple por construcción (siempre reescribe la MISMA fila, nunca
inserta una segunda). Bajo dos rotaciones simultáneas, gana la que
guarda último (last-write-wins): el otro secreto en texto plano
devuelto a ese admin queda inválido de inmediato. Es una ambigüedad de
UX aceptable (quedó documentada), nunca una fila duplicada, un tenant
sin clave, ni una excepción no controlada."""

import threading

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from apps.api import services
from apps.api.models import ApiKey
from apps.tenants.models import Tenant

User = get_user_model()


class ApiKeyRotationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrencia API Key", slug="concurrencia-api-key")
        self.owner = User.objects.create_user(email="owner.concurrencia.api@example.com", password="clave-de-prueba-987")
        self.api_key, self.secreto_original = services.generate_api_key(
            self.tenant, user=self.owner, scopes=["inventory:read"],
        )

    def test_dos_rotaciones_simultaneas_dejan_exactamente_una_clave_activa_consistente(self):
        resultados = []
        errores = []
        barrera = threading.Barrier(2)

        def rotar():
            barrera.wait()
            try:
                api_key_fila = ApiKey.all_objects.get(pk=self.api_key.pk)
                _api_key, secreto = services.rotate_api_key(api_key_fila, user=self.owner)
                resultados.append(secreto)
            except Exception as error:  # noqa: BLE001 — la prueba debe ver cualquier excepción, no solo las esperadas.
                errores.append(error)
            finally:
                connection.close()

        hilos = [threading.Thread(target=rotar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        self.assertEqual(errores, [], "Ninguna rotación concurrente debe lanzar una excepción no controlada.")
        self.assertEqual(len(resultados), 2)

        # Nunca una fila duplicada — sigue existiendo exactamente una
        # `ApiKey` para el tenant, siempre la misma fila (mismo pk).
        self.assertEqual(ApiKey.all_objects.filter(tenant=self.tenant).count(), 1)
        clave_final = ApiKey.all_objects.get(tenant=self.tenant)
        self.assertEqual(clave_final.pk, self.api_key.pk)
        self.assertEqual(clave_final.status, ApiKey.Status.ACTIVE)

        # Exactamente uno de los dos secretos devueltos (el de la
        # rotación que guardó último) es el que realmente autentica
        # ahora — nunca ambos, nunca ninguno, nunca el original.
        autenticaciones_validas = [
            secreto for secreto in resultados
            if services.authenticate_api_key(secreto) is not None
        ]
        self.assertEqual(len(autenticaciones_validas), 1)
        self.assertIsNone(services.authenticate_api_key(self.secreto_original))
