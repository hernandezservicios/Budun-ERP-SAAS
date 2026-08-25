from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.sales import services
from apps.sales.models import SalesActivityLog, SalesDocumentAttachment

from ._helpers import PDF_VALIDO, SalesTestCase


class SalesAttachmentServiceTests(SalesTestCase):
    def setUp(self):
        super().setUp()
        self.quotation = services.create_quotation(self.tenant, user=self.user)

    def test_registrar_adjunto_valido(self):
        archivo = SimpleUploadedFile("cotizacion_firmada.pdf", PDF_VALIDO, content_type="application/pdf")
        adjunto = services.register_attachment(
            tenant=self.tenant, document_type="quotation", document_id=self.quotation.pk,
            archivo=archivo, category="documento_fiscal", user=self.user,
        )
        self.assertEqual(adjunto.original_filename, "cotizacion_firmada.pdf")
        self.assertTrue(
            SalesActivityLog.all_objects.filter(tenant=self.tenant, entity_type="quotation", action="attachment_uploaded").exists()
        )

    def test_registrar_adjunto_disfrazado_es_rechazado(self):
        from django.core.exceptions import ValidationError

        archivo = SimpleUploadedFile("factura.pdf", b"MZ\x90\x00\x03\x00\x00\x00", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            services.register_attachment(
                tenant=self.tenant, document_type="quotation", document_id=self.quotation.pk,
                archivo=archivo, category="otro", user=self.user,
            )
        self.assertFalse(SalesDocumentAttachment.all_objects.filter(tenant=self.tenant).exists())

    def test_eliminar_adjunto_borra_archivo_fisico(self):
        import os

        archivo = SimpleUploadedFile("doc.pdf", PDF_VALIDO, content_type="application/pdf")
        adjunto = services.register_attachment(
            tenant=self.tenant, document_type="quotation", document_id=self.quotation.pk,
            archivo=archivo, category="otro", user=self.user,
        )
        ruta = adjunto.file.path
        self.assertTrue(os.path.exists(ruta))
        services.delete_attachment(adjunto, self.user)
        self.assertFalse(os.path.exists(ruta))
        self.assertFalse(SalesDocumentAttachment.all_objects.filter(pk=adjunto.pk).exists())


class SalesAttachmentHttpViewTests(SalesTestCase):
    def setUp(self):
        super().setUp()
        self.quotation = services.create_quotation(self.tenant, user=self.user)

    def test_subir_adjunto_via_http(self):
        archivo = SimpleUploadedFile("doc.pdf", PDF_VALIDO, content_type="application/pdf")
        respuesta = self.client.post(
            reverse("sales:quotation_attachment_upload", args=[self.quotation.pk]),
            {"file": archivo, "category": "otro", "notes": ""},
        )
        self.assertRedirects(respuesta, reverse("sales:quotation_detail", args=[self.quotation.pk]))
        self.assertTrue(SalesDocumentAttachment.all_objects.filter(tenant=self.tenant, document_type="quotation").exists())

    def test_descargar_adjunto_via_http(self):
        archivo = SimpleUploadedFile("doc.pdf", PDF_VALIDO, content_type="application/pdf")
        self.client.post(
            reverse("sales:quotation_attachment_upload", args=[self.quotation.pk]),
            {"file": archivo, "category": "otro", "notes": ""},
        )
        adjunto = SalesDocumentAttachment.all_objects.get(tenant=self.tenant, document_type="quotation")
        respuesta = self.client.get(reverse("sales:quotation_attachment_download", args=[self.quotation.pk, adjunto.pk]))
        self.assertEqual(respuesta.status_code, 200)
        b"".join(respuesta.streaming_content)

    def test_eliminar_adjunto_via_http(self):
        archivo = SimpleUploadedFile("doc.pdf", PDF_VALIDO, content_type="application/pdf")
        self.client.post(
            reverse("sales:quotation_attachment_upload", args=[self.quotation.pk]),
            {"file": archivo, "category": "otro", "notes": ""},
        )
        adjunto = SalesDocumentAttachment.all_objects.get(tenant=self.tenant, document_type="quotation")
        respuesta = self.client.post(reverse("sales:quotation_attachment_delete", args=[self.quotation.pk, adjunto.pk]))
        self.assertRedirects(respuesta, reverse("sales:quotation_detail", args=[self.quotation.pk]))
        self.assertFalse(SalesDocumentAttachment.all_objects.filter(pk=adjunto.pk).exists())
