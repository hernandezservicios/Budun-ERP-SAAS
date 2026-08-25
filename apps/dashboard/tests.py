"""
Tests del Panel (FASE 7): aislamiento Multi-Tenant, seguridad, estados
(loading/empty/error/success) y performance (N+1).
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.tenants.models import Membership, Tenant

User = get_user_model()


class DashboardSecurityTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Segura", slug="empresa-segura")
        self.user = User.objects.create_user(email="dueno@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)

    def test_requiere_usuario_autenticado(self):
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("accounts:login"), respuesta.url)

    def test_usuario_sin_tenant_es_redirigido_a_onboarding(self):
        user_sin_tenant = User.objects.create_user(email="nuevo@example.com", password="clave-de-prueba-987")
        self.client.login(username="nuevo@example.com", password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertRedirects(respuesta, reverse("accounts:onboarding"))

    def test_miembro_no_owner_tambien_puede_ver_su_propio_panel(self):
        """El Panel no restringe la sola visualización por rol: cualquier
        miembro activo de su propio tenant puede verlo."""
        miembro = User.objects.create_user(email="miembro@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=miembro, tenant=self.tenant, role=Membership.Role.MEMBER)
        self.client.login(username="miembro@example.com", password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertEqual(respuesta.status_code, 200)


class DashboardIsolationTests(TestCase):
    """Objetivo explícito de FASE 7: todo dato mostrado debe pertenecer
    solo al tenant del usuario autenticado; nunca una consulta global."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant Panel A", slug="tenant-panel-a")
        self.tenant_b = Tenant.objects.create(name="Tenant Panel B", slug="tenant-panel-b")

        self.user_a = User.objects.create_user(email="panel.a@example.com", password="clave-de-prueba-987")
        self.user_b = User.objects.create_user(email="panel.b@example.com", password="clave-de-prueba-987")

        Membership.objects.create(user=self.user_a, tenant=self.tenant_a, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.user_b, tenant=self.tenant_b, role=Membership.Role.OWNER)

        # Tenant B tiene más miembros: si el panel de A filtrara mal,
        # se notaría inmediatamente en el KPI y en la actividad.
        for i in range(3):
            miembro = User.objects.create_user(
                email=f"extra{i}@example.com", password="clave-de-prueba-987"
            )
            Membership.objects.create(user=miembro, tenant=self.tenant_b, role=Membership.Role.MEMBER)

    def test_panel_muestra_solo_el_nombre_del_tenant_propio(self):
        self.client.login(username="panel.a@example.com", password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertContains(respuesta, "Tenant Panel A")
        self.assertNotContains(respuesta, "Tenant Panel B")

    def test_kpi_de_miembros_no_mezcla_tenants(self):
        self.client.login(username="panel.a@example.com", password="clave-de-prueba-987")
        respuesta_a = self.client.get(reverse("dashboard:panel"))
        self.assertContains(respuesta_a, '<p class="kpi__valor">1</p>')  # solo el owner en tenant A

        self.client.login(username="panel.b@example.com", password="clave-de-prueba-987")
        respuesta_b = self.client.get(reverse("dashboard:panel"))
        self.assertContains(respuesta_b, '<p class="kpi__valor">4</p>')  # owner + 3 miembros en tenant B

    def test_actividad_reciente_no_expone_usuarios_de_otro_tenant(self):
        self.client.login(username="panel.a@example.com", password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertNotContains(respuesta, "extra0@example.com")
        self.assertNotContains(respuesta, "extra1@example.com")

    def test_sesion_manipulada_hacia_otro_tenant_no_filtra_datos(self):
        """Regresión directa de FASE 3: ni siquiera manipulando la sesión
        se puede ver el panel de otro tenant sin pertenecer a él."""
        self.client.login(username="panel.a@example.com", password="clave-de-prueba-987")
        session = self.client.session
        session["active_tenant_id"] = self.tenant_b.id
        session.save()

        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertContains(respuesta, "Tenant Panel A")
        self.assertNotContains(respuesta, "Tenant Panel B")


class DashboardStatesTests(TestCase):
    """Estados de UX pedidos: loading (vista previa tipo skeleton),
    empty, error y success."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Estados", slug="empresa-estados")
        self.user = User.objects.create_user(email="estados@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)
        self.client.login(username="estados@example.com", password="clave-de-prueba-987")

    def test_estado_vacio_con_solo_el_dueno(self):
        """Con solo el dueño, la actividad reciente NO está vacía: el
        alta del propio dueño es una actividad real y legítima (patrón
        habitual: "creaste tu empresa"), no un dato fabricado. Lo que sí
        debe verse vacío/pendiente son los KPIs de módulos que todavía
        no existen, y debe aparecer la alerta de equipo de una persona."""
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertContains(respuesta, "se unió al equipo como Propietario")
        self.assertContains(respuesta, "Todavía eres el único miembro")
        self.assertContains(respuesta, "Se activará con el módulo de Ventas.")
        self.assertNotContains(respuesta, "Aún no hay actividad reciente")

    def test_actividad_reciente_esta_realmente_vacia_sin_membresias_activas(self):
        """Cubre el estado vacío real de `obtener_actividad_reciente`:
        ocurre cuando no hay ninguna membresía ACTIVA (p. ej. todas
        desactivadas), no en el flujo normal de onboarding (que siempre
        crea al menos la del dueño)."""
        from apps.dashboard.services import obtener_actividad_reciente

        Membership.objects.filter(tenant=self.tenant).update(is_active=False)
        self.assertEqual(obtener_actividad_reciente(self.tenant), [])

    def test_estado_success_con_datos_reales_al_agregar_miembro(self):
        otro = User.objects.create_user(email="segundo@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=otro, tenant=self.tenant, role=Membership.Role.MEMBER)

        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertContains(respuesta, "se unió al equipo como Miembro")
        self.assertNotContains(respuesta, "Todavía eres el único miembro")

    def test_estado_loading_vista_previa_de_tendencias(self):
        """No hay fetch asíncrono todavía (server-rendered): el estado de
        "cargando" se representa como una vista previa tipo skeleton,
        honesta sobre que no son datos reales."""
        respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertContains(respuesta, "tendencia-preview")
        self.assertContains(respuesta, "Vista previa")

    def test_estado_error_no_rompe_la_pagina(self):
        """Si una fuente de datos falla, el panel degrada con una alerta
        en vez de un 500."""
        with mock.patch(
            "apps.dashboard.services.obtener_kpis", side_effect=RuntimeError("boom")
        ):
            respuesta = self.client.get(reverse("dashboard:panel"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se pudieron cargar algunos datos del panel")


class DashboardPerformanceTests(TestCase):
    """Objetivo explícito de FASE 7: revisar número de queries y N+1."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Empresa Performance", slug="empresa-performance")
        self.user = User.objects.create_user(email="perf@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.OWNER)
        self.client.login(username="perf@example.com", password="clave-de-prueba-987")

    def _cantidad_de_queries(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as contexto:
            self.client.get(reverse("dashboard:panel"))
        return len(contexto.captured_queries)

    def test_numero_de_queries_no_crece_con_mas_miembros(self):
        """Prueba directa de ausencia de N+1: agregar más filas no debe
        aumentar el número de consultas (select_related evita 1 query
        por fila)."""
        queries_con_un_miembro = self._cantidad_de_queries()

        for i in range(9):
            miembro = User.objects.create_user(
                email=f"masmiembros{i}@example.com", password="clave-de-prueba-987"
            )
            Membership.objects.create(user=miembro, tenant=self.tenant, role=Membership.Role.MEMBER)

        queries_con_diez_miembros = self._cantidad_de_queries()

        self.assertEqual(
            queries_con_un_miembro,
            queries_con_diez_miembros,
            "El número de queries del Panel no debería depender de cuántos "
            "miembros tenga el tenant (indicaría un N+1).",
        )
