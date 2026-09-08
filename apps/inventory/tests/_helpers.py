"""
Utilidades compartidas por los tests de inventario (no es un módulo de
tests en sí: no empieza con "test", así que Django no lo ejecuta
directamente, solo se importa desde los demás archivos)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tenants.models import Membership, Tenant

User = get_user_model()


class InventoryTestCase(TestCase):
    """Crea un tenant con un usuario dueño ya autenticado, listo para
    probar cualquier vista de inventario."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Inventario", slug="empresa-inventario")
        self.user = User.objects.create_user(
            email="inventario@example.com", password="clave-de-prueba-987"
        )
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)
        self.client.login(username="inventario@example.com", password="clave-de-prueba-987")


def construir_excel(filas, *, headers=None, nombre="archivo.xlsx"):
    """Construye un `.xlsx` real en memoria (nunca un mock) — usado por
    los tests de importación masiva de productos
    (`apps.inventory.product_import`). `headers` por defecto son los
    encabezados oficiales del propio módulo."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from openpyxl import Workbook

    from apps.inventory.product_import import _HEADERS_OFICIALES

    libro = Workbook()
    hoja = libro.active
    hoja.append(list(headers if headers is not None else _HEADERS_OFICIALES))
    for fila in filas:
        hoja.append(list(fila))
    buffer = BytesIO()
    libro.save(buffer)
    return SimpleUploadedFile(
        nombre, buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def fila_producto(
    sku="SKU-001", name="Producto de prueba", barcode="", category="", description="",
    brand="", model_name="", tracking="", sale_price="100.00", purchase_price="", tax_rate="",
    min_stock="", is_active="", variant_attributes="",
):
    """Fila en el MISMO orden que `_HEADERS_OFICIALES` — evita repetir
    14 posiciones en cada test."""
    return [
        sku, name, barcode, category, description, brand, model_name, tracking,
        sale_price, purchase_price, tax_rate, min_stock, is_active, variant_attributes,
    ]
