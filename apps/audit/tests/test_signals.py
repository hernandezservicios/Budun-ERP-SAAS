from apps.audit.models import AuditLog

from ._helpers import AuditTestCase


class LoginSignalTests(AuditTestCase):
    def test_login_exitoso_genera_evento_con_tenant_resuelto(self):
        cliente = self.client_class()
        cliente.login(username="owner.auditoria@example.com", password="clave-de-prueba-987")
        evento = AuditLog.objects.filter(action=AuditLog.Action.LOGIN, user=self.owner).first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.tenant, self.tenant)
        self.assertEqual(evento.domain, "auth")

    def test_login_fallido_no_guarda_contrasena(self):
        cliente = self.client_class()
        cliente.login(username="owner.auditoria@example.com", password="clave-incorrecta")
        evento = AuditLog.objects.filter(action=AuditLog.Action.LOGIN_FAILED).first()
        self.assertIsNotNone(evento)
        self.assertIsNone(evento.user)
        for valor in evento.metadata.values():
            self.assertNotEqual(valor, "clave-incorrecta")
        self.assertNotIn("password", evento.metadata)

    def test_login_fallido_de_email_inexistente_no_tiene_tenant(self):
        cliente = self.client_class()
        cliente.login(username="no.existe@example.com", password="lo-que-sea")
        evento = AuditLog.objects.filter(action=AuditLog.Action.LOGIN_FAILED).order_by("-created_at").first()
        self.assertIsNotNone(evento)
        self.assertIsNone(evento.tenant)

    def test_logout_genera_evento(self):
        cliente = self.client_class()
        cliente.login(username="owner.auditoria@example.com", password="clave-de-prueba-987")
        cliente.logout()
        evento = AuditLog.objects.filter(action=AuditLog.Action.LOGOUT, user=self.owner).first()
        self.assertIsNotNone(evento)
