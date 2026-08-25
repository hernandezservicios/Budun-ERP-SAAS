from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.customers import services
from apps.customers.forms import SupplierForm
from apps.customers.models import ActivityLog, Supplier
from apps.tenants.models import Tenant

from ._helpers import CustomersTestCase


class SupplierModelConstraintTests(CustomersTestCase):
    def test_proveedor_sin_ningun_nombre_es_rechazado(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Supplier.objects.create(tenant=self.tenant)

    def test_proveedor_solo_con_nombre_comercial_es_valido(self):
        proveedor = Supplier.objects.create(tenant=self.tenant, trade_name="Ferretería El Tornillo")
        self.assertEqual(proveedor.display_name, "Ferretería El Tornillo")

    def test_identificacion_duplicada_en_el_mismo_tenant_es_rechazada(self):
        Supplier.objects.create(
            tenant=self.tenant, legal_name="Proveedor A", identification_type="rnc", identification_number="RNC-1"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Supplier.objects.create(
                    tenant=self.tenant, legal_name="Proveedor B", identification_type="rnc", identification_number="RNC-1"
                )

    def test_mismo_documento_en_dos_tenants_es_permitido(self):
        otro_tenant = Tenant.objects.create(name="Otra Empresa Proveedores", slug="otra-empresa-proveedores")
        Supplier.objects.create(
            tenant=self.tenant, legal_name="Proveedor A", identification_type="rnc", identification_number="COMPARTIDO"
        )
        # No debe lanzar IntegrityError.
        Supplier.objects.create(
            tenant=otro_tenant, legal_name="Proveedor A", identification_type="rnc", identification_number="COMPARTIDO"
        )

    def test_numero_identificacion_sin_tipo_es_rechazado(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Supplier.objects.create(tenant=self.tenant, legal_name="Proveedor", identification_number="123")


class SupplierFormTests(CustomersTestCase):
    def _datos_validos(self, **overrides):
        datos = {
            "party_type": "empresa",
            "legal_name": "Distribuidora ABC",
            "trade_name": "ABC",
            "identification_type": "rnc",
            "identification_number": "1-30-00000-1",
            "email": "compras@abc.example.com",
            "phone": "8095550000",
            "address": "",
            "city": "",
            "state_province": "",
            "country": "",
            "payment_terms": "net_30",
            "credit_days": "30",
            "credit_enabled": "",
            "currency": "USD",
            "notes": "",
            "is_active": "on",
        }
        datos.update(overrides)
        return datos

    def test_formulario_valido_con_datos_completos(self):
        form = SupplierForm(data=self._datos_validos(), tenant=self.tenant)
        self.assertTrue(form.is_valid(), form.errors)

    def test_formulario_sin_ningun_nombre_es_invalido(self):
        form = SupplierForm(data=self._datos_validos(legal_name="", trade_name=""), tenant=self.tenant)
        self.assertFalse(form.is_valid())

    def test_formulario_rechaza_identificacion_duplicada(self):
        Supplier.objects.create(
            tenant=self.tenant, legal_name="Existente", identification_type="rnc", identification_number="DUP-1"
        )
        form = SupplierForm(data=self._datos_validos(identification_number="DUP-1"), tenant=self.tenant)
        self.assertFalse(form.is_valid())


class SupplierServiceTests(CustomersTestCase):
    def setUp(self):
        super().setUp()
        self.activo = Supplier.objects.create(tenant=self.tenant, legal_name="Proveedor Activo")
        self.inactivo = Supplier.objects.create(tenant=self.tenant, legal_name="Proveedor Inactivo", is_active=False)

    def test_list_suppliers_solo_activos_por_defecto(self):
        resultado = services.list_suppliers(self.tenant)
        self.assertNotIn(self.inactivo, list(resultado))

    def test_busqueda_por_razon_social(self):
        resultado = services.list_suppliers(self.tenant, search="Activo")
        self.assertEqual(list(resultado), [self.activo])


class SupplierViewCrudTests(CustomersTestCase):
    def _datos_validos(self, **overrides):
        datos = {
            "party_type": "empresa",
            "legal_name": "Nuevo Proveedor",
            "trade_name": "",
            "identification_type": "",
            "identification_number": "",
            "email": "",
            "phone": "",
            "address": "",
            "city": "",
            "state_province": "",
            "country": "",
            "payment_terms": "contado",
            "credit_days": "0",
            "credit_enabled": "",
            "currency": "USD",
            "notes": "",
            "is_active": "on",
        }
        datos.update(overrides)
        return datos

    def test_crear_proveedor_via_http(self):
        respuesta = self.client.post(reverse("customers:supplier_create"), self._datos_validos())
        proveedor = Supplier.all_objects.filter(tenant=self.tenant, legal_name="Nuevo Proveedor").first()
        self.assertIsNotNone(proveedor)
        self.assertRedirects(respuesta, reverse("customers:supplier_detail", args=[proveedor.pk]))
        self.assertTrue(
            ActivityLog.all_objects.filter(tenant=self.tenant, entity_type="supplier", action="created").exists()
        )

    def test_desactivar_proveedor_via_http(self):
        proveedor = Supplier.objects.create(tenant=self.tenant, legal_name="Activo")
        respuesta = self.client.post(reverse("customers:supplier_status", args=[proveedor.pk]))
        self.assertRedirects(respuesta, reverse("customers:supplier_detail", args=[proveedor.pk]))
        proveedor.refresh_from_db()
        self.assertFalse(proveedor.is_active)

    def test_listado_de_proveedores_via_http(self):
        Supplier.objects.create(tenant=self.tenant, legal_name="Visible SRL")
        respuesta = self.client.get(reverse("customers:supplier_list"))
        self.assertContains(respuesta, "Visible SRL")
