"""Tests de la ampliación de cierre de FASE 14: costeo por promedio
ponderado + COGS, Compras/Cuentas por Pagar, cierre de caja
(sobrante/faltante) e impuestos multi-código. Ver el plan aprobado
para el diseño completo y `docs/accounting.md` para la doctrina."""

from decimal import Decimal

from apps.accounting.models import JournalEntry
from apps.accounting import services as acct_services
from apps.customers.models import Customer, Supplier
from apps.inventory import services as inv_services
from apps.inventory.models import Product
from apps.pos.models import CashRegister
from apps.pos import services as pos_services
from apps.purchases import services as purchases_services
from apps.purchases.models import PurchaseReceiptItem
from apps.sales import services as sales_services
from apps.sales.models import SaleItem

from ._helpers import AccountingTestCase


def _linea_ledger(entry):
    return list(acct_services.get_journal_entry_lines(entry))


class SaleCogsTests(AccountingTestCase):
    def setUp(self):
        super().setUp()
        self.configurar_mapeos_completos()
        self.cliente = Customer.objects.create(tenant=self.tenant, first_name="Cliente", last_name="COGS")
        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto Cantidad", sku="COGS-QTY-1",
            sale_price=Decimal("100"), tax_rate=Decimal("0"),
        )
        self.producto_serial = Product.objects.create(
            tenant=self.tenant, name="Producto Serial", sku="COGS-SER-1",
            sale_price=Decimal("900"), tax_rate=Decimal("0"),
            inventory_tracking_type=Product.TrackingType.SERIALIZED,
        )

    def _confirmar_venta_cantidad(self, cantidad=Decimal("1")):
        venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.cliente)
        sales_services.add_sale_item(venta, product=self.producto, quantity=cantidad, user=self.owner)
        return sales_services.confirm_sale(venta, self.owner)

    def test_venta_quantity_genera_cogs_con_promedio_ponderado(self):
        # Dos entradas a costos distintos -> promedio ponderado = (10*30 + 10*40)/20 = 35
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=Decimal("30"))
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=Decimal("40"))
        self.assertEqual(inv_services.get_current_average_cost(self.producto), Decimal("35"))

        venta = self._confirmar_venta_cantidad(Decimal("1"))
        item = SaleItem.all_objects.get(tenant=self.tenant, sale=venta)
        self.assertEqual(item.cost_amount, Decimal("35"))

        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="sale", source_event_key=f"sale-cogs-{venta.pk}")
        self.assertEqual(asiento.status, JournalEntry.Status.POSTED)
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_costos.pk].debit, Decimal("35"))
        self.assertEqual(lineas[self.cuenta_inventario.pk].credit, Decimal("35"))

    def test_venta_serialized_usa_costo_especifico_de_la_unidad(self):
        unidad = inv_services.register_serialized_unit(
            product=self.producto_serial, user=self.owner, imei_1="111222333444555", unit_cost=Decimal("600"),
        )
        venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.cliente)
        sales_services.add_sale_item(venta, product=self.producto_serial, quantity=Decimal("1"), user=self.owner, inventory_unit=unidad)
        venta = sales_services.confirm_sale(venta, self.owner)
        item = SaleItem.all_objects.get(tenant=self.tenant, sale=venta)
        self.assertEqual(item.cost_amount, Decimal("600"))
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="sale", source_event_key=f"sale-cogs-{venta.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_costos.pk].debit, Decimal("600"))

    def test_venta_sin_costo_conocido_no_genera_asiento_de_cogs(self):
        # Entrada SIN unit_cost -> promedio sigue en 0, sin costo real que contabilizar.
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner)
        venta = self._confirmar_venta_cantidad(Decimal("1"))
        self.assertFalse(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="sale", source_event_key=f"sale-cogs-{venta.pk}").exists())
        # La entrada de INGRESOS sigue intacta pese a que COGS no se pudo contabilizar.
        self.assertTrue(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="sale", source_event_key=f"sale-confirmed-{venta.pk}").exists())

    def test_reintento_no_duplica_el_asiento_de_cogs(self):
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=Decimal("30"))
        venta = self._confirmar_venta_cantidad(Decimal("1"))
        acct_services.try_record_sale_cogs(venta, self.owner)
        self.assertEqual(
            JournalEntry.all_objects.filter(tenant=self.tenant, source_type="sale", source_event_key=f"sale-cogs-{venta.pk}").count(), 1,
        )

    def test_devolucion_total_reversa_cogs_completo(self):
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=Decimal("30"))
        venta = self._confirmar_venta_cantidad(Decimal("2"))
        item = SaleItem.all_objects.get(tenant=self.tenant, sale=venta)
        devolucion = sales_services.create_return(
            venta, items=[{"sale_item": item, "quantity_returned": Decimal("2")}], user=self.owner,
        )
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="return", source_event_key=f"return-cogs-{devolucion.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_inventario.pk].debit, Decimal("60"))
        self.assertEqual(lineas[self.cuenta_costos.pk].credit, Decimal("60"))

    def test_devolucion_parcial_reversa_cogs_proporcional(self):
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=Decimal("30"))
        venta = self._confirmar_venta_cantidad(Decimal("4"))
        item = SaleItem.all_objects.get(tenant=self.tenant, sale=venta)
        devolucion = sales_services.create_return(
            venta, items=[{"sale_item": item, "quantity_returned": Decimal("1")}], user=self.owner,
        )
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="return", source_event_key=f"return-cogs-{devolucion.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_inventario.pk].debit, Decimal("30"))  # 1/4 de 120

    def test_devolucion_sin_cogs_original_no_genera_reverso(self):
        # Sin costo conocido -> nunca se posteó COGS -> nada que reversar.
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner)
        venta = self._confirmar_venta_cantidad(Decimal("1"))
        item = SaleItem.all_objects.get(tenant=self.tenant, sale=venta)
        devolucion = sales_services.create_return(
            venta, items=[{"sale_item": item, "quantity_returned": Decimal("1")}], user=self.owner,
        )
        self.assertFalse(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="return", source_event_key=f"return-cogs-{devolucion.pk}").exists())

    def test_refund_monetario_nunca_afecta_cogs(self):
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=Decimal("30"))
        venta = self._confirmar_venta_cantidad(Decimal("1"))
        # Pago SIN aplicar (create_payment, no record_payment_for_sale) para
        # que su saldo esté disponible y record_refund pueda usarlo
        # directamente, sin pasar por reverse_allocation.
        pago = sales_services.create_payment(self.tenant, customer=self.cliente, method="cash", amount=venta.total, user=self.owner)
        sales_services.record_refund(pago, amount=venta.total, user=self.owner, reason="prueba")
        # El COGS original sigue intacto; nunca se creó un "return-cogs" por el refund.
        self.assertTrue(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="sale", source_event_key=f"sale-cogs-{venta.pk}").exists())
        self.assertFalse(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="return").exists())


class SupplierInvoiceApTests(AccountingTestCase):
    def setUp(self):
        super().setUp()
        self.configurar_mapeos_completos()
        self.supplier = Supplier.objects.create(tenant=self.tenant, legal_name="Proveedor AP SRL", currency="USD")
        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto Compra", sku="AP-QTY-1", sale_price=Decimal("50"),
        )

    def _orden_enviada_y_recibida(self, *, unit_cost=Decimal("20"), tax_rate=Decimal("0")):
        orden = purchases_services.create_purchase_order(self.tenant, supplier=self.supplier, user=self.owner)
        item = purchases_services.add_purchase_order_item(
            orden, product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=unit_cost, tax_rate=tax_rate,
        )
        orden = purchases_services.send_purchase_order(orden, self.owner, tenant=self.tenant)
        recepcion = purchases_services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("10"), "unit_cost": unit_cost}],
            user=self.owner, tenant=self.tenant,
        )
        return orden, item, recepcion

    def test_factura_con_linea_de_inventario_genera_dr_inventario(self):
        orden, item, _recepcion = self._orden_enviada_y_recibida()
        factura = purchases_services.create_supplier_invoice(
            self.tenant, supplier=self.supplier, supplier_invoice_number="F-001", user=self.owner, purchase_order=orden,
        )
        purchases_services.add_supplier_invoice_item(
            factura, description="Producto Compra", quantity=Decimal("10"), unit_cost=Decimal("20"),
            user=self.owner, purchase_order_item=item,
        )
        factura = purchases_services.confirm_supplier_invoice(factura, self.owner)
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="supplier_invoice", source_event_key=f"supplier-invoice-confirmed-{factura.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_inventario.pk].debit, Decimal("200.00"))
        self.assertEqual(lineas[self.cuenta_cxp.pk].credit, Decimal("200.00"))

    def test_factura_con_linea_sin_orden_genera_dr_gasto_operativo(self):
        factura = purchases_services.create_supplier_invoice(
            self.tenant, supplier=self.supplier, supplier_invoice_number="F-002", user=self.owner,
        )
        purchases_services.add_supplier_invoice_item(
            factura, description="Servicio de mantenimiento", quantity=Decimal("1"), unit_cost=Decimal("150"), user=self.owner,
        )
        factura = purchases_services.confirm_supplier_invoice(factura, self.owner)
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="supplier_invoice", source_event_key=f"supplier-invoice-confirmed-{factura.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_gastos.pk].debit, Decimal("150.00"))
        self.assertEqual(lineas[self.cuenta_cxp.pk].credit, Decimal("150.00"))

    def test_factura_con_impuesto_genera_linea_de_impuesto_por_recuperar(self):
        factura = purchases_services.create_supplier_invoice(
            self.tenant, supplier=self.supplier, supplier_invoice_number="F-003", user=self.owner,
        )
        purchases_services.add_supplier_invoice_item(
            factura, description="Servicio con impuesto", quantity=Decimal("1"), unit_cost=Decimal("100"),
            tax_rate=Decimal("18"), user=self.owner,
        )
        factura = purchases_services.confirm_supplier_invoice(factura, self.owner)
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="supplier_invoice", source_event_key=f"supplier-invoice-confirmed-{factura.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_impuesto_recuperar.pk].debit, Decimal("18.00"))
        self.assertEqual(lineas[self.cuenta_cxp.pk].credit, Decimal("118.00"))

    def test_pago_a_proveedor_genera_asiento_dr_ap_cr_caja(self):
        factura = purchases_services.create_supplier_invoice(
            self.tenant, supplier=self.supplier, supplier_invoice_number="F-004", user=self.owner,
        )
        purchases_services.add_supplier_invoice_item(
            factura, description="Servicio", quantity=Decimal("1"), unit_cost=Decimal("100"), user=self.owner,
        )
        purchases_services.confirm_supplier_invoice(factura, self.owner)
        pago = purchases_services.create_supplier_payment(
            self.tenant, supplier=self.supplier, method="transfer", amount=Decimal("100"), user=self.owner,
        )
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="supplier_payment", source_event_key=f"supplier-payment-recorded-{pago.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_cxp.pk].debit, Decimal("100"))
        self.assertEqual(lineas[self.cuenta_caja.pk].credit, Decimal("100"))

    def test_devolucion_a_proveedor_sin_factura_contabilizada_no_genera_asiento(self):
        orden, item, recepcion = self._orden_enviada_y_recibida()
        receipt_item = PurchaseReceiptItem.all_objects.get(tenant=self.tenant, receipt=recepcion)
        devolucion = purchases_services.create_supplier_return(
            orden, items=[{"receipt_item": receipt_item, "quantity_returned": Decimal("2")}], user=self.owner,
        )
        self.assertFalse(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="supplier_return", source_event_key=f"supplier-return-{devolucion.pk}").exists())

    def test_devolucion_a_proveedor_con_factura_contabilizada_genera_asiento(self):
        orden, item, recepcion = self._orden_enviada_y_recibida(unit_cost=Decimal("20"))
        factura = purchases_services.create_supplier_invoice(
            self.tenant, supplier=self.supplier, supplier_invoice_number="F-005", user=self.owner, purchase_order=orden,
        )
        purchases_services.add_supplier_invoice_item(
            factura, description="Producto Compra", quantity=Decimal("10"), unit_cost=Decimal("20"),
            user=self.owner, purchase_order_item=item,
        )
        purchases_services.confirm_supplier_invoice(factura, self.owner)

        receipt_item = PurchaseReceiptItem.all_objects.get(tenant=self.tenant, receipt=recepcion)
        devolucion = purchases_services.create_supplier_return(
            orden, items=[{"receipt_item": receipt_item, "quantity_returned": Decimal("2")}], user=self.owner,
        )
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="supplier_return", source_event_key=f"supplier-return-{devolucion.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_cxp.pk].debit, Decimal("40"))  # 2 * 20
        self.assertEqual(lineas[self.cuenta_inventario.pk].credit, Decimal("40"))


class CashSessionClosingAccountingTests(AccountingTestCase):
    def setUp(self):
        super().setUp()
        self.configurar_mapeos_completos()
        self.caja = CashRegister.all_objects.create(tenant=self.tenant, name="Caja Contable", code="CAJA-CONT")
        self.caja.authorized_users.add(self.owner)

    def test_cierre_exacto_no_genera_asiento(self):
        sesion = pos_services.open_cash_session(self.tenant, cash_register=self.caja, user=self.owner, opening_amount=Decimal("100"))
        sesion = pos_services.close_cash_session(sesion, self.owner, counted_cash=Decimal("100"))
        self.assertFalse(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="cash_session", source_event_key=f"cash-session-closed-{sesion.pk}").exists())

    def test_sobrante_genera_asiento_cash_over(self):
        sesion = pos_services.open_cash_session(self.tenant, cash_register=self.caja, user=self.owner, opening_amount=Decimal("100"))
        sesion = pos_services.close_cash_session(sesion, self.owner, counted_cash=Decimal("120"))
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="cash_session", source_event_key=f"cash-session-closed-{sesion.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_caja.pk].debit, Decimal("20"))
        self.assertEqual(lineas[self.cuenta_sobrante_caja.pk].credit, Decimal("20"))

    def test_faltante_genera_asiento_cash_short(self):
        sesion = pos_services.open_cash_session(self.tenant, cash_register=self.caja, user=self.owner, opening_amount=Decimal("100"))
        sesion = pos_services.close_cash_session(sesion, self.owner, counted_cash=Decimal("85"))
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="cash_session", source_event_key=f"cash-session-closed-{sesion.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_faltante_caja.pk].debit, Decimal("15"))
        self.assertEqual(lineas[self.cuenta_caja.pk].credit, Decimal("15"))


class TaxCodeTests(AccountingTestCase):
    def setUp(self):
        super().setUp()
        self.configurar_mapeos_completos()
        self.cliente = Customer.objects.create(tenant=self.tenant, first_name="Cliente", last_name="Impuestos")
        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto Impuestos", sku="TAX-1", sale_price=Decimal("1000"), tax_rate=Decimal("10"),
        )
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("5"), user=self.owner, unit_cost=Decimal("10"))

    def _crear_venta(self):
        venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.cliente)
        sales_services.add_sale_item(venta, product=self.producto, quantity=Decimal("1"), user=self.owner)
        return venta

    def test_venta_sin_taxcode_usa_camino_simple_existente(self):
        venta = sales_services.confirm_sale(self._crear_venta(), self.owner)
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="sale", source_event_key=f"sale-confirmed-{venta.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_impuestos.pk].credit, Decimal("100.00"))

    def test_venta_con_un_taxcode_usa_su_propia_cuenta(self):
        codigo = acct_services.create_tax_code(self.tenant, code="ITBIS", name="ITBIS", rate=Decimal("10"), account=self.cuenta_impuesto_recuperar, user=self.owner)
        venta = self._crear_venta()
        item = SaleItem.all_objects.get(tenant=self.tenant, sale=venta)
        acct_services.apply_tax_code_to_sale_item(item, codigo)
        venta = sales_services.confirm_sale(venta, self.owner)
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="sale", source_event_key=f"sale-confirmed-{venta.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_impuesto_recuperar.pk].credit, Decimal("100.00"))
        self.assertNotIn(self.cuenta_impuestos.pk, lineas)

    def test_venta_con_multiples_taxcodes_agrupa_por_cuenta(self):
        codigo_a = acct_services.create_tax_code(self.tenant, code="ITBIS", name="ITBIS", rate=Decimal("6"), account=self.cuenta_impuesto_recuperar, user=self.owner)
        codigo_b = acct_services.create_tax_code(self.tenant, code="OTRO", name="Otro impuesto", rate=Decimal("4"), account=self.cuenta_sobrante_caja, user=self.owner)
        venta = self._crear_venta()
        item = SaleItem.all_objects.get(tenant=self.tenant, sale=venta)
        acct_services.apply_tax_code_to_sale_item(item, codigo_a)
        acct_services.apply_tax_code_to_sale_item(item, codigo_b)
        venta = sales_services.confirm_sale(venta, self.owner)
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="sale", source_event_key=f"sale-confirmed-{venta.pk}")
        lineas = {l.account_id: l for l in _linea_ledger(asiento)}
        self.assertEqual(lineas[self.cuenta_impuesto_recuperar.pk].credit, Decimal("60.00"))
        self.assertEqual(lineas[self.cuenta_sobrante_caja.pk].credit, Decimal("40.00"))


class InventoryValuationReconciliationTests(AccountingTestCase):
    def setUp(self):
        super().setUp()
        self.configurar_mapeos_completos()
        # Nota: TODO el stock de este producto entra vía la orden de
        # compra confirmada en el test (nunca un register_stock_in
        # manual fuera de ese flujo) -- de lo contrario la valorización
        # física incluiría unidades que la contabilidad nunca vio, y la
        # reconciliación mostraría una diferencia esperada, no un bug.
        self.producto = Product.objects.create(tenant=self.tenant, name="Producto Valorizado", sku="VAL-1", sale_price=Decimal("100"))

    def test_reconciliacion_coincide_tras_una_compra_contabilizada(self):
        supplier = Supplier.objects.create(tenant=self.tenant, legal_name="Proveedor Valorizado", currency="USD")
        orden = purchases_services.create_purchase_order(self.tenant, supplier=supplier, user=self.owner)
        item = purchases_services.add_purchase_order_item(orden, product=self.producto, quantity=Decimal("10"), user=self.owner, unit_cost=Decimal("5"))
        orden = purchases_services.send_purchase_order(orden, self.owner, tenant=self.tenant)
        purchases_services.receive_purchase_order(
            orden, lines=[{"purchase_order_item": item, "quantity_received": Decimal("10"), "unit_cost": Decimal("5")}],
            user=self.owner, tenant=self.tenant,
        )
        factura = purchases_services.create_supplier_invoice(self.tenant, supplier=supplier, supplier_invoice_number="F-VAL", user=self.owner, purchase_order=orden)
        purchases_services.add_supplier_invoice_item(factura, description="Compra", quantity=Decimal("10"), unit_cost=Decimal("5"), user=self.owner, purchase_order_item=item)
        purchases_services.confirm_supplier_invoice(factura, self.owner)

        reconciliacion = acct_services.get_inventory_gl_reconciliation(self.tenant)
        self.assertEqual(reconciliacion["difference"], Decimal("0"))
