from django.shortcuts import render


def home(request):
    """Página de fundación del proyecto (FASE 1).

    Confirma que el proyecto Django arranca correctamente. No es la landing
    page final del producto (eso corresponde a FASE 6 — Landing + Pricing).
    """
    contexto = {
        "fase_actual": "FASE 1 — Project Foundation",
    }
    return render(request, "core/home.html", contexto)
