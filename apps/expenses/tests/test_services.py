from datetime import date, timedelta
from decimal import Decimal

from apps.approvals import services as approvals_services
from apps.expenses import services
from apps.expenses.models import Expense, ExpenseCategory, ExpensePayment, ExpenseRecurrence
from apps.pos.models import CashMovement
from apps.pos.services import InvalidPosOperation

from ._helpers import ExpensesTestCase


class ExpenseCategoryServiceTests(ExpensesTestCase):
    def test_crear_categoria_duplicada_es_rechazada(self):
        with self.assertRaises(services.InvalidExpenseOperation):
            services.create_expense_category(self.tenant, name="Servicios")

    def test_categoria_duplicada_es_insensible_a_mayusculas(self):
        with self.assertRaises(services.InvalidExpenseOperation):
            services.create_expense_category(self.tenant, name="SERVICIOS")

    def test_crear_categorias_por_defecto_no_duplica_existentes(self):
        creadas = services.create_default_expense_categories(self.tenant)
        self.assertEqual(len(creadas), len(services.DEFAULT_EXPENSE_CATEGORIES) - 1)  # "Servicios" ya existía.
        total = ExpenseCategory.all_objects.filter(tenant=self.tenant).count()
        self.assertEqual(total, len(services.DEFAULT_EXPENSE_CATEGORIES))

        # Segunda llamada: no crea nada nuevo.
        creadas_de_nuevo = services.create_default_expense_categories(self.tenant)
        self.assertEqual(len(creadas_de_nuevo), 0)
        self.assertEqual(ExpenseCategory.all_objects.filter(tenant=self.tenant).count(), len(services.DEFAULT_EXPENSE_CATEGORIES))

    def test_categorias_aisladas_por_tenant(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa", slug="otra-empresa-gastos")
        self.assertEqual(list(services.list_expense_categories(otro_tenant)), [])


class ExpenseLifecycleServiceTests(ExpensesTestCase):
    def test_crear_gasto_calcula_total(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="Internet oficina",
            expense_date=date.today(), amount=Decimal("100"), tax_amount=Decimal("18"), discount_amount=Decimal("10"),
        )
        self.assertEqual(gasto.total, Decimal("108"))
        self.assertEqual(gasto.status, Expense.Status.DRAFT)
        self.assertTrue(gasto.number.startswith("GAS-"))

    def test_categoria_de_otro_tenant_es_rechazada(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa", slug="otra-empresa-gastos-2")
        otra_categoria = ExpenseCategory.all_objects.create(tenant=otro_tenant, name="Otra")
        with self.assertRaises(services.InvalidExpenseOperation):
            services.create_expense(
                self.tenant, category=otra_categoria, user=self.owner, description="x",
                expense_date=date.today(), amount=Decimal("10"),
            )

    def test_monto_cero_o_negativo_es_rechazado(self):
        with self.assertRaises(services.InvalidExpenseOperation):
            services.create_expense(
                self.tenant, category=self.categoria, user=self.owner, description="x",
                expense_date=date.today(), amount=Decimal("0"),
            )

    def test_editar_gasto_en_draft_recalcula_total(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="Internet",
            expense_date=date.today(), amount=Decimal("100"),
        )
        gasto = services.update_expense(gasto, self.owner, amount=Decimal("200"), tax_amount=Decimal("36"))
        self.assertEqual(gasto.total, Decimal("236"))

    def test_no_se_puede_editar_un_gasto_aprobado(self):
        gasto = self._gasto_aprobado_por_owner(Decimal("50"))
        with self.assertRaises(services.InvalidExpenseOperation):
            services.update_expense(gasto, self.owner, amount=Decimal("999"))

    def _gasto_aprobado_por_owner(self, amount):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="Gasto de prueba",
            expense_date=date.today(), amount=amount,
        )
        gasto = services.submit_expense_for_approval(gasto, self.owner)
        return services.approve_expense(gasto, self.owner)

    def test_flujo_completo_propietario_aprueba_sin_politica(self):
        gasto = self._gasto_aprobado_por_owner(Decimal("500"))
        self.assertEqual(gasto.status, Expense.Status.APPROVED)

    def test_miembro_sin_politica_requiere_autorizacion_para_cualquier_monto(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.empleado, description="Gasto de prueba",
            expense_date=date.today(), amount=Decimal("1"),
        )
        gasto = services.submit_expense_for_approval(gasto, self.empleado)
        with self.assertRaises(services.ExpenseOverThresholdRequiresApproval):
            services.approve_expense(gasto, self.empleado)

    def test_reintento_tras_aprobacion_de_gasto_sobre_el_limite(self):
        approvals_services.set_role_policy(
            self.tenant, role="member", max_discount_percent=Decimal("0"), max_discount_amount=Decimal("0"),
            max_credit_overage=Decimal("0"), can_approve=False, max_expense_amount=Decimal("100"),
        )
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.empleado, description="Gasto grande",
            expense_date=date.today(), amount=Decimal("500"),
        )
        gasto = services.submit_expense_for_approval(gasto, self.empleado)
        with self.assertRaises(services.ExpenseOverThresholdRequiresApproval) as contexto:
            services.approve_expense(gasto, self.empleado)
        error = contexto.exception
        solicitud = approvals_services.request_approval(
            self.tenant, action_type="expense_over_threshold", requested_by=self.empleado,
            requested_value=gasto.total, allowed_limit=error.limit, document_type="expense", document_id=gasto.pk,
        )
        approvals_services.resolve_approval(solicitud, approved=True, user=self.owner, approved_value=error.overage_amount)

        gasto = services.approve_expense(gasto, self.empleado)
        self.assertEqual(gasto.status, Expense.Status.APPROVED)
        solicitud.refresh_from_db()
        self.assertIsNotNone(solicitud.consumed_at)

    def test_gasto_excepcional_requiere_autorizacion_sin_importar_el_monto(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="Gasto raro",
            expense_date=date.today(), amount=Decimal("1"), is_exceptional=True, exceptional_reason="pago urgente",
        )
        gasto = services.submit_expense_for_approval(gasto, self.owner)
        # El propietario SIEMPRE está autorizado (regla explícita) — no debería lanzar.
        gasto = services.approve_expense(gasto, self.owner)
        self.assertEqual(gasto.status, Expense.Status.APPROVED)

        gasto_miembro = services.create_expense(
            self.tenant, category=self.categoria, user=self.empleado, description="Gasto raro 2",
            expense_date=date.today(), amount=Decimal("1"), is_exceptional=True, exceptional_reason="pago urgente",
        )
        gasto_miembro = services.submit_expense_for_approval(gasto_miembro, self.empleado)
        with self.assertRaises(services.ExpenseExceptionalRequiresApproval):
            services.approve_expense(gasto_miembro, self.empleado)

    def test_rechazar_gasto(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="x",
            expense_date=date.today(), amount=Decimal("10"),
        )
        gasto = services.submit_expense_for_approval(gasto, self.owner)
        gasto = services.reject_expense(gasto, self.owner, reason="falta comprobante")
        self.assertEqual(gasto.status, Expense.Status.REJECTED)

    def test_gasto_rechazado_puede_editarse_y_reenviarse(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="x",
            expense_date=date.today(), amount=Decimal("10"),
        )
        gasto = services.submit_expense_for_approval(gasto, self.owner)
        gasto = services.reject_expense(gasto, self.owner)
        gasto = services.update_expense(gasto, self.owner, amount=Decimal("20"))
        self.assertEqual(gasto.status, Expense.Status.DRAFT)
        gasto = services.submit_expense_for_approval(gasto, self.owner)
        self.assertEqual(gasto.status, Expense.Status.PENDING_APPROVAL)

    def test_cancelar_gasto_draft(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="x",
            expense_date=date.today(), amount=Decimal("10"),
        )
        gasto = services.cancel_expense(gasto, self.owner, reason="duplicado")
        self.assertEqual(gasto.status, Expense.Status.CANCELED)

    def test_no_se_puede_cancelar_un_gasto_con_pagos(self):
        gasto = self._gasto_aprobado_por_owner(Decimal("50"))
        services.record_expense_payment(self.tenant, gasto, method="transfer", amount=Decimal("50"), user=self.owner)
        gasto.refresh_from_db()
        with self.assertRaises(services.InvalidExpenseOperation):
            services.cancel_expense(gasto, self.owner)


class ExpensePaymentServiceTests(ExpensesTestCase):
    def setUp(self):
        super().setUp()
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="Alquiler",
            expense_date=date.today(), amount=Decimal("1000"),
        )
        gasto = services.submit_expense_for_approval(gasto, self.owner)
        self.gasto = services.approve_expense(gasto, self.owner)

    def test_pago_parcial_deja_partially_paid(self):
        services.record_expense_payment(self.tenant, self.gasto, method="transfer", amount=Decimal("400"), user=self.owner)
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.status, Expense.Status.PARTIALLY_PAID)
        self.assertEqual(services.get_expense_balance_due(self.gasto), Decimal("600"))

    def test_pago_completo_deja_paid(self):
        services.record_expense_payment(self.tenant, self.gasto, method="transfer", amount=Decimal("1000"), user=self.owner)
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.status, Expense.Status.PAID)

    def test_no_se_puede_pagar_un_gasto_no_aprobado(self):
        borrador = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="x",
            expense_date=date.today(), amount=Decimal("10"),
        )
        with self.assertRaises(services.InvalidExpenseOperation):
            services.record_expense_payment(self.tenant, borrador, method="cash", amount=Decimal("10"), user=self.owner)

    def test_no_se_puede_sobre_pagar(self):
        with self.assertRaises(services.InvalidExpenseOperation):
            services.record_expense_payment(self.tenant, self.gasto, method="transfer", amount=Decimal("1001"), user=self.owner)

    def test_pago_en_moneda_distinta_es_rechazado(self):
        with self.assertRaises(services.InvalidExpenseOperation):
            services.record_expense_payment(
                self.tenant, self.gasto, method="transfer", amount=Decimal("100"), user=self.owner, currency="DOP",
            )

    def test_pago_en_efectivo_exige_caja_abierta(self):
        with self.assertRaises(InvalidPosOperation):
            services.record_expense_payment(self.tenant, self.gasto, method="cash", amount=Decimal("100"), user=self.owner)

    def test_pago_en_efectivo_genera_cash_movement(self):
        sesion = self.abrir_caja(self.owner)
        pago = services.record_expense_payment(
            self.tenant, self.gasto, method="cash", amount=Decimal("100"), user=self.owner, cash_session=sesion,
        )
        movimiento = CashMovement.all_objects.get(
            tenant=self.tenant, reference_type="expense_payment", reference_id=pago.pk,
        )
        self.assertEqual(movimiento.movement_type, CashMovement.MovementType.EXPENSE_PAYMENT_CASH)
        self.assertEqual(movimiento.amount, Decimal("100"))

    def test_anular_pago_revierte_estado(self):
        pago = services.record_expense_payment(self.tenant, self.gasto, method="transfer", amount=Decimal("1000"), user=self.owner)
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.status, Expense.Status.PAID)
        services.void_expense_payment(pago, self.owner)
        self.gasto.refresh_from_db()
        self.assertEqual(self.gasto.status, Expense.Status.APPROVED)

    def test_idempotencia_por_clave(self):
        p1 = services.record_expense_payment(
            self.tenant, self.gasto, method="transfer", amount=Decimal("100"), user=self.owner, idempotency_key="clave-x",
        )
        p2 = services.record_expense_payment(
            self.tenant, self.gasto, method="transfer", amount=Decimal("100"), user=self.owner, idempotency_key="clave-x",
        )
        self.assertEqual(p1.pk, p2.pk)
        self.assertEqual(ExpensePayment.all_objects.filter(tenant=self.tenant, expense=self.gasto).count(), 1)


class ExpenseRecurrenceServiceTests(ExpensesTestCase):
    def test_generar_gasto_de_recurrencia_vencida(self):
        recurrencia = services.create_expense_recurrence(
            self.tenant, category=self.categoria, description="Internet mensual", amount=Decimal("50"),
            frequency=ExpenseRecurrence.Frequency.MONTHLY, start_date=date.today() - timedelta(days=1), user=self.owner,
        )
        self.assertTrue(services.is_recurrence_due(recurrencia))
        gasto = services.generate_due_expense(recurrencia, self.owner)
        self.assertEqual(gasto.status, Expense.Status.DRAFT)
        self.assertEqual(gasto.source_recurrence_id, recurrencia.pk)
        self.assertEqual(gasto.amount, Decimal("50"))

    def test_no_genera_dos_veces_para_el_mismo_periodo(self):
        recurrencia = services.create_expense_recurrence(
            self.tenant, category=self.categoria, description="Internet mensual", amount=Decimal("50"),
            frequency=ExpenseRecurrence.Frequency.MONTHLY, start_date=date.today(), user=self.owner,
        )
        services.generate_due_expense(recurrencia, self.owner)
        recurrencia.refresh_from_db()
        self.assertFalse(services.is_recurrence_due(recurrencia))
        with self.assertRaises(services.InvalidExpenseOperation):
            services.generate_due_expense(recurrencia, self.owner)
        self.assertEqual(Expense.all_objects.filter(tenant=self.tenant, source_recurrence=recurrencia).count(), 1)

    def test_pausar_recurrencia_impide_generar(self):
        recurrencia = services.create_expense_recurrence(
            self.tenant, category=self.categoria, description="Internet", amount=Decimal("50"),
            frequency=ExpenseRecurrence.Frequency.WEEKLY, start_date=date.today(), user=self.owner,
        )
        services.pause_recurrence(recurrencia, self.owner)
        recurrencia.refresh_from_db()
        with self.assertRaises(services.InvalidExpenseOperation):
            services.generate_due_expense(recurrencia, self.owner)

    def test_reanudar_recurrencia_permite_generar_de_nuevo(self):
        recurrencia = services.create_expense_recurrence(
            self.tenant, category=self.categoria, description="Internet", amount=Decimal("50"),
            frequency=ExpenseRecurrence.Frequency.WEEKLY, start_date=date.today(), user=self.owner,
        )
        services.pause_recurrence(recurrencia, self.owner)
        recurrencia.refresh_from_db()
        services.resume_recurrence(recurrencia, self.owner)
        recurrencia.refresh_from_db()
        gasto = services.generate_due_expense(recurrencia, self.owner)
        self.assertIsNotNone(gasto)

    def test_recurrencia_vencida_por_fecha_fin_se_cancela(self):
        recurrencia = services.create_expense_recurrence(
            self.tenant, category=self.categoria, description="Internet", amount=Decimal("50"),
            frequency=ExpenseRecurrence.Frequency.WEEKLY, start_date=date.today() - timedelta(days=10),
            end_date=date.today() - timedelta(days=5), user=self.owner,
        )
        # El próximo período vencido (today-10, dentro del rango) ya
        # pasó — simula que la recurrencia ya avanzó más allá de
        # `end_date` (escenario real tras varias generaciones previas).
        ExpenseRecurrence.all_objects.filter(pk=recurrencia.pk).update(next_run_date=date.today() - timedelta(days=1))
        recurrencia.refresh_from_db()
        with self.assertRaises(services.InvalidExpenseOperation):
            services.generate_due_expense(recurrencia, self.owner)
        recurrencia.refresh_from_db()
        self.assertEqual(recurrencia.status, ExpenseRecurrence.Status.CANCELED)

    def test_list_due_recurrences(self):
        vencida = services.create_expense_recurrence(
            self.tenant, category=self.categoria, description="Vencida", amount=Decimal("10"),
            frequency=ExpenseRecurrence.Frequency.WEEKLY, start_date=date.today() - timedelta(days=1), user=self.owner,
        )
        futura = services.create_expense_recurrence(
            self.tenant, category=self.categoria, description="Futura", amount=Decimal("10"),
            frequency=ExpenseRecurrence.Frequency.WEEKLY, start_date=date.today() + timedelta(days=5), user=self.owner,
        )
        vencidas = list(services.list_due_recurrences(self.tenant))
        self.assertIn(vencida, vencidas)
        self.assertNotIn(futura, vencidas)


class ExpenseMultiTenantServiceTests(ExpensesTestCase):
    def test_list_expenses_aislado_por_tenant(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa", slug="otra-empresa-gastos-3")
        otra_categoria = ExpenseCategory.all_objects.create(tenant=otro_tenant, name="Otra")
        services.create_expense(
            otro_tenant, category=otra_categoria, user=self.owner, description="Gasto ajeno",
            expense_date=date.today(), amount=Decimal("10"),
        )
        services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="Gasto propio",
            expense_date=date.today(), amount=Decimal("10"),
        )
        gastos_tenant_a = services.list_expenses(self.tenant)
        self.assertEqual(gastos_tenant_a.count(), 1)
        self.assertEqual(gastos_tenant_a.first().description, "Gasto propio")
