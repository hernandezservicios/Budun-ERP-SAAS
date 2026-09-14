"""
Geometría de gráficas SVG para el panel SaaS (FASE — Rediseño Visual
Maestro) — matemática de PRESENTACIÓN pura (coordenadas de puntos,
longitudes de arco), nunca una fuente de datos nueva: los totales/
conteos reales siempre vienen ya calculados de
`apps.billing.services.reports`. Sin ninguna librería de gráficas
(Chart.js/D3/etc.) — CLAUDE.md exige no introducir dependencias
nuevas sin necesidad real, y estas dos gráficas (línea, dona) son lo
bastante simples para dibujarse a mano con SVG inline."""

import math

from django import template

from .ui_extras import estado_badge

register = template.Library()


@register.simple_tag
def linea_chart_datos(filas, ancho=600, alto=160, relleno_x=20, relleno_y=18):
    """`filas`: lista de dicts con clave `total` (Decimal/número) en
    orden cronológico — devuelve coordenadas SVG listas para dibujar
    (`polyline`, `area`, `puntos`), sin decidir NINGÚN valor de datos,
    solo su posición geométrica."""
    valores = [float(fila["total"]) for fila in filas]
    if not valores:
        return {"ancho": ancho, "alto": alto, "polyline": "", "area": "", "puntos": [], "base_y": alto - relleno_y}

    maximo, minimo = max(valores), min(valores)
    rango = (maximo - minimo) or 1
    n = len(valores)
    paso_x = (ancho - 2 * relleno_x) / (n - 1) if n > 1 else 0
    base_y = alto - relleno_y

    puntos = []
    for indice, valor in enumerate(valores):
        x = relleno_x + indice * paso_x
        y_normalizado = (valor - minimo) / rango
        y = base_y - y_normalizado * (alto - 2 * relleno_y)
        puntos.append({"x": round(x, 1), "y": round(y, 1)})

    polyline = " ".join(f"{p['x']},{p['y']}" for p in puntos)
    area = f"{polyline} {puntos[-1]['x']},{base_y} {puntos[0]['x']},{base_y}"
    return {"ancho": ancho, "alto": alto, "polyline": polyline, "area": area, "puntos": puntos, "base_y": base_y}


@register.simple_tag
def dona_chart_segmentos(filas, radio=44):
    """`filas`: lista de `{"codigo", "etiqueta", "conteo"}` reales (de
    `get_subscription_status_breakdown`). Devuelve un segmento por fila
    con conteo > 0, con el color semántico correspondiente (mismo mapa
    que `estado_badge`) y la geometría real del arco — nunca inventa
    una categoría ni omite una con datos reales."""
    circunferencia = 2 * math.pi * radio
    total = sum(fila["conteo"] for fila in filas)
    segmentos = []
    offset_acumulado = 0.0
    for fila in filas:
        conteo = fila["conteo"]
        if not conteo:
            continue
        variante = estado_badge(fila["codigo"])
        porcentaje = round(conteo / total * 100) if total else 0
        longitud = circunferencia * conteo / total if total else 0
        segmentos.append({
            "codigo": fila["codigo"], "etiqueta": fila["etiqueta"], "variante": variante,
            "conteo": conteo, "porcentaje": porcentaje,
            "dasharray": f"{longitud:.2f} {circunferencia:.2f}", "dashoffset": round(-offset_acumulado, 2),
        })
        offset_acumulado += longitud
    return {"radio": radio, "circunferencia": circunferencia, "total": total, "segmentos": segmentos}
