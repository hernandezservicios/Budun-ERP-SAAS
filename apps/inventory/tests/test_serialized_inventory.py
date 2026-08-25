"""
Inventario SERIALIZADO (adición a FASE 8, requisito auditado por el
usuario): `Product.inventory_tracking_type`, `InventoryUnit`, la máquina
de estados de unidad, la búsqueda unificada (`services.search_catalog`)
y las reglas de venta (`ensure_unit_available_for_sale`).
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.inventory import services
from apps.inventory.models import InventoryUnit, Product
from apps.inventory.services import InvalidInventoryOperation

from ._helpers import InventoryTestCase


class InventoryUnitConstraintTests(InventoryTestCase):
    """Constraints de PostgreSQL a nivel de base de datos (no solo de
    formulario): deben rechazar datos inválidos incluso si alguien se
    salta la capa de servicios."""

    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(
            tenant=self.tenant,
            name="Teléfono Serializado",
            sku="TEL-1",
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )

    def test_serial_duplicado_en_el_mismo_tenant_es_rechazado(self):
        InventoryUnit.objects.create(tenant=self.tenant, product=self.product, serial="SN-100")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryUnit.objects.create(tenant=self.tenant, product=self.product, serial="SN-100")

    def test_imei1_duplicado_en_el_mismo_tenant_es_rechazado(self):
        InventoryUnit.objects.create(tenant=self.tenant, product=self.product, imei_1="111111111111111")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryUnit.objects.create(
                    tenant=self.tenant, product=self.product, imei_1="111111111111111"
                )

    def test_imei2_duplicado_en_el_mismo_tenant_es_rechazado(self):
        InventoryUnit.objects.create(tenant=self.tenant, product=self.product, imei_2="222222222222222")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryUnit.objects.create(
                    tenant=self.tenant, product=self.product, imei_2="222222222222222"
                )

    def test_dos_unidades_con_serial_vacio_son_permitidas(self):
        # La unicidad de "serial" es PARCIAL (solo aplica a no-vacíos):
        # varias unidades pueden no tener número de serie a la vez,
        # siempre que tengan al menos un IMEI.
        InventoryUnit.objects.create(tenant=self.tenant, product=self.product, imei_1="AAA")
        InventoryUnit.objects.create(tenant=self.tenant, product=self.product, imei_1="BBB")
        # `all_objects`, no `objects`: fuera de una request HTTP real el
        # ContextVar de TenantManager no está fijado (mismo principio que
        # `services.py`, ver su docstring).
        self.assertEqual(InventoryUnit.all_objects.filter(product=self.product).count(), 2)

    def test_imei1_igual_a_imei2_es_rechazado(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryUnit.objects.create(
                    tenant=self.tenant, product=self.product, imei_1="333", imei_2="333"
                )

    def test_unidad_sin_ningun_identificador_es_rechazada(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryUnit.objects.create(tenant=self.tenant, product=self.product)

    def test_costo_unitario_negativo_es_rechazado(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryUnit.objects.create(
                    tenant=self.tenant, product=self.product, serial="SN-NEG", unit_cost=Decimal("-1")
                )

    def test_mismo_serial_en_dos_tenants_distintos_es_permitido(self):
        # La unicidad es POR TENANT, no global: dos empresas distintas
        # pueden coincidir en un mismo número de serie sin conflicto.
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa", slug="otra-empresa-serial")
        otro_producto = Product.objects.create(
            tenant=otro_tenant,
            name="Otro Teléfono",
            sku="TEL-OTRO",
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        InventoryUnit.objects.create(tenant=self.tenant, product=self.product, serial="SN-COMPARTIDO")
        # No debe lanzar IntegrityError.
        InventoryUnit.objects.create(tenant=otro_tenant, product=otro_producto, serial="SN-COMPARTIDO")


class RegisterSerializedUnitServiceTests(InventoryTestCase):
    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(
            tenant=self.tenant,
            name="Teléfono Serializado",
            sku="TEL-2",
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )

    def test_registrar_unidad_por_imei_queda_en_stock(self):
        unidad = services.register_serialized_unit(
            product=self.product, user=self.user, imei_1="123456789012345", unit_cost=Decimal("500")
        )
        self.assertEqual(unidad.status, InventoryUnit.Status.EN_STOCK)
        self.assertEqual(unidad.tenant, self.tenant)
        self.assertEqual(services.get_current_stock(self.product), 1)

    def test_registrar_unidad_sin_ningun_identificador_es_rechazada(self):
        with self.assertRaises(InvalidInventoryOperation):
            services.register_serialized_unit(product=self.product, user=self.user)

    def test_registrar_unidad_con_imei_iguales_es_rechazada(self):
        with self.assertRaises(InvalidInventoryOperation):
            services.register_serialized_unit(
                product=self.product, user=self.user, imei_1="999", imei_2="999"
            )

    def test_registrar_unidad_en_producto_por_cantidad_es_rechazada(self):
        producto_cantidad = Product.objects.create(tenant=self.tenant, name="Por cantidad", sku="CANT-1")
        with self.assertRaises(InvalidInventoryOperation):
            services.register_serialized_unit(product=producto_cantidad, user=self.user, serial="X-1")

    def test_registrar_movimiento_de_cantidad_en_producto_serializado_es_rechazado(self):
        with self.assertRaises(InvalidInventoryOperation):
            services.register_stock_in(product=self.product, quantity=Decimal("1"), user=self.user)
        with self.assertRaises(InvalidInventoryOperation):
            services.register_stock_out(product=self.product, quantity=Decimal("1"), user=self.user)
        with self.assertRaises(InvalidInventoryOperation):
            services.register_stock_adjustment(product=self.product, new_stock=Decimal("1"), user=self.user)

    def test_stock_de_producto_serializado_cuenta_solo_unidades_en_stock(self):
        services.register_serialized_unit(product=self.product, user=self.user, serial="A-1")
        services.register_serialized_unit(product=self.product, user=self.user, serial="A-2")
        unidad_vendida = services.register_serialized_unit(product=self.product, user=self.user, serial="A-3")
        services.transition_unit_status(
            unit=unidad_vendida, new_status=InventoryUnit.Status.VENDIDO, user=self.user
        )
        self.assertEqual(services.get_current_stock(self.product), 2)


class UnitStatusTransitionTests(InventoryTestCase):
    """Máquina de estados: solo ciertas transiciones son válidas (regla
    de negocio #8 del usuario: nunca se debe poder "vender" dos veces la
    misma unidad, ni una que está en reparación, etc.)."""

    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(
            tenant=self.tenant,
            name="Teléfono Serializado",
            sku="TEL-3",
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.unit = services.register_serialized_unit(product=self.product, user=self.user, serial="ST-1")

    def test_en_stock_a_vendido_es_valido(self):
        actualizada = services.transition_unit_status(
            unit=self.unit, new_status=InventoryUnit.Status.VENDIDO, user=self.user
        )
        self.assertEqual(actualizada.status, InventoryUnit.Status.VENDIDO)

    def test_vendido_a_reservado_no_es_valido(self):
        services.transition_unit_status(unit=self.unit, new_status=InventoryUnit.Status.VENDIDO, user=self.user)
        self.unit.refresh_from_db()
        with self.assertRaises(InvalidInventoryOperation):
            services.transition_unit_status(
                unit=self.unit, new_status=InventoryUnit.Status.RESERVADO, user=self.user
            )

    def test_perdido_es_un_estado_terminal_sin_salida(self):
        services.transition_unit_status(unit=self.unit, new_status=InventoryUnit.Status.PERDIDO, user=self.user)
        self.unit.refresh_from_db()
        with self.assertRaises(InvalidInventoryOperation):
            services.transition_unit_status(
                unit=self.unit, new_status=InventoryUnit.Status.EN_STOCK, user=self.user
            )

    def test_reparacion_a_garantia_y_de_vuelta_a_en_stock_es_valido(self):
        services.transition_unit_status(unit=self.unit, new_status=InventoryUnit.Status.REPARACION, user=self.user)
        self.unit.refresh_from_db()
        services.transition_unit_status(unit=self.unit, new_status=InventoryUnit.Status.GARANTIA, user=self.user)
        self.unit.refresh_from_db()
        actualizada = services.transition_unit_status(
            unit=self.unit, new_status=InventoryUnit.Status.EN_STOCK, user=self.user
        )
        self.assertEqual(actualizada.status, InventoryUnit.Status.EN_STOCK)

    def test_transicion_invalida_no_expone_el_identificador_completo_en_el_error(self):
        services.transition_unit_status(unit=self.unit, new_status=InventoryUnit.Status.VENDIDO, user=self.user)
        self.unit.refresh_from_db()
        with self.assertRaises(InvalidInventoryOperation) as contexto:
            services.transition_unit_status(
                unit=self.unit, new_status=InventoryUnit.Status.RESERVADO, user=self.user
            )
        mensaje = str(contexto.exception)
        self.assertNotIn("ST-1", mensaje)
        self.assertIn("TEL-3", mensaje)

    def test_status_changed_by_se_actualiza(self):
        services.transition_unit_status(unit=self.unit, new_status=InventoryUnit.Status.VENDIDO, user=self.user)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status_changed_by, self.user)


class EnsureUnitAvailableForSaleTests(InventoryTestCase):
    def setUp(self):
        super().setUp()
        self.product = Product.objects.create(
            tenant=self.tenant,
            name="Teléfono Serializado",
            sku="TEL-4",
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )

    def test_unidad_en_stock_esta_disponible(self):
        unidad = services.register_serialized_unit(product=self.product, user=self.user, serial="DISP-1")
        services.ensure_unit_available_for_sale(unidad)  # no debe lanzar nada

    def test_unidad_vendida_no_esta_disponible(self):
        unidad = services.register_serialized_unit(product=self.product, user=self.user, serial="DISP-2")
        services.transition_unit_status(unit=unidad, new_status=InventoryUnit.Status.VENDIDO, user=self.user)
        unidad.refresh_from_db()
        with self.assertRaises(InvalidInventoryOperation):
            services.ensure_unit_available_for_sale(unidad)

    def test_unidad_reservada_no_esta_disponible(self):
        unidad = services.register_serialized_unit(product=self.product, user=self.user, serial="DISP-3")
        services.transition_unit_status(unit=unidad, new_status=InventoryUnit.Status.RESERVADO, user=self.user)
        unidad.refresh_from_db()
        with self.assertRaises(InvalidInventoryOperation):
            services.ensure_unit_available_for_sale(unidad)

    def test_unidad_en_reparacion_no_esta_disponible(self):
        unidad = services.register_serialized_unit(product=self.product, user=self.user, serial="DISP-4")
        services.transition_unit_status(unit=unidad, new_status=InventoryUnit.Status.REPARACION, user=self.user)
        unidad.refresh_from_db()
        with self.assertRaises(InvalidInventoryOperation):
            services.ensure_unit_available_for_sale(unidad)

    def test_error_de_no_disponibilidad_no_expone_el_serial_completo(self):
        unidad = services.register_serialized_unit(product=self.product, user=self.user, serial="SECRETO-999")
        services.transition_unit_status(unit=unidad, new_status=InventoryUnit.Status.VENDIDO, user=self.user)
        unidad.refresh_from_db()
        with self.assertRaises(InvalidInventoryOperation) as contexto:
            services.ensure_unit_available_for_sale(unidad)
        self.assertNotIn("SECRETO-999", str(contexto.exception))


class SearchCatalogTests(InventoryTestCase):
    """`services.search_catalog`: búsqueda unificada por nombre, SKU,
    código de barras, número de serie e IMEI (requisito #6/#7 del
    usuario, preparación explícita para FASE 10/11/15)."""

    def setUp(self):
        super().setUp()
        self.producto_cantidad = Product.objects.create(
            tenant=self.tenant, name="Cable USB-C", sku="CABLE-1", barcode="7501234567890"
        )
        self.producto_serial = Product.objects.create(
            tenant=self.tenant,
            name="Teléfono Localizable",
            sku="TEL-BUS",
            barcode="7509999999999",
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.unidad = services.register_serialized_unit(
            product=self.producto_serial, user=self.user, serial="BUS-SERIAL-1", imei_1="BUS-IMEI-1", imei_2="BUS-IMEI-2"
        )

    def test_busqueda_por_nombre_encuentra_producto_por_cantidad(self):
        resultados = services.search_catalog(self.tenant, "Cable")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].product, self.producto_cantidad)
        self.assertIsNone(resultados[0].unit)
        self.assertFalse(resultados[0].requires_unit_selection)

    def test_busqueda_por_sku_encuentra_producto(self):
        resultados = services.search_catalog(self.tenant, "CABLE-1")
        self.assertEqual(resultados[0].product, self.producto_cantidad)

    def test_busqueda_por_codigo_de_barras_encuentra_producto(self):
        resultados = services.search_catalog(self.tenant, "7501234567890")
        self.assertEqual(resultados[0].product, self.producto_cantidad)

    def test_busqueda_por_nombre_de_producto_serializado_pide_seleccionar_unidad(self):
        resultados = services.search_catalog(self.tenant, "Teléfono Localizable")
        self.assertEqual(len(resultados), 1)
        self.assertTrue(resultados[0].requires_unit_selection)
        self.assertIsNone(resultados[0].unit)

    def test_busqueda_por_serial_exacto_devuelve_la_unidad_directamente(self):
        resultados = services.search_catalog(self.tenant, "BUS-SERIAL-1")
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].unit, self.unidad)
        self.assertFalse(resultados[0].requires_unit_selection)

    def test_busqueda_por_imei1_exacto_devuelve_la_unidad(self):
        resultados = services.search_catalog(self.tenant, "BUS-IMEI-1")
        self.assertEqual(resultados[0].unit, self.unidad)

    def test_busqueda_por_imei2_exacto_devuelve_la_unidad(self):
        resultados = services.search_catalog(self.tenant, "BUS-IMEI-2")
        self.assertEqual(resultados[0].unit, self.unidad)

    def test_busqueda_vacia_no_devuelve_nada(self):
        self.assertEqual(services.search_catalog(self.tenant, ""), [])
        self.assertEqual(services.search_catalog(self.tenant, "   "), [])

    def test_busqueda_sin_coincidencias_devuelve_lista_vacia(self):
        self.assertEqual(services.search_catalog(self.tenant, "no-existe-nada-parecido"), [])


class SerializedInventoryIsolationTests(InventoryTestCase):
    """Multi-Tenancy específica de unidades/IMEI/serie (requisito #9 del
    usuario): Tenant A no debe poder detectar ni acceder a unidades de
    Tenant B, ni siquiera a través de la búsqueda unificada."""

    def setUp(self):
        super().setUp()
        from apps.tenants.models import Membership, Tenant

        self.tenant_b = Tenant.objects.create(name="Empresa Serial B", slug="empresa-serial-b")
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user_b = User.objects.create_user(email="serial.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

        self.producto_a = Product.objects.create(
            tenant=self.tenant,
            name="Teléfono A",
            sku="TEL-A",
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.producto_b = Product.objects.create(
            tenant=self.tenant_b,
            name="Teléfono B",
            sku="TEL-B",
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.unidad_b = services.register_serialized_unit(
            product=self.producto_b, user=self.user_b, serial="SECRETO-B", imei_1="IMEI-SECRETO-B"
        )

        self.client_b = self.client_class()
        self.client_b.login(username="serial.b@example.com", password="clave-de-prueba-987")

    def test_busqueda_de_tenant_a_por_serial_de_tenant_b_no_encuentra_nada(self):
        resultados = services.search_catalog(self.tenant, "SECRETO-B")
        self.assertEqual(resultados, [])

    def test_busqueda_de_tenant_a_por_imei_de_tenant_b_no_encuentra_nada(self):
        resultados = services.search_catalog(self.tenant, "IMEI-SECRETO-B")
        self.assertEqual(resultados, [])

    def test_tenant_a_no_puede_acceder_por_url_directa_a_unidad_de_tenant_b(self):
        respuesta = self.client.post(
            reverse("inventory:unit_status_change", args=[self.producto_b.pk, self.unidad_b.pk]),
            {"new_status": InventoryUnit.Status.VENDIDO, "notes": ""},
        )
        self.assertEqual(respuesta.status_code, 404)
        self.unidad_b.refresh_from_db()
        self.assertEqual(self.unidad_b.status, InventoryUnit.Status.EN_STOCK)

    def test_tenant_a_no_puede_registrar_unidad_para_producto_de_tenant_b(self):
        respuesta = self.client.post(
            reverse("inventory:unit_create", args=[self.producto_b.pk]),
            {"serial": "INTENTO-HACKEO", "imei_1": "", "imei_2": "", "unit_cost": "0", "purchase_origin": "", "notes": ""},
        )
        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(InventoryUnit.all_objects.filter(serial="INTENTO-HACKEO").exists())

    def test_detalle_de_producto_de_tenant_a_no_muestra_unidades_de_tenant_b(self):
        services.register_serialized_unit(product=self.producto_a, user=self.user, serial="UNIDAD-A")
        respuesta = self.client.get(reverse("inventory:product_detail", args=[self.producto_a.pk]))
        self.assertContains(respuesta, "UNIDAD-A")
        self.assertNotContains(respuesta, "SECRETO-B")


class UnitHttpViewTests(InventoryTestCase):
    """Flujo HTTP real de alta/estado de unidades, y las guardas que
    impiden mezclar el flujo de cantidad con el de serializado."""

    def setUp(self):
        super().setUp()
        self.producto_serial = Product.objects.create(
            tenant=self.tenant,
            name="Teléfono HTTP",
            sku="TEL-HTTP",
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )
        self.producto_cantidad = Product.objects.create(tenant=self.tenant, name="Cantidad HTTP", sku="CANT-HTTP")

    def test_registrar_unidad_via_http(self):
        respuesta = self.client.post(
            reverse("inventory:unit_create", args=[self.producto_serial.pk]),
            {
                "serial": "HTTP-SN-1",
                "imei_1": "",
                "imei_2": "",
                "unit_cost": "250.00",
                "purchase_origin": "Proveedor X",
                "notes": "",
            },
        )
        self.assertRedirects(
            respuesta, reverse("inventory:product_detail", args=[self.producto_serial.pk])
        )
        self.assertTrue(
            InventoryUnit.all_objects.filter(product=self.producto_serial, serial="HTTP-SN-1").exists()
        )

    def test_registrar_unidad_sin_identificador_muestra_error_sin_romper(self):
        respuesta = self.client.post(
            reverse("inventory:unit_create", args=[self.producto_serial.pk]),
            {"serial": "", "imei_1": "", "imei_2": "", "unit_cost": "0", "purchase_origin": "", "notes": ""},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "al menos un identificador")

    def test_registrar_unidad_en_producto_por_cantidad_redirige_con_error(self):
        respuesta = self.client.get(
            reverse("inventory:unit_create", args=[self.producto_cantidad.pk])
        )
        self.assertRedirects(
            respuesta, reverse("inventory:product_detail", args=[self.producto_cantidad.pk])
        )

    def test_entrada_de_stock_en_producto_serializado_redirige_con_error(self):
        respuesta = self.client.get(reverse("inventory:stock_in", args=[self.producto_serial.pk]))
        self.assertRedirects(
            respuesta, reverse("inventory:product_detail", args=[self.producto_serial.pk])
        )

    def test_cambiar_estado_via_http(self):
        unidad = services.register_serialized_unit(product=self.producto_serial, user=self.user, serial="HTTP-SN-2")
        respuesta = self.client.post(
            reverse("inventory:unit_status_change", args=[self.producto_serial.pk, unidad.pk]),
            {"new_status": InventoryUnit.Status.RESERVADO, "notes": "Apartado por cliente"},
        )
        self.assertRedirects(
            respuesta, reverse("inventory:product_detail", args=[self.producto_serial.pk])
        )
        unidad.refresh_from_db()
        self.assertEqual(unidad.status, InventoryUnit.Status.RESERVADO)

    def test_detalle_de_producto_serializado_muestra_unidades_no_movimientos(self):
        services.register_serialized_unit(product=self.producto_serial, user=self.user, serial="VISIBLE-1")
        respuesta = self.client.get(reverse("inventory:product_detail", args=[self.producto_serial.pk]))
        self.assertContains(respuesta, "Unidades individuales")
        self.assertNotContains(respuesta, "Historial de movimientos")


class ProductFormTrackingTypeTests(InventoryTestCase):
    def test_no_se_puede_cambiar_tipo_de_seguimiento_con_historial(self):
        from apps.inventory.forms import ProductForm

        producto = Product.objects.create(tenant=self.tenant, name="Con Historial", sku="HIST-1")
        services.register_stock_in(product=producto, quantity=Decimal("5"), user=self.user)

        form = ProductForm(
            data={
                "name": "Con Historial",
                "sku": "HIST-1",
                "barcode": "",
                "category": "",
                "description": "",
                "inventory_tracking_type": Product.TrackingType.SERIALIZED,
                "purchase_price": "0",
                "sale_price": "0",
                "tax_rate": "0",
                "min_stock": "0",
                "is_active": "on",
            },
            instance=producto,
            tenant=self.tenant,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("inventory_tracking_type", form.errors)
