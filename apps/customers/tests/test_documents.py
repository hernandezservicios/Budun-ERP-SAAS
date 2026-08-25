import os

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.customers import services
from apps.customers.file_validation import (
    MAX_UPLOAD_SIZE_BYTES,
    nombre_original_seguro,
    validar_archivo_adjunto,
)
from apps.customers.models import ActivityLog, Customer, CustomerDocument, DocumentCategory

from ._helpers import PDF_VALIDO, CustomersTestCase


class FileValidationUnitTests(CustomersTestCase):
    """Unit tests directos de `file_validation.py`, sin pasar por HTTP:
    cubren la lista blanca de formatos, la lista negra explícita, la
    verificación de firma binaria y el límite de tamaño."""

    def test_pdf_valido_es_aceptado(self):
        archivo = SimpleUploadedFile("doc.pdf", PDF_VALIDO, content_type="application/pdf")
        extension, content_type = validar_archivo_adjunto(archivo)
        self.assertEqual(extension, ".pdf")
        self.assertEqual(content_type, "application/pdf")

    def test_png_valido_es_aceptado(self):
        archivo = SimpleUploadedFile("img.png", b"\x89PNG\r\n\x1a\n" + b"resto", content_type="image/png")
        extension, content_type = validar_archivo_adjunto(archivo)
        self.assertEqual(extension, ".png")

    def test_jpg_valido_es_aceptado(self):
        archivo = SimpleUploadedFile("foto.jpg", b"\xff\xd8\xff" + b"resto", content_type="image/jpeg")
        validar_archivo_adjunto(archivo)  # no debe lanzar

    def test_docx_valido_es_aceptado(self):
        archivo = SimpleUploadedFile("doc.docx", b"PK\x03\x04" + b"resto", content_type="application/octet-stream")
        validar_archivo_adjunto(archivo)  # no debe lanzar

    def test_exe_renombrado_a_pdf_es_rechazado(self):
        """Defensa central contra archivos disfrazados: el contenido real
        (cabecera MZ de un ejecutable de Windows) no coincide con la
        extensión declarada."""
        archivo = SimpleUploadedFile("factura.pdf", b"MZ\x90\x00\x03\x00\x00\x00", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validar_archivo_adjunto(archivo)

    def test_extension_exe_directa_es_rechazada(self):
        archivo = SimpleUploadedFile("instalador.exe", b"MZ\x90\x00", content_type="application/octet-stream")
        with self.assertRaises(ValidationError):
            validar_archivo_adjunto(archivo)

    def test_extension_bat_es_rechazada(self):
        archivo = SimpleUploadedFile("script.bat", b"@echo off", content_type="text/plain")
        with self.assertRaises(ValidationError):
            validar_archivo_adjunto(archivo)

    def test_extension_ps1_es_rechazada(self):
        archivo = SimpleUploadedFile("script.ps1", b"Write-Host hola", content_type="text/plain")
        with self.assertRaises(ValidationError):
            validar_archivo_adjunto(archivo)

    def test_extension_dll_es_rechazada(self):
        archivo = SimpleUploadedFile("lib.dll", b"MZ\x90\x00", content_type="application/octet-stream")
        with self.assertRaises(ValidationError):
            validar_archivo_adjunto(archivo)

    def test_extension_no_reconocida_es_rechazada(self):
        archivo = SimpleUploadedFile("archivo.zip", b"PK\x03\x04resto", content_type="application/zip")
        with self.assertRaises(ValidationError):
            validar_archivo_adjunto(archivo)

    def test_archivo_que_excede_el_limite_de_tamano_es_rechazado(self):
        archivo = SimpleUploadedFile("grande.pdf", b"%PDF-" + b"0" * (MAX_UPLOAD_SIZE_BYTES + 1), content_type="application/pdf")
        with self.assertRaises(ValidationError):
            validar_archivo_adjunto(archivo)

    def test_archivo_justo_en_el_limite_es_aceptado(self):
        contenido = b"%PDF-" + b"0" * (MAX_UPLOAD_SIZE_BYTES - 5)
        archivo = SimpleUploadedFile("limite.pdf", contenido, content_type="application/pdf")
        validar_archivo_adjunto(archivo)  # no debe lanzar

    def test_nombre_original_seguro_elimina_separadores_de_ruta(self):
        self.assertEqual(nombre_original_seguro("../../etc/passwd"), "passwd")
        self.assertEqual(nombre_original_seguro("C:\\Windows\\System32\\config.pdf"), "config.pdf")

    def test_nombre_original_seguro_nunca_queda_vacio(self):
        self.assertEqual(nombre_original_seguro(""), "documento")
        self.assertEqual(nombre_original_seguro("///"), "documento")


class CustomerDocumentServiceTests(CustomersTestCase):
    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(tenant=self.tenant, first_name="Con Documentos")

    def test_registrar_documento_valido(self):
        archivo = SimpleUploadedFile("cedula.pdf", PDF_VALIDO, content_type="application/pdf")
        documento = services.register_customer_document(
            customer=self.customer, archivo=archivo, category=DocumentCategory.IDENTIFICACION, user=self.user
        )
        self.assertEqual(documento.tenant, self.tenant)
        self.assertEqual(documento.original_filename, "cedula.pdf")
        self.assertTrue(os.path.exists(documento.file.path))
        self.assertTrue(
            ActivityLog.all_objects.filter(
                tenant=self.tenant, entity_type="customer", action="document_uploaded"
            ).exists()
        )

    def test_registrar_documento_invalido_no_crea_fila_ni_archivo(self):
        archivo = SimpleUploadedFile("virus.pdf", b"MZ\x90\x00", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            services.register_customer_document(
                customer=self.customer, archivo=archivo, category=DocumentCategory.OTRO, user=self.user
            )
        self.assertEqual(CustomerDocument.all_objects.filter(customer=self.customer).count(), 0)

    def test_eliminar_documento_borra_fila_y_archivo_fisico(self):
        archivo = SimpleUploadedFile("cedula.pdf", PDF_VALIDO, content_type="application/pdf")
        documento = services.register_customer_document(
            customer=self.customer, archivo=archivo, category=DocumentCategory.IDENTIFICACION, user=self.user
        )
        ruta = documento.file.path
        self.assertTrue(os.path.exists(ruta))
        services.delete_customer_document(documento=documento, user=self.user)
        self.assertFalse(CustomerDocument.all_objects.filter(pk=documento.pk).exists())
        self.assertFalse(os.path.exists(ruta), "El archivo no debe quedar huérfano en disco tras eliminar el documento")

    def test_documento_se_guarda_con_nombre_generado_no_con_el_original(self):
        archivo = SimpleUploadedFile("información confidencial.pdf", PDF_VALIDO, content_type="application/pdf")
        documento = services.register_customer_document(
            customer=self.customer, archivo=archivo, category=DocumentCategory.OTRO, user=self.user
        )
        # El nombre en disco es un UUID generado, nunca el nombre original
        # (defensa contra path traversal / colisiones / nombres inseguros).
        self.assertNotIn("información confidencial", documento.file.name)
        self.assertEqual(documento.original_filename, "información confidencial.pdf")


class DocumentHttpViewTests(CustomersTestCase):
    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(tenant=self.tenant, first_name="Con Documentos HTTP")

    def _subir(self, nombre="doc.pdf", contenido=PDF_VALIDO, categoria="identificacion"):
        archivo = SimpleUploadedFile(nombre, contenido, content_type="application/pdf")
        return self.client.post(
            reverse("customers:customer_document_upload", args=[self.customer.pk]),
            {"file": archivo, "category": categoria, "notes": ""},
        )

    def test_subir_documento_valido_via_http(self):
        respuesta = self._subir()
        self.assertRedirects(respuesta, reverse("customers:customer_detail", args=[self.customer.pk]))
        self.assertTrue(CustomerDocument.all_objects.filter(customer=self.customer).exists())

    def test_subir_archivo_disfrazado_via_http_no_crea_documento(self):
        self._subir(nombre="factura.pdf", contenido=b"MZ\x90\x00\x03\x00\x00\x00")
        self.assertEqual(CustomerDocument.all_objects.filter(customer=self.customer).count(), 0)

    def test_subir_extension_prohibida_via_http_no_crea_documento(self):
        self._subir(nombre="script.exe", contenido=b"MZ\x90\x00")
        self.assertEqual(CustomerDocument.all_objects.filter(customer=self.customer).count(), 0)

    def test_descargar_documento_responde_200_y_registra_auditoria(self):
        self._subir()
        documento = CustomerDocument.all_objects.get(customer=self.customer)
        respuesta = self.client.get(
            reverse("customers:customer_document_download", args=[self.customer.pk, documento.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        b"".join(respuesta.streaming_content)  # liberar el handle del archivo (ver nota en smoke test)
        self.assertTrue(
            ActivityLog.all_objects.filter(
                tenant=self.tenant, entity_type="customer", action="document_downloaded"
            ).exists()
        )

    def test_eliminar_documento_via_http(self):
        self._subir()
        documento = CustomerDocument.all_objects.get(customer=self.customer)
        respuesta = self.client.post(
            reverse("customers:customer_document_delete", args=[self.customer.pk, documento.pk])
        )
        self.assertRedirects(respuesta, reverse("customers:customer_detail", args=[self.customer.pk]))
        self.assertFalse(CustomerDocument.all_objects.filter(pk=documento.pk).exists())

    def test_documento_de_producto_ajeno_al_cliente_da_404(self):
        """Un `document_pk` real pero perteneciente a OTRO cliente del
        mismo tenant nunca debe ser accesible a través de la URL de un
        cliente distinto (aislamiento por objeto, no solo por tenant)."""
        otro_customer = Customer.objects.create(tenant=self.tenant, first_name="Otro Cliente")
        self._subir()
        documento = CustomerDocument.all_objects.get(customer=self.customer)
        respuesta = self.client.get(
            reverse("customers:customer_document_download", args=[otro_customer.pk, documento.pk])
        )
        self.assertEqual(respuesta.status_code, 404)
