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

from apps.billing.models import BankAccount, Plan, Tenant
from apps.core.templatetags.ui_extras import enmascarar_cuenta, estado_badge, estado_paypal, monto

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
        """FASE E — Master Shell (Design System V1 Hybrid,
        docs/design-system-v1-hybrid.md §11): 8 grupos — los 7 aprobados
        del Design System (Inicio/Clientes y tenants/Comercial/
        Facturación/Finanzas/Reportes/Configuración y cuenta) más
        "Integraciones" (PayPal), una funcionalidad real existente que
        el usuario pidió conservar explícitamente aunque no estuviera en
        la lista de 7 grupos de la galería de referencia — la regla
        "funcionalidad real > restricción de la galería de demostración"
        tiene prioridad. "Facturación" ahora agrupa solo Facturas;
        Pagos/Transferencias/Reembolsos/Cuentas bancarias se movieron a
        "Finanzas" (antes repartidos entre "Facturación" y "Finanzas").
        "Mi perfil"/"Cambiar contraseña" ahora también viven en el
        sidebar (grupo "Configuración / cuenta"), no solo en el dropdown
        del topbar. No existe un enlace real de "Configuración general"
        ni de "Notas de crédito" — no se inventó ningún destino ficticio."""
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        # Grupos reales — solo los que tienen destinos reales (nunca
        # enlaces ficticios).
        for grupo in [
            "Inicio", "Clientes y tenants", "Comercial", "Facturación",
            "Finanzas", "Reportes", "Configuración / cuenta", "Integraciones",
        ]:
            self.assertContains(respuesta, grupo)
        self.assertContains(respuesta, "Budun ERP")
        self.assertNotContains(respuesta, "Budun SaaS")
        self.assertNotContains(respuesta, "Plataforma — Super Admin")
        self.assertNotContains(respuesta, "Configuración general")
        self.assertNotContains(respuesta, "Nota de crédito")
        self.assertNotContains(respuesta, "Notas de crédito")
        # Cada destino real listado en admin_urls.py debe estar enlazado.
        for nombre_url in [
            "tenants_list", "customers_list", "plans_list", "subscriptions_list",
            "invoices_list", "payments_list", "transfers_queue",
            "refunds_list", "reports", "manual_sale", "bank_accounts_list",
            "profile", "password_change",
        ]:
            self.assertContains(respuesta, reverse(f"billing_admin:{nombre_url}"))
        self.assertContains(respuesta, reverse("billing_platform:status"))

    def test_sidebar_finanzas_agrupa_pagos_transferencias_reembolsos_y_cuentas(self):
        """Reagrupación explícita del Design System V1: Facturación
        contiene solo Facturas; Pagos/Transferencias/Reembolsos/Cuentas
        bancarias viven en Finanzas — antes Facturación cargaba con los
        primeros tres y Finanzas solo tenía Cuentas bancarias."""
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        inicio_facturacion = contenido.index(">Facturación<")
        inicio_finanzas = contenido.index(">Finanzas<")
        inicio_reportes = contenido.index(">Reportes<")
        self.assertLess(inicio_facturacion, inicio_finanzas)
        bloque_facturacion = contenido[inicio_facturacion:inicio_finanzas]
        bloque_finanzas = contenido[inicio_finanzas:inicio_reportes]
        self.assertIn("Facturas</span>", bloque_facturacion)
        self.assertNotIn("Pagos</span>", bloque_facturacion)
        for texto in ["Pagos</span>", "Transferencias</span>", "Reembolsos</span>", "Cuentas bancarias</span>"]:
            self.assertIn(texto, bloque_finanzas)

    def test_sidebar_configuracion_cuenta_enlaza_perfil_y_cambiar_contrasena(self):
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        inicio_grupo = contenido.index("Configuración / cuenta")
        fin_grupo = contenido.index("Integraciones")
        bloque = contenido[inicio_grupo:fin_grupo]
        self.assertIn(reverse("billing_admin:profile"), bloque)
        self.assertIn(reverse("billing_admin:password_change"), bloque)

    def test_sidebar_tiene_el_toggle_de_ancho_real(self):
        """FASE E — botón real (no decorativo) para alternar entre 76px
        compacto y 228px expandido, distinto del toggle móvil off-canvas."""
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        self.assertContains(respuesta, "data-sidebar-ancho-toggle")
        self.assertContains(respuesta, 'class="sidebar__nav-scroll"')

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

    def test_menu_del_avatar_saas_ya_no_ofrece_salir_al_erp(self):
        """Hallazgo real corregido: el menú del avatar del shell SaaS
        enlazaba a `dashboard:panel` ("Salir a mi ERP"), a `accounts:perfil`
        ("Mi perfil", que usa `layout_app.html`) y a `accounts:password_change`
        ("Cambiar contraseña", que usa `base.html` y cuyo "volver" regresaba a
        `accounts:perfil`) — todos mezclaban el contexto SaaS con el del ERP
        del tenant. Ahora los 3 ítems del menú (Mi perfil/Cambiar
        contraseña/Cerrar sesión) permanecen dentro de `billing_admin`."""
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        self.assertNotContains(respuesta, "Salir a mi ERP")
        self.assertNotContains(respuesta, reverse("accounts:perfil"))
        self.assertNotContains(respuesta, reverse("accounts:password_change"))
        self.assertContains(respuesta, reverse("billing_admin:profile"))
        self.assertContains(respuesta, reverse("billing_admin:password_change"))

    def test_perfil_del_super_admin_usa_el_shell_saas_y_no_el_del_erp(self):
        respuesta = self.client.get(reverse("billing_admin:profile"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'sidebar--saas')
        for texto in _TEXTOS_EXCLUSIVOS_DEL_ERP:
            self.assertNotContains(respuesta, texto)
        # Mismo ProfileForm real (3 campos), sin mezclar datos de tenant/empresa.
        self.assertContains(respuesta, "Guardar cambios")
        self.assertNotContains(respuesta, "Configurar mi empresa")

    def test_guardar_perfil_del_super_admin_redirige_dentro_del_shell_saas(self):
        respuesta = self.client.post(reverse("billing_admin:profile"), {
            "first_name": "Carlos", "last_name": "Mendizábal", "email": self.superadmin.email,
        })
        self.assertRedirects(respuesta, reverse("billing_admin:profile"))

    def test_perfil_del_super_admin_exige_superusuario(self):
        tenant, owner = crear_tenant_con_owner(slug="tenant-perfil-saas-403")
        self.client.logout()
        self.client.login(username=owner.email, password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("billing_admin:profile"))
        self.assertEqual(respuesta.status_code, 403)

    def test_perfil_saas_enlaza_cambiar_contrasena_dentro_del_shell_saas(self):
        respuesta = self.client.get(reverse("billing_admin:profile"))
        self.assertContains(respuesta, reverse("billing_admin:password_change"))
        self.assertNotContains(respuesta, reverse("accounts:password_change"))

    def test_cambiar_contrasena_del_super_admin_usa_el_shell_saas(self):
        respuesta = self.client.get(reverse("billing_admin:password_change"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'sidebar--saas')
        for texto in _TEXTOS_EXCLUSIVOS_DEL_ERP:
            self.assertNotContains(respuesta, texto)
        # El "volver" debe quedarse en SaaS, nunca regresar a `accounts:perfil`.
        self.assertContains(respuesta, reverse("billing_admin:profile"))
        self.assertNotContains(respuesta, reverse("accounts:perfil"))

    def test_cambiar_contrasena_del_super_admin_exitoso_permanece_en_saas(self):
        respuesta = self.client.post(reverse("billing_admin:password_change"), {
            "old_password": "clave-de-prueba-987",
            "new_password1": "otra-clave-nueva-654",
            "new_password2": "otra-clave-nueva-654",
        })
        self.assertRedirects(respuesta, reverse("billing_admin:password_change_done"))
        pagina_final = self.client.get(reverse("billing_admin:password_change_done"))
        self.assertContains(pagina_final, 'sidebar--saas')
        self.assertContains(pagina_final, reverse("billing_admin:profile"))
        self.assertNotContains(pagina_final, reverse("accounts:perfil"))
        # La sesión sigue activa y la nueva contraseña quedó efectivamente aplicada.
        self.client.logout()
        self.assertTrue(self.client.login(username=self.superadmin.email, password="otra-clave-nueva-654"))

    def test_cambiar_contrasena_del_super_admin_exige_superusuario(self):
        tenant, owner = crear_tenant_con_owner(slug="tenant-password-saas-403")
        self.client.logout()
        self.client.login(username=owner.email, password="clave-de-prueba-987")
        respuesta = self.client.get(reverse("billing_admin:password_change"))
        self.assertEqual(respuesta.status_code, 403)

    def test_flujo_erp_de_perfil_y_contrasena_sigue_intacto(self):
        """El ERP (`accounts:perfil`/`accounts:password_change`, usados por
        cualquier usuario normal) no debe verse afectado por la corrección
        del shell SaaS — sigue usando `layout_app.html`/`base.html` como
        siempre."""
        tenant, owner = crear_tenant_con_owner(slug="tenant-erp-intacto")
        self.client.logout()
        self.client.login(username=owner.email, password="clave-de-prueba-987")
        perfil = self.client.get(reverse("accounts:perfil"))
        self.assertContains(perfil, 'class="sidebar"')
        self.assertNotContains(perfil, 'sidebar--saas')
        cambiar = self.client.get(reverse("accounts:password_change"))
        self.assertNotContains(cambiar, 'sidebar--saas')


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
            "Facturas vencidas", "Reembolsos del mes",
        ]:
            self.assertContains(respuesta, texto)

    def test_dashboard_nunca_muestra_las_etiquetas_tecnicas_crudas(self):
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        # "MRR"/"ARR"/"PAST_DUE" como ETIQUETA de KPI ya no existen (el
        # hallazgo real de la auditoría) — se buscan como fragmento de
        # etiqueta (envueltos en <p class="saas-kpi-card__etiqueta">)
        # para no dar un falso positivo si la palabra apareciera dentro
        # de otro texto.
        self.assertNotIn('saas-kpi-card__etiqueta">MRR<', contenido)
        self.assertNotIn('saas-kpi-card__etiqueta">ARR<', contenido)
        self.assertNotIn('saas-kpi-card__etiqueta">PAST_DUE<', contenido)


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
        """Hallazgo real de este bloque (ver KNOWN_ISSUES.md #139):
        Pagos atrasados/Suspendidas/Cancelaciones este mes aplicaban su
        color de advertencia/peligro de forma incondicional.

        NOTA (FASE — Rediseño Visual Maestro): las KPI cards se
        reconstruyeron por completo (`.saas-kpi-card`, icono circular
        con color FIJO por identidad de métrica — nunca condicional al
        valor, siguiendo el lenguaje visual de la imagen de referencia
        maestra) reemplazando el componente `.kpi`/`.kpi--advertencia`/
        `.kpi--peligro` (que sigue existiendo intacto, compartido con
        el ERP — nunca se tocó). El hallazgo original de "color
        incondicional" ya no puede reproducirse porque esas clases ni
        siquiera se usan en este dashboard — se verifica aquí
        explícitamente esa ausencia."""
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        self.assertNotIn("kpi--advertencia", contenido)
        self.assertNotIn("kpi--peligro", contenido)
        self.assertEqual(contenido.count('class="saas-kpi-card"'), 11)

    def test_dashboard_ya_no_muestra_los_acronimos_mrr_arr_en_el_texto_de_ayuda(self):
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        self.assertNotIn("MRR —", contenido)
        self.assertNotIn("ARR —", contenido)

    def test_sidebar_agrupa_venta_manual_junto_a_planes_y_suscripciones(self):
        """Hallazgo original de este bloque: Venta manual crea un Tenant
        real, por lo que se agrupó junto a Clientes/Tenants (nunca junto a
        'Configuración', un título de grupo que ni siquiera enlaza a nada).
        FASE 7.2 — reubicado dentro del grupo 'Comercial' (junto a Planes/
        Suscripciones) para igualar la agrupación del diseño Stitch
        aprobado. Sigue sin estar bajo 'Finanzas'/'Integraciones' (los
        títulos que reemplazaron a 'Configuración')."""
        respuesta = self.client.get(reverse("billing_admin:dashboard"))
        contenido = respuesta.content.decode()
        inicio_grupo = contenido.index("Comercial")
        fin_grupo = contenido.index("Facturación")
        self.assertIn("Venta manual", contenido[inicio_grupo:fin_grupo])
        self.assertIn("Planes", contenido[inicio_grupo:fin_grupo])
        self.assertIn("Suscripciones", contenido[inicio_grupo:fin_grupo])

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


class PlanesYCuentasBancariasModalTests(TestCase):
    """FASE 3 (implementación visual): "Nuevo plan" y "Nueva cuenta" pasan
    de formulario inline a modal (mismo patrón `data-modal-open`/`<dialog>`
    ya usado en el resto del proyecto — sin backend/URL/form nuevos), y la
    columna "Cuenta" del listado de Cuentas bancarias se enmascara solo en
    presentación — el dato real (`BankAccount.account_number`) y el modal
    de edición siguen completos."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.modales@example.com", password="clave-de-prueba-987")
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_planes_tiene_boton_y_modal_nuevo_plan_sin_subtitulo_inventado(self):
        respuesta = self.client.get(reverse("billing_admin:plans_list"))
        self.assertContains(respuesta, "+ Nuevo plan")
        self.assertContains(respuesta, 'data-modal-open="modal-nuevo-plan"')
        self.assertContains(respuesta, 'id="modal-nuevo-plan"')
        # El <h1> real nunca tuvo subtítulo — no se debe haber inventado ninguno.
        self.assertNotContains(respuesta, "Configuración de catálogo de planes")

    def test_crear_plan_invalido_no_crea_nada_y_muestra_el_mensaje_real(self):
        total_antes = Plan.objects.count()
        respuesta = self.client.post(reverse("billing_admin:plans_list"), {"name": "", "slug": ""}, follow=True)
        self.assertContains(respuesta, "Revisa los datos del plan.")
        self.assertEqual(Plan.objects.count(), total_antes)

    def test_crear_plan_valido_desde_el_modal_funciona_igual_que_antes(self):
        respuesta = self.client.post(reverse("billing_admin:plans_list"), {
            "name": "Plan de Prueba Modal", "slug": "plan-prueba-modal", "description": "",
            "is_active": "on", "sort_order": "0",
        }, follow=True)
        self.assertContains(respuesta, "Plan creado.")
        self.assertTrue(Plan.objects.filter(slug="plan-prueba-modal").exists())

    def test_cuentas_bancarias_tiene_boton_y_modal_nueva_cuenta(self):
        respuesta = self.client.get(reverse("billing_admin:bank_accounts_list"))
        self.assertContains(respuesta, "+ Nueva cuenta")
        self.assertContains(respuesta, 'data-modal-open="modal-nueva-cuenta"')
        self.assertContains(respuesta, 'id="modal-nueva-cuenta"')

    def test_columna_cuenta_del_listado_muestra_el_numero_enmascarado(self):
        BankAccount.objects.create(
            bank_name="BHD León", country="República Dominicana", currency="USD",
            account_holder="Budun Global Dominicana S.R.L.", account_number="1015236789015616", is_active=True,
        )
        respuesta = self.client.get(reverse("billing_admin:bank_accounts_list"))
        self.assertContains(respuesta, "····5616")

    def test_modal_de_editar_cuenta_sigue_mostrando_el_numero_completo(self):
        cuenta = BankAccount.objects.create(
            bank_name="BHD León", country="República Dominicana", currency="USD",
            account_holder="Budun Global Dominicana S.R.L.", account_number="1015236789015616", is_active=True,
        )
        respuesta = self.client.get(reverse("billing_admin:bank_accounts_list"))
        # El campo del modal de edición renderiza el valor real del form
        # ligado a la instancia — nunca pasa por el filtro de enmascaramiento.
        self.assertContains(respuesta, f'value="{cuenta.account_number}"')

    def test_crear_cuenta_invalida_no_crea_nada_y_muestra_el_mensaje_real(self):
        total_antes = BankAccount.objects.count()
        respuesta = self.client.post(reverse("billing_admin:bank_accounts_list"), {"bank_name": ""}, follow=True)
        self.assertContains(respuesta, "Revisa los datos de la cuenta.")
        self.assertEqual(BankAccount.objects.count(), total_antes)

    def test_crear_cuenta_valida_desde_el_modal_funciona_igual_que_antes(self):
        respuesta = self.client.post(reverse("billing_admin:bank_accounts_list"), {
            "bank_name": "Banco Nuevo Modal", "country": "RD", "currency": "USD",
            "account_holder": "Budun SRL", "account_number": "9999888877776666",
            "account_type": "", "is_active": "on", "priority": "0", "notes": "",
        }, follow=True)
        self.assertContains(respuesta, "Cuenta bancaria creada.")
        self.assertTrue(BankAccount.objects.filter(account_number="9999888877776666").exists())

    def test_filtro_enmascarar_cuenta_no_toca_el_valor_real_solo_la_presentacion(self):
        self.assertEqual(enmascarar_cuenta("1015236789015616"), "····5616")
        self.assertEqual(enmascarar_cuenta("123"), "123")
        self.assertEqual(enmascarar_cuenta(""), "")


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


class RevisionVisualFaseCTests(TestCase):
    """FASE SIGUIENTE — Revisión visual SaaS vista por vista, Bloque C
    (Facturación y Pagos: Facturas, detalle de factura, Pagos,
    Transferencias, Comprobantes, Reembolsos, Notas de crédito). Cada
    test cubre una inconsistencia real encontrada y corregida durante
    la auditoría de este bloque — nunca una regla de negocio nueva."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(email="super.fasec@example.com", password="clave-de-prueba-987")
        self.client.login(username=self.superadmin.email, password="clave-de-prueba-987")

    def test_invoices_list_muestra_estado_vacio_real_cuando_no_hay_facturas(self):
        respuesta = self.client.get(reverse("billing_admin:invoices_list"))
        self.assertContains(respuesta, "Sin facturas todavía")
        self.assertContains(respuesta, "estado-vacio")

    def test_invoice_detail_muestra_el_desglose_real_de_totales_y_periodo(self):
        """Hallazgo real: `SaaSInvoice` tiene subtotal/discount_total/
        tax_total/total/period_start/period_end/issue_date, pero
        invoice_detail.html solo mostraba el total en el encabezado —
        nunca el desglose ni el período facturado."""
        from apps.billing.services import invoicing as invoicing_services
        from apps.billing.services import subscriptions as subscription_services

        from ._helpers_saas import crear_plan_con_version, crear_saas_customer

        tenant, owner = crear_tenant_con_owner(slug="tenant-desglose-factura")
        plan, version = crear_plan_con_version(slug="plan-desglose-factura", precio=Decimal("50.00"))
        saas_customer = crear_saas_customer(email="cliente.desglose@example.com")
        subscription = subscription_services.create_subscription(tenant, saas_customer=saas_customer, plan_version=version)
        invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription)
        respuesta = self.client.get(reverse("billing_admin:invoice_detail", args=[invoice.pk]))
        contenido = respuesta.content.decode()
        self.assertIn("Subtotal", contenido)
        self.assertIn("50.00 USD", contenido)
        # La plantilla renderiza la fecha ya localizada (es-ES, ej. "14 de
        # septiembre de 2026"), nunca el ISO crudo de `str(date)` — se
        # compara contra el mismo formateador que usa el template.
        from django.utils.formats import date_format

        self.assertIn(date_format(invoice.period_start), contenido)

    def test_payments_list_muestra_estado_vacio_real_cuando_no_hay_pagos(self):
        respuesta = self.client.get(reverse("billing_admin:payments_list"))
        self.assertContains(respuesta, "Sin pagos todavía")
        self.assertContains(respuesta, "estado-vacio")

    def test_payments_list_muestra_fecha_y_referencia_reales(self):
        """Hallazgo real: `SaaSPayment.external_reference`/`received_at`
        existían en el modelo pero nunca se mostraban en el listado."""
        from apps.billing.models import SaaSPayment
        from apps.billing.services import payments as payment_services

        from ._helpers_saas import crear_saas_customer

        tenant, owner = crear_tenant_con_owner(slug="tenant-pago-referencia")
        saas_customer = crear_saas_customer(email="cliente.pago.referencia@example.com")
        payment = payment_services.record_payment(
            tenant=tenant, saas_customer=saas_customer, method=SaaSPayment.Method.MANUAL_OTHER,
            amount=Decimal("29.00"), currency="USD", external_reference="REF-AUDITORIA-001",
            status=SaaSPayment.Status.PENDING,
        )
        payment_services.confirm_payment(payment)
        respuesta = self.client.get(reverse("billing_admin:payments_list"))
        self.assertContains(respuesta, "REF-AUDITORIA-001")

    def test_payments_list_reembolsar_usa_modal_de_confirmacion_no_envio_directo(self):
        """"Reembolsar total" ya no envía el formulario en un solo clic —
        abre un modal de confirmación (mismo patrón que Suspender/
        Cancelar de tenant_detail.html, Bloque A). El formulario real
        sigue apuntando al mismo endpoint, sin cambios de vista."""
        from apps.billing.models import SaaSPayment
        from apps.billing.services import payments as payment_services

        from ._helpers_saas import crear_saas_customer

        tenant, owner = crear_tenant_con_owner(slug="tenant-pago-modal-reembolso")
        saas_customer = crear_saas_customer(email="cliente.pago.modal@example.com")
        payment = payment_services.record_payment(
            tenant=tenant, saas_customer=saas_customer, method=SaaSPayment.Method.MANUAL_OTHER,
            amount=Decimal("29.00"), currency="USD", status=SaaSPayment.Status.PENDING,
        )
        payment_services.confirm_payment(payment)
        respuesta = self.client.get(reverse("billing_admin:payments_list"))
        contenido = respuesta.content.decode()
        self.assertIn(f'data-modal-open="modal-reembolsar-{payment.pk}"', contenido)
        self.assertIn(f'id="modal-reembolsar-{payment.pk}"', contenido)
        self.assertIn(reverse("billing_admin:request_refund", args=[payment.pk]), contenido)

    def test_transfers_queue_muestra_fecha_y_cuenta_bancaria_reales(self):
        """Hallazgo real: `PaymentProof.uploaded_at`/`bank_account` nunca
        aparecían como columna en la cola de transferencias."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.billing.models import BankAccount
        from apps.billing.services import invoicing as invoicing_services
        from apps.billing.services import subscriptions as subscription_services
        from apps.billing.services import transfers as transfer_services

        from ._helpers_saas import crear_plan_con_version, crear_saas_customer

        tenant, owner = crear_tenant_con_owner(slug="tenant-cola-transferencia")
        plan, version = crear_plan_con_version(slug="plan-cola-transferencia")
        saas_customer = crear_saas_customer(email="cliente.cola.transferencia@example.com")
        subscription = subscription_services.create_subscription(tenant, saas_customer=saas_customer, plan_version=version)
        invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription)
        bank_account = BankAccount.objects.create(
            bank_name="Banco Auditoria", country="RD", currency="USD", account_holder="Budun ERP", account_number="1111",
        )
        transfer_services.submit_payment_proof(
            subscription=subscription, invoice=invoice, bank_account=bank_account,
            declared_amount=invoice.total, declared_currency="USD",
            file=SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )
        respuesta = self.client.get(reverse("billing_admin:transfers_queue"))
        self.assertContains(respuesta, "Banco Auditoria")
        # FASE 6 — "Revisar" pasó de contorno gris a azul sólido (btn--primario),
        # mismo destino real (proof_detail), solo cambia la presentación.
        self.assertContains(respuesta, 'class="btn btn--primario btn--sm"')

    def test_transfers_queue_estado_vacio_sin_emoji(self):
        """Hallazgo real: el barrido de emojis de la FASE REDISEÑO VISUAL
        MAESTRO usaba un regex que no cubría el bloque Dingbats y dejó
        pasar el ✅ de este estado vacío — corregido a
        {% icono "check-circulo" %} durante la auditoría de Bloque C."""
        respuesta = self.client.get(reverse("billing_admin:transfers_queue"))
        contenido = respuesta.content.decode()
        self.assertIn("Sin transferencias pendientes", contenido)
        self.assertNotIn("✅", contenido)
        self.assertIn("icono-svg", contenido)

    def test_transfers_queue_usa_titulo_corto_y_boton_revisar_azul_solido(self):
        """FASE 6 — implementación visual: el diseño Stitch final aprobado
        (editado manualmente por el usuario) acorta el título a
        "Transferencias" y cambia "Revisar" de contorno gris a azul sólido
        (`btn--primario`) — mismo enlace/URL/destino real, solo cambia la
        presentación."""
        respuesta = self.client.get(reverse("billing_admin:transfers_queue"))
        contenido = respuesta.content.decode()
        self.assertIn("<h1>Transferencias</h1>", contenido)
        self.assertNotIn("Transferencias por verificar", contenido)

    def test_proof_detail_aprobar_usa_modal_de_confirmacion(self):
        """"Aprobar" ya no es un envío directo de un clic — abre un modal
        de confirmación; "Rechazar" sigue igual (ya exige escribir un
        motivo). El envío POST real (`accion=aprobar`) sigue funcionando
        exactamente igual que antes — cero cambios en la vista."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.billing.models import BankAccount, PaymentProof
        from apps.billing.services import invoicing as invoicing_services
        from apps.billing.services import subscriptions as subscription_services
        from apps.billing.services import transfers as transfer_services

        from ._helpers_saas import crear_plan_con_version, crear_saas_customer

        tenant, owner = crear_tenant_con_owner(slug="tenant-modal-aprobar")
        plan, version = crear_plan_con_version(slug="plan-modal-aprobar")
        saas_customer = crear_saas_customer(email="cliente.modal.aprobar@example.com")
        subscription = subscription_services.create_subscription(tenant, saas_customer=saas_customer, plan_version=version)
        invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription)
        bank_account = BankAccount.objects.create(
            bank_name="Banco Modal", country="RD", currency="USD", account_holder="Budun ERP", account_number="2222",
        )
        proof = transfer_services.submit_payment_proof(
            subscription=subscription, invoice=invoice, bank_account=bank_account,
            declared_amount=invoice.total, declared_currency="USD",
            file=SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )
        respuesta = self.client.get(reverse("billing_admin:proof_detail", args=[proof.pk]))
        contenido = respuesta.content.decode()
        self.assertIn('data-modal-open="modal-aprobar-comprobante"', contenido)
        self.assertIn('id="modal-aprobar-comprobante"', contenido)
        respuesta_post = self.client.post(reverse("billing_admin:proof_detail", args=[proof.pk]), {"accion": "aprobar"})
        self.assertRedirects(respuesta_post, reverse("billing_admin:proof_detail", args=[proof.pk]))
        proof.refresh_from_db()
        self.assertEqual(proof.status, PaymentProof.Status.APPROVED)

    def test_refunds_list_muestra_estado_vacio_real_cuando_no_hay_reembolsos(self):
        respuesta = self.client.get(reverse("billing_admin:refunds_list"))
        self.assertContains(respuesta, "Sin reembolsos todavía")
        self.assertContains(respuesta, "estado-vacio")

    def test_refunds_list_muestra_fecha_y_motivo_reales(self):
        """Hallazgo real: `BillingRefund.created_at`/`reason` existían en
        el modelo pero nunca se mostraban en el listado."""
        from apps.billing.models import SaaSPayment
        from apps.billing.services import payments as payment_services
        from apps.billing.services import refunds as refund_services

        from ._helpers_saas import crear_saas_customer

        tenant, owner = crear_tenant_con_owner(slug="tenant-reembolso-motivo")
        saas_customer = crear_saas_customer(email="cliente.reembolso.motivo@example.com")
        payment = payment_services.record_payment(
            tenant=tenant, saas_customer=saas_customer, method=SaaSPayment.Method.MANUAL_OTHER,
            amount=Decimal("29.00"), currency="USD", status=SaaSPayment.Status.PENDING,
        )
        payment_services.confirm_payment(payment)
        refund_services.request_billing_refund(payment, reason="Cliente canceló por error", user=self.superadmin)
        respuesta = self.client.get(reverse("billing_admin:refunds_list"))
        self.assertContains(respuesta, "Cliente canceló por error")

    def test_refunds_list_marcar_completado_usa_modal_de_confirmacion(self):
        """"Marcar completado" (reembolso manual, sin reversión posible)
        ya no es un envío directo de un clic — mismo patrón de modal ya
        aplicado a Reembolsar/Aprobar/Suspender/Cancelar."""
        from apps.billing.models import SaaSPayment
        from apps.billing.services import payments as payment_services
        from apps.billing.services import refunds as refund_services

        from ._helpers_saas import crear_saas_customer

        tenant, owner = crear_tenant_con_owner(slug="tenant-reembolso-modal")
        saas_customer = crear_saas_customer(email="cliente.reembolso.modal@example.com")
        payment = payment_services.record_payment(
            tenant=tenant, saas_customer=saas_customer, method=SaaSPayment.Method.MANUAL_OTHER,
            amount=Decimal("29.00"), currency="USD", status=SaaSPayment.Status.PENDING,
        )
        payment_services.confirm_payment(payment)
        refund = refund_services.request_billing_refund(payment, reason="Prueba modal", user=self.superadmin)
        respuesta = self.client.get(reverse("billing_admin:refunds_list"))
        contenido = respuesta.content.decode()
        self.assertIn(f'data-modal-open="modal-completar-{refund.pk}"', contenido)
        self.assertIn(f'id="modal-completar-{refund.pk}"', contenido)
        self.assertIn(reverse("billing_admin:complete_refund", args=[refund.pk]), contenido)

    # NOTA (retiro de Notas de crédito del SaaS Super Admin): las pruebas
    # `test_credit_notes_list_muestra_estado_vacio_real_cuando_no_hay_notas` y
    # `test_credit_notes_list_muestra_saldo_disponible_y_estado_real` probaban
    # `CreditNotesListView`/`billing_admin:credit_notes_list`, retirados junto con el
    # resto de la UI manual de Notas de crédito del Super Admin.
