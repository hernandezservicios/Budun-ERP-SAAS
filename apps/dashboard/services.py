"""
Capa de servicios del Panel (FASE 7).

Punto de extensión pensado a propósito: cada módulo de negocio futuro
(ventas, inventario, compras, gastos, clientes, reportes) reemplazará su
propia función `obtener_kpi_<modulo>` por una consulta real cuando ese
módulo exista, sin tocar la vista ni la plantilla. Mientras tanto, cada
KPI que todavía no tiene módulo real se marca explícitamente con
`estado="vacio"` — nunca se inventa un número.

Todas las consultas reciben `tenant` explícitamente y filtran por él: el
Panel NUNCA hace una consulta global y filtra "por si acaso" en la
plantilla — el filtro por tenant vive en el propio queryset (ver
CLAUDE.md — Multi-tenancy).
"""

import dataclasses
import logging

from apps.inventory.models import Product
from apps.inventory.services import get_low_stock_products
from apps.tenants.models import Membership

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class KPI:
    clave: str
    etiqueta: str
    valor: str
    estado: str = "ok"  # "ok" | "vacio"
    ayuda: str = ""


@dataclasses.dataclass
class ActividadItem:
    descripcion: str
    fecha: object


@dataclasses.dataclass
class Alerta:
    tipo: str  # "info" | "advertencia" | "peligro" | "exito"
    mensaje: str


def obtener_kpis(tenant):
    """KPIs principales del tenant activo.

    "Miembros del equipo" y, desde FASE 8, "Productos en inventario" son
    datos REALES de PostgreSQL. Ventas y Gastos siguen siendo placeholders
    honestos: esos módulos todavía no existen, así que se muestran como
    "estado vacío" en vez de simular un número.
    """
    total_miembros = Membership.objects.filter(tenant=tenant, is_active=True).count()
    # all_objects + filtro explícito por tenant (no `objects`/TenantManager):
    # ver la nota de diseño en apps/inventory/services.py.
    total_productos = Product.all_objects.filter(tenant=tenant, is_active=True).count()

    return [
        KPI(
            clave="miembros",
            etiqueta="Miembros del equipo",
            valor=str(total_miembros),
            estado="ok",
        ),
        KPI(
            clave="ventas",
            etiqueta="Ventas del mes",
            valor="—",
            estado="vacio",
            ayuda="Se activará con el módulo de Ventas.",
        ),
        KPI(
            clave="inventario",
            etiqueta="Productos en inventario",
            valor=str(total_productos),
            estado="ok" if total_productos else "vacio",
            ayuda="" if total_productos else "Crea tu primer producto en Inventario.",
        ),
        KPI(
            clave="gastos",
            etiqueta="Gastos del mes",
            valor="—",
            estado="vacio",
            ayuda="Se activará con el módulo de Gastos.",
        ),
    ]


def obtener_actividad_reciente(tenant, limite=5):
    """Actividad reciente real: altas de miembros del equipo (único
    evento que existe hoy). Un registro de auditoría completo por
    módulo es alcance de FASE 15 — Roles + Audit."""
    membresias = (
        Membership.objects.filter(tenant=tenant, is_active=True)
        .select_related("user")
        .order_by("-created_at")[:limite]
    )
    return [
        ActividadItem(
            descripcion=(
                f"{membresia.user.get_full_name() or membresia.user.email} "
                f"se unió al equipo como {membresia.get_role_display()}"
            ),
            fecha=membresia.created_at,
        )
        for membresia in membresias
    ]


def obtener_alertas(tenant):
    """Alertas derivadas de datos reales del tenant (nunca inventadas)."""
    alertas = []
    total_miembros = Membership.objects.filter(tenant=tenant, is_active=True).count()
    if total_miembros == 1:
        alertas.append(
            Alerta(
                tipo="info",
                mensaje="Todavía eres el único miembro de tu equipo en esta empresa.",
            )
        )

    total_stock_bajo = get_low_stock_products(tenant).count()
    if total_stock_bajo:
        plural = "producto" if total_stock_bajo == 1 else "productos"
        alertas.append(
            Alerta(
                tipo="advertencia",
                mensaje=f"{total_stock_bajo} {plural} con stock en o por debajo del mínimo.",
            )
        )
    return alertas


def obtener_datos_del_panel(tenant):
    """Agrega todo lo que necesita la vista en una sola función,
    aislando los errores de cada fuente (estado "error" en vez de un
    500 si una consulta falla)."""
    resultado = {
        "kpis": [],
        "actividad": [],
        "alertas": [],
        "hubo_error": False,
    }
    try:
        resultado["kpis"] = obtener_kpis(tenant)
        resultado["actividad"] = obtener_actividad_reciente(tenant)
        resultado["alertas"] = obtener_alertas(tenant)
    except Exception:
        logger.exception("Error al obtener datos del Panel para el tenant %s", tenant.id)
        resultado["hubo_error"] = True
    return resultado
