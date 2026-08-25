"""
Performance de Clientes y Proveedores (FASE 9): número de queries y
ausencia de N+1, verificado comparando el conteo de queries con pocos
registros vs. muchos — no solo asumido.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.customers import services
from apps.customers.models import Customer, Supplier

from ._helpers import PDF_VALIDO, CustomersTestCase


class CustomerSupplierPerformanceTests(CustomersTestCase):
    def _contar_queries(self, url):
        with CaptureQueriesContext(connection) as contexto:
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 200)
        return len(contexto.captured_queries)

    def test_listado_de_clientes_no_crece_con_mas_clientes(self):
        for i in range(3):
            Customer.objects.create(tenant=self.tenant, first_name=f"Cliente {i}")
        queries_con_3 = self._contar_queries(reverse("customers:customer_list"))

        for i in range(3, 15):
            Customer.objects.create(tenant=self.tenant, first_name=f"Cliente {i}")
        queries_con_15 = self._contar_queries(reverse("customers:customer_list"))

        self.assertEqual(
            queries_con_3,
            queries_con_15,
            "El listado de clientes no debería ejecutar más queries solo "
            "porque hay más clientes en la misma página (indicaría N+1).",
        )

    def test_listado_de_proveedores_no_crece_con_mas_proveedores(self):
        for i in range(3):
            Supplier.objects.create(tenant=self.tenant, legal_name=f"Proveedor {i}")
        queries_con_3 = self._contar_queries(reverse("customers:supplier_list"))

        for i in range(3, 15):
            Supplier.objects.create(tenant=self.tenant, legal_name=f"Proveedor {i}")
        queries_con_15 = self._contar_queries(reverse("customers:supplier_list"))

        self.assertEqual(queries_con_3, queries_con_15)

    def test_detalle_de_cliente_con_muchos_documentos_no_incurre_en_n_mas_1(self):
        """La tabla de documentos usa `select_related("uploaded_by")`: no
        debe crecer con más documentos."""
        customer = Customer.objects.create(tenant=self.tenant, first_name="Con Documentos")
        for i in range(2):
            archivo = SimpleUploadedFile(f"doc{i}.pdf", PDF_VALIDO, content_type="application/pdf")
            services.register_customer_document(
                customer=customer, archivo=archivo, category="otro", user=self.user
            )
        queries_con_2 = self._contar_queries(reverse("customers:customer_detail", args=[customer.pk]))

        for i in range(2, 10):
            archivo = SimpleUploadedFile(f"doc{i}.pdf", PDF_VALIDO, content_type="application/pdf")
            services.register_customer_document(
                customer=customer, archivo=archivo, category="otro", user=self.user
            )
        queries_con_10 = self._contar_queries(reverse("customers:customer_detail", args=[customer.pk]))

        self.assertEqual(queries_con_2, queries_con_10)

    def tearDown(self):
        from apps.customers.models import CustomerDocument

        for documento in CustomerDocument.all_objects.all():
            if documento.file:
                documento.file.delete(save=False)
        super().tearDown()
