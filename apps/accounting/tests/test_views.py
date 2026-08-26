from datetime import date
from decimal import Decimal

from django.urls import reverse

from apps.accounting import services
from apps.accounting.models import Account, AccountingPeriod, JournalEntry
from apps.tenants.models import Membership, Tenant

from ._helpers import AccountingTestCase


class AccountHttpTests(AccountingTestCase):
    def test_crear_cuenta_via_http(self):
        respuesta = self.owner_client.post(reverse("accounting:account_list"), {
            "code": "1300", "name": "Inventario", "account_type": "asset", "parent": self.cuenta_activos.pk,
            "allows_posting": "on", "description": "",
        })
        self.assertRedirects(respuesta, reverse("accounting:account_list"))
        self.assertTrue(Account.all_objects.filter(tenant=self.tenant, code="1300").exists())


class AccountingPeriodHttpTests(AccountingTestCase):
    def test_abrir_y_cerrar_periodo_via_http(self):
        respuesta = self.owner_client.post(reverse("accounting:period_list"), {
            "name": "2025-02", "start_date": date(2025, 2, 1).isoformat(), "end_date": date(2025, 2, 28).isoformat(), "notes": "",
        })
        periodo = AccountingPeriod.all_objects.get(tenant=self.tenant, name="2025-02")
        self.assertRedirects(respuesta, reverse("accounting:period_detail", args=[periodo.pk]))

        respuesta = self.owner_client.post(reverse("accounting:period_close", args=[self.periodo.pk]))
        self.assertRedirects(respuesta, reverse("accounting:period_detail", args=[self.periodo.pk]))
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, AccountingPeriod.Status.CLOSED)

        respuesta = self.owner_client.post(reverse("accounting:period_reopen", args=[self.periodo.pk]), {"reason": "ajuste"})
        self.assertRedirects(respuesta, reverse("accounting:period_detail", args=[self.periodo.pk]))
        self.periodo.refresh_from_db()
        self.assertEqual(self.periodo.status, AccountingPeriod.Status.REOPENED)


class JournalEntryHttpTests(AccountingTestCase):
    def test_crear_asiento_balanceado_via_http(self):
        respuesta = self.owner_client.post(reverse("accounting:journal_entry_create"), {
            "entry_date": date(2025, 1, 10).isoformat(), "description": "Asiento manual", "reference": "",
            "form-TOTAL_FORMS": "4", "form-INITIAL_FORMS": "0", "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-account": self.cuenta_caja.pk, "form-0-debit": "100", "form-0-credit": "0", "form-0-description": "",
            "form-0-customer": "", "form-0-supplier": "",
            "form-1-account": self.cuenta_ingresos.pk, "form-1-debit": "0", "form-1-credit": "100", "form-1-description": "",
            "form-1-customer": "", "form-1-supplier": "",
            "form-2-account": "", "form-2-debit": "", "form-2-credit": "", "form-2-description": "", "form-2-customer": "", "form-2-supplier": "",
            "form-3-account": "", "form-3-debit": "", "form-3-credit": "", "form-3-description": "", "form-3-customer": "", "form-3-supplier": "",
        })
        asiento = JournalEntry.all_objects.filter(tenant=self.tenant, description="Asiento manual").first()
        self.assertIsNotNone(asiento)
        self.assertEqual(asiento.status, JournalEntry.Status.POSTED)
        self.assertRedirects(respuesta, reverse("accounting:journal_entry_detail", args=[asiento.pk]))

    def test_reversar_asiento_via_http(self):
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[{"account": self.cuenta_caja, "debit": Decimal("100")}, {"account": self.cuenta_ingresos, "credit": Decimal("100")}],
        )
        asiento = services.post_journal_entry(asiento, self.owner)
        respuesta = self.owner_client.post(reverse("accounting:journal_entry_reverse", args=[asiento.pk]), {"reason": "error"})
        self.assertRedirects(respuesta, reverse("accounting:journal_entry_detail", args=[asiento.pk]))
        self.assertTrue(services.is_entry_reversed(asiento))


class AccountMappingHttpTests(AccountingTestCase):
    def test_configurar_mapeo_via_http(self):
        respuesta = self.owner_client.post(reverse("accounting:mapping_list"), {
            "key": "cash_and_equivalents", "account": self.cuenta_caja.pk,
        })
        self.assertRedirects(respuesta, reverse("accounting:mapping_list"))
        self.assertEqual(services.get_mapped_account(self.tenant, "cash_and_equivalents"), self.cuenta_caja)


class AccountingReportsHttpTests(AccountingTestCase):
    def setUp(self):
        super().setUp()
        asiento = services.create_journal_entry(
            self.tenant, entry_date=date(2025, 1, 10), description="x", user=self.owner,
            lines=[{"account": self.cuenta_caja, "debit": Decimal("100")}, {"account": self.cuenta_ingresos, "credit": Decimal("100")}],
        )
        services.post_journal_entry(asiento, self.owner)

    def test_balance_de_comprobacion_200(self):
        respuesta = self.owner_client.get(reverse("accounting:trial_balance"), {"periodo": self.periodo.pk})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "100")

    def test_libro_mayor_200(self):
        respuesta = self.owner_client.get(reverse("accounting:general_ledger"), {"cuenta": self.cuenta_caja.pk})
        self.assertEqual(respuesta.status_code, 200)

    def test_libro_diario_200(self):
        respuesta = self.owner_client.get(reverse("accounting:general_journal"))
        self.assertEqual(respuesta.status_code, 200)

    def test_balance_general_200(self):
        respuesta = self.owner_client.get(reverse("accounting:balance_sheet"), {"periodo": self.periodo.pk})
        self.assertEqual(respuesta.status_code, 200)

    def test_estado_resultados_200(self):
        respuesta = self.owner_client.get(reverse("accounting:income_statement"), {"periodo": self.periodo.pk})
        self.assertEqual(respuesta.status_code, 200)


class AccountingMultiTenantHttpTests(AccountingTestCase):
    def setUp(self):
        super().setUp()
        self.tenant_b = Tenant.objects.create(name="Empresa Contable B", slug="empresa-contable-b")
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.owner_b = User.objects.create_user(email="owner.contable.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.owner_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

    def test_tenant_b_no_puede_ver_periodo_de_tenant_a(self):
        client_b = self.client_class()
        client_b.login(username="owner.contable.b@example.com", password="clave-de-prueba-987")
        respuesta = client_b.get(reverse("accounting:period_detail", args=[self.periodo.pk]))
        self.assertEqual(respuesta.status_code, 404)
