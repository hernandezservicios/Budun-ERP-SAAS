"""
Tests de Importación/Exportación masiva de productos vía Excel
(extensión de FASE 8 — ver `docs/products.md`,
`apps.inventory.product_import`).
"""

import threading
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from openpyxl import load_workbook

from apps.audit.models import AuditLog
from apps.inventory import product_import
from apps.inventory.models import Category, InventoryUnit, Product, ProductImportBatch, StockMovement
from apps.inventory.services import register_stock_in
from apps.tenants.models import Membership, Tenant

from ._helpers import InventoryTestCase, construir_excel, fila_producto

User = get_user_model()


# ------------------------------------------------------------------
# Plantilla
# ------------------------------------------------------------------


class TemplateTests(InventoryTestCase):
    def test_descargar_plantilla_devuelve_xlsx_con_encabezados_oficiales(self):
        respuesta = self.client.get(reverse("inventory:product_import_template"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        libro = load_workbook(BytesIO(respuesta.content))
        encabezados = [c.value for c in libro.active[1]]
        self.assertEqual(encabezados, product_import._HEADERS_OFICIALES)

    def test_plantilla_nunca_incluye_columnas_no_soportadas(self):
        """Regla explícita del adendo: nunca inventar `currency`/`unit
        of measure` — ver `docs/products.md`."""
        respuesta = self.client.get(reverse("inventory:product_import_template"))
        libro = load_workbook(BytesIO(respuesta.content))
        encabezados = " ".join(str(c.value) for c in libro.active[1]).lower()
        self.assertNotIn("moneda", encabezados)
        self.assertNotIn("unidad de medida", encabezados)

    def test_fila_de_ejemplo_es_una_fila_de_datos_real_y_valida(self):
        """Las filas de ejemplo de la propia plantilla deben poder
        importarse tal cual, sin editarlas — es la garantía de que la
        plantilla nunca queda desincronizada del validador real. Las
        categorías de ejemplo ("Ropa"/"Electrónica") deben existir para
        que esto sea cierto — se crean aquí, mismo criterio que un
        tenant real seguiría la sugerencia de la propia plantilla."""
        Category.objects.create(tenant=self.tenant, name="Ropa")
        Category.objects.create(tenant=self.tenant, name="Electrónica")
        respuesta = self.client.get(reverse("inventory:product_import_template"))
        archivo = SimpleUploadedFile(
            "plantilla.xlsx", respuesta.content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.error_count, 0)
        self.assertEqual(lote.total_rows, 2)


# ------------------------------------------------------------------
# Subida + preview (build_preview)
# ------------------------------------------------------------------


class UploadValidationTests(InventoryTestCase):
    def test_archivo_no_xlsx_es_rechazado(self):
        archivo = SimpleUploadedFile("productos.csv", b"sku,nombre\n1,x", content_type="text/csv")
        with self.assertRaises(product_import.ProductImportError):
            product_import.build_preview(self.tenant, archivo, user=self.user)

    def test_archivo_xlsx_disfrazado_es_rechazado(self):
        """Extensión `.xlsx` pero contenido que no es un ZIP real —
        `apps.customers.file_validation` ya lo detecta por firma."""
        archivo = SimpleUploadedFile(
            "falso.xlsx", b"esto no es un excel", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        with self.assertRaises(product_import.ProductImportError):
            product_import.build_preview(self.tenant, archivo, user=self.user)

    def test_archivo_con_macros_es_rechazado(self):
        """Un `.xlsx` renombrado desde `.xlsm` comparte la misma firma
        ZIP — se detecta por la presencia de `xl/vbaProject.bin`."""
        import zipfile

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("xl/vbaProject.bin", b"contenido de macro simulado")
            zf.writestr("[Content_Types].xml", "<Types/>")
        archivo = SimpleUploadedFile(
            "con_macro.xlsx", buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        with self.assertRaises(product_import.ProductImportError):
            product_import.build_preview(self.tenant, archivo, user=self.user)

    def test_columna_desconocida_rechaza_el_archivo_completo(self):
        archivo = construir_excel([fila_producto()], headers=["SKU RARO"] + product_import._HEADERS_OFICIALES[1:])
        with self.assertRaises(product_import.ProductImportError):
            product_import.build_preview(self.tenant, archivo, user=self.user)

    def test_falta_columna_obligatoria_rechaza_el_archivo_completo(self):
        headers_sin_sku = [h for h in product_import._HEADERS_OFICIALES if h != "SKU *"]
        archivo = construir_excel([], headers=headers_sin_sku)
        with self.assertRaises(product_import.ProductImportError):
            product_import.build_preview(self.tenant, archivo, user=self.user)

    def test_archivo_sin_filas_de_datos_es_rechazado(self):
        archivo = construir_excel([])
        with self.assertRaises(product_import.ProductImportError):
            product_import.build_preview(self.tenant, archivo, user=self.user)

    def test_columnas_en_otro_orden_se_reconocen_por_encabezado(self):
        """El orden de columnas no importa — se identifican por nombre
        de encabezado, nunca por posición."""
        headers = ["Nombre *", "SKU *", "Precio de venta *"]
        archivo = construir_excel([["Producto reordenado", "SKU-REORD", "77.00"]], headers=headers)
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.error_count, 0)
        self.assertEqual(lote.preview_data[0]["sku"], "SKU-REORD")


class CreateUpdateTests(InventoryTestCase):
    def setUp(self):
        super().setUp()
        self.categoria = Category.objects.create(tenant=self.tenant, name="Ropa")

    def test_sku_inexistente_crea(self):
        archivo = construir_excel([fila_producto(sku="NUEVO-1", sale_price="99.99")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.preview_data[0]["action"], "CREATE")
        lote = product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        producto = Product.all_objects.get(tenant=self.tenant, sku="NUEVO-1")
        self.assertEqual(producto.sale_price, Decimal("99.99"))

    def test_sku_existente_actualiza(self):
        Product.objects.create(tenant=self.tenant, sku="EXISTE-1", name="Viejo", sale_price=Decimal("10"))
        archivo = construir_excel([fila_producto(sku="EXISTE-1", name="Nombre nuevo", sale_price="55.00")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.preview_data[0]["action"], "UPDATE")
        product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        producto = Product.all_objects.get(tenant=self.tenant, sku="EXISTE-1")
        self.assertEqual(producto.name, "Nombre nuevo")
        self.assertEqual(producto.sale_price, Decimal("55.00"))
        self.assertEqual(Product.all_objects.filter(tenant=self.tenant).count(), 1, "Nunca debe crear un segundo producto para un SKU existente.")

    def test_nombre_nunca_se_usa_como_identificador(self):
        """Dos productos con el MISMO nombre pero SKU distinto deben
        seguir siendo dos productos distintos — nunca fusionados por
        nombre."""
        Product.objects.create(tenant=self.tenant, sku="A-1", name="Igual", sale_price=Decimal("1"))
        archivo = construir_excel([fila_producto(sku="A-2", name="Igual", sale_price="2")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.preview_data[0]["action"], "CREATE")
        product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        self.assertEqual(Product.all_objects.filter(tenant=self.tenant, name="Igual").count(), 2)

    def test_celda_en_blanco_en_update_no_borra_el_valor_existente(self):
        """Regla documentada explícitamente: en un UPDATE, una columna
        opcional en blanco significa 'no cambiar', nunca 'vaciar'."""
        producto = Product.objects.create(
            tenant=self.tenant, sku="BLANK-1", name="Original", barcode="123", category=self.categoria,
            brand="MarcaOriginal", sale_price=Decimal("10"),
        )
        archivo = construir_excel([fila_producto(sku="BLANK-1", name="Original", sale_price="20.00")])  # resto en blanco
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        producto.refresh_from_db()
        self.assertEqual(producto.sale_price, Decimal("20.00"))
        self.assertEqual(producto.barcode, "123", "El barcode no se envió en la fila — no debía tocarse.")
        self.assertEqual(producto.category_id, self.categoria.pk)
        self.assertEqual(producto.brand, "MarcaOriginal")

    def test_celda_en_blanco_en_create_usa_default_del_modelo(self):
        archivo = construir_excel([fila_producto(sku="DEF-1", sale_price="30.00")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        producto = Product.all_objects.get(tenant=self.tenant, sku="DEF-1")
        self.assertEqual(producto.barcode, "")
        self.assertEqual(producto.purchase_price, Decimal("0"))
        self.assertTrue(producto.is_active)
        self.assertEqual(producto.inventory_tracking_type, Product.TrackingType.QUANTITY)

    def test_categoria_por_nombre_case_insensitive(self):
        archivo = construir_excel([fila_producto(sku="CAT-1", category="ropa", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.error_count, 0)
        product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        self.assertEqual(Product.all_objects.get(tenant=self.tenant, sku="CAT-1").category_id, self.categoria.pk)

    def test_atributos_de_variante_se_parsean_a_json(self):
        archivo = construir_excel([fila_producto(sku="VAR-1", sale_price="1", variant_attributes="color:Rojo;talla:L")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        self.assertEqual(
            Product.all_objects.get(tenant=self.tenant, sku="VAR-1").variant_attributes,
            {"color": "Rojo", "talla": "L"},
        )


class ValidationTests(InventoryTestCase):
    def test_sku_vacio_es_error(self):
        archivo = construir_excel([fila_producto(sku="", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertGreater(lote.error_count, 0)
        self.assertTrue(any(e["column"] == "SKU" for e in lote.errors_data))

    def test_sku_duplicado_en_archivo_es_error(self):
        archivo = construir_excel([fila_producto(sku="DUP", sale_price="1"), fila_producto(sku="DUP", sale_price="2")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any("duplicado" in e["reason"].lower() for e in lote.errors_data))
        self.assertFalse(lote.can_confirm)

    def test_barcode_duplicado_contra_otro_producto_existente(self):
        Product.objects.create(tenant=self.tenant, sku="OWN-1", name="Dueño", barcode="999", sale_price=Decimal("1"))
        archivo = construir_excel([fila_producto(sku="OTRO-1", barcode="999", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any("código de barras" in e["reason"].lower() or "Ya lo usa" in e["reason"] for e in lote.errors_data))

    def test_categoria_inexistente_es_error(self):
        archivo = construir_excel([fila_producto(sku="C-1", category="NoExiste", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any(e["column"] == "Categoría" for e in lote.errors_data))

    def test_precio_invalido_es_error(self):
        archivo = construir_excel([fila_producto(sku="P-1", sale_price="no-es-un-numero")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any(e["column"] == "Precio de venta" for e in lote.errors_data))

    def test_precio_negativo_es_error(self):
        archivo = construir_excel([fila_producto(sku="P-2", sale_price="-5")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any(e["column"] == "Precio de venta" for e in lote.errors_data))

    def test_precio_obligatorio_en_create(self):
        archivo = construir_excel([fila_producto(sku="P-3", sale_price="")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any(e["column"] == "Precio de venta" and "obligatorio" in e["reason"].lower() for e in lote.errors_data))

    def test_booleano_invalido_es_error(self):
        archivo = construir_excel([fila_producto(sku="B-1", sale_price="1", is_active="tal-vez")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any(e["column"] == "Activo" for e in lote.errors_data))

    def test_tracking_invalido_es_error(self):
        archivo = construir_excel([fila_producto(sku="T-1", sale_price="1", tracking="volador")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any(e["column"] == "Tipo de seguimiento" for e in lote.errors_data))

    def test_nombre_demasiado_largo_es_error(self):
        archivo = construir_excel([fila_producto(sku="L-1", name="x" * 300, sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any(e["column"] == "Nombre" for e in lote.errors_data))

    def test_valor_con_apariencia_de_formula_es_error(self):
        archivo = construir_excel([fila_producto(sku="F-1", name="=cmd|'/c calc'!A1", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any("fórmula" in e["reason"].lower() for e in lote.errors_data))

    def test_fila_completamente_vacia_se_ignora_sin_error(self):
        archivo = construir_excel([fila_producto(sku="OK-1", sale_price="1"), ["" for _ in product_import._HEADERS_OFICIALES]])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.total_rows, 1)
        self.assertEqual(lote.error_count, 0)

    def test_fila_de_comentario_se_ignora(self):
        archivo = construir_excel([
            ["#instrucciones"] + [""] * (len(product_import._HEADERS_OFICIALES) - 1),
            fila_producto(sku="OK-2", sale_price="1"),
        ])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.total_rows, 1)

    def test_sin_cambios_en_update_genera_advertencia_no_error(self):
        Product.objects.create(tenant=self.tenant, sku="NC-1", name="Igual", sale_price=Decimal("1"))
        archivo = construir_excel([fila_producto(sku="NC-1", name="", sale_price="")])  # todo en blanco salvo sku
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.error_count, 0)
        self.assertEqual(lote.warning_count, 1)
        self.assertTrue(lote.can_confirm)


class StrictModeTests(InventoryTestCase):
    def test_lote_con_errores_no_se_puede_confirmar(self):
        archivo = construir_excel([fila_producto(sku="OK-3", sale_price="1"), fila_producto(sku="", sale_price="2")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertGreater(lote.error_count, 0)
        with self.assertRaises(product_import.InvalidImportOperation):
            product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        self.assertEqual(Product.all_objects.filter(tenant=self.tenant, sku="OK-3").count(), 0, "Modo estricto: ni las filas válidas se aplican si el lote tiene errores.")

    def test_lote_ya_confirmado_no_se_puede_reconfirmar(self):
        archivo = construir_excel([fila_producto(sku="ONCE-1", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        with self.assertRaises(product_import.InvalidImportOperation):
            product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)


class SerializedSeparationTests(InventoryTestCase):
    """El adendo exige explícitamente: la importación general NUNCA
    modifica stock/StockMovement/InventoryUnit/IMEI/serial/costos
    históricos/COGS."""

    def test_importacion_nunca_crea_stockmovement(self):
        archivo = construir_excel([fila_producto(sku="SM-1", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        self.assertEqual(StockMovement.all_objects.filter(tenant=self.tenant).count(), 0)

    def test_importacion_nunca_crea_inventoryunit(self):
        archivo = construir_excel([fila_producto(sku="SER-1", sale_price="1", tracking="Serializado")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
        self.assertEqual(InventoryUnit.all_objects.filter(tenant=self.tenant).count(), 0)

    def test_no_permite_cambiar_tracking_si_ya_tiene_historial(self):
        producto = Product.objects.create(tenant=self.tenant, sku="HIST-1", name="Con historial", sale_price=Decimal("1"))
        register_stock_in(product=producto, quantity=Decimal("5"), user=self.user)
        archivo = construir_excel([fila_producto(sku="HIST-1", sale_price="1", tracking="Serializado")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertTrue(any(e["column"] == "Tipo de seguimiento" for e in lote.errors_data))

    def test_permite_cambiar_tracking_sin_historial(self):
        Product.objects.create(tenant=self.tenant, sku="SINHIST-1", name="Sin historial", sale_price=Decimal("1"))
        archivo = construir_excel([fila_producto(sku="SINHIST-1", sale_price="1", tracking="Serializado")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.assertEqual(lote.error_count, 0)


# ------------------------------------------------------------------
# Vistas HTTP: permisos, seguridad, tenant isolation
# ------------------------------------------------------------------


class ViewsAndSecurityTests(InventoryTestCase):
    def test_subir_via_http_crea_lote_y_redirige_al_preview(self):
        archivo = construir_excel([fila_producto(sku="HTTP-1", sale_price="1")])
        respuesta = self.client.post(reverse("inventory:product_import_upload"), {"file": archivo})
        lote = ProductImportBatch.all_objects.get(tenant=self.tenant, original_filename__isnull=False)
        self.assertRedirects(respuesta, reverse("inventory:product_import_detail", args=[lote.pk]))

    def test_confirmar_via_http_aplica_el_lote(self):
        archivo = construir_excel([fila_producto(sku="HTTP-2", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        respuesta = self.client.post(reverse("inventory:product_import_detail", args=[lote.pk]))
        self.assertRedirects(respuesta, reverse("inventory:product_import_detail", args=[lote.pk]))
        lote.refresh_from_db()
        self.assertEqual(lote.status, ProductImportBatch.Status.CONFIRMED)

    def test_miembro_sin_permiso_no_puede_importar(self):
        empleado = User.objects.create_user(email="empleado@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=empleado, tenant=self.tenant, role=Membership.Role.MEMBER)
        self.client.logout()
        self.client.login(username="empleado@example.com", password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("inventory:product_import_upload"))
        self.assertEqual(respuesta.status_code, 403)

    def test_miembro_sin_permiso_no_puede_exportar(self):
        empleado = User.objects.create_user(email="empleado2@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=empleado, tenant=self.tenant, role=Membership.Role.MEMBER)
        self.client.logout()
        self.client.login(username="empleado2@example.com", password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("inventory:product_export"))
        self.assertEqual(respuesta.status_code, 403)

    def test_anonimo_redirige_a_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("inventory:product_import_upload"))
        self.assertEqual(respuesta.status_code, 302)

    def test_lote_de_otro_tenant_da_404(self):
        otro_tenant = Tenant.objects.create(name="Otra Empresa Import", slug="otra-empresa-import")
        otro_user = User.objects.create_user(email="otro.import@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=otro_user, tenant=otro_tenant, role=Membership.Role.OWNER)
        archivo = construir_excel([fila_producto(sku="AJENO-1", sale_price="1")])
        lote_ajeno = product_import.build_preview(otro_tenant, archivo, user=otro_user)

        respuesta = self.client.get(reverse("inventory:product_import_detail", args=[lote_ajeno.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_no_puede_confirmar_lote_de_otro_tenant(self):
        otro_tenant = Tenant.objects.create(name="Otra Empresa Import 2", slug="otra-empresa-import-2")
        otro_user = User.objects.create_user(email="otro2.import@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=otro_user, tenant=otro_tenant, role=Membership.Role.OWNER)
        archivo = construir_excel([fila_producto(sku="AJENO-2", sale_price="1")])
        lote_ajeno = product_import.build_preview(otro_tenant, archivo, user=otro_user)

        respuesta = self.client.post(reverse("inventory:product_import_detail", args=[lote_ajeno.pk]))
        self.assertEqual(respuesta.status_code, 404)
        lote_ajeno.refresh_from_db()
        self.assertEqual(lote_ajeno.status, ProductImportBatch.Status.PENDING_REVIEW, "Nunca debe confirmarse cruzando tenant.")

    def test_reporte_de_errores_solo_incluye_los_del_propio_tenant(self):
        archivo = construir_excel([fila_producto(sku="", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        respuesta = self.client.get(reverse("inventory:product_import_errors", args=[lote.pk]))
        self.assertEqual(respuesta.status_code, 200)
        libro = load_workbook(BytesIO(respuesta.content))
        self.assertGreaterEqual(libro.active.max_row, 2)


class AuditTests(InventoryTestCase):
    def test_confirmar_importacion_genera_evento_de_auditoria(self):
        archivo = construir_excel([fila_producto(sku="AUD-1", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        self.client.post(reverse("inventory:product_import_detail", args=[lote.pk]))
        evento = AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.PRODUCT_IMPORT_CONFIRMED).first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.after["created"], 1)

    def test_exportar_genera_evento_de_auditoria(self):
        respuesta = self.client.get(reverse("inventory:product_export"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.EXPORT_PERFORMED, domain="products").exists())


class ExportTests(InventoryTestCase):
    def test_exportacion_respeta_tenant(self):
        Product.objects.create(tenant=self.tenant, sku="EXP-1", name="Mío", sale_price=Decimal("1"))
        otro_tenant = Tenant.objects.create(name="Otra Empresa Export", slug="otra-empresa-export")
        Product.objects.create(tenant=otro_tenant, sku="EXP-AJENO", name="Ajeno", sale_price=Decimal("1"))

        respuesta = self.client.get(reverse("inventory:product_export"))
        libro = load_workbook(BytesIO(respuesta.content))
        skus = [fila[0] for fila in libro.active.iter_rows(min_row=2, values_only=True)]
        self.assertIn("EXP-1", skus)
        self.assertNotIn("EXP-AJENO", skus)

    def test_exportacion_nunca_incluye_imei_ni_costos_internos_de_unidades(self):
        respuesta = self.client.get(reverse("inventory:product_export"))
        libro = load_workbook(BytesIO(respuesta.content))
        encabezados = [str(c.value).lower() for c in libro.active[1]]
        for prohibido in ("imei", "serial", "unit_cost"):
            self.assertFalse(any(prohibido in h for h in encabezados))


class ErrorReportTests(InventoryTestCase):
    def test_reporte_de_errores_contiene_fila_columna_valor_motivo(self):
        archivo = construir_excel([fila_producto(sku="", sale_price="no-numero")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)
        respuesta = product_import.generar_reporte_errores_xlsx(lote)
        libro = load_workbook(BytesIO(respuesta.content))
        encabezados = [c.value for c in libro.active[1]]
        self.assertEqual(encabezados, ["Fila", "Columna", "Valor", "Motivo"])
        self.assertGreater(libro.active.max_row, 1)


# ------------------------------------------------------------------
# Performance
# ------------------------------------------------------------------


class PerformanceTests(InventoryTestCase):
    def test_validar_archivo_no_incurre_en_n_mas_1(self):
        """Conteo de queries constante entre 5 y 50 filas — confirma que
        la búsqueda de SKUs/barcodes/categorías existentes es en bloque,
        nunca una consulta por fila."""
        filas_5 = [fila_producto(sku=f"PERF-{i}", sale_price="1") for i in range(5)]
        archivo_5 = construir_excel(filas_5)
        with CaptureQueriesContext(connection) as ctx:
            product_import.build_preview(self.tenant, archivo_5, user=self.user)
        queries_5 = len(ctx.captured_queries)

        filas_50 = [fila_producto(sku=f"PERF2-{i}", sale_price="1") for i in range(50)]
        archivo_50 = construir_excel(filas_50)
        with CaptureQueriesContext(connection) as ctx:
            product_import.build_preview(self.tenant, archivo_50, user=self.user)
        queries_50 = len(ctx.captured_queries)

        self.assertEqual(queries_5, queries_50, "El número de queries no debería crecer con más filas (indicaría N+1).")


# ------------------------------------------------------------------
# Concurrencia (PostgreSQL real, hilos reales)
# ------------------------------------------------------------------


class ImportConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrencia Import", slug="concurrencia-import")
        self.user = User.objects.create_user(email="conc.import@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)

    def test_dos_confirmaciones_simultaneas_del_mismo_lote_solo_aplican_una_vez(self):
        archivo = construir_excel([fila_producto(sku="CONC-1", sale_price="1")])
        lote = product_import.build_preview(self.tenant, archivo, user=self.user)

        resultados = []
        barrera = threading.Barrier(2)

        def confirmar():
            barrera.wait()
            try:
                product_import.apply_import_batch(lote.pk, tenant=self.tenant, user=self.user)
                resultados.append("ok")
            except product_import.InvalidImportOperation:
                resultados.append("rechazado")
            finally:
                connection.close()

        hilos = [threading.Thread(target=confirmar) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(resultados.count("ok"), 1)
        self.assertEqual(resultados.count("rechazado"), 1)
        self.assertEqual(Product.all_objects.filter(tenant=self.tenant, sku="CONC-1").count(), 1)

    def test_dos_lotes_distintos_con_el_mismo_sku_nuevo_solo_uno_gana(self):
        archivo_a = construir_excel([fila_producto(sku="CONC-SKU", sale_price="1")])
        archivo_b = construir_excel([fila_producto(sku="CONC-SKU", sale_price="2")])
        lote_a = product_import.build_preview(self.tenant, archivo_a, user=self.user)
        lote_b = product_import.build_preview(self.tenant, archivo_b, user=self.user)

        resultados = []
        barrera = threading.Barrier(2)

        def confirmar(lote_pk):
            barrera.wait()
            try:
                product_import.apply_import_batch(lote_pk, tenant=self.tenant, user=self.user)
                resultados.append("ok")
            except product_import.InvalidImportOperation:
                resultados.append("fallo")
            finally:
                connection.close()

        hilos = [threading.Thread(target=confirmar, args=(lote_a.pk,)), threading.Thread(target=confirmar, args=(lote_b.pk,))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(resultados.count("ok"), 1, "Exactamente uno de los dos lotes concurrentes con el mismo SKU nuevo debe ganar.")
        self.assertEqual(Product.all_objects.filter(tenant=self.tenant, sku="CONC-SKU").count(), 1, "Nunca dos productos con el mismo SKU.")

    def test_dos_actualizaciones_concurrentes_del_mismo_producto_nunca_corrompen_datos(self):
        Product.objects.create(tenant=self.tenant, sku="CONC-UPD", name="Original", sale_price=Decimal("1"))
        archivo_a = construir_excel([fila_producto(sku="CONC-UPD", sale_price="10.00")])
        archivo_b = construir_excel([fila_producto(sku="CONC-UPD", sale_price="20.00")])
        lote_a = product_import.build_preview(self.tenant, archivo_a, user=self.user)
        lote_b = product_import.build_preview(self.tenant, archivo_b, user=self.user)

        resultados = []
        barrera = threading.Barrier(2)

        def confirmar(lote_pk):
            barrera.wait()
            try:
                product_import.apply_import_batch(lote_pk, tenant=self.tenant, user=self.user)
                resultados.append("ok")
            except product_import.InvalidImportOperation:
                resultados.append("fallo")
            finally:
                connection.close()

        hilos = [threading.Thread(target=confirmar, args=(lote_a.pk,)), threading.Thread(target=confirmar, args=(lote_b.pk,))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        # Ambas actualizaciones son operaciones de negocio legítimas
        # sobre el mismo producto — deben serializarse (una espera a la
        # otra vía select_for_update), nunca corromperse; el resultado
        # final es el de quien conf‌irmó al último, sin excepción no
        # controlada.
        self.assertEqual(resultados.count("ok"), 2)
        producto = Product.all_objects.get(tenant=self.tenant, sku="CONC-UPD")
        self.assertIn(producto.sale_price, (Decimal("10.00"), Decimal("20.00")))

    def test_conflicto_de_barcode_entre_dos_lotes_concurrentes(self):
        archivo_a = construir_excel([fila_producto(sku="BC-A", barcode="7778889990", sale_price="1")])
        archivo_b = construir_excel([fila_producto(sku="BC-B", barcode="7778889990", sale_price="2")])
        lote_a = product_import.build_preview(self.tenant, archivo_a, user=self.user)
        lote_b = product_import.build_preview(self.tenant, archivo_b, user=self.user)
        self.assertTrue(lote_a.can_confirm)
        self.assertTrue(lote_b.can_confirm, "Ninguno de los dos veía al otro en su propio preview — ambos parecían válidos por separado.")

        resultados = []
        barrera = threading.Barrier(2)

        def confirmar(lote_pk):
            barrera.wait()
            try:
                product_import.apply_import_batch(lote_pk, tenant=self.tenant, user=self.user)
                resultados.append("ok")
            except product_import.InvalidImportOperation:
                resultados.append("fallo")
            finally:
                connection.close()

        hilos = [threading.Thread(target=confirmar, args=(lote_a.pk,)), threading.Thread(target=confirmar, args=(lote_b.pk,))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(resultados.count("ok"), 1, "El UniqueConstraint de barcode debe dejar ganar solo a uno de los dos.")
        self.assertEqual(Product.all_objects.filter(tenant=self.tenant, barcode="7778889990").count(), 1)
