from django.test import TestCase
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
