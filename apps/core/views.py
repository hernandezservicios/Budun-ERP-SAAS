from django.shortcuts import render

from .pricing import PLANS


def home(request):
    """Landing pública del producto (FASE 6 — Landing + Pricing).

    Reemplaza la página de verificación técnica de FASE 1 ("Fundación del
    proyecto lista"), que ya cumplió su propósito. La URL (`core:home`,
    `/`) y el nombre de la vista se mantienen sin cambios para no romper
    los enlaces/redirects existentes (logout, navbar, tests).
    """
    contexto = {
        "planes": PLANS,
    }
    return render(request, "core/landing.html", contexto)


def design_system(request):
    """Página de referencia interna del Design System (FASE 5).

    Muestra todos los componentes reutilizables con datos de ejemplo, para
    poder verificar consistencia visual, accesibilidad y responsive con
    evidencia real (HTML servido de verdad, no una maqueta aparte). No es
    una página de negocio ni se enlaza desde la navegación principal.
    """
    return render(request, "core/design_system.html")


def design_system(request):
    """Página de referencia interna del Design System (FASE 5).

    Muestra todos los componentes reutilizables con datos de ejemplo, para
    poder verificar consistencia visual, accesibilidad y responsive con
    evidencia real (HTML servido de verdad, no una maqueta aparte). No es
    una página de negocio ni se enlaza desde la navegación principal.
    """
    return render(request, "core/design_system.html")
