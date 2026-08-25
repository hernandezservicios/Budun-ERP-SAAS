"""
Utilidades compartidas por los tests del motor comercial (no es un
módulo de tests en sí: no empieza con "test", así que Django no lo
ejecuta directamente, solo se importa desde los demás archivos)."""

import atexit
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.customers.models import Customer
from apps.inventory import services as inv_services
from apps.inventory.models import Product
from apps.tenants.models import Membership, Tenant

User = get_user_model()

# Bytes mínimos con firma binaria real de PDF — usados por los tests que
# suben adjuntos (ver `apps.customers.file_validation`).
PDF_VALIDO = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\ncontenido de prueba"

# Los tests de adjuntos suben archivos reales a disco. Igual que en
# FASE 9, se redirige `MEDIA_ROOT` a un directorio temporal exclusivo de
# los tests (Django `TestCase` revierte la base de datos por
# transacción, pero NO revierte el almacenamiento de archivos).
MEDIA_ROOT_TEMPORAL_TESTS = tempfile.mkdtemp(prefix="erp-saas-test-media-sales-")
atexit.register(shutil.rmtree, MEDIA_ROOT_TEMPORAL_TESTS, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TEMPORAL_TESTS)
class SalesTestCase(TestCase):
    """Crea un tenant con un usuario dueño ya autenticado, un cliente,
    un producto por CANTIDAD con stock y un producto SERIALIZADO con una
    unidad EN_STOCK — listo para probar cualquier vista/servicio del
    motor comercial."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Ventas", slug="empresa-ventas")
        self.user = User.objects.create_user(email="ventas@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)
        self.client.login(username="ventas@example.com", password="clave-de-prueba-987")

        self.customer = Customer.objects.create(tenant=self.tenant, first_name="Cliente", last_name="De Prueba")

        self.producto_cantidad = Product.objects.create(
            tenant=self.tenant, name="Cable HDMI", sku="TST-CABLE-1",
            sale_price=Decimal("20.00"), tax_rate=Decimal("18"),
        )
        inv_services.register_stock_in(product=self.producto_cantidad, quantity=Decimal("50"), user=self.user)

        self.producto_serial = Product.objects.create(
            tenant=self.tenant, name="iPhone Test", sku="TST-TEL-1",
            sale_price=Decimal("800.00"), tax_rate=Decimal("18"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.unidad = inv_services.register_serialized_unit(
            product=self.producto_serial, user=self.user, imei_1="111222333444555"
        )
