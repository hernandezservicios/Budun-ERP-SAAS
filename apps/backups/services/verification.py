"""Restore verification real (FASE 20, sección 6).

"No declarar VERIFIED solo porque `pg_restore` terminó con exit code
0" — esta verificación cuenta filas REALES en tablas representativas
de cada dominio del proyecto (tenants, productos, inventario por
cantidad/serializado, ventas, pagos, compras, gastos, RRHH, nómina,
contabilidad, Billing, auditoría) contra la base RECIÉN RESTAURADA y
las compara con el snapshot de conteos tomado al momento del backup
(`counts_at_backup` en el `.meta.json`).

Cuenta filas con SQL directo (`psycopg`, mismo mecanismo ya usado en
`services.database` para las operaciones administrativas) sobre la
TABLA física de cada modelo (`Model._meta.db_table`) — nunca a través
del ORM/manager de Django. Esto evita por construcción el bug-class ya
documentado repetidas veces en `KNOWN_ISSUES.md` (#90/#95/#97/#108/
#118/#120): un `SELECT COUNT(*)` sobre la tabla física cuenta TODAS
las filas sin importar ningún `ContextVar` de tenant activo — a
diferencia de `Model.objects` (el manager tenant-scoped por defecto),
que devolvería silenciosamente cero fuera de una request HTTP real.
También evita depender de la maquinaria de múltiples bases de datos
del test runner de Django (que exige declarar cada alias dinámico por
adelantado) — la base a verificar puede ser CUALQUIERA (la activa o
una aislada de restore, incluso corriendo en un proceso que no es
`manage.py test`), conectada con sus propias credenciales."""

from __future__ import annotations

import dataclasses

import psycopg
from django.apps import apps as django_apps
from psycopg import sql

# (app_label, nombre de modelo, etiqueta legible) — un modelo
# representativo por cada dominio mencionado explícitamente en la
# sección 6 de la especificación de fase.
CRITICAL_MODELS: tuple[tuple[str, str, str], ...] = (
    ("tenants", "Tenant", "tenants"),
    ("tenants", "Membership", "usuarios/membresías"),
    ("inventory", "Category", "categorías"),
    ("inventory", "Product", "productos"),
    ("inventory", "StockMovement", "movimientos de stock"),
    ("inventory", "InventoryUnit", "unidades serializadas"),
    ("sales", "Sale", "ventas"),
    ("sales", "Payment", "pagos"),
    ("purchases", "PurchaseOrder", "compras"),
    ("expenses", "Expense", "gastos"),
    ("hr", "Employee", "RRHH (empleados)"),
    ("payroll", "Payroll", "nómina"),
    ("accounting", "JournalEntry", "contabilidad (asientos)"),
    ("billing", "Subscription", "Billing (suscripciones)"),
    ("audit", "AuditLog", "auditoría"),
)


@dataclasses.dataclass
class VerificationReport:
    connection_ok: bool
    migrations_applied: int
    counts: dict
    expected_counts: dict | None
    mismatches: dict
    ok: bool
    error: str = ""


def _conninfo(db_settings: dict) -> str:
    return psycopg.conninfo.make_conninfo(
        dbname=db_settings["NAME"],
        user=db_settings["USER"],
        password=db_settings.get("PASSWORD") or "",
        host=db_settings.get("HOST") or "127.0.0.1",
        port=str(db_settings.get("PORT") or "5432"),
    )


def count_critical_tables(db_settings: dict) -> dict:
    """Cuenta filas en `CRITICAL_MODELS` (más `django_migrations`) sobre
    la base descrita por `db_settings` — puede ser la base activa o una
    base aislada de restore. Se usa tanto para tomar el snapshot al
    momento del backup como para verificar después de un restore."""
    counts: dict = {}
    with psycopg.connect(_conninfo(db_settings), autocommit=True) as conn:
        with conn.cursor() as cur:
            for app_label, model_name, label in CRITICAL_MODELS:
                model = django_apps.get_model(app_label, model_name)
                table_name = model._meta.db_table
                cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name)))
                (count,) = cur.fetchone()
                counts[label] = count

            cur.execute("SELECT COUNT(*) FROM django_migrations")
            (migrations_count,) = cur.fetchone()
            counts["__migrations_applied__"] = migrations_count

    return counts


def verify_restored_database(db_settings: dict, *, expected_counts: dict | None = None) -> VerificationReport:
    try:
        counts = count_critical_tables(db_settings)
    except Exception as error:  # tabla inexistente, conexión rechazada, etc.
        return VerificationReport(
            connection_ok=False,
            migrations_applied=0,
            counts={},
            expected_counts=expected_counts,
            mismatches={},
            ok=False,
            error=str(error)[:500],
        )

    migrations_applied = counts.pop("__migrations_applied__", 0)
    mismatches = {}
    if expected_counts:
        for label, expected_value in expected_counts.items():
            if label == "__migrations_applied__":
                continue
            actual_value = counts.get(label)
            if actual_value != expected_value:
                mismatches[label] = {"esperado": expected_value, "real": actual_value}

    ok = migrations_applied > 0 and not mismatches
    return VerificationReport(
        connection_ok=True,
        migrations_applied=migrations_applied,
        counts=counts,
        expected_counts=expected_counts,
        mismatches=mismatches,
        ok=ok,
    )
