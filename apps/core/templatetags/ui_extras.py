"""
Template tags del Design System (FASE 5).
"""

from django import template

register = template.Library()

_MAPA_TOAST = {
    "success": "exito",
    "error": "peligro",
    "warning": "advertencia",
    "info": "info",
    "debug": "info",
}


@register.filter
def clase_toast(tags):
    """Convierte las etiquetas de `django.contrib.messages` (en inglés)
    a la variante en español del componente Toast (ver
    static/css/design-system.css)."""
    primera_etiqueta = (tags or "info").split(" ")[0]
    return _MAPA_TOAST.get(primera_etiqueta, "info")
