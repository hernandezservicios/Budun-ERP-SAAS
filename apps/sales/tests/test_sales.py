from decimal import Decimal

from django.urls import reverse

from apps.inventory import services as inv_services
from apps.inventory.models import InventoryUnit
from apps.sales import services
from apps.sales.models import Sale

from ._helpers import SalesTestCase


class SaleServiceTests(SalesTestCase):
    def test_crear_venta_directa_en_borrador(self):
        sale = services.create_sale(self.tenant, user=self.user, customer=self.customer)
        self.assertTrue(sale.number.startswith("FAC-"))
        self.assertEqual(sale.status, Sale.Status.DRAFT)

    def test_confirmar_venta_producto_cantidad_reduce_stock(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("5"), user=self.user)
        stock_antes = inv_services.get_current_stock(self.producto_cantidad)
        sale = services.confirm_sale(sale, self.user)
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)
        self.assertEqual(inv_services.get_current_stock(self.producto_cantidad), stock_antes - Decimal("5"))

    def test_confirmar_venta_producto_serializado_vende_unidad(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
        services.confirm_sale(sale, self.user)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.status, InventoryUnit.Status.VENDIDO)

    def test_no_se_puede_confirmar_venta_sin_lineas(self):
        sale = services.create_sale(self.tenant, user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.confirm_sale(sale, self.user)

    def test_no_se_puede_confirmar_venta_serializada_con_unidad_ya_vendida(self):
        sale1 = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale1, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
        services.confirm_sale(sale1, self.user)

        sale2 = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale2, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad)
        with self.assertRaises(services.InvalidSalesOperation):
            services.confirm_sale(sale2, self.user)

    def test_confirmar_venta_sin_stock_suficiente_es_rechazado(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("9999"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.confirm_sale(sale, self.user)

    def test_confirmar_venta_es_idempotente(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("3"), user=self.user)
        services.confirm_sale(sale, self.user)
        stock_tras_primera_confirmacion = inv_services.get_current_stock(self.producto_cantidad)
        services.confirm_sale(sale, self.user)  # repetir
        self.assertEqual(inv_services.get_current_stock(self.producto_cantidad), stock_tras_primera_confirmacion)

    def test_cancelar_venta_en_borrador(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.cancel_sale(sale, self.user, reason="Error de captura")
        self.assertEqual(sale.status, Sale.Status.CANCELED)
        self.assertEqual(sale.cancel_reason, "Error de captura")

    def test_no_se_puede_cancelar_venta_confirmada(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        services.confirm_sale(sale, self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.cancel_sale(sale, self.user)

    def test_cancelar_venta_en_borrador_no_afecta_stock(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("5"), user=self.user)
        stock_antes = inv_services.get_current_stock(self.producto_cantidad)
        services.cancel_sale(sale, self.user)
        self.assertEqual(inv_services.get_current_stock(self.producto_cantidad), stock_antes)

    def test_venta_serializada_sin_unidad_asignada_es_rechazada_al_confirmar(self):
        sale = services.create_sale(self.tenant, user=self.user)
        # Se agrega directamente sin pasar por el form (que exigiría IMEI) para simular datos corruptos.
        from apps.sales.models import SaleItem

        SaleItem.all_objects.create(
            tenant=self.tenant, sale=sale, product=self.producto_serial, description="x", sku_snapshot="x",
            quantity=Decimal("1"), unit_price=Decimal("1"), line_order=1,
        )
        with self.assertRaises(services.InvalidSalesOperation):
            services.confirm_sale(sale, self.user)


class SaleItemFixedDiscountClampTests(SalesTestCase):
    """FASE 7 — BLOQUE A0.1: protege el clamp de `discount_amount` fijo
    contra `line_subtotal` en `_recalculate_item`. Usa `tax_rate=0`
    explícito para aislar el comportamiento del descuento (el producto
    de prueba trae 18% por defecto) — las cifras coinciden así con el
    escenario exacto que bloqueó el Bloque A de edición de cantidad."""

    def test_descuento_fijo_valido_se_aplica_tal_cual(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_cantidad, quantity=Decimal("10"), user=self.user,
            unit_price=Decimal("100"), tax_rate=Decimal("0"), discount_amount=Decimal("100"),
        )
        self.assertEqual(item.subtotal, Decimal("1000.00"))
        self.assertEqual(item.discount_amount, Decimal("100.00"))
        self.assertEqual(item.total, Decimal("900.00"))

    def test_descuento_fijo_igual_al_subtotal_produce_total_cero(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user,
            unit_price=Decimal("100"), tax_rate=Decimal("0"), discount_amount=Decimal("100"),
        )
        self.assertEqual(item.discount_amount, Decimal("100.00"))
        self.assertEqual(item.total, Decimal("0.00"))

    def test_descuento_fijo_superior_al_subtotal_queda_limitado(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user,
            unit_price=Decimal("100"), tax_rate=Decimal("0"), discount_amount=Decimal("150"),
        )
        self.assertEqual(item.discount_amount, Decimal("100.00"))
        self.assertEqual(item.total, Decimal("0.00"))

    def test_clamp_protege_una_reduccion_posterior_de_cantidad(self):
        # Escenario exacto que bloqueó el Bloque A: una línea con
        # descuento fijo válido para su cantidad original deja de serlo
        # si `quantity` se reduce después. `update_sale_item_quantity`
        # todavía no existe — se simula la mutación directamente sobre
        # el modelo, igual que hizo el análisis de la auditoría A0.
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_cantidad, quantity=Decimal("10"), user=self.user,
            unit_price=Decimal("100"), tax_rate=Decimal("0"), discount_amount=Decimal("900"),
        )
        item.quantity = Decimal("1")
        services._recalculate_item(item)
        self.assertEqual(item.subtotal, Decimal("100.00"))
        self.assertEqual(item.discount_amount, Decimal("100.00"))
        self.assertEqual(item.total, Decimal("0.00"))

    def test_descuento_porcentual_no_se_ve_afectado_por_el_clamp(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_cantidad, quantity=Decimal("10"), user=self.user,
            unit_price=Decimal("100"), tax_rate=Decimal("0"),
            discount_percent=Decimal("10"), discount_amount=Decimal("999"),
        )
        self.assertEqual(item.discount_amount, Decimal("100.00"))  # 10% de 1000, no 999
        self.assertEqual(item.total, Decimal("900.00"))

    def test_descuento_fijo_valido_se_conserva_como_monto_absoluto_al_aumentar_cantidad(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user,
            unit_price=Decimal("100"), tax_rate=Decimal("0"), discount_amount=Decimal("90"),
        )
        item.quantity = Decimal("10")
        services._recalculate_item(item)
        self.assertEqual(item.subtotal, Decimal("1000.00"))
        self.assertEqual(item.discount_amount, Decimal("90.00"))
        self.assertEqual(item.total, Decimal("910.00"))


class SaleItemQuantityUpdateTests(SalesTestCase):
    """FASE 7 — BLOQUE A: `services.update_sale_item_quantity` modifica
    ÚNICAMENTE `quantity`, reutilizando `_recalculate_item`/
    `recalculate_document_totals` — nunca una fórmula paralela."""

    def test_aumentar_cantidad_recalcula_subtotal_descuento_impuesto_y_total(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user,
            unit_price=Decimal("100"), discount_percent=Decimal("10"), tax_rate=Decimal("18"),
        )
        item = services.update_sale_item_quantity(item, Decimal("5"))
        self.assertEqual(item.quantity, Decimal("5.000"))
        self.assertEqual(item.subtotal, Decimal("500.00"))
        self.assertEqual(item.discount_amount, Decimal("50.00"))  # 10% de 500
        self.assertEqual(item.tax_amount, Decimal("81.00"))  # 18% de (500-50)
        self.assertEqual(item.total, Decimal("531.00"))
        # precio, % de descuento y producto conservados sin cambios
        self.assertEqual(item.unit_price, Decimal("100.00"))
        self.assertEqual(item.discount_percent, Decimal("10.00"))
        self.assertEqual(item.product_id, self.producto_cantidad.pk)

    def test_disminuir_cantidad_recalcula_subtotal_descuento_impuesto_y_total(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_cantidad, quantity=Decimal("10"), user=self.user,
            unit_price=Decimal("100"), discount_percent=Decimal("10"), tax_rate=Decimal("18"),
        )
        item = services.update_sale_item_quantity(item, Decimal("2"))
        self.assertEqual(item.quantity, Decimal("2.000"))
        self.assertEqual(item.subtotal, Decimal("200.00"))
        self.assertEqual(item.discount_amount, Decimal("20.00"))
        self.assertEqual(item.tax_amount, Decimal("32.40"))
        self.assertEqual(item.total, Decimal("212.40"))

    def test_descuento_fijo_queda_protegido_por_el_clamp_real_de_a01(self):
        # A diferencia del test equivalente de A0.1 (que simulaba la
        # mutación manualmente porque esta operación todavía no
        # existía), este test invoca la operación REAL de Bloque A y
        # confirma que hereda la protección de A0.1 sin duplicar clamp
        # alguno dentro de `update_sale_item_quantity`.
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_cantidad, quantity=Decimal("10"), user=self.user,
            unit_price=Decimal("100"), tax_rate=Decimal("0"), discount_amount=Decimal("900"),
        )
        item = services.update_sale_item_quantity(item, Decimal("1"))
        self.assertLessEqual(item.discount_amount, item.subtotal)
        self.assertGreaterEqual(item.total, Decimal("0"))
        self.assertEqual(item.subtotal, Decimal("100.00"))
        self.assertEqual(item.discount_amount, Decimal("100.00"))
        self.assertEqual(item.total, Decimal("0.00"))

    def test_rechaza_cantidad_cero(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("5"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.update_sale_item_quantity(item, Decimal("0"))
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("5.000"))

    def test_rechaza_cantidad_negativa(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("5"), user=self.user)
        with self.assertRaises(services.InvalidSalesOperation):
            services.update_sale_item_quantity(item, Decimal("-3"))
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("5.000"))

    def test_rechaza_linea_serializada(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(
            sale, product=self.producto_serial, quantity=Decimal("1"), user=self.user, inventory_unit=self.unidad,
        )
        with self.assertRaises(services.InvalidSalesOperation):
            services.update_sale_item_quantity(item, Decimal("2"))
        item.refresh_from_db()
        self.assertEqual(item.quantity, Decimal("1.000"))
        self.assertEqual(item.inventory_unit_id, self.unidad.pk)

    def test_venta_permanece_en_draft_tras_editar_cantidad(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        services.update_sale_item_quantity(item, Decimal("7"))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.DRAFT)

    def test_no_se_puede_editar_cantidad_de_venta_confirmada(self):
        sale = services.create_sale(self.tenant, user=self.user)
        item = services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        services.confirm_sale(sale, self.user)
        sale.refresh_from_db()  # `confirm_sale` opera sobre su propia fila `select_for_update`, no sobre este objeto
        with self.assertRaises(services.InvalidSalesOperation):
            services.update_sale_item_quantity(item, Decimal("5"))


class SaleHttpViewTests(SalesTestCase):
    def test_crear_venta_via_http(self):
        respuesta = self.client.post(reverse("sales:sale_create"), {
            "customer": self.customer.pk, "currency": "USD", "payment_terms": "contado",
            "notes": "", "terms": "", "global_discount_percent": "0", "global_discount_amount": "0", "issue_date": "",
        })
        sale = Sale.all_objects.filter(tenant=self.tenant).first()
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))

    def test_confirmar_venta_via_http(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("2"), user=self.user)
        respuesta = self.client.post(reverse("sales:sale_confirm", args=[sale.pk]))
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)

    def test_cancelar_venta_via_http(self):
        sale = services.create_sale(self.tenant, user=self.user)
        respuesta = self.client.post(reverse("sales:sale_cancel", args=[sale.pk]))
        self.assertRedirects(respuesta, reverse("sales:sale_detail", args=[sale.pk]))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CANCELED)

    def test_recibo_via_http(self):
        sale = services.create_sale(self.tenant, user=self.user)
        respuesta = self.client.get(reverse("sales:sale_receipt", args=[sale.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, sale.number)

    def test_recibo_contiene_el_enlace_real_de_devolucion_con_el_id_correcto(self):
        # FASE 7 — BLOQUE H: el recibo debe enlazar exactamente a la
        # URL real de `SaleReturnCreateView` (nunca una URL inventada),
        # con el pk de esta misma venta — sin duplicar ninguna regla de
        # `apps.sales.services.create_return`.
        sale = services.create_sale(self.tenant, user=self.user)
        respuesta = self.client.get(reverse("sales:sale_receipt", args=[sale.pk]))
        url_devolucion_real = reverse("sales:sale_return_create", args=[sale.pk])
        self.assertContains(respuesta, f'href="{url_devolucion_real}"')

    def test_recibo_muestra_recibido_y_cambio_cuando_existen(self):
        # FASE 7 — BLOQUE B: el recibo lee `Payment.amount_received`/
        # `change_amount` ya persistidos — nunca los recalcula.
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.confirm_sale(sale, self.user)
        services.record_payment_for_sale(
            sale, method="cash", amount=sale.total, user=self.user,
            amount_received=sale.total + Decimal("6.40"), change_amount=Decimal("6.40"),
        )
        respuesta = self.client.get(reverse("sales:sale_receipt", args=[sale.pk]))
        self.assertContains(respuesta, "Recibido")
        self.assertContains(respuesta, "Cambio")
        # Formato local (coma decimal) — el mismo que ya usa el resto del recibo.
        self.assertContains(respuesta, "$30,00")
        self.assertContains(respuesta, "$6,40")

    def test_recibo_no_muestra_columnas_de_cambio_cuando_no_hubo(self):
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.confirm_sale(sale, self.user)
        services.record_payment_for_sale(sale, method="cash", amount=sale.total, user=self.user)
        respuesta = self.client.get(reverse("sales:sale_receipt", args=[sale.pk]))
        # Columnas específicas de la tabla de pagos — no una búsqueda de
        # la palabra suelta (el CSS de impresión del Bloque C la cita
        # dentro de un comentario, al explicar el mensaje de checkout).
        self.assertNotContains(respuesta, "<th class=\"recibo-num\">Recibido</th>")
        self.assertNotContains(respuesta, "<th class=\"recibo-num\">Cambio</th>")

    def test_recibo_muestra_el_cambio_en_una_carga_posterior_sin_depender_del_mensaje_flash(self):
        # El mensaje flash de checkout se consume (se muestra una sola
        # vez); el recibo debe seguir mostrando el cambio en cualquier
        # carga posterior porque lo lee de `Payment`, no del mensaje.
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        sale = services.confirm_sale(sale, self.user)
        services.record_payment_for_sale(
            sale, method="cash", amount=sale.total, user=self.user,
            amount_received=sale.total + Decimal("6.40"), change_amount=Decimal("6.40"),
        )
        self.client.get(reverse("sales:sale_receipt", args=[sale.pk]))  # primera carga: consume mensajes, si los hubiera
        respuesta = self.client.get(reverse("sales:sale_receipt", args=[sale.pk]))  # segunda carga
        self.assertContains(respuesta, "Cambio")
        self.assertContains(respuesta, "$6,40")

    def test_recibo_oculta_las_notificaciones_toast_al_imprimir(self):
        # FASE 7 — BLOQUE C: hallazgo real de la auditoría — un mensaje
        # flash (ej. el de confirmar/cobrar) queda visible en pantalla
        # en la página siguiente que lo renderice, y sin la regla de
        # impresión agregada en este bloque se imprimiría flotando
        # sobre el recibo. Se confirma el escenario real (el mensaje
        # SÍ aparece en el HTML) y que la regla que lo oculta al
        # imprimir está presente.
        sale = services.create_sale(self.tenant, user=self.user)
        services.add_sale_item(sale, product=self.producto_cantidad, quantity=Decimal("1"), user=self.user)
        self.client.post(reverse("sales:sale_confirm", args=[sale.pk]))  # deja un mensaje encolado, sin consumir
        respuesta = self.client.get(reverse("sales:sale_receipt", args=[sale.pk]))
        self.assertContains(respuesta, "confirmada")  # el toast realmente aparece en el HTML del recibo
        self.assertContains(respuesta, ".toasts { display: none !important; }")

    def test_no_imprimir_sigue_marcado_en_los_controles_de_pantalla(self):
        sale = services.create_sale(self.tenant, user=self.user)
        respuesta = self.client.get(reverse("sales:sale_receipt", args=[sale.pk]))
        self.assertContains(respuesta, '<div class="no-imprimir recibo-acciones">')
