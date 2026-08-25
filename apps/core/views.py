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


def design_system(request):
    """Página de referencia interna del Design System (FASE 5).

    Muestra todos los componentes reutilizables con datos de ejemplo, para
    poder verificar consistencia visual, accesibilidad y responsive con
    evidencia real (HTML servido de verdad, no una maqueta aparte). No es
    una página de negocio ni se enlaza desde la navegación principal.
    """
    return render(request, "core/design_system.html")
