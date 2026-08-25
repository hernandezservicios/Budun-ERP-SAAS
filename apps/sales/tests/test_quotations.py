from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.sales import services
from apps.sales.models import ProformaInvoice, Quotation, Sale, SalesActivityLog

from ._helpers import SalesTestCase


class QuotationServiceTests(SalesTestCase):
    def test_crear_cotizacion_genera_numero_con_prefijo_cot(self):
        quotation = services.create_quotation(self.tenant, user=self.user, customer=self.customer)
        self.assertTrue(quotation.number.startswith("COT-"))
        self.assertEqual(quotation.status, Quotation.Status.DRAFT)
        self.assertTrue(
            SalesActivityLog.all_objects.filter(tenant=self.tenant, entity_type="quotation", action="created").exists()
        )

    def test_numeros_consecutivos_por_tenant(self):
        q1 = services.create_quotation(self.tenant, user=self.user)
        q2 = services.create_quotation(self.tenant, user=self.user)
        n1 = int(q1.number.split("-")[1])
        n2 = int(q2.number.split("-")[1])
        self.assertEqual(n2, n1 + 1)

    def test_agregar_linea_calcula_snapshot_y_totales(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        item = services.add_quotation_item(quotation, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        self.assertEqual(item.unit_price, Decimal("20.00"))
        self.assertEqual(item.subtotal, Decimal("40.00"))
        self.assertEqual(item.tax_amount, Decimal("7.20"))  # 18% de 40
        self.assertEqual(item.total, Decimal("47.20"))
        quotation.refresh_from_db()
        self.assertEqual(quotation.total, Decimal("47.20"))

    def test_modificar_precio_del_producto_no_afecta_linea_ya_guardada(self):
        """Snapshot histórico: cambiar `sale_price` después no debe
        alterar una línea ya agregada."""
        quotation = services.create_quotation(self.tenant, user=self.user)
        item = services.add_quotation_item(quotation, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        self.producto_cantidad.sale_price = Decimal("999.00")
        self.producto_cantidad.save(update_fields=["sale_price"])
        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal("20.00"))

    def test_descuento_por_porcentaje_tiene_prioridad_sobre_monto_fijo(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        item = services.add_quotation_item(
            quotation, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user,
            discount_percent=Decimal("10"), discount_amount=Decimal("999"),
        )
        self.assertEqual(item.discount_amount, Decimal("2.00"))  # 10% de 20, no 999

    def test_descuento_global_se_aplica_como_rebaja_final(self):
        quotation = services.create_quotation(self.tenant, user=self.user, global_discount_amount=Decimal("5"))
        services.add_quotation_item(quotation, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        quotation.refresh_from_db()
        # total de línea = 20 + 18% = 23.60; menos 5 de descuento global = 18.60
        self.assertEqual(quotation.total, Decimal("18.60"))
        self.assertEqual(quotation.discount_total, Decimal("5.00"))

    def test_eliminar_linea_recalcula_totales(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        item = services.add_quotation_item(quotation, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        services.remove_quotation_item(item)
        quotation.refresh_from_db()
        self.assertEqual(quotation.total, Decimal("0"))

    def test_no_se_puede_editar_cotizacion_fuera_de_borrador(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        quotation = services.transition_quotation_status(quotation, Quotation.Status.SENT, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.add_quotation_item(quotation, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)

    def test_transiciones_validas_e_invalidas(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        quotation = services.transition_quotation_status(quotation, Quotation.Status.SENT, self.user)
        quotation = services.transition_quotation_status(quotation, Quotation.Status.REJECTED, self.user)
        self.assertEqual(quotation.status, Quotation.Status.REJECTED)
        with self.assertRaises(services.InvalidSalesOperation):
            services.transition_quotation_status(quotation, Quotation.Status.SENT, self.user)

    def test_vencer_cotizacion_via_expire_due_quotations(self):
        quotation = services.create_quotation(self.tenant, user=self.user, expiry_date=timezone.localdate().replace(year=2000))
        services.transition_quotation_status(quotation, Quotation.Status.SENT, self.user)
        vencidas = services.expire_due_quotations(self.tenant)
        self.assertEqual(len(vencidas), 1)
        quotation.refresh_from_db()
        self.assertEqual(quotation.status, Quotation.Status.EXPIRED)

    def test_duplicar_cotizacion_crea_nueva_en_borrador_con_mismas_lineas(self):
        quotation = services.create_quotation(self.tenant, user=self.user, customer=self.customer)
        services.add_quotation_item(quotation, product=self.producto_cantidad, quantity=Decimal("3"), user=self.user)
        services.transition_quotation_status(quotation, Quotation.Status.SENT, self.user)

        duplicada = services.duplicate_quotation(quotation, self.user)
        self.assertNotEqual(duplicada.number, quotation.number)
        self.assertEqual(duplicada.status, Quotation.Status.DRAFT)
        self.assertEqual(duplicada.total, quotation.total)
        self.assertEqual(services.get_quotation_items(duplicada).count(), 1)

    def test_convertir_a_proforma_copia_lineas_y_marca_convertida(self):
        quotation = services.create_quotation(self.tenant, user=self.user, customer=self.customer)
        services.add_quotation_item(quotation, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        proforma = services.convert_quotation_to_proforma(quotation, self.user)
        self.assertTrue(proforma.number.startswith("PRO-"))
        self.assertEqual(proforma.total, quotation.total)
        quotation.refresh_from_db()
        self.assertEqual(quotation.status, Quotation.Status.CONVERTED)
        self.assertIsNotNone(quotation.converted_at)
        self.assertEqual(quotation.converted_by, self.user)

    def test_no_se_puede_convertir_dos_veces(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        services.convert_quotation_to_proforma(quotation, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.convert_quotation_to_proforma(quotation, self.user)

    def test_convertir_directo_a_venta(self):
        quotation = services.create_quotation(self.tenant, user=self.user, customer=self.customer)
        services.add_quotation_item(quotation, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.convert_quotation_to_sale(quotation, self.user)
        self.assertTrue(sale.number.startswith("FAC-"))
        self.assertEqual(sale.status, Sale.Status.DRAFT)
        self.assertEqual(sale.source_quotation_id, quotation.pk)


class QuotationHttpViewTests(SalesTestCase):
    def _datos_validos(self, **overrides):
        datos = {
            "customer": self.customer.pk, "currency": "USD", "payment_terms": "contado",
            "notes": "", "terms": "", "global_discount_percent": "0", "global_discount_amount": "0",
            "issue_date": "", "expiry_date": "",
        }
        datos.update(overrides)
        return datos

    def test_crear_cotizacion_via_http(self):
        respuesta = self.client.post(reverse("sales:quotation_create"), self._datos_validos())
        quotation = Quotation.all_objects.filter(tenant=self.tenant).first()
        self.assertIsNotNone(quotation)
        self.assertRedirects(respuesta, reverse("sales:quotation_detail", args=[quotation.pk]))

    def test_agregar_linea_via_http(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        respuesta = self.client.post(
            reverse("sales:quotation_item_add", args=[quotation.pk]),
            {"product": self.producto_cantidad.pk, "quantity": "2", "unit_identifier": "", "unit_price": "", "discount_percent": "0", "discount_amount": "0"},
        )
        self.assertRedirects(respuesta, reverse("sales:quotation_detail", args=[quotation.pk]))
        self.assertEqual(services.get_quotation_items(quotation).count(), 1)

    def test_agregar_linea_serializada_requiere_imei(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        respuesta = self.client.post(
            reverse("sales:quotation_item_add", args=[quotation.pk]),
            {"product": self.producto_serial.pk, "quantity": "1", "unit_identifier": "", "unit_price": "", "discount_percent": "0", "discount_amount": "0"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(services.get_quotation_items(quotation).count(), 0)

    def test_agregar_linea_serializada_con_imei_valido(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        respuesta = self.client.post(
            reverse("sales:quotation_item_add", args=[quotation.pk]),
            {"product": self.producto_serial.pk, "quantity": "1", "unit_identifier": "111222333444555", "unit_price": "", "discount_percent": "0", "discount_amount": "0"},
        )
        self.assertEqual(respuesta.status_code, 302)
        item = services.get_quotation_items(quotation).first()
        self.assertEqual(item.inventory_unit_id, self.unidad.pk)

    def test_convertir_a_proforma_via_http(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        respuesta = self.client.post(reverse("sales:quotation_convert_proforma", args=[quotation.pk]))
        proforma = ProformaInvoice.all_objects.filter(tenant=self.tenant).first()
        self.assertRedirects(respuesta, reverse("sales:proforma_detail", args=[proforma.pk]))

    def test_listado_de_cotizaciones_via_http(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        respuesta = self.client.get(reverse("sales:quotation_list"))
        self.assertContains(respuesta, quotation.number)

    def test_imprimir_cotizacion_via_http(self):
        quotation = services.create_quotation(self.tenant, user=self.user)
        respuesta = self.client.get(reverse("sales:quotation_print", args=[quotation.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, quotation.number)
