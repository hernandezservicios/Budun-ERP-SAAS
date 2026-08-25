"""
Pruebas automatizadas de aislamiento Multi-Tenant (FASE 3).

Cubren, con datos reales en PostgreSQL:
- Aislamiento a nivel de manager/queryset (`TenantScopedModel`/`TenantManager`).
- Aislamiento a nivel de servicio (`services.py`).
- Aislamiento a nivel de vista completa, pasando por `TenantMiddleware`
  (`views.whoami_view`).
- Que el backend determina el tenant y que un `tenant_id` enviado por el
  "frontend" (querystring o sesión manipulada) nunca es de fiar.
- Controles de autorización por rol (`permissions.require_role`).
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from .middleware import ACTIVE_TENANT_SESSION_KEY, TenantMiddleware
from .models import IsolationSample, Membership, Tenant
from .permissions import require_role, require_tenant
from .scoping import get_current_tenant, tenant_context
from .services import create_isolation_sample, list_isolation_samples_for_current_tenant
from .views import whoami_view

User = get_user_model()


class TenantIsolationTestCase(TestCase):
    """Escenario base: Tenant A y Tenant B, cada uno con su propio dueño y
    su propio dato privado (objetivo 11 de FASE 3)."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")

        self.user_a = User.objects.create_user(email="a@example.com", password="clave-de-prueba-123")
        self.user_b = User.objects.create_user(email="b@example.com", password="clave-de-prueba-123")

        self.membership_a = Membership.objects.create(
            user=self.user_a, tenant=self.tenant_a, role=Membership.Role.OWNER
        )
        self.membership_b = Membership.objects.create(
            user=self.user_b, tenant=self.tenant_b, role=Membership.Role.OWNER
        )

        with tenant_context(self.tenant_a):
            create_isolation_sample(self.tenant_a, "dato-privado-A")
        with tenant_context(self.tenant_b):
            create_isolation_sample(self.tenant_b, "dato-privado-B")

    def _authenticated_request(self, user, path="/"):
        request = RequestFactory().get(path)
        request.user = user
        request.session = SessionStore()
        return request

    # ------------------------------------------------------------------
    # Manager / QuerySet
    # ------------------------------------------------------------------

    def test_sin_tenant_activo_el_manager_no_devuelve_nada(self):
        """Sin contexto, el manager nunca debe devolver "todo" por error:
        debe devolver un queryset vacío."""
        self.assertIsNone(get_current_tenant())
        self.assertEqual(list(IsolationSample.objects.all()), [])

    def test_manager_solo_ve_los_datos_de_su_propio_tenant(self):
        with tenant_context(self.tenant_a):
            resultados = list(IsolationSample.objects.all())
        self.assertEqual([r.label for r in resultados], ["dato-privado-A"])

        with tenant_context(self.tenant_b):
            resultados = list(IsolationSample.objects.all())
        self.assertEqual([r.label for r in resultados], ["dato-privado-B"])

    def test_tenant_a_no_puede_leer_registro_de_tenant_b_por_id(self):
        """Aunque Tenant A conociera el ID exacto del registro de Tenant B
        (p. ej. por enumeración), el manager tenant-aware no lo expone."""
        registro_de_b = IsolationSample.all_objects.get(tenant=self.tenant_b)

        with tenant_context(self.tenant_a):
            existe = IsolationSample.objects.filter(pk=registro_de_b.pk).exists()
            obtenido = IsolationSample.objects.filter(pk=registro_de_b.pk).first()

        self.assertFalse(existe, "Tenant A pudo detectar la existencia de un registro de Tenant B")
        self.assertIsNone(obtenido, "Tenant A pudo leer un registro de Tenant B por su ID")

    def test_all_objects_es_una_via_de_escape_consciente_y_separada(self):
        """`all_objects` existe para tareas internas (auditoría, admin) y
        confirma que en total hay 2 registros — pero nunca se usa desde
        servicios/vistas de negocio (ver `services.py`)."""
        self.assertEqual(IsolationSample.all_objects.count(), 2)

    # ------------------------------------------------------------------
    # Servicio
    # ------------------------------------------------------------------

    def test_servicio_lista_solo_el_tenant_activo(self):
        with tenant_context(self.tenant_a):
            resultados = list_isolation_samples_for_current_tenant()
        self.assertEqual([r.label for r in resultados], ["dato-privado-A"])

        with tenant_context(self.tenant_b):
            resultados = list_isolation_samples_for_current_tenant()
        self.assertEqual([r.label for r in resultados], ["dato-privado-B"])

    # ------------------------------------------------------------------
    # Middleware (determina el tenant; el backend decide, no el frontend)
    # ------------------------------------------------------------------

    def test_middleware_resuelve_el_tenant_correcto_por_usuario(self):
        middleware = TenantMiddleware(get_response=lambda r: r)

        request_a = self._authenticated_request(self.user_a)
        middleware(request_a)
        self.assertEqual(request_a.tenant, self.tenant_a)
        self.assertEqual(request_a.membership, self.membership_a)

        request_b = self._authenticated_request(self.user_b)
        middleware(request_b)
        self.assertEqual(request_b.tenant, self.tenant_b)

    def test_usuario_sin_membresia_no_obtiene_ningun_tenant(self):
        user_c = User.objects.create_user(email="c@example.com", password="clave-de-prueba-123")
        middleware = TenantMiddleware(get_response=lambda r: r)
        request_c = self._authenticated_request(user_c)
        middleware(request_c)
        self.assertIsNone(request_c.tenant)

    def test_usuario_no_autenticado_no_obtiene_ningun_tenant(self):
        from django.contrib.auth.models import AnonymousUser

        middleware = TenantMiddleware(get_response=lambda r: r)
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        request.session = SessionStore()
        middleware(request)
        self.assertIsNone(request.tenant)

    def test_tenant_id_en_querystring_es_completamente_ignorado(self):
        """Objetivo 9: un tenant_id enviado por el 'frontend' nunca debe
        poder cambiar el tenant resuelto por el backend."""
        request = RequestFactory().get(f"/?tenant_id={self.tenant_b.id}")
        request.user = self.user_a
        request.session = SessionStore()

        middleware = TenantMiddleware(get_response=lambda r: r)
        middleware(request)

        self.assertEqual(request.tenant, self.tenant_a)
        self.assertNotEqual(request.tenant, self.tenant_b)

    def test_sesion_manipulada_hacia_otro_tenant_es_descartada(self):
        """Simula que alguien manipuló la sesión (o intentó forzar un
        active_tenant_id) para apuntar al tenant de otro usuario: el
        middleware valida contra las membresías reales y lo rechaza."""
        request = self._authenticated_request(self.user_a)
        request.session[ACTIVE_TENANT_SESSION_KEY] = self.tenant_b.id

        middleware = TenantMiddleware(get_response=lambda r: r)
        middleware(request)

        self.assertEqual(request.tenant, self.tenant_a)
        self.assertNotEqual(request.tenant, self.tenant_b)
        self.assertNotIn(ACTIVE_TENANT_SESSION_KEY, request.session)

    def test_sesion_con_tenant_propio_valido_si_se_respeta(self):
        """Un `active_tenant_id` en sesión SÍ se respeta cuando corresponde
        a una membresía real y activa del propio usuario."""
        request = self._authenticated_request(self.user_a)
        request.session[ACTIVE_TENANT_SESSION_KEY] = self.tenant_a.id

        middleware = TenantMiddleware(get_response=lambda r: r)
        middleware(request)

        self.assertEqual(request.tenant, self.tenant_a)

    # ------------------------------------------------------------------
    # Vista completa (middleware + permisos + servicio + manager)
    # ------------------------------------------------------------------

    def test_vista_protegida_devuelve_solo_los_datos_de_su_propio_tenant(self):
        middleware = TenantMiddleware(get_response=whoami_view)

        respuesta_a = middleware(self._authenticated_request(self.user_a))
        datos_a = json.loads(respuesta_a.content)
        self.assertEqual(datos_a["tenant_slug"], "tenant-a")
        self.assertEqual(datos_a["registros"], ["dato-privado-A"])

        respuesta_b = middleware(self._authenticated_request(self.user_b))
        datos_b = json.loads(respuesta_b.content)
        self.assertEqual(datos_b["tenant_slug"], "tenant-b")
        self.assertEqual(datos_b["registros"], ["dato-privado-B"])

    def test_vista_protegida_rechaza_a_quien_no_tiene_tenant(self):
        user_c = User.objects.create_user(email="c2@example.com", password="clave-de-prueba-123")
        middleware = TenantMiddleware(get_response=whoami_view)
        with self.assertRaises(PermissionDenied):
            middleware(self._authenticated_request(user_c))

    # ------------------------------------------------------------------
    # Autorización por rol (objetivo 8)
    # ------------------------------------------------------------------

    def test_require_role_permite_al_owner(self):
        request = self._authenticated_request(self.user_a)
        TenantMiddleware(get_response=lambda r: r)(request)

        membership = require_role(request, [Membership.Role.OWNER])
        self.assertEqual(membership, self.membership_a)

    def test_require_role_bloquea_a_quien_no_tiene_el_rol_requerido(self):
        user_member = User.objects.create_user(email="member@example.com", password="clave-de-prueba-123")
        Membership.objects.create(user=user_member, tenant=self.tenant_a, role=Membership.Role.MEMBER)

        request = self._authenticated_request(user_member)
        TenantMiddleware(get_response=lambda r: r)(request)

        with self.assertRaises(PermissionDenied):
            require_role(request, [Membership.Role.OWNER])

    def test_require_tenant_bloquea_sin_tenant_activo(self):
        request = RequestFactory().get("/")
        request.tenant = None
        with self.assertRaises(PermissionDenied):
            require_tenant(request)
