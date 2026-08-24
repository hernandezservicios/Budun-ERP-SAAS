from django.test import SimpleTestCase
from django.urls import reverse


class HomePageTests(SimpleTestCase):
    """Smoke tests de fundación (FASE 1).

    Se usa SimpleTestCase (no TestCase) porque la vista `home` no accede a
    la base de datos y esta fase no requiere una conexión PostgreSQL real
    todavía (eso es alcance de FASE 2 — PostgreSQL Foundation).
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
