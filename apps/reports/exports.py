"""
Exportación PDF/XLSX de reportes tabulares — ampliación de cierre de
FASE 14 (ver docs/reports.md). `reportlab` (PDF) y `openpyxl` (XLSX)
son ambas puro-Python, sin dependencias nativas, aprobadas
explícitamente por el usuario para esta ampliación (a diferencia de
WeasyPrint/ReportLab con GTK, rechazado en FASE 10/14 por depender de
librerías del sistema operativo).

Estas funciones son deliberadamente genéricas (header + rows, igual
que `views._csv_response`) — nunca un exportador distinto por reporte.
No incluyen logo de tenant: `Tenant` no tiene un campo de logo/branding
hoy (ninguna función de "subir logo" existe en el proyecto), así que
el encabezado del PDF solo muestra el nombre del tenant como texto —
documentado, no inventado."""

from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet


def pdf_response(*, filename, title, tenant, generated_by, header, rows, filters_label=""):
    """Genera un PDF tabular real: título, tenant, filtros aplicados,
    usuario y fecha de generación, encabezado de columnas, filas y
    paginación automática (a cargo de `SimpleDocTemplate`). Orientación
    horizontal cuando hay más de 5 columnas (evita truncar texto)."""
    buffer = BytesIO()
    pagesize = landscape(A4) if len(header) > 5 else A4
    documento = SimpleDocTemplate(buffer, pagesize=pagesize, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    estilos = getSampleStyleSheet()

    elementos = [
        Paragraph(title, estilos["Title"]),
        Paragraph(f"{tenant.name} — generado por {generated_by} el {timezone.localtime().strftime('%Y-%m-%d %H:%M')}", estilos["Normal"]),
    ]
    if filters_label:
        elementos.append(Paragraph(f"Filtros: {filters_label}", estilos["Normal"]))
    elementos.append(Spacer(1, 0.5 * cm))

    datos_tabla = [list(header)] + [[str(valor) for valor in fila] for fila in rows]
    tabla = Table(datos_tabla, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    elementos.append(tabla)
    documento.build(elementos)

    respuesta = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="{filename}"'
    return respuesta


def xlsx_response(*, filename, sheet_title, header, rows):
    """Genera un XLSX real de una sola hoja: encabezados en negrita,
    una fila por registro. Sin formato de moneda/fecha específico por
    columna (columnas heterogéneas entre reportes) — texto/número
    simple, suficiente para abrir y filtrar en Excel/LibreOffice."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = sheet_title[:31]  # límite de Excel para nombres de hoja

    hoja.append(list(header))
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for fila in rows:
        hoja.append(list(fila))

    for columna in hoja.columns:
        ancho = max((len(str(c.value)) for c in columna if c.value is not None), default=10)
        hoja.column_dimensions[columna[0].column_letter].width = min(ancho + 2, 40)

    buffer = BytesIO()
    libro.save(buffer)
    respuesta = HttpResponse(buffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    respuesta["Content-Disposition"] = f'attachment; filename="{filename}"'
    return respuesta
