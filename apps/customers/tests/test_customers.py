from decimal import Decimal

from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.customers import services
from apps.customers.forms import CustomerForm
from apps.customers.models import ActivityLog, Customer
from apps.tenants.models import Tenant

from ._helpers import CustomersTestCase


class CustomerModelConstraintTests(CustomersTestCase):
    def test_cliente_sin_ningun_nombre_es_rechazado(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(tenant=self.tenant)

    def test_cliente_solo_con_empresa_es_valido(self):
        cliente = Customer.objects.create(tenant=self.tenant, company_name="Acme Corp")
        self.assertEqual(cliente.display_name, "Acme Corp")

    def test_cliente_solo_con_nombre_comercial_es_valido(self):
        cliente = Customer.objects.create(tenant=self.tenant, trade_name="El Rincón")
        self.assertEqual(cliente.display_name, "El Rincón")

    def test_identificacion_duplicada_en_el_mismo_tenant_es_rechazada(self):
        Customer.objects.create(
            tenant=self.tenant, first_name="Ana", identification_type="cedula", identification_number="001-1"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(
                    tenant=self.tenant, first_name="Otra", identification_type="cedula", identification_number="001-1"
                )

    def test_email_duplicado_en_el_mismo_tenant_es_rechazado(self):
        Customer.objects.create(tenant=self.tenant, first_name="Ana", email="ana@example.com")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(tenant=self.tenant, first_name="Otra", email="ana@example.com")

    def test_mismo_email_en_dos_tenants_es_permitido(self):
        otro_tenant = Tenant.objects.create(name="Otra Empresa Clientes", slug="otra-empresa-clientes")
        Customer.objects.create(tenant=self.tenant, first_name="Ana", email="compartido@example.com")
        # No debe lanzar IntegrityError.
        Customer.objects.create(tenant=otro_tenant, first_name="Ana", email="compartido@example.com")

    def test_numero_identificacion_sin_tipo_es_rechazado(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(tenant=self.tenant, first_name="Ana", identification_number="123")

    def test_credit_limit_negativo_es_rechazado(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(tenant=self.tenant, first_name="Ana", credit_limit=Decimal("-1"))

    def test_display_name_combina_empresa_y_persona_de_contacto(self):
        cliente = Customer.objects.create(
            tenant=self.tenant, first_name="Juan", last_name="Pérez", company_name="Acme Corp"
        )
        self.assertEqual(cliente.display_name, "Acme Corp (Juan Pérez)")


class CustomerFormTests(CustomersTestCase):
    def _datos_validos(self, **overrides):
        datos = {
            "party_type": "persona",
            "first_name": "María",
            "last_name": "Gómez",
            "company_name": "",
            "trade_name": "",
            "identification_type": "cedula",
            "identification_number": "001-9999999-1",
            "email": "maria@example.com",
            "alternate_email": "",
            "phone": "8095551111",
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
        }
        datos.update(overrides)
        return datos

    def test_formulario_valido_con_datos_completos(self):
        form = CustomerForm(data=self._datos_validos(), tenant=self.tenant)
        self.assertTrue(form.is_valid(), form.errors)

    def test_formulario_sin_ningun_nombre_es_invalido(self):
        form = CustomerForm(
            data=self._datos_validos(first_name="", last_name="", company_name="", trade_name=""),
            tenant=self.tenant,
        )
        self.assertFalse(form.is_valid())

    def test_formulario_con_numero_sin_tipo_de_identificacion_es_invalido(self):
        form = CustomerForm(
            data=self._datos_validos(identification_type="", identification_number="123"),
            tenant=self.tenant,
        )
        self.assertFalse(form.is_valid())

    def test_formulario_rechaza_identificacion_duplicada(self):
        Customer.objects.create(
            tenant=self.tenant, first_name="Existente", identification_type="cedula", identification_number="DUP-1"
        )
        form = CustomerForm(data=self._datos_validos(identification_number="DUP-1"), tenant=self.tenant)
        self.assertFalse(form.is_valid())
        self.assertIn("identification_number", form.errors)

    def test_formulario_rechaza_credit_limit_negativo(self):
        form = CustomerForm(data=self._datos_validos(credit_limit="-5"), tenant=self.tenant)
        self.assertFalse(form.is_valid())


class CustomerServiceTests(CustomersTestCase):
    def setUp(self):
        super().setUp()
        self.activo_a = Customer.objects.create(tenant=self.tenant, first_name="Ana", company_name="Alpha SRL")
        self.activo_b = Customer.objects.create(tenant=self.tenant, first_name="Beto", email="beto@example.com")
        self.inactivo = Customer.objects.create(tenant=self.tenant, first_name="Carla", is_active=False)

    def test_list_customers_solo_activos_por_defecto(self):
        resultado = services.list_customers(self.tenant)
        self.assertNotIn(self.inactivo, list(resultado))
        self.assertIn(self.activo_a, list(resultado))

    def test_list_customers_incluye_inactivos_si_se_pide(self):
        resultado = services.list_customers(self.tenant, only_active=False)
        self.assertIn(self.inactivo, list(resultado))

    def test_busqueda_por_nombre(self):
        resultado = services.list_customers(self.tenant, search="Ana")
        self.assertEqual(list(resultado), [self.activo_a])

    def test_busqueda_por_empresa(self):
        resultado = services.list_customers(self.tenant, search="Alpha")
        self.assertEqual(list(resultado), [self.activo_a])

    def test_busqueda_por_email(self):
        resultado = services.list_customers(self.tenant, search="beto@example.com")
        self.assertEqual(list(resultado), [self.activo_b])

    def test_ordenamiento_desconocido_cae_al_default_sin_error(self):
        # Un valor de `orden` fuera de la lista blanca nunca debe romper
        # la consulta ni construir un ORDER BY arbitrario.
        resultado = services.list_customers(self.tenant, order="algo-inventado; DROP TABLE")
        self.assertEqual(len(list(resultado)), 2)

    def test_get_active_customers_no_incluye_inactivos(self):
        resultado = services.get_active_customers(self.tenant)
        self.assertNotIn(self.inactivo, list(resultado))


class CustomerViewCrudTests(CustomersTestCase):
    def _datos_validos(self, **overrides):
        datos = {
            "party_type": "persona",
            "first_name": "Pedro",
            "last_name": "Ramírez",
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
        }
        datos.update(overrides)
        return datos

    def test_crear_cliente_via_http(self):
        respuesta = self.client.post(reverse("customers:customer_create"), self._datos_validos())
        cliente = Customer.all_objects.filter(tenant=self.tenant, first_name="Pedro").first()
        self.assertIsNotNone(cliente)
        self.assertRedirects(respuesta, reverse("customers:customer_detail", args=[cliente.pk]))
        self.assertTrue(
            ActivityLog.all_objects.filter(tenant=self.tenant, entity_type="customer", action="created").exists()
        )

    def test_editar_cliente_via_http(self):
        cliente = Customer.objects.create(tenant=self.tenant, first_name="Original")
        respuesta = self.client.post(
            reverse("customers:customer_update", args=[cliente.pk]),
            self._datos_validos(first_name="Actualizado"),
        )
        self.assertRedirects(respuesta, reverse("customers:customer_detail", args=[cliente.pk]))
        cliente.refresh_from_db()
        self.assertEqual(cliente.first_name, "Actualizado")
        self.assertTrue(
            ActivityLog.all_objects.filter(tenant=self.tenant, entity_type="customer", action="updated").exists()
        )

    def test_desactivar_y_reactivar_cliente_via_http(self):
        cliente = Customer.objects.create(tenant=self.tenant, first_name="Activo")
        respuesta = self.client.post(reverse("customers:customer_status", args=[cliente.pk]))
        self.assertRedirects(respuesta, reverse("customers:customer_detail", args=[cliente.pk]))
        cliente.refresh_from_db()
        self.assertFalse(cliente.is_active)

        respuesta = self.client.post(
            reverse("customers:customer_status", args=[cliente.pk]), {"accion": "reactivar"}
        )
        cliente.refresh_from_db()
        self.assertTrue(cliente.is_active)

    def test_listado_pagina_20_por_pagina(self):
        for i in range(25):
            Customer.objects.create(tenant=self.tenant, first_name=f"Cliente{i:02d}")
        respuesta = self.client.get(reverse("customers:customer_list"))
        self.assertEqual(len(respuesta.context["customers"]), 20)
        self.assertTrue(respuesta.context["is_paginated"])

    def test_busqueda_en_listado_via_http(self):
        Customer.objects.create(tenant=self.tenant, first_name="Encontrable")
        Customer.objects.create(tenant=self.tenant, first_name="Otro")
        respuesta = self.client.get(reverse("customers:customer_list"), {"q": "Encontrable"})
        self.assertContains(respuesta, "Encontrable")
        self.assertNotContains(respuesta, "Otro")

    def test_filtro_mostrar_inactivos_via_http(self):
        Customer.objects.create(tenant=self.tenant, first_name="Inactivo", is_active=False)
        respuesta = self.client.get(reverse("customers:customer_list"))
        self.assertNotContains(respuesta, "Inactivo")
        respuesta = self.client.get(reverse("customers:customer_list"), {"mostrar_inactivos": "1"})
        self.assertContains(respuesta, "Inactivo")

    def test_detalle_muestra_estado_vacio_de_documentos_y_actividad(self):
        cliente = Customer.objects.create(tenant=self.tenant, first_name="SinDocs")
        respuesta = self.client.get(reverse("customers:customer_detail", args=[cliente.pk]))
        self.assertContains(respuesta, "Sin documentos todavía")
