"""
FASE DE REDISEÑO VISUAL SaaS — Design System + Shell + Dashboard +
Navegación. Estas pruebas verifican el RESULTADO VISUAL/estructural de
la fase (nunca reglas de negocio de Billing, que ya están cubiertas por
el resto de `apps.billing.tests`): separación real de shell SaaS/ERP,
textos humanos en el dashboard, badges con color semántico, botones
"Volver", y el nuevo flujo de editar/desactivar cuentas bancarias.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.billing.models import BankAccount, Tenant
from apps.core.templatetags.ui_extras import estado_badge, estado_paypal, monto

from ._helpers_saas import crear_tenant_con_owner

User = get_user_model()

# Textos que SOLO existen en el sidebar del ERP (`layout_app.html`) —
# ninguno debe aparecer en una página de la plataforma SaaS
# (`layout_saas_admin.html`), que es exactamente el bug que esta fase
# corrige (ver KNOWN_ISSUES.md).
_TEXTOS_EXCLUSIVOS_DEL_ERP = ["Inventario", "Proformas", "Cotizaciones", "RRHH", "Nómina", "Contabilidad"]


class ShellSaaSSeparadoDelErpTests(TestCase):
    """Sección 4 de la fase: el Super Admin nunca debe ver los menús del ERP
    mientras administra la plataforma SaaS, y viceversa el Portal del tenant
    (que SÍ vive dentro de su propio ERP) conserva el shell ERP normal."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.shell@example.com", password="clave-de-prueba-987")
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_dashboard_billing_admin_usa_el_shell_saas_y_nunca_el_del_erp(self):
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        self.assertContains(respuesta, 'sidebar--saas')
        for texto in _TEXTOS_EXCLUSIVOS_DEL_ERP:
            self.assertNotContains(respuesta, texto)

    def test_gateway_status_de_plataforma_usa_el_shell_saas(self):
        respuesta = self.client.get(reverse("billing_platform:status"))
        self.assertContains(respuesta, 'sidebar--saas')
        for texto in _TEXTOS_EXCLUSIVOS_DEL_ERP:
            self.assertNotContains(respuesta, texto)

    def test_sidebar_saas_agrupa_por_seccion_con_destinos_reales(self):
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        # Grupos pedidos en la sección 5 de la fase — solo los que tienen
        # destinos reales (nunca enlaces ficticios).
        for grupo in ["Clientes / Tenants", "Suscripciones y planes", "Facturación", "Reportes", "Configuración"]:
            self.assertContains(respuesta, grupo)
        # Cada destino real listado en admin_urls.py debe estar enlazado.
        for nombre_url in [
            "tenants_list", "customers_list", "plans_list", "subscriptions_list",
            "invoices_list", "payments_list", "transfers_queue", "credit_notes_list",
            "refunds_list", "reports", "manual_sale", "bank_accounts_list",
        ]:
            self.assertContains(respuesta, reverse(f"billing_admin:{nombre_url}"))
        self.assertContains(respuesta, reverse("billing_platform:status"))

    def test_portal_del_tenant_conserva_el_shell_erp_normal(self):
        """El Portal (`billing_portal`) es la vista del PROPIO tenant sobre
        su facturación, dentro de su sesión ERP normal — a propósito NO usa
        el shell SaaS de plataforma."""
        tenant, owner = crear_tenant_con_owner(slug="tenant-portal-shell")
        self.client.logout()
        self.client.login(username=owner.email, password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertNotContains(respuesta, 'sidebar--saas')
        self.assertContains(respuesta, 'class="sidebar"')


class DashboardTextoHumanoTests(TestCase):
    """Sección 7: ningún término técnico/abreviado crudo (MRR, ARR,
    PAST_DUE...) debe aparecer como etiqueta visible del dashboard."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.dashboard@example.com", password="clave-de-prueba-987")
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_dashboard_traduce_los_kpis_a_lenguaje_humano(self):
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        for texto in [
            "Ingresos recurrentes mensuales", "Ingresos recurrentes anuales", "Ingresos de este mes",
            "Suscripciones activas", "Nuevas suscripciones este mes", "Pagos atrasados",
            "Suscripciones suspendidas", "Cancelaciones este mes", "Transferencias pendientes",
            "Facturas vencidas", "Reembolsos de este mes", "Notas de crédito de este mes",
        ]:
            self.assertContains(respuesta, texto)

    def test_dashboard_nunca_muestra_las_etiquetas_tecnicas_crudas(self):
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        # "MRR"/"ARR"/"PAST_DUE" como ETIQUETA de KPI ya no existen (el
        # hallazgo real de la auditoría) — se buscan como fragmento de
        # etiqueta (envueltos en <p class="kpi__etiqueta">) para no dar un
        # falso positivo si la palabra apareciera dentro de otro texto.
        self.assertNotIn('kpi__etiqueta">MRR<', contenido)
        self.assertNotIn('kpi__etiqueta">ARR<', contenido)
        self.assertNotIn('kpi__etiqueta">PAST_DUE<', contenido)


class BadgeEstadoSemanticoTests(TestCase):
    """Sección 14: cada estado de dominio debe mostrarse con un color
    semántico consistente (nunca decorativo ni ausente)."""

    def test_filtro_estado_badge_clasifica_los_estados_reales(self):
        self.assertEqual(estado_badge("active"), "verde")
        self.assertEqual(estado_badge("past_due"), "advertencia")
        self.assertEqual(estado_badge("suspended"), "peligro")
        self.assertEqual(estado_badge("cancelled"), "peligro")
        self.assertEqual(estado_badge("draft"), "neutro")
        self.assertEqual(estado_badge("refunded"), "azul")

    def test_filtro_estado_badge_nunca_revienta_con_un_codigo_desconocido(self):
        self.assertEqual(estado_badge("algo-que-no-existe"), "neutro")
        self.assertEqual(estado_badge(None), "neutro")

    def test_filtro_estado_paypal_traduce_sin_ocultar_lo_desconocido(self):
        self.assertEqual(estado_paypal("ACTIVE"), "activa")
        self.assertEqual(estado_paypal("CODIGO-NUEVO"), "CODIGO-NUEVO")

    def test_filtro_monto_formatea_separador_de_miles(self):
        self.assertEqual(monto(Decimal("1234.5")), "1,234.50")
        self.assertEqual(monto(None), None)

    def test_tenants_list_muestra_el_badge_con_color_segun_estado(self):
        superadmin = User.objects.create_superuser(email="super.badge@example.com", password="clave-de-prueba-987")
        self.client.login(username=superadmin.email, password="clave-de-prueba-987")
        tenant, _ = crear_tenant_con_owner(slug="tenant-badge-suspendido")
        tenant.billing_status = Tenant.BillingStatus.SUSPENDED
        tenant.save(update_fields=["billing_status"])
        respuesta = self.client.get(reverse("billing_admin:tenants_list"))
        self.assertContains(respuesta, "badge badge--peligro")


class BotonVolverTests(TestCase):
    """Sección 10: toda página de detalle/formulario/confirmación de
    Billing Admin debe ofrecer una ruta explícita de regreso."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.volver@example.com", password="clave-de-prueba-987")
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_detalle_de_tenant_tiene_boton_volver_a_tenants(self):
        tenant, _ = crear_tenant_con_owner(slug="tenant-volver")
        respuesta = self.client.get(reverse("billing_admin:tenant_detail", args=[tenant.pk]))
        self.assertContains(respuesta, "Volver a tenants")
        self.assertContains(respuesta, reverse("billing_admin:tenants_list"))


class BankAccountEditarDesactivarTests(TestCase):
    """Sección 11: editar y desactivar (nunca borrado físico) para
    `BankAccount` desde la UI de plataforma."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.cuentas@example.com", password="clave-de-prueba-987")
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")
        self.cuenta = BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD",
            account_holder="Budun SRL", account_number="0001-0002-0003", is_active=True,
        )

    def test_listado_no_ofrece_boton_eliminar_pero_si_editar_y_desactivar(self):
        respuesta = self.client.get(reverse("billing_admin:bank_accounts_list"))
        self.assertContains(respuesta, "Editar")
        self.assertContains(respuesta, "Desactivar")
        self.assertNotContains(respuesta, ">Eliminar<")

    def test_editar_cuenta_actualiza_los_datos_reales(self):
        respuesta = self.client.post(reverse("billing_admin:bank_account_update", args=[self.cuenta.pk]), {
            "bank_name": "Banco Actualizado", "country": "RD", "currency": "USD",
            "account_holder": "Budun SRL", "account_number": "0001-0002-0003",
            "account_type": "", "is_active": "on", "priority": "0", "notes": "",
        })
        self.assertRedirects(respuesta, reverse("billing_admin:bank_accounts_list"))
        self.cuenta.refresh_from_db()
        self.assertEqual(self.cuenta.bank_name, "Banco Actualizado")

    def test_desactivar_y_reactivar_cuenta_nunca_la_borra(self):
        respuesta = self.client.post(reverse("billing_admin:bank_account_toggle_active", args=[self.cuenta.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.cuenta.refresh_from_db()
        self.assertFalse(self.cuenta.is_active)
        self.assertTrue(BankAccount.objects.filter(pk=self.cuenta.pk).exists())

        respuesta = self.client.post(reverse("billing_admin:bank_account_toggle_active", args=[self.cuenta.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.cuenta.refresh_from_db()
        self.assertTrue(self.cuenta.is_active)

    def test_bankaccount_esta_protegida_por_diseno_contra_borrado_fisico(self):
        """Confirma la razón documentada de por qué esta fase NO agrega un
        botón "Eliminar": `PaymentProof.bank_account` ya usa
        `on_delete=PROTECT` desde FASE 17 — un borrado físico con
        comprobantes/pagos históricos reales asociados fallaría en la base
        de datos, por diseño. Ver `apps/billing/models/transfers.py`."""
        from django.db import models as django_models

        from apps.billing.models import PaymentProof

        campo = PaymentProof._meta.get_field("bank_account")
        self.assertIs(campo.remote_field.on_delete, django_models.PROTECT)
