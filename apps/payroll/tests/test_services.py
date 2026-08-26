from datetime import date
from decimal import Decimal

from apps.approvals import services as approvals_services
from apps.payroll import services
from apps.payroll.models import Payroll, PayrollLine, PayrollPeriod
from apps.pos.models import CashMovement

from ._helpers import PayrollTestCase


class PayrollPeriodServiceTests(PayrollTestCase):
    def test_crear_periodo(self):
        periodo = services.create_payroll_period(
            self.tenant, start_date=date(2025, 1, 1), end_date=date(2025, 1, 15),
            pay_date=date(2025, 1, 16), user=self.owner,
        )
        self.assertEqual(periodo.status, PayrollPeriod.Status.DRAFT)
        self.assertTrue(periodo.number.startswith("NOM-"))

    def test_fecha_fin_antes_de_inicio_es_rechazada(self):
        with self.assertRaises(services.InvalidPayrollOperation):
            services.create_payroll_period(
                self.tenant, start_date=date(2025, 1, 15), end_date=date(2025, 1, 1),
                pay_date=date(2025, 1, 16), user=self.owner,
            )


class PayrollCalculationServiceTests(PayrollTestCase):
    def setUp(self):
        super().setUp()
        self.periodo = services.create_payroll_period(
            self.tenant, start_date=date(2025, 1, 1), end_date=date(2025, 1, 15),
            pay_date=date(2025, 1, 16), user=self.owner,
        )

    def test_calcular_nomina_snapshotea_salario_base(self):
        nomina = services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)
        self.assertEqual(nomina.base_salary_snapshot, Decimal("50000"))
        self.assertEqual(nomina.gross_total, Decimal("50000"))
        self.assertEqual(nomina.net_total, Decimal("50000"))
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.Status.PROCESSING)

    def test_calcular_con_lineas_extra(self):
        nomina = services.calculate_payroll_for_employee(
            self.tenant, self.periodo, self.empleado, user=self.owner,
            extra_lines=[
                {"category": PayrollLine.Category.EARNING, "concept": PayrollLine.Concept.BONUS, "amount": Decimal("1000")},
                {"category": PayrollLine.Category.DEDUCTION, "concept": PayrollLine.Concept.TAX_WITHHOLDING, "amount": Decimal("2000")},
            ],
        )
        self.assertEqual(nomina.gross_total, Decimal("51000"))
        self.assertEqual(nomina.deductions_total, Decimal("2000"))
        self.assertEqual(nomina.net_total, Decimal("49000"))

    def test_no_se_puede_calcular_dos_veces_el_mismo_empleado_en_el_mismo_periodo(self):
        services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)
        with self.assertRaises(services.InvalidPayrollOperation):
            services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)

    def test_empleado_de_otro_tenant_es_rechazado(self):
        from apps.hr.models import Employee
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa", slug="otra-empresa-nomina")
        ajeno = Employee.all_objects.create(tenant=otro_tenant, first_name="Ajeno", last_name="X", hire_date=date(2024, 1, 1))
        with self.assertRaises(services.InvalidPayrollOperation):
            services.calculate_payroll_for_employee(self.tenant, self.periodo, ajeno, user=self.owner)

    def test_agregar_linea_recalcula_totales(self):
        nomina = services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)
        services.add_payroll_line(nomina, category=PayrollLine.Category.EARNING, concept=PayrollLine.Concept.OVERTIME, amount=Decimal("500"))
        nomina.refresh_from_db()
        self.assertEqual(nomina.gross_total, Decimal("50500"))

    def test_no_se_puede_agregar_linea_a_periodo_aprobado(self):
        nomina = services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)
        services.approve_period(self.periodo, self.owner)
        with self.assertRaises(services.InvalidPayrollOperation):
            services.add_payroll_line(nomina, category=PayrollLine.Category.EARNING, concept=PayrollLine.Concept.BONUS, amount=Decimal("100"))


class PayrollApprovalServiceTests(PayrollTestCase):
    def setUp(self):
        super().setUp()
        self.periodo = services.create_payroll_period(
            self.tenant, start_date=date(2025, 1, 1), end_date=date(2025, 1, 15),
            pay_date=date(2025, 1, 16), user=self.owner,
        )

    def test_no_se_puede_aprobar_sin_nominas_calculadas(self):
        with self.assertRaises(services.InvalidPayrollOperation):
            services.approve_period(self.periodo, self.owner)

    def test_propietario_aprueba_periodo(self):
        services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)
        periodo = services.approve_period(self.periodo, self.owner)
        self.assertEqual(periodo.status, PayrollPeriod.Status.APPROVED)

    def test_staff_sin_permiso_no_puede_aprobar(self):
        services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)
        with self.assertRaises(services.InvalidPayrollOperation):
            services.approve_period(self.periodo, self.staff)

    def test_cancelar_periodo_en_borrador(self):
        periodo = services.cancel_period(self.periodo, self.owner)
        self.assertEqual(periodo.status, PayrollPeriod.Status.CANCELED)

    def test_no_se_puede_cancelar_periodo_aprobado(self):
        services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)
        services.approve_period(self.periodo, self.owner)
        with self.assertRaises(services.InvalidPayrollOperation):
            services.cancel_period(self.periodo, self.owner)

    def test_cerrar_periodo_con_nominas_pendientes_es_rechazado(self):
        services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)
        services.approve_period(self.periodo, self.owner)
        with self.assertRaises(services.InvalidPayrollOperation):
            services.close_period(self.periodo, self.owner)


class PayrollPaymentServiceTests(PayrollTestCase):
    def setUp(self):
        super().setUp()
        self.periodo = services.create_payroll_period(
            self.tenant, start_date=date(2025, 1, 1), end_date=date(2025, 1, 15),
            pay_date=date(2025, 1, 16), user=self.owner,
        )
        self.nomina = services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado, user=self.owner)

    def test_no_se_puede_pagar_antes_de_aprobar_el_periodo(self):
        with self.assertRaises(services.InvalidPayrollOperation):
            services.record_payroll_payment(self.tenant, self.nomina, method="transfer", amount=Decimal("50000"), user=self.owner)

    def test_pago_completo_deja_paid_y_cierra_disponibilidad(self):
        services.approve_period(self.periodo, self.owner)
        services.record_payroll_payment(self.tenant, self.nomina, method="transfer", amount=Decimal("50000"), user=self.owner)
        self.nomina.refresh_from_db()
        self.assertEqual(self.nomina.status, Payroll.Status.PAID)

    def test_periodo_pasa_a_paid_cuando_todas_las_nominas_estan_pagadas(self):
        services.approve_period(self.periodo, self.owner)
        services.record_payroll_payment(self.tenant, self.nomina, method="transfer", amount=Decimal("50000"), user=self.owner)
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.Status.PAID)

    def test_periodo_con_dos_empleados_no_pasa_a_paid_hasta_pagar_ambos(self):
        nomina_2 = services.calculate_payroll_for_employee(self.tenant, self.periodo, self.empleado_2, user=self.owner)
        services.approve_period(self.periodo, self.owner)
        services.record_payroll_payment(self.tenant, self.nomina, method="transfer", amount=Decimal("50000"), user=self.owner)
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.Status.APPROVED)
        services.record_payroll_payment(self.tenant, nomina_2, method="transfer", amount=Decimal("40000"), user=self.owner)
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, PayrollPeriod.Status.PAID)

    def test_cerrar_periodo_tras_pagar_todo(self):
        services.approve_period(self.periodo, self.owner)
        services.record_payroll_payment(self.tenant, self.nomina, method="transfer", amount=Decimal("50000"), user=self.owner)
        periodo = services.close_period(self.periodo, self.owner)
        self.assertEqual(periodo.status, PayrollPeriod.Status.CLOSED)

    def test_no_se_puede_sobre_pagar(self):
        services.approve_period(self.periodo, self.owner)
        with self.assertRaises(services.InvalidPayrollOperation):
            services.record_payroll_payment(self.tenant, self.nomina, method="transfer", amount=Decimal("50001"), user=self.owner)

    def test_pago_en_moneda_distinta_es_rechazado(self):
        services.approve_period(self.periodo, self.owner)
        with self.assertRaises(services.InvalidPayrollOperation):
            services.record_payroll_payment(self.tenant, self.nomina, method="transfer", amount=Decimal("100"), user=self.owner, currency="DOP")

    def test_pago_en_efectivo_genera_cash_movement(self):
        services.approve_period(self.periodo, self.owner)
        sesion = self.abrir_caja(self.owner)
        pago = services.record_payroll_payment(
            self.tenant, self.nomina, method="cash", amount=Decimal("50000"), user=self.owner, cash_session=sesion,
        )
        movimiento = CashMovement.all_objects.get(tenant=self.tenant, reference_type="payroll_payment", reference_id=pago.pk)
        self.assertEqual(movimiento.movement_type, CashMovement.MovementType.PAYROLL_PAYMENT_CASH)

    def test_anular_pago_revierte_estado(self):
        services.approve_period(self.periodo, self.owner)
        pago = services.record_payroll_payment(self.tenant, self.nomina, method="transfer", amount=Decimal("50000"), user=self.owner)
        self.nomina.refresh_from_db()
        self.assertEqual(self.nomina.status, Payroll.Status.PAID)
        services.void_payroll_payment(pago, self.owner)
        self.nomina.refresh_from_db()
        self.assertEqual(self.nomina.status, Payroll.Status.PENDING)

    def test_idempotencia_por_clave(self):
        services.approve_period(self.periodo, self.owner)
        p1 = services.record_payroll_payment(
            self.tenant, self.nomina, method="transfer", amount=Decimal("100"), user=self.owner, idempotency_key="clave-x",
        )
        p2 = services.record_payroll_payment(
            self.tenant, self.nomina, method="transfer", amount=Decimal("100"), user=self.owner, idempotency_key="clave-x",
        )
        self.assertEqual(p1.pk, p2.pk)
