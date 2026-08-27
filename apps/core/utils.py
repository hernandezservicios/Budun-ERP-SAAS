"""Utilidades compartidas, sin dependencias de ningún dominio de
negocio — solo `apps.core` (la app más fundacional) puede alojar algo
que TODAS las demás apps puedan importar sin crear una dependencia
circular."""


def mask_secret(value, *, keep=4):
    """Enmascara un identificador sensible mostrando solo los últimos
    `keep` caracteres — mismo criterio ya usado en
    `InventoryUnitAdmin.identificador_enmascarado` (IMEI/número de
    serie), generalizado aquí para reutilizarse también en la
    visualización de claves de API (`apps.api`). Nunca se muestra el
    valor completo una vez enmascarado."""
    if not value:
        return ""
    if len(value) <= keep:
        return value
    return f"···{value[-keep:]}"


def get_client_ip(request):
    """IP real del cliente — respeta `X-Forwarded-For` (primer valor,
    el más cercano al cliente) cuando el proyecto corra detrás de un
    proxy/balanceador en producción, con `REMOTE_ADDR` como respaldo en
    desarrollo directo.

    Generalizado en FASE 18 (Security Hardening) a partir de la
    implementación idéntica que ya vivía únicamente en
    `apps.audit.services` — ahora es la única fuente de verdad,
    reutilizada también por `apps.accounts.rate_limit` para el
    throttling de login/recuperación de contraseña."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# Caracteres con los que Excel/Google Sheets/LibreOffice interpretan el
# contenido de una celda como el INICIO de una fórmula en vez de texto
# literal — lista estándar de la mitigación de CSV/XLSX Formula
# Injection (OWASP). Tab y retorno de carro se incluyen porque también
# permiten inyectar una fórmula en la celda SIGUIENTE al pegarse en
# algunas versiones de Excel.
_DISPARADORES_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell_value(value):
    """Neutraliza CSV/XLSX Formula Injection (FASE 18 — Security
    Hardening, hallazgo ya documentado en `docs/security.md` como
    "Pendiente en FASE 18"): un campo de texto libre controlado por el
    usuario (nombre de cliente/proveedor/producto, motivo, nota) que
    empiece con `=`/`+`/`-`/`@` se interpretaría como fórmula al abrir
    la exportación en Excel/Sheets — ej. un cliente registrado con el
    nombre `=cmd|'/c calc'!A1` ejecutaría código en la máquina de quien
    abre el reporte. Se antepone un apóstrofe: Excel/Sheets lo muestran
    entonces como texto literal, nunca lo evalúan.

    Deliberadamente solo actúa sobre `str`: un número/`Decimal`/fecha
    real nunca se interpreta como fórmula (por ejemplo, un monto
    negativo legítimo como `Decimal('-50.00')` no debe convertirse en
    texto), así que se devuelve sin tocar. Reutilizado tanto por la
    exportación CSV (`apps.reports.views._csv_response`) como XLSX
    (`apps.reports.exports.xlsx_response`) — una única fuente de
    verdad, nunca una sanitización distinta por formato."""
    if isinstance(value, str) and value.startswith(_DISPARADORES_FORMULA):
        return f"'{value}"
    return value
