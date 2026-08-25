from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse


class LandingPageTests(TestCase):
    """FASE 6 — landing pública. Sigue usando TestCase (no SimpleTestCase)
    a propósito: verifica el ciclo de vida completo contra PostgreSQL
    real, no solo la vista (igual que en fases anteriores)."""

    def test_landing_responde_200(self):
        respuesta = self.client.get(reverse("core:home"))
        self.assertEqual(respuesta.status_code, 200)

    def test_landing_usa_template_esperado(self):
        respuesta = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(respuesta, "core/landing.html")

    def test_landing_incluye_enlace_para_saltar_al_contenido(self):
        """Accesibilidad (FASE 5): todo documento debe ofrecer un skip
        link al contenido principal."""
        respuesta = self.client.get(reverse("core:home"))
        self.assertContains(respuesta, 'href="#contenido-principal"')
        self.assertContains(respuesta, 'id="contenido-principal"')

    def test_landing_carga_los_estilos_del_design_system(self):
        respuesta = self.client.get(reverse("core:home"))
        self.assertContains(respuesta, "css/base.css")
        self.assertContains(respuesta, "css/design-system.css")

    def test_landing_incluye_seo_basico(self):
        respuesta = self.client.get(reverse("core:home"))
        self.assertContains(respuesta, '<meta name="description"')
        self.assertContains(respuesta, 'property="og:title"')
        self.assertContains(respuesta, 'property="og:description"')
        self.assertContains(respuesta, "<title>ERP SaaS")

    def test_landing_incluye_todas_las_secciones_pedidas(self):
        respuesta = self.client.get(reverse("core:home"))
        secciones = [
            "El ERP Multi-Tenant que ordena tu negocio",  # qué es / propuesta de valor
            "¿Para quién es?",
            "Problemas que resuelve",
            "Qué incluye",  # módulos
            "Cómo funciona",
            "Ventajas",
            "Seguridad",
            "Integración con agentes CRM IA",
            "Precios",
            "Preguntas frecuentes",
        ]
        for texto in secciones:
            self.assertContains(respuesta, texto)

    def test_landing_tiene_un_solo_h1(self):
        """Semántica correcta: un único <h1> por página."""
        respuesta = self.client.get(reverse("core:home"))
        self.assertEqual(respuesta.content.decode().count("<h1"), 1)

    def test_landing_cta_apunta_al_registro(self):
        respuesta = self.client.get(reverse("core:home"))
        self.assertContains(respuesta, reverse("accounts:registro"))

    def test_landing_no_implica_api_o_paypal_funcionales(self):
        """La integración API/IA se presenta como capacidad futura, no
        como funcionalidad ya disponible (todavía no se construye la API
        real ni PayPal — eso es FASE 15/16/17)."""
        respuesta = self.client.get(reverse("core:home"))
        self.assertContains(respuesta, "Próximamente")
        self.assertContains(respuesta, "Todavía no está disponible")


class PricingSectionTests(TestCase):
    """FASE 6 — precios configurables desde un único origen de datos."""

    def test_precios_vienen_de_apps_core_pricing(self):
        from apps.core.pricing import PLANS

        respuesta = self.client.get(reverse("core:home"))
        for plan in PLANS:
            self.assertContains(respuesta, plan["nombre"])
            self.assertContains(respuesta, plan["precio"])

    def test_precios_no_estan_hardcodeados_en_otras_plantillas(self):
        """Ninguna otra plantilla del proyecto debe repetir los precios:
        deben venir siempre de apps/core/pricing.py."""
        import pathlib

        from apps.core.pricing import PLANS

        raiz = pathlib.Path(__file__).resolve().parent.parent.parent
        plantillas_precio = list((raiz / "apps").glob("**/templates/**/*.html"))
        plantillas_precio += list((raiz / "templates").glob("**/*.html"))
        montos_no_triviales = [
            plan["precio"] for plan in PLANS if plan["precio"] not in {"Gratis", "Personalizado"}
        ]

        for plantilla in plantillas_precio:
            if plantilla.name == "landing.html":
                continue
            contenido = plantilla.read_text(encoding="utf-8")
            for monto in montos_no_triviales:
                self.assertNotIn(
                    monto, contenido,
                    f"Precio '{monto}' hardcodeado en {plantilla}, debería venir solo de pricing.py",
                )


class DesignSystemPageTests(TestCase):
    """FASE 5 — página de referencia interna de componentes."""

    def test_pagina_responde_200(self):
        respuesta = self.client.get(reverse("core:design_system"))
        self.assertEqual(respuesta.status_code, 200)

    def test_pagina_muestra_todos_los_componentes_pedidos(self):
        respuesta = self.client.get(reverse("core:design_system"))
        componentes_esperados = [
            "Botones", "Formularios (inputs, selects)", "Badges", "Alerts",
            "Toasts", "Cards", "Tablas", "Tabs", "Dropdown", "Modal",
            "Breadcrumbs", "Empty state", "Loading states", "Error states",
        ]
        for nombre in componentes_esperados:
            self.assertContains(respuesta, nombre)

    def test_pagina_usa_el_shell_con_sidebar_y_navbar(self):
        respuesta = self.client.get(reverse("core:design_system"))
        self.assertContains(respuesta, 'class="sidebar"')
        self.assertContains(respuesta, 'class="navbar"')

    def test_modal_usa_dialog_nativo_accesible(self):
        respuesta = self.client.get(reverse("core:design_system"))
        self.assertContains(respuesta, "<dialog")

    def test_tabs_usan_atributos_aria_correctos(self):
        respuesta = self.client.get(reverse("core:design_system"))
        self.assertContains(respuesta, 'role="tablist"')
        self.assertContains(respuesta, 'role="tabpanel"')
        self.assertContains(respuesta, 'aria-selected="true"')


class ErrorPagesTests(TestCase):
    """FASE 5 — páginas de error consistentes con el Design System."""

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
    def test_404_personalizado_se_muestra_con_debug_false(self):
        respuesta = self.client.get("/esta-ruta-no-existe/")
        self.assertEqual(respuesta.status_code, 404)
        self.assertContains(respuesta, "Página no encontrada", status_code=404)

    def test_plantilla_500_renderiza_sin_contexto_de_request(self):
        """500.html se renderiza deliberadamente sin RequestContext (así
        lo hace Django en producción); se verifica que no dependa de
        `request`/`messages` y renderice sin errores."""
        html = render_to_string("500.html")
        self.assertIn("Algo salió mal", html)
        self.assertIn("500", html)
