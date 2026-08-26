from decimal import Decimal

from apps.audit import services
from apps.audit.models import AuditLog
from apps.customers.models import ActivityLog as CustomersActivityLog
from apps.inventory import services as inv_services
from apps.inventory.models import Product

from ._helpers import AuditTestCase


class LogEventTests(AuditTestCase):
    def test_log_event_crea_una_fila_inmutable(self):
        evento = services.log_event(
            self.tenant, user=self.owner, action=AuditLog.Action.GENERIC, domain="pruebas",
            object_type="algo", object_id=42, reason="motivo de prueba",
        )
        # `AuditTestCase.setUp` ya inicia sesión con `owner_client`/
        # `employee_client`, lo que genera sus propios eventos LOGIN
        # reales (ver `apps.audit.signals`) — se filtra por `action`
        # para aislar exactamente la fila creada por este test.
        self.assertEqual(AuditLog.objects.filter(tenant=self.tenant, action=AuditLog.Action.GENERIC).count(), 1)
        self.assertEqual(evento.object_id, "42")
        self.assertEqual(evento.domain, "pruebas")

    def test_log_event_acepta_tenant_none(self):
        evento = services.log_event(None, action=AuditLog.Action.LOGIN_FAILED, domain="auth")
        self.assertIsNone(evento.tenant)

    def test_log_event_nunca_guarda_mas_de_255_caracteres_de_user_agent(self):
        evento = services.log_event(
            self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas", user_agent="x" * 500,
        )
        self.assertEqual(len(evento.user_agent), 255)


class SearchAuditEventsTests(AuditTestCase):
    def setUp(self):
        super().setUp()
        self.producto = Product.objects.create(
            tenant=self.tenant, name="Producto Auditoría", sku="AUD-1", sale_price=Decimal("10.00"),
        )

    def test_busqueda_federa_auditlog_y_activitylog_de_otro_dominio(self):
        # Línea base DESPUÉS de `setUp` (que ya generó sus propios
        # eventos LOGIN reales al autenticar los clientes de prueba) —
        # se verifica el INCREMENTO, no un total absoluto.
        total_base = services.search_audit_events(self.tenant)["total"]
        services.log_event(self.tenant, user=self.owner, action=AuditLog.Action.GENERIC, domain="pruebas")
        CustomersActivityLog.all_objects.create(
            tenant=self.tenant, entity_type="customer", entity_id=1, entity_label="Cliente X",
            action=CustomersActivityLog.Action.CREATED, user=self.owner,
        )
        resultado = services.search_audit_events(self.tenant)
        fuentes = {fila["source"] for fila in resultado["rows"]}
        self.assertIn("audit", fuentes)
        self.assertIn("customers", fuentes)
        self.assertEqual(resultado["total"] - total_base, 2)

    def test_busqueda_federa_movimientos_de_inventario(self):
        inv_services.register_stock_in(product=self.producto, quantity=Decimal("5"), user=self.owner)
        resultado = services.search_audit_events(self.tenant, source="inventory")
        self.assertEqual(resultado["total"], 1)
        self.assertEqual(resultado["rows"][0]["source"], "inventory")
        self.assertEqual(resultado["rows"][0]["label"], "Producto Auditoría")

    def test_filtro_por_source_excluye_otras_fuentes(self):
        total_base = services.search_audit_events(self.tenant, source="audit")["total"]
        services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas")
        CustomersActivityLog.all_objects.create(
            tenant=self.tenant, entity_type="customer", entity_id=1, entity_label="Cliente X",
            action=CustomersActivityLog.Action.CREATED, user=self.owner,
        )
        resultado = services.search_audit_events(self.tenant, source="audit")
        self.assertEqual(resultado["total"] - total_base, 1)
        self.assertTrue(all(fila["source"] == "audit" for fila in resultado["rows"]))

    def test_filtro_por_texto_busca_en_label_y_resumen(self):
        CustomersActivityLog.all_objects.create(
            tenant=self.tenant, entity_type="customer", entity_id=1, entity_label="Cliente Único Rodríguez",
            action=CustomersActivityLog.Action.CREATED, user=self.owner,
        )
        resultado = services.search_audit_events(self.tenant, q="Rodríguez")
        self.assertEqual(resultado["total"], 1)
        resultado_vacio = services.search_audit_events(self.tenant, q="NoExiste")
        self.assertEqual(resultado_vacio["total"], 0)

    def test_paginacion_respeta_limit_y_offset(self):
        for indice in range(5):
            services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas", object_id=indice)
        # `action=GENERIC` aísla exactamente las 5 filas creadas, sin
        # contar los eventos LOGIN reales que ya generó `setUp`.
        resultado = services.search_audit_events(self.tenant, action=AuditLog.Action.GENERIC, limit=2, offset=0)
        self.assertEqual(len(resultado["rows"]), 2)
        self.assertEqual(resultado["total"], 5)

    def test_busqueda_nunca_mezcla_eventos_de_otro_tenant(self):
        from apps.tenants.models import Tenant

        total_base = services.search_audit_events(self.tenant)["total"]
        otro_tenant = Tenant.objects.create(name="Otra Empresa Auditoría", slug="otra-empresa-auditoria")
        services.log_event(otro_tenant, action=AuditLog.Action.GENERIC, domain="pruebas")
        services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas")
        resultado = services.search_audit_events(self.tenant)
        self.assertEqual(resultado["total"] - total_base, 1)


class GetEventDetailTests(AuditTestCase):
    def test_get_event_detail_recupera_fila_completa_de_auditlog(self):
        evento = services.log_event(self.tenant, action=AuditLog.Action.GENERIC, domain="pruebas", reason="motivo")
        detalle = services.get_event_detail(self.tenant, source="audit", row_id=evento.pk)
        self.assertEqual(detalle.reason, "motivo")

    def test_get_event_detail_recupera_fila_de_un_activitylog_legado(self):
        fila = CustomersActivityLog.all_objects.create(
            tenant=self.tenant, entity_type="customer", entity_id=1, entity_label="Cliente X",
            action=CustomersActivityLog.Action.CREATED, user=self.owner,
        )
        detalle = services.get_event_detail(self.tenant, source="customers", row_id=fila.pk)
        self.assertEqual(detalle.entity_label, "Cliente X")

    def test_get_event_detail_nunca_cruza_tenant(self):
        from apps.tenants.models import Tenant

        otro_tenant = Tenant.objects.create(name="Otra Empresa Auditoría 2", slug="otra-empresa-auditoria-2")
        evento = services.log_event(otro_tenant, action=AuditLog.Action.GENERIC, domain="pruebas")
        detalle = services.get_event_detail(self.tenant, source="audit", row_id=evento.pk)
        self.assertIsNone(detalle)
