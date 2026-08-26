"""
UI de Auditoría (FASE 15). Vista de búsqueda federada
(`services.search_audit_events`) + detalle con antes/después. Nunca
permite editar ni borrar un evento — de solo lectura por completo,
mismo principio que `_ReadOnlyAdmin`."""

import csv
import math

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

from apps.permissions.services import require_permission
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import AuditSearchForm

PAGE_SIZE = 50


def _filtros_desde_form(form):
    if not form.is_valid():
        return {}
    datos = form.cleaned_data
    return {
        "source": datos.get("source") or None,
        "domain": datos.get("domain") or None,
        "action": datos.get("action") or None,
        "user": datos.get("user"),
        "date_from": datos.get("date_from"),
        "date_to": datos.get("date_to"),
        "ip_address": datos.get("ip_address") or None,
        "q": datos.get("q") or "",
    }


class AuditSearchView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_permission(request, "audit.view")
        form = AuditSearchForm(request.GET or None, tenant=request.tenant)
        filtros = _filtros_desde_form(form)
        try:
            pagina = max(int(request.GET.get("page", 1)), 1)
        except ValueError:
            pagina = 1

        resultado = services.search_audit_events(
            request.tenant, limit=PAGE_SIZE, offset=(pagina - 1) * PAGE_SIZE, **filtros,
        )
        total_paginas = max(math.ceil(resultado["total"] / PAGE_SIZE), 1)
        contexto = {
            "form": form, "eventos": resultado["rows"], "total": resultado["total"],
            "pagina": pagina, "total_paginas": total_paginas,
            "puede_exportar": _tiene_permiso_exportar(request),
        }
        return render(request, "audit/search.html", contexto)


def _tiene_permiso_exportar(request):
    from apps.permissions.services import has_permission

    return has_permission(request.tenant, request.user, "audit.export")


class AuditDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, source, row_id):
        require_permission(request, "audit.view")
        evento = services.get_event_detail(request.tenant, source=source, row_id=row_id)
        if evento is None:
            raise Http404("Evento de auditoría no encontrado.")
        return render(request, "audit/detail.html", {"evento": evento, "source": source})


class AuditExportView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        require_permission(request, "audit.export")
        form = AuditSearchForm(request.GET or None, tenant=request.tenant)
        filtros = _filtros_desde_form(form)
        resultado = services.search_audit_events(request.tenant, limit=10000, offset=0, **filtros)

        respuesta = HttpResponse(content_type="text/csv")
        respuesta["Content-Disposition"] = 'attachment; filename="auditoria.csv"'
        escritor = csv.writer(respuesta)
        escritor.writerow(["Fecha", "Origen", "Dominio", "Acción", "Tipo de objeto", "Id de objeto", "Usuario", "Resumen"])
        for fila in resultado["rows"]:
            escritor.writerow([
                fila["created_at"], fila["source"], fila["domain"], fila["action"],
                fila["object_type"], fila["object_id"], fila["user_id"] or "—", fila["summary"] or "",
            ])

        from .models import AuditLog

        services.log_event(
            request.tenant, user=request.user, action=AuditLog.Action.EXPORT_PERFORMED, domain="audit",
            object_type="audit_search", ip_address=services.get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""), metadata={"filtros": {k: str(v) for k, v in filtros.items() if v}},
        )
        return respuesta
