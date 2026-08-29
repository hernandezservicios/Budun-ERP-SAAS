"""
Performance del Libro Diario (FASE 19). N+1 real encontrado y
corregido: `get_general_journal` llamaba a `get_journal_entry_lines`
una vez POR ASIENTO dentro del `for` — medido con un dataset de 300
asientos vía `perf_baseline.py` (scratchpad de la sesión, no
commiteado): 301 queries y 783ms, contra 2 queries y 189ms tras la
corrección (`Prefetch` explícito, ver `docs/performance.md`). Este
test fija el comportamiento correcto como regresión, mismo patrón que
`apps/inventory/tests/test_performance.py`: el conteo de queries no
debe crecer con más asientos.
"""

from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounting import services
from apps.accounting.models import JournalEntry, JournalEntryLine

from ._helpers import AccountingTestCase


class GeneralJournalPerformanceTests(AccountingTestCase):
    def _crear_asientos(self, cantidad):
        # Creación directa (no vía `create_journal_entry`/
        # `post_journal_entry`): esto mide el camino de LECTURA
        # (`get_general_journal`), no la escritura — mismo criterio ya
        # usado en otros `test_performance.py` del proyecto.
        inicio = getattr(self, "_contador_asiento", 0)
        for i in range(inicio, inicio + cantidad):
            asiento = JournalEntry.all_objects.create(
                tenant=self.tenant, number=f"AST-PERF-{i:05d}", period=self.periodo,
                entry_date=self.periodo.start_date, description=f"Asiento perf {i}",
                status=JournalEntry.Status.POSTED, source_type="perf_test", source_event_key=f"perf-{i}",
            )
            JournalEntryLine.all_objects.bulk_create([
                JournalEntryLine(tenant=self.tenant, journal_entry=asiento, account=self.cuenta_caja, debit=Decimal("100"), credit=Decimal("0"), line_order=1),
                JournalEntryLine(tenant=self.tenant, journal_entry=asiento, account=self.cuenta_ingresos, debit=Decimal("0"), credit=Decimal("100"), line_order=2),
            ])
        self._contador_asiento = inicio + cantidad

    def _contar_queries(self):
        with CaptureQueriesContext(connection):
            pass
        with CaptureQueriesContext(connection) as contexto:
            filas = services.get_general_journal(self.tenant)
        return len(contexto.captured_queries), filas

    def test_libro_diario_no_crece_con_mas_asientos(self):
        self._crear_asientos(5)
        queries_con_5, filas_con_5 = self._contar_queries()
        self.assertEqual(len(filas_con_5), 5)

        self._crear_asientos(45)  # 50 en total
        queries_con_50, filas_con_50 = self._contar_queries()
        self.assertEqual(len(filas_con_50), 50)

        self.assertEqual(
            queries_con_5, queries_con_50,
            "El libro diario no debería ejecutar más queries solo porque "
            "hay más asientos (indicaría N+1 — ver docs/performance.md).",
        )
        # Además del conteo constante, nunca más de 2 (una para los
        # asientos, una para el prefetch de líneas) — fija el número
        # exacto, no solo "constante en algún valor".
        self.assertLessEqual(queries_con_50, 2)

    def test_libro_diario_trae_las_lineas_correctas_por_asiento(self):
        self._crear_asientos(3)
        filas = services.get_general_journal(self.tenant)
        for fila in filas:
            self.assertEqual(len(fila["lines"]), 2)
            self.assertEqual({linea.account_id for linea in fila["lines"]}, {self.cuenta_caja.pk, self.cuenta_ingresos.pk})
