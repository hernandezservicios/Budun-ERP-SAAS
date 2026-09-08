"""FASE 20, sección 6 — restore verification real, sobre PostgreSQL de
verdad. `count_critical_tables` cuenta con SQL directo (`psycopg`)
sobre la tabla física de cada modelo — nunca a través del manager de
Django — así que ve exactamente las mismas filas que vería un
`pg_dump`/`pg_restore` real, sin depender de ningún `ContextVar` de
tenant activo (mismo bug-class evitado repetidas veces en el proyecto,
ver `KNOWN_ISSUES.md` #90/#95/#97/#108/#118/#120 — aquí evitado por
construcción, ni siquiera hace falta recordar usar `all_objects`).
`TransactionTestCase`: los datos de `setUp()` deben estar COMMITTED
para que la conexión psycopg externa e independiente los vea (un
`TestCase` normal los dejaría en una transacción sin confirmar,
invisible fuera de la conexión ORM del propio test)."""

from django.db import connection
from django.test import TransactionTestCase

from apps.backups.services import verification as verification_service
from apps.inventory.models import Category, Product
from apps.tenants.models import Tenant


class CountCriticalTablesTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.db_settings = dict(connection.settings_dict)
        self.tenant = Tenant.objects.create(name="Verification Tenant", slug="verification-tenant")
        category = Category.objects.create(tenant=self.tenant, name="Categoría de prueba")
        Product.objects.create(
            tenant=self.tenant, sku="VER-1", name="Producto de prueba",
            category=category, sale_price="10.00",
        )

    def test_cuenta_filas_reales_con_sql_directo(self):
        counts = verification_service.count_critical_tables(self.db_settings)
        self.assertGreaterEqual(counts["tenants"], 1)
        self.assertGreaterEqual(counts["productos"], 1)
        self.assertGreaterEqual(counts["categorías"], 1)
        self.assertIn("__migrations_applied__", counts)
        self.assertGreater(counts["__migrations_applied__"], 0)

    def test_credenciales_invalidas_lanza_en_vez_de_devolver_conteos_falsos(self):
        bad_settings = dict(self.db_settings)
        bad_settings["PASSWORD"] = "credencial-incorrecta"
        with self.assertRaises(Exception):
            verification_service.count_critical_tables(bad_settings)


class VerifyRestoredDatabaseTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.db_settings = dict(connection.settings_dict)
        Tenant.objects.create(name="Verify Report Tenant", slug="verify-report-tenant")

    def test_conteos_coincidentes_reportan_ok(self):
        expected = verification_service.count_critical_tables(self.db_settings)
        report = verification_service.verify_restored_database(self.db_settings, expected_counts=expected)
        self.assertTrue(report.ok)
        self.assertEqual(report.mismatches, {})

    def test_discrepancia_se_reporta_nunca_se_oculta(self):
        expected = verification_service.count_critical_tables(self.db_settings)
        expected_con_error = dict(expected)
        expected_con_error["tenants"] = expected["tenants"] + 999

        report = verification_service.verify_restored_database(
            self.db_settings, expected_counts=expected_con_error
        )
        self.assertFalse(report.ok)
        self.assertIn("tenants", report.mismatches)
        self.assertEqual(report.mismatches["tenants"]["esperado"], expected["tenants"] + 999)

    def test_conexion_invalida_se_reporta_como_error_no_como_excepcion_sin_atrapar(self):
        bad_settings = dict(self.db_settings)
        bad_settings["NAME"] = "esta_base_de_datos_no_existe_en_absoluto"

        report = verification_service.verify_restored_database(bad_settings)
        self.assertFalse(report.connection_ok)
        self.assertFalse(report.ok)
        self.assertTrue(report.error)
