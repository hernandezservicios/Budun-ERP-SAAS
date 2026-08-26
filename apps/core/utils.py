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
