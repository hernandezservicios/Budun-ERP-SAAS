"""
Sistema de iconos ligero de la plataforma SaaS (FASE — Rediseño Visual
Maestro). SVG inline (trazo 2px, estilo "outline" consistente, 24x24),
sin ninguna librería/fuente de iconos externa — mismo criterio del
proyecto de "sin dependencias nuevas sin necesidad real" (CLAUDE.md).
Reemplaza el uso de emoji como iconografía de interfaz en el shell/
componentes SaaS (el emoji seguía siendo válido como contenido textual
normal en otras partes del proyecto — aquí es específicamente sobre
ICONOS de interfaz).

Uso: `{% icono "home" %}` o `{% icono "home" clase="sidebar__icono" %}`.
Cada icono es un `<svg>` `aria-hidden="true"` (decorativo por defecto,
el texto visible junto al icono ya transmite el significado) — si un
icono se usa SOLO, sin texto visible, pasar `titulo="..."` para que se
renderice con `role="img"` y `<title>` accesible en su lugar.
"""

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Cada valor es el contenido interior del <svg> (los <path>/<circle>/etc,
# sin el elemento <svg> en sí — eso lo agrega `icono()` una sola vez,
# con los atributos comunes). Trazos simples de 24x24, estilo outline
# genérico (equivalente en espíritu a Feather/Lucide, redibujados a
# mano para este proyecto — nunca un archivo de una librería externa).
_ICONOS = {
    "home": '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/><path d="M9.5 20v-6h5v6"/>',
    "usuarios": '<circle cx="9" cy="8" r="3.25"/><path d="M3.5 20c0-3.5 2.5-6 5.5-6s5.5 2.5 5.5 6"/><path d="M16 9a2.75 2.75 0 1 0 0-5.5"/><path d="M15 14.2c2.5.4 4.5 2.6 4.5 5.8"/>',
    "edificio": '<rect x="5" y="3.5" width="10" height="17" rx="1"/><path d="M15 9h4.5v11.5H15"/><path d="M8.5 7.5h.01M11.5 7.5h.01M8.5 11h.01M11.5 11h.01M8.5 14.5h.01M11.5 14.5h.01"/>',
    "carrito": '<circle cx="10" cy="20" r="1.4"/><circle cx="17.5" cy="20" r="1.4"/><path d="M3 4h2.2l1.9 11h11.4l1.7-7.5H6.4"/>',
    "repetir": '<path d="M4 11a8 8 0 0 1 13.6-5.7L20 7.5"/><path d="M20 4v3.5h-3.5"/><path d="M20 13a8 8 0 0 1-13.6 5.7L4 16.5"/><path d="M4 20v-3.5h3.5"/>',
    "paquete": '<path d="M12 3 4 7v10l8 4 8-4V7Z"/><path d="M4 7l8 4 8-4"/><path d="M12 11v10"/>',
    "documento": '<path d="M7 3h7l4 4v14H7Z"/><path d="M14 3v4h4"/><path d="M9.5 12.5h5M9.5 15.5h5M9.5 9.5h2"/>',
    "tarjeta": '<rect x="3" y="6" width="18" height="13" rx="1.5"/><path d="M3 10.5h18"/><path d="M6.5 15h4"/>',
    "intercambio": '<path d="M4 8h13l-3-3"/><path d="M20 16H7l3 3"/>',
    "nota-mas": '<path d="M7 3h7l4 4v14H7Z"/><path d="M14 3v4h4"/><path d="M12 10.5v5M9.5 13h5"/>',
    "reembolso": '<path d="M4 12a8 8 0 1 0 2.5-5.8"/><path d="M3 4v4.5h4.5"/><path d="M12 8.5v7M9.5 10.2h3.3a1.65 1.65 0 0 1 0 3.3H9.8a1.65 1.65 0 0 0 0 3.3H13"/>',
    "barras": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "banco": '<path d="M3 10h18M4 10v9M8 10v9M12 10v9M16 10v9M20 10v9M3 20h18M12 3 3 8h18Z"/>',
    "paypal": '<path d="M8 19 10 5h5.2c2.4 0 4 1.5 3.6 3.8-.5 3-2.9 4.6-5.7 4.6h-2.4l-.8 5.6Z"/><path d="M6.5 19 8.3 7h5"/>',
    "engranaje": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.2M12 18.8V21M21 12h-2.2M5.2 12H3M18.1 5.9l-1.6 1.6M7.5 16.5l-1.6 1.6M18.1 18.1l-1.6-1.6M7.5 7.5 5.9 5.9"/>',
    "buscar": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.3-4.3"/>',
    "chevron-abajo": '<path d="m6 9 6 6 6-6"/>',
    "chevron-derecha": '<path d="m9 6 6 6-6 6"/>',
    "menu": '<path d="M4 6.5h16M4 12h16M4 17.5h16"/>',
    "cerrar": '<path d="M6 6l12 12M18 6 6 18"/>',
    "flecha-izquierda": '<path d="M19 12H5"/><path d="m11 18-6-6 6-6"/>',
    "flecha-arriba": '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
    "flecha-abajo": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    "reloj": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "pausa": '<rect x="7" y="5.5" width="3.2" height="13" rx="0.8"/><rect x="13.8" y="5.5" width="3.2" height="13" rx="0.8"/>',
    "alerta-triangulo": '<path d="M12 4 2.5 20h19Z"/><path d="M12 10v4.2"/><circle cx="12" cy="17" r="0.15" fill="currentColor" stroke="none"/>',
    "usuario-mas": '<circle cx="9" cy="8" r="3.25"/><path d="M3.5 20c0-3.5 2.5-6 5.5-6s5.5 2.5 5.5 6"/><path d="M18 8v4.5M20.25 10.25h-4.5"/>',
    "equis-circulo": '<circle cx="12" cy="12" r="8.5"/><path d="m9.3 9.3 5.4 5.4M14.7 9.3l-5.4 5.4"/>',
    "check-circulo": '<circle cx="12" cy="12" r="8.5"/><path d="m8 12.3 2.6 2.6 5.4-6"/>',
    "recibo": '<path d="M6 3h12v18l-2.5-1.6L13 21l-1.5-1.6L10 21l-2.5-1.6L6 21Z"/><path d="M9 8h6M9 11.5h6M9 15h4"/>',
    "actividad": '<path d="M3 12h4l2-7 4 14 2-7h6"/>',
    "grafico-torta": '<path d="M12 3v9l7.5 4.3"/><circle cx="12" cy="12" r="8.5"/>',
    # FASE E — Master Shell (Design System V1 Hybrid): el sidebar SaaS
    # ahora enlaza "Mi perfil"/"Cambiar contraseña" también desde la
    # navegación (antes solo vivían en el dropdown del topbar). Ningún
    # icono existente encajaba (usuarios/usuario-mas son de 2 personas,
    # pensados para "Clientes") — se agregan estos 2, mismo estilo
    # outline 24x24 del resto del catálogo.
    "perfil": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="10" r="3"/><path d="M6.7 18.5a5.7 5.7 0 0 1 10.6 0"/>',
    "candado": '<rect x="5" y="11" width="14" height="9" rx="1.5"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
}


@register.simple_tag
def icono(nombre, clase="", titulo=""):
    """Renderiza un icono SVG inline. `clase` se agrega tal cual al
    `<svg>` (dimensiones/color se resuelven casi siempre por CSS,
    heredando `currentColor`). Sin `titulo`, el icono es decorativo
    (`aria-hidden="true"`) — usar `titulo` únicamente cuando el icono
    es el ÚNICO contenido de un control (ej. un botón de solo-ícono)."""
    contenido = _ICONOS.get(nombre)
    if contenido is None:
        # Nunca revienta el render por un nombre no registrado — un
        # icono ausente es más fácil de notar visualmente (hueco) que
        # un 500 en producción.
        return mark_safe("")
    atributos_clase = f' class="icono-svg {clase}"' if clase else ' class="icono-svg"'
    if titulo:
        interior_titulo = f"<title>{titulo}</title>"
        atributos_a11y = ' role="img"'
    else:
        interior_titulo = ""
        atributos_a11y = ' aria-hidden="true"'
    svg = (
        f'<svg{atributos_clase}{atributos_a11y} viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f"{interior_titulo}{contenido}</svg>"
    )
    return mark_safe(svg)
