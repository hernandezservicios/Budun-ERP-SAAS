from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse


class HomePageTests(TestCase):
    """Smoke tests de fundación, ahora contra PostgreSQL real (FASE 2).

    Se usa TestCase (no SimpleTestCase) a propósito: Django crea y destruye
    una base de datos de prueba real en PostgreSQL (usando el rol
    erp_saas_app, que tiene privilegio CREATEDB) en cada corrida, lo que
    verifica el ciclo de vida completo de la conexión PostgreSQL, no solo
    la vista.
    """

    def test_home_page_responde_200(self):
        respuesta = self.client.get(reverse("core:home"))
        self.assertEqual(respuesta.status_code, 200)

    def test_home_page_usa_template_esperado(self):
        respuesta = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(respuesta, "core/home.html")

    def test_home_page_contenido_en_espanol(self):
        respuesta = self.client.get(reverse("core:home"))
        self.assertContains(respuesta, "Fundación del proyecto")

    def test_home_page_incluye_enlace_para_saltar_al_contenido(self):
        """Accesibilidad (FASE 5): todo documento debe ofrecer un skip
        link al contenido principal."""
        respuesta = self.client.get(reverse("core:home"))
        self.assertContains(respuesta, 'href="#contenido-principal"')
        self.assertContains(respuesta, 'id="contenido-principal"')

    def test_home_page_carga_los_estilos_del_design_system(self):
        respuesta = self.client.get(reverse("core:home"))
        self.assertContains(respuesta, "css/base.css")
        self.assertContains(respuesta, "css/design-system.css")


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
