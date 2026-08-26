from datetime import date
from decimal import Decimal

from apps.accounting import services
from apps.accounting.models import Account, AccountingPeriod, AccountMapping, JournalEntry, JournalEntryLine
from apps.customers.models import Customer

from ._helpers import AccountingTestCase


class AccountServiceTests(AccountingTestCase):
    def test_crear_cuenta_calcula_nivel_desde_el_padre(self):
        self.assertEqual(self.cuenta_activos.level, 1)
        self.assertEqual(self.cuenta_caja.level, 2)

    def test_codigo_duplicado_es_rechazado(self):
        with self.assertRaises(services.InvalidAccountingOperation):
            services.create_account(self.tenant, code="1100", name="Otra", account_type=Account.AccountType.ASSET)

    def test_naturaleza_por_defecto_segun_tipo(self):
        cuenta = services.create_account(self.tenant, code="9999", name="Prueba", account_type=Account.AccountType.LIABILITY)
        self.assertEqual(cuenta.normal_balance, Account.NormalBalance.CREDIT)

    def test_padre_de_otro_tenant_es_rechazado(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa", slug="otra-empresa-contable")
        cuenta_ajena = Account.all_objects.create(
            tenant=otro_tenant, code="1000", name="Activos", account_type=Account.AccountType.ASSET,
            normal_balance=Account.NormalBalance.DEBIT,
        )
        with self.assertRaises(services.InvalidAccountingOperation):
            services.create_account(self.tenant, code="1500", name="x", account_type=Account.AccountType.ASSET, parent=cuenta_ajena)

    def test_arbol_de_cuentas_anida_correctamente(self):
        arbol = services.get_account_tree(self.tenant)
        raiz_activos = next(n for n in arbol if n["cuenta"].code == "1000")
        codigos_hijos = {n["cuenta"].code for n in raiz_activos["hijos"]}
        self.assertEqual(codigos_hijos, {"1100", "1200"})


class AccountingPeriodServiceTests(AccountingTestCase):
    def test_periodo_solapado_es_rechazado(self):
        with self.assertRaises(services.InvalidAccountingOperation):
            services.open_period(
                self.tenant, name="2025-01-b", start_date=date(2025, 1, 15), end_date=date(2025, 2, 10), user=self.owner,
            )

    def test_cerrar_periodo_balanceado(self):
        cuenta_a = self.cuenta_caja
        cuenta_b = self.cuenta_ingresos
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[{"account": cuenta_a, "debit": Decimal("100")}, {"account": cuenta_b, "credit": Decimal("100")}],
        )
        services.post_journal_entry(asiento, self.owner)
        periodo = services.close_period(self.periodo, self.owner)
        self.assertEqual(periodo.status, AccountingPeriod.Status.CLOSED)

    def test_reabrir_exige_motivo(self):
        services.close_period(self.periodo, self.owner)
        with self.assertRaises(services.InvalidAccountingOperation):
            services.reopen_period(self.periodo, self.owner, reason="")

    def test_reabrir_periodo_cerrado(self):
        services.close_period(self.periodo, self.owner)
        periodo = services.reopen_period(self.periodo, self.owner, reason="corrección necesaria")
        self.assertEqual(periodo.status, AccountingPeriod.Status.REOPENED)

    def test_no_se_puede_contabilizar_en_periodo_cerrado(self):
        services.close_period(self.periodo, self.owner)
        asiento = JournalEntry.all_objects.create(
            tenant=self.tenant, number="AST-TEST-1", entry_date=date(2025, 1, 10), period=self.periodo,
            description="x", user=self.owner,
        )
        JournalEntryLine.all_objects.create(tenant=self.tenant, journal_entry=asiento, account=self.cuenta_caja, debit=Decimal("10"), line_order=1)
        JournalEntryLine.all_objects.create(tenant=self.tenant, journal_entry=asiento, account=self.cuenta_ingresos, credit=Decimal("10"), line_order=2)
        with self.assertRaises(services.InvalidAccountingOperation):
            services.post_journal_entry(asiento, self.owner)


class JournalEntryServiceTests(AccountingTestCase):
    def test_asiento_balanceado_se_contabiliza(self):
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="Venta al contado", user=self.owner,
            lines=[
                {"account": self.cuenta_caja, "debit": Decimal("118")},
                {"account": self.cuenta_ingresos, "credit": Decimal("100")},
                {"account": self.cuenta_impuestos, "credit": Decimal("18")},
            ],
        )
        asiento = services.post_journal_entry(asiento, self.owner)
        self.assertEqual(asiento.status, JournalEntry.Status.POSTED)
        self.assertTrue(asiento.number.startswith("AST-"))

    def test_asiento_descuadrado_es_rechazado(self):
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[{"account": self.cuenta_caja, "debit": Decimal("100")}, {"account": self.cuenta_ingresos, "credit": Decimal("90")}],
        )
        with self.assertRaises(services.InvalidAccountingOperation):
            services.post_journal_entry(asiento, self.owner)

    def test_monedas_mezcladas_son_rechazadas(self):
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[
                {"account": self.cuenta_caja, "debit": Decimal("100"), "currency": "USD"},
                {"account": self.cuenta_ingresos, "credit": Decimal("100"), "currency": "DOP"},
            ],
        )
        with self.assertRaises(services.InvalidAccountingOperation):
            services.post_journal_entry(asiento, self.owner)

    def test_cuenta_de_agrupacion_no_admite_movimientos(self):
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[{"account": self.cuenta_activos, "debit": Decimal("100")}, {"account": self.cuenta_ingresos, "credit": Decimal("100")}],
        )
        with self.assertRaises(services.InvalidAccountingOperation):
            services.post_journal_entry(asiento, self.owner)

    def test_no_se_puede_contabilizar_dos_veces(self):
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[{"account": self.cuenta_caja, "debit": Decimal("100")}, {"account": self.cuenta_ingresos, "credit": Decimal("100")}],
        )
        asiento = services.post_journal_entry(asiento, self.owner)
        with self.assertRaises(services.InvalidAccountingOperation):
            services.post_journal_entry(asiento, self.owner)

    def test_reversar_asiento_invierte_montos(self):
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[{"account": self.cuenta_caja, "debit": Decimal("100")}, {"account": self.cuenta_ingresos, "credit": Decimal("100")}],
        )
        asiento = services.post_journal_entry(asiento, self.owner)
        reversa = services.reverse_journal_entry(asiento, self.owner, reason="error de captura")
        self.assertEqual(reversa.status, JournalEntry.Status.POSTED)
        lineas_reversa = {linea.account_id: (linea.debit, linea.credit) for linea in services.get_journal_entry_lines(reversa)}
        self.assertEqual(lineas_reversa[self.cuenta_caja.pk], (Decimal("0"), Decimal("100")))
        self.assertEqual(lineas_reversa[self.cuenta_ingresos.pk], (Decimal("100"), Decimal("0")))
        self.assertTrue(services.is_entry_reversed(asiento))

    def test_reversar_es_idempotente(self):
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[{"account": self.cuenta_caja, "debit": Decimal("100")}, {"account": self.cuenta_ingresos, "credit": Decimal("100")}],
        )
        asiento = services.post_journal_entry(asiento, self.owner)
        primera = services.reverse_journal_entry(asiento, self.owner)
        segunda = services.reverse_journal_entry(asiento, self.owner)
        self.assertEqual(primera.pk, segunda.pk)

    def test_no_se_puede_reversar_un_borrador(self):
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[{"account": self.cuenta_caja, "debit": Decimal("100")}, {"account": self.cuenta_ingresos, "credit": Decimal("100")}],
        )
        with self.assertRaises(services.InvalidAccountingOperation):
            services.reverse_journal_entry(asiento, self.owner)


class RecordBusinessEventServiceTests(AccountingTestCase):
    def test_idempotente_por_source_event_key(self):
        lines = [{"account": self.cuenta_caja, "debit": Decimal("50")}, {"account": self.cuenta_ingresos, "credit": Decimal("50")}]
        primero = services.record_business_event(
            self.tenant, source_type="test", source_id=1, source_event_key="evento-1",
            entry_date=date(2025, 1, 10), description="x", lines=lines, user=self.owner,
        )
        segundo = services.record_business_event(
            self.tenant, source_type="test", source_id=1, source_event_key="evento-1",
            entry_date=date(2025, 1, 10), description="x (reintento)", lines=lines, user=self.owner,
        )
        self.assertEqual(primero.pk, segundo.pk)
        self.assertEqual(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="test", source_id=1).count(), 1)


class AccountMappingServiceTests(AccountingTestCase):
    def test_set_y_get_mapeo(self):
        services.set_account_mapping(self.tenant, key=AccountMapping.Key.CASH_AND_EQUIVALENTS, account=self.cuenta_caja)
        self.assertEqual(services.get_mapped_account(self.tenant, AccountMapping.Key.CASH_AND_EQUIVALENTS), self.cuenta_caja)

    def test_sin_mapeo_devuelve_none(self):
        self.assertIsNone(services.get_mapped_account(self.tenant, AccountMapping.Key.PAYROLL_EXPENSE))


class AutoPostingIntegrationTests(AccountingTestCase):
    def setUp(self):
        super().setUp()
        self.customer = Customer.objects.create(tenant=self.tenant, first_name="Cliente", last_name="Contable")

    def _crear_venta_confirmada(self, total_deseado, tax_rate=Decimal("0")):
        from apps.inventory import services as inv_services
        from apps.inventory.models import Product
        from apps.sales import services as sales_services

        producto = Product.objects.create(
            tenant=self.tenant, name="Producto contable", sku="TST-ACC-1", sale_price=Decimal("1"), tax_rate=tax_rate,
        )
        inv_services.register_stock_in(product=producto, quantity=total_deseado, user=self.owner)
        venta = sales_services.create_sale(self.tenant, user=self.owner, customer=self.customer)
        sales_services.add_sale_item(venta, product=producto, quantity=total_deseado, user=self.owner, unit_price=Decimal("1"), tax_rate=tax_rate)
        return sales_services.confirm_sale(venta, self.owner)

    def test_venta_confirmada_sin_mapeo_no_contabiliza_ni_rompe(self):
        venta = self._crear_venta_confirmada(Decimal("100"))
        self.assertEqual(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="sale", source_id=venta.pk).count(), 0)

    def test_venta_confirmada_con_mapeo_contabiliza_correctamente(self):
        self.configurar_mapeos_completos()
        venta = self._crear_venta_confirmada(Decimal("100"), tax_rate=Decimal("18"))
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="sale", source_id=venta.pk)
        self.assertEqual(asiento.status, JournalEntry.Status.POSTED)
        lineas = {linea.account_id: (linea.debit, linea.credit) for linea in services.get_journal_entry_lines(asiento)}
        self.assertEqual(lineas[self.cuenta_ar.pk], (venta.total, Decimal("0")))
        self.assertEqual(lineas[self.cuenta_ingresos.pk], (Decimal("0"), venta.subtotal - venta.discount_total))
        self.assertEqual(lineas[self.cuenta_impuestos.pk], (Decimal("0"), venta.tax_total))

    def test_venta_confirmada_no_duplica_asiento_en_confirm_idempotente(self):
        self.configurar_mapeos_completos()
        from apps.sales import services as sales_services

        venta = self._crear_venta_confirmada(Decimal("100"))
        sales_services.confirm_sale(venta, self.owner)  # reintento idempotente, ya CONFIRMED
        self.assertEqual(JournalEntry.all_objects.filter(tenant=self.tenant, source_type="sale", source_id=venta.pk).count(), 1)

    def test_pago_de_cliente_contabiliza_correctamente(self):
        self.configurar_mapeos_completos()
        from apps.sales import services as sales_services

        pago = sales_services.create_payment(self.tenant, customer=self.customer, method="cash", amount=Decimal("50"), user=self.owner)
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="payment", source_id=pago.pk)
        lineas = {linea.account_id: (linea.debit, linea.credit) for linea in services.get_journal_entry_lines(asiento)}
        self.assertEqual(lineas[self.cuenta_caja.pk], (Decimal("50"), Decimal("0")))
        self.assertEqual(lineas[self.cuenta_ar.pk], (Decimal("0"), Decimal("50")))

    def test_pago_de_gasto_contabiliza_correctamente(self):
        self.configurar_mapeos_completos()
        from apps.expenses import services as expenses_services
        from apps.expenses.models import ExpenseCategory

        categoria = ExpenseCategory.all_objects.create(tenant=self.tenant, name="Servicios")
        gasto = expenses_services.create_expense(
            self.tenant, category=categoria, user=self.owner, description="Internet", expense_date=date(2025, 1, 10), amount=Decimal("50"),
        )
        gasto = expenses_services.submit_expense_for_approval(gasto, self.owner)
        gasto = expenses_services.approve_expense(gasto, self.owner)
        pago = expenses_services.record_expense_payment(self.tenant, gasto, method="transfer", amount=Decimal("50"), user=self.owner)
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="expense_payment", source_id=pago.pk)
        lineas = {linea.account_id: (linea.debit, linea.credit) for linea in services.get_journal_entry_lines(asiento)}
        self.assertEqual(lineas[self.cuenta_gastos.pk], (Decimal("50"), Decimal("0")))
        self.assertEqual(lineas[self.cuenta_caja.pk], (Decimal("0"), Decimal("50")))

    def test_pago_de_nomina_contabiliza_correctamente(self):
        self.configurar_mapeos_completos()
        from apps.hr.models import Employee
        from apps.payroll import services as payroll_services

        empleado = Employee.all_objects.create(tenant=self.tenant, first_name="Ana", last_name="Pérez", hire_date=date(2024, 1, 15), base_salary=Decimal("1000"))
        periodo_nomina = payroll_services.create_payroll_period(
            self.tenant, start_date=date(2025, 1, 1), end_date=date(2025, 1, 15), pay_date=date(2025, 1, 16), user=self.owner,
        )
        nomina = payroll_services.calculate_payroll_for_employee(self.tenant, periodo_nomina, empleado, user=self.owner)
        payroll_services.approve_period(periodo_nomina, self.owner)
        pago = payroll_services.record_payroll_payment(self.tenant, nomina, method="transfer", amount=Decimal("1000"), user=self.owner)
        asiento = JournalEntry.all_objects.get(tenant=self.tenant, source_type="payroll_payment", source_id=pago.pk)
        lineas = {linea.account_id: (linea.debit, linea.credit) for linea in services.get_journal_entry_lines(asiento)}
        self.assertEqual(lineas[self.cuenta_nomina.pk], (Decimal("1000"), Decimal("0")))
        self.assertEqual(lineas[self.cuenta_caja.pk], (Decimal("0"), Decimal("1000")))


class AccountingReportsServiceTests(AccountingTestCase):
    def setUp(self):
        super().setUp()
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="Venta al contado", user=self.owner,
            lines=[
                {"account": self.cuenta_caja, "debit": Decimal("118")},
                {"account": self.cuenta_ingresos, "credit": Decimal("100")},
                {"account": self.cuenta_impuestos, "credit": Decimal("18")},
            ],
        )
        self.asiento = services.post_journal_entry(asiento, self.owner)

    def test_balance_de_comprobacion_cuadra(self):
        balance = services.get_trial_balance(self.tenant, self.periodo)
        self.assertEqual(balance["total_debit"], balance["total_credit"])
        self.assertEqual(balance["total_debit"], Decimal("118"))

    def test_libro_mayor_saldo_acumulado(self):
        filas = services.get_general_ledger(self.tenant, self.cuenta_caja)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["running_balance"], Decimal("118"))

    def test_libro_diario_lista_el_asiento(self):
        asientos = services.get_general_journal(self.tenant, date_from=date(2025, 1, 1), date_to=date(2025, 1, 31))
        self.assertEqual(len(asientos), 1)
        self.assertEqual(asientos[0]["entry"].pk, self.asiento.pk)

    def test_balance_general_incluye_activos_y_pasivos(self):
        balance = services.get_balance_sheet(self.tenant, self.periodo)
        self.assertEqual(balance["total_assets"], Decimal("118"))
        self.assertEqual(balance["total_liabilities"], Decimal("18"))

    def test_estado_de_resultados_calcula_utilidad(self):
        estado = services.get_income_statement(self.tenant, self.periodo)
        self.assertEqual(estado["total_revenue"], Decimal("100"))
        self.assertEqual(estado["net_income"], Decimal("100"))

    def test_estado_de_resultados_excluye_periodo_distinto(self):
        otro_periodo = services.open_period(
            self.tenant, name="2025-02", start_date=date(2025, 2, 1), end_date=date(2025, 2, 28), user=self.owner,
        )
        estado = services.get_income_statement(self.tenant, otro_periodo)
        self.assertEqual(estado["total_revenue"], Decimal("0"))

    def test_balance_general_es_acumulado_entre_periodos(self):
        otro_periodo = services.open_period(
            self.tenant, name="2025-02", start_date=date(2025, 2, 1), end_date=date(2025, 2, 28), user=self.owner,
        )
        balance = services.get_balance_sheet(self.tenant, otro_periodo)
        self.assertEqual(balance["total_assets"], Decimal("118"))
