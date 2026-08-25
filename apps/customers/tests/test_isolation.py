"""
Aislamiento Multi-Tenant de Clientes, Proveedores y sus Documentos
(FASE 9, objetivo explícito del usuario): Tenant A nunca debe poder leer,
modificar, eliminar, buscar, filtrar, paginar ni descargar datos de
Tenant B, ni siquiera manipulando IDs/URLs directamente.
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.customers import services
from apps.customers.models import ActivityLog, Customer, CustomerDocument, Supplier, SupplierDocument
from apps.tenants.models import Membership, Tenant

from ._helpers import MEDIA_ROOT_TEMPORAL_TESTS, PDF_VALIDO

User = get_user_model()


@override_settings(MEDIA_ROOT=MEDIA_ROOT_TEMPORAL_TESTS)
class CustomersSuppliersIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Clientes Tenant A", slug="clientes-tenant-a")
        self.tenant_b = Tenant.objects.create(name="Clientes Tenant B", slug="clientes-tenant-b")

        self.user_a = User.objects.create_user(email="cli.a@example.com", password="clave-de-prueba-987")
        self.user_b = User.objects.create_user(email="cli.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user_a, tenant=self.tenant_a, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.user_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

        self.customer_a = Customer.objects.create(tenant=self.tenant_a, first_name="Cliente Secreto A")
        self.customer_b = Customer.objects.create(tenant=self.tenant_b, first_name="Cliente Secreto B")
        self.supplier_a = Supplier.objects.create(tenant=self.tenant_a, legal_name="Proveedor Secreto A")
        self.supplier_b = Supplier.objects.create(tenant=self.tenant_b, legal_name="Proveedor Secreto B")

        archivo_a = SimpleUploadedFile("doc_a.pdf", PDF_VALIDO, content_type="application/pdf")
        self.document_a = services.register_customer_document(
            customer=self.customer_a, archivo=archivo_a, category="otro", user=self.user_a
        )
        archivo_b = SimpleUploadedFile("doc_b.pdf", PDF_VALIDO, content_type="application/pdf")
        self.document_b = services.register_customer_document(
            customer=self.customer_b, archivo=archivo_b, category="otro", user=self.user_b
        )

        self.client_a = self.client_class()
        self.client_a.login(username="cli.a@example.com", password="clave-de-prueba-987")
        self.client_b = self.client_class()
        self.client_b.login(username="cli.b@example.com", password="clave-de-prueba-987")

    def tearDown(self):
        # Limpieza de archivos físicos subidos durante el test (además
        # del registro en BD, que el TestCase ya revierte por transacción).
        for documento in CustomerDocument.all_objects.all():
            if documento.file:
                documento.file.delete(save=False)

    # --- Lectura -----------------------------------------------------------

    def test_tenant_a_no_puede_leer_cliente_de_tenant_b_por_url(self):
        respuesta = self.client_a.get(reverse("customers:customer_detail", args=[self.customer_b.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_tenant_a_no_puede_leer_proveedor_de_tenant_b_por_url(self):
        respuesta = self.client_a.get(reverse("customers:supplier_detail", args=[self.supplier_b.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_listado_de_clientes_no_mezcla_tenants(self):
        respuesta = self.client_a.get(reverse("customers:customer_list"))
        self.assertContains(respuesta, "Cliente Secreto A")
        self.assertNotContains(respuesta, "Cliente Secreto B")

    def test_listado_de_proveedores_no_mezcla_tenants(self):
        respuesta = self.client_a.get(reverse("customers:supplier_list"))
        self.assertContains(respuesta, "Proveedor Secreto A")
        self.assertNotContains(respuesta, "Proveedor Secreto B")

    # --- Búsqueda, filtros y paginación --------------------------------------

    def test_busqueda_de_tenant_a_no_encuentra_cliente_de_tenant_b(self):
        respuesta = self.client_a.get(reverse("customers:customer_list"), {"q": "Secreto B"})
        self.assertNotContains(respuesta, "Cliente Secreto B")

    def test_service_list_customers_nunca_mezcla_tenants(self):
        resultado = list(services.list_customers(self.tenant_a))
        self.assertIn(self.customer_a, resultado)
        self.assertNotIn(self.customer_b, resultado)

    def test_paginacion_de_tenant_a_no_expone_clientes_de_tenant_b(self):
        respuesta = self.client_a.get(reverse("customers:customer_list"), {"page": "1"})
        self.assertNotContains(respuesta, "Cliente Secreto B")

    # --- Modificación / desactivación ---------------------------------------

    def test_tenant_a_no_puede_editar_cliente_de_tenant_b(self):
        respuesta = self.client_a.post(
            reverse("customers:customer_update", args=[self.customer_b.pk]),
            {
                "party_type": "persona",
                "first_name": "Hackeado",
                "last_name": "",
                "company_name": "",
                "trade_name": "",
                "identification_type": "",
                "identification_number": "",
                "email": "",
                "alternate_email": "",
                "phone": "",
                "secondary_phone": "",
                "address": "",
                "city": "",
                "state_province": "",
                "postal_code": "",
                "country": "",
                "payment_terms": "contado",
                "credit_days": "0",
                "credit_enabled": "",
                "credit_limit": "0",
                "currency": "USD",
                "commercial_notes": "",
                "notes": "",
                "is_active": "on",
            },
        )
        self.assertEqual(respuesta.status_code, 404)
        self.customer_b.refresh_from_db()
        self.assertEqual(self.customer_b.first_name, "Cliente Secreto B")

    def test_tenant_a_no_puede_desactivar_cliente_de_tenant_b(self):
        respuesta = self.client_a.post(reverse("customers:customer_status", args=[self.customer_b.pk]))
        self.assertEqual(respuesta.status_code, 404)
        self.customer_b.refresh_from_db()
        self.assertTrue(self.customer_b.is_active)

    def test_tenant_a_no_puede_desactivar_proveedor_de_tenant_b(self):
        respuesta = self.client_a.post(reverse("customers:supplier_status", args=[self.supplier_b.pk]))
        self.assertEqual(respuesta.status_code, 404)
        self.supplier_b.refresh_from_db()
        self.assertTrue(self.supplier_b.is_active)

    # --- Documentos: subida, descarga, eliminación --------------------------

    def test_tenant_a_no_puede_descargar_documento_de_tenant_b(self):
        respuesta = self.client_a.get(
            reverse("customers:customer_document_download", args=[self.customer_b.pk, self.document_b.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_tenant_a_no_puede_eliminar_documento_de_tenant_b(self):
        respuesta = self.client_a.post(
            reverse("customers:customer_document_delete", args=[self.customer_b.pk, self.document_b.pk])
        )
        self.assertEqual(respuesta.status_code, 404)
        self.assertTrue(CustomerDocument.all_objects.filter(pk=self.document_b.pk).exists())

    def test_tenant_a_no_puede_subir_documento_a_cliente_de_tenant_b(self):
        archivo = SimpleUploadedFile("intento.pdf", PDF_VALIDO, content_type="application/pdf")
        respuesta = self.client_a.post(
            reverse("customers:customer_document_upload", args=[self.customer_b.pk]),
            {"file": archivo, "category": "otro", "notes": ""},
        )
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(CustomerDocument.all_objects.filter(customer=self.customer_b).count(), 1)

    def test_id_de_documento_real_de_tenant_b_bajo_cliente_de_tenant_a_da_404(self):
        """Ni siquiera combinando el `pk` real de un cliente de Tenant A
        con el `document_pk` real de un documento de Tenant B (que
        pertenece a otro cliente) debe exponer o afectar nada — la
        vista exige que el documento pertenezca EXACTAMENTE al cliente
        de la URL, dentro del tenant activo."""
        respuesta = self.client_a.get(
            reverse("customers:customer_document_download", args=[self.customer_a.pk, self.document_b.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    # --- IDs manipulados en todas las URLs -----------------------------------

    def test_ids_manipulados_en_urls_de_cliente_devuelven_404(self):
        urls_con_id_ajeno = [
            reverse("customers:customer_detail", args=[self.customer_b.pk]),
            reverse("customers:customer_update", args=[self.customer_b.pk]),
        ]
        for url in urls_con_id_ajeno:
            with self.subTest(url=url):
                self.assertEqual(self.client_a.get(url).status_code, 404)

    def test_ids_manipulados_en_urls_de_proveedor_devuelven_404(self):
        urls_con_id_ajeno = [
            reverse("customers:supplier_detail", args=[self.supplier_b.pk]),
            reverse("customers:supplier_update", args=[self.supplier_b.pk]),
        ]
        for url in urls_con_id_ajeno:
            with self.subTest(url=url):
                self.assertEqual(self.client_a.get(url).status_code, 404)

    def test_manipular_sesion_hacia_otro_tenant_no_filtra_clientes(self):
        """Regresión directa de FASE 3: ni siquiera manipulando
        `active_tenant_id` en la sesión se puede ver clientes de otro
        tenant."""
        session = self.client_a.session
        session["active_tenant_id"] = self.tenant_b.id
        session.save()
        respuesta = self.client_a.get(reverse("customers:customer_list"))
        self.assertNotContains(respuesta, "Cliente Secreto B")

    # --- Auditoría: la bitácora tampoco mezcla tenants -----------------------

    def test_activity_log_de_tenant_a_no_expone_eventos_de_tenant_b(self):
        eventos_b = services.get_activity_log(self.tenant_b, entity_type="customer", entity_id=self.customer_b.pk)
        eventos_a = services.get_activity_log(self.tenant_a, entity_type="customer", entity_id=self.customer_b.pk)
        self.assertTrue(len(list(eventos_b)) >= 1)
        self.assertEqual(len(list(eventos_a)), 0)
