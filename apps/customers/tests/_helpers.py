"""
Utilidades compartidas por los tests de Clientes y Proveedores (no es un
módulo de tests en sí: no empieza con "test", así que Django no lo
ejecuta directamente, solo se importa desde los demás archivos)."""

import atexit
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.tenants.models import Membership, Tenant

User = get_user_model()

# Bytes mínimos con firma binaria real de PDF — usados por los tests que
# suben documentos (ver `file_validation.py`).
PDF_VALIDO = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\ncontenido de prueba"

# Los tests de documentos suben archivos reales a disco. Como Django
# `TestCase` revierte la base de datos por transacción pero NO revierte
# el almacenamiento de archivos, sin esto los archivos subidos durante
# los tests quedarían huérfanos en el `media-private/` real del
# proyecto en cada corrida. Se redirige `MEDIA_ROOT` a un directorio
# temporal exclusivo de los tests, limpiado al terminar el proceso.
MEDIA_ROOT_TEMPORAL_TESTS = tempfile.mkdtemp(prefix="erp-saas-test-media-customers-")
atexit.register(shutil.rmtree, MEDIA_ROOT_TEMPORAL_TESTS, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TEMPORAL_TESTS)
class CustomersTestCase(TestCase):
    """Crea un tenant con un usuario dueño ya autenticado, listo para
    probar cualquier vista de Clientes/Proveedores."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Clientes", slug="empresa-clientes")
        self.user = User.objects.create_user(
            email="clientes@example.com", password="clave-de-prueba-987"
        )
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)
        self.client.login(username="clientes@example.com", password="clave-de-prueba-987")
