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
        for grupo in ["Clientes y empresas", "Suscripciones y planes", "Facturación", "Reportes", "Configuración"]:
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
            "Ingresos recurrentes mensuales", "Ingresos recurrentes anuales", "Ingresos del mes",
            "Suscripciones activas", "Altas este mes", "Pagos atrasados",
            "Suspendidas", "Cancelaciones este mes", "Transferencias pendientes",
            "Facturas vencidas", "Reembolsos del mes", "Notas de crédito del mes",
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


class RevisionVisualFaseATests(TestCase):
    """FASE SIGUIENTE — Revisión visual SaaS vista por vista, bloque A
    (Dashboard, sidebar, Clientes/Tenants, detalle de tenant, venta
    manual). Cada test cubre una inconsistencia real encontrada y
    corregida durante la auditoría de este bloque."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.fasea@example.com", password="clave-de-prueba-987")
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_dashboard_kpis_de_alerta_no_muestran_color_de_advertencia_cuando_el_conteo_es_cero(self):
        """Hallazgo real: Pagos atrasados/Suspendidas/Cancelaciones este
        mes mostraban su color de advertencia/peligro incluso con 0 —
        inconsistente con Transferencias pendientes/Facturas vencidas,
        que ya eran condicionales. Con la BD de test vacía (sin ninguna
        suscripción), el conteo real es 0 para las tres."""
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        self.assertIn('<div class="kpi ">\n                <p class="kpi__etiqueta"><span class="kpi__icono" aria-hidden="true">⏰</span> Pagos atrasados', contenido)
        self.assertIn('<div class="kpi ">\n                <p class="kpi__etiqueta"><span class="kpi__icono" aria-hidden="true">⛔</span> Suspendidas', contenido)
        self.assertIn('<div class="kpi ">\n                <p class="kpi__etiqueta"><span class="kpi__icono" aria-hidden="true">❌</span> Cancelaciones este mes', contenido)

    def test_dashboard_ya_no_muestra_los_acronimos_mrr_arr_en_el_texto_de_ayuda(self):
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        self.assertNotIn("MRR —", contenido)
        self.assertNotIn("ARR —", contenido)

    def test_sidebar_agrupa_venta_manual_junto_a_clientes_y_tenants(self):
        """Venta manual crea un Tenant real — pertenece conceptualmente
        al grupo 'Clientes y empresas', no a 'Configuración'."""
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        inicio_grupo = contenido.index("Clientes y empresas")
        fin_grupo = contenido.index("Suscripciones y planes")
        self.assertIn("Venta manual", contenido[inicio_grupo:fin_grupo])

    def test_tenants_list_muestra_estado_vacio_real_cuando_no_hay_tenants(self):
        respuesta = self.client.get(reverse("billing_admin:tenants_list"))
        self.assertContains(respuesta, "Sin tenants todavía")
        self.assertContains(respuesta, "estado-vacio")

    def test_tenants_list_columna_activo_es_un_badge_no_texto_plano(self):
        tenant, _ = crear_tenant_con_owner(slug="tenant-badge-activo")
        respuesta = self.client.get(reverse("billing_admin:tenants_list"))
        self.assertContains(respuesta, "badge--verde")

    def test_detalle_de_tenant_pide_confirmacion_antes_de_suspender_o_cancelar(self):
        tenant, owner = crear_tenant_con_owner(slug="tenant-confirmacion")
        from apps.billing.services import subscriptions as subscription_services
        from ._helpers_saas import crear_plan_con_version, crear_saas_customer

        plan, version = crear_plan_con_version(slug="plan-confirmacion")
        saas_customer = crear_saas_customer(email="cliente.confirmacion@example.com")
        subscription = subscription_services.create_subscription(tenant, saas_customer=saas_customer, plan_version=version)
        subscription_services.activate_subscription(subscription)
        respuesta = self.client.get(reverse("billing_admin:tenant_detail", args=[tenant.pk]))
        self.assertContains(respuesta, 'id="modal-suspender-tenant"')
        self.assertContains(respuesta, 'id="modal-cancelar-tenant"')
        self.assertContains(respuesta, "data-modal-open=\"modal-suspender-tenant\"")
        self.assertContains(respuesta, "¿Confirmas la suspensión?")

    def test_suspender_via_el_modal_sigue_funcionando_igual_que_antes(self):
        """El cambio es solo de presentación (confirmación) — el POST
        real al mismo endpoint debe seguir funcionando exactamente igual."""
        tenant, owner = crear_tenant_con_owner(slug="tenant-suspender-modal")
        from apps.billing.services import subscriptions as subscription_services
        from ._helpers_saas import crear_plan_con_version, crear_saas_customer

        plan, version = crear_plan_con_version(slug="plan-suspender-modal")
        saas_customer = crear_saas_customer(email="cliente.suspender.modal@example.com")
        subscription = subscription_services.create_subscription(tenant, saas_customer=saas_customer, plan_version=version)
        subscription_services.activate_subscription(subscription)
        self.client.post(reverse("billing_admin:tenant_detail", args=[tenant.pk]), {"accion": "suspender"})
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, subscription.Status.SUSPENDED)

    def test_manual_sale_agrupa_los_campos_por_entidad_real(self):
        respuesta = self.client.get(reverse("billing_admin:manual_sale"))
        contenido = respuesta.content.decode()
        for texto in ["Cliente SaaS", "Tenant", "Propietario (Owner)", "Registrar venta manual"]:
            self.assertContains(respuesta, texto)
        # El orden real debe respetar la agrupación (Cliente antes que
        # Tenant antes que Propietario).
        self.assertLess(contenido.index("Cliente SaaS"), contenido.index(">Tenant<"))
        self.assertLess(contenido.index(">Tenant<"), contenido.index("Propietario (Owner)"))


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


class RevisionVisualFaseBTests(TestCase):
    """FASE SIGUIENTE — Revisión visual SaaS vista por vista, Bloque B
    (Planes, versiones de planes, Suscripciones, detalle de suscripción,
    estados de suscripción). Cada test cubre una inconsistencia real
    encontrada y corregida durante la auditoría de este bloque."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.faseb@example.com", password="clave-de-prueba-987")
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_plans_list_no_muestra_el_slug_interno_en_el_titulo(self):
        from apps.billing.models import Plan

        Plan.objects.create(name="Plan Slug Oculto", slug="plan-slug-oculto")
        respuesta = self.client.get(reverse("billing_admin:plans_list"))
        contenido = respuesta.content.decode()
        # El slug sigue siendo consultable (dato real, nunca oculto),
        # pero nunca dentro del título principal de la tarjeta.
        self.assertNotIn("Plan Slug Oculto (plan-slug-oculto)", contenido)
        self.assertIn("plan-slug-oculto", contenido)

    def test_plans_list_muestra_estado_vacio_real_cuando_no_hay_planes(self):
        respuesta = self.client.get(reverse("billing_admin:plans_list"))
        self.assertContains(respuesta, "No hay planes registrados")
        self.assertContains(respuesta, "estado-vacio")

    def test_plans_list_formulario_de_version_usa_labels_reales(self):
        """Hallazgo real: la vista ya pasaba `version_form` (con
        validación real de PlanVersionForm) pero la plantilla lo
        ignoraba y usaba <select>/<input> sueltos sin ningún label."""
        from apps.billing.models import Plan

        Plan.objects.create(name="Plan Con Form", slug="plan-con-form")
        respuesta = self.client.get(reverse("billing_admin:plans_list"))
        contenido = respuesta.content.decode()
        for texto in ["Frecuencia", "Precio", "Moneda"]:
            self.assertIn(f">{texto}<", contenido)

    def test_plans_list_precio_se_muestra_antes_que_la_frecuencia(self):
        from apps.billing.models import Plan, PlanVersion

        plan = Plan.objects.create(name="Plan Precio Visible", slug="plan-precio-visible")
        PlanVersion.objects.create(plan=plan, frequency="monthly", price_amount=Decimal("29.00"), price_currency="USD", is_current=True)
        respuesta = self.client.get(reverse("billing_admin:plans_list"))
        contenido = respuesta.content.decode()
        self.assertLess(contenido.index("29.00 USD"), contenido.index("Mensual"))

    def test_subscriptions_list_muestra_estado_vacio_real(self):
        respuesta = self.client.get(reverse("billing_admin:subscriptions_list"))
        self.assertContains(respuesta, "No hay suscripciones registradas")
        self.assertContains(respuesta, "estado-vacio")

    def test_subscriptions_list_ofrece_ver_detalle_hacia_el_tenant(self):
        """Hallazgo real: no existía ninguna vía de drill-down desde la
        lista de suscripciones — ni un enlace ni una columna de acción.
        `tenant_detail.html` ya es, en la práctica, el detalle real de
        gestión de la suscripción vigente de ese tenant."""
        from apps.billing.services import subscriptions as subscription_services

        from ._helpers_saas import crear_plan_con_version, crear_saas_customer

        tenant, owner = crear_tenant_con_owner(slug="tenant-drilldown-suscripcion")
        plan, version = crear_plan_con_version(slug="plan-drilldown-suscripcion")
        saas_customer = crear_saas_customer(email="cliente.drilldown@example.com")
        subscription_services.create_subscription(tenant, saas_customer=saas_customer, plan_version=version)
        respuesta = self.client.get(reverse("billing_admin:subscriptions_list"))
        self.assertContains(respuesta, reverse("billing_admin:tenant_detail", args=[tenant.pk]))

    def test_detalle_de_tenant_muestra_precio_y_frecuencia_de_la_suscripcion(self):
        """Hallazgo real: la tarjeta de suscripción de tenant_detail.html
        mostraba el nombre del plan y el estado, pero nunca el precio ni
        la frecuencia real que el tenant está pagando."""
        from apps.billing.services import subscriptions as subscription_services

        from ._helpers_saas import crear_plan_con_version, crear_saas_customer

        tenant, owner = crear_tenant_con_owner(slug="tenant-precio-visible")
        plan, version = crear_plan_con_version(slug="plan-precio-tenant", precio=Decimal("29.00"))
        saas_customer = crear_saas_customer(email="cliente.precio.tenant@example.com")
        subscription = subscription_services.create_subscription(tenant, saas_customer=saas_customer, plan_version=version)
        subscription_services.activate_subscription(subscription)
        respuesta = self.client.get(reverse("billing_admin:tenant_detail", args=[tenant.pk]))
        self.assertContains(respuesta, "29.00 USD")
        self.assertContains(respuesta, "Próxima renovación")

    def test_detalle_de_tenant_enlaza_al_cliente_saas_propietario(self):
        """Hallazgo real: tenant_detail.html nunca mostraba ni enlazaba
        al SaaSCustomer (Tenant.saas_customer) dueño real del tenant."""
        from apps.billing.models import SaaSCustomer

        tenant, owner = crear_tenant_con_owner(slug="tenant-con-cliente-saas")
        saas_customer = SaaSCustomer.objects.create(name="Cliente Dueño Real", email="dueno.real@example.com")
        tenant.saas_customer = saas_customer
        tenant.save(update_fields=["saas_customer"])
        respuesta = self.client.get(reverse("billing_admin:tenant_detail", args=[tenant.pk]))
        self.assertContains(respuesta, "Cliente Dueño Real")
        self.assertContains(respuesta, reverse("billing_admin:customer_detail", args=[saas_customer.pk]))

    def test_todos_los_estados_reales_de_subscription_tienen_color_semantico_mapeado(self):
        """'Estados de suscripción' (sección del Bloque B): verificado sin
        necesitar cambios — los 6 códigos reales de Subscription.Status
        ya estaban cubiertos por el mapa de estado_badge desde la fase
        anterior."""
        from apps.billing.models import Subscription

        codigos_reales = [c for c, _ in Subscription.Status.choices]
        self.assertEqual(set(codigos_reales), {"pending", "active", "past_due", "suspended", "cancelled", "expired"})
        for codigo in codigos_reales:
            self.assertNotEqual(estado_badge(codigo), "neutro", f"Estado real {codigo!r} no debería caer al color por defecto")
