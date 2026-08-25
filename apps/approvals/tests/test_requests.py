from decimal import Decimal

from django.urls import reverse

from apps.approvals import services
from apps.approvals.models import ApprovalRequest

from ._helpers import ApprovalsTestCase


class ApprovalRequestServiceTests(ApprovalsTestCase):
    def test_request_approval_crea_pending(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member,
            requested_value=Decimal("50"), allowed_limit=Decimal("10"), reason="prueba",
        )
        self.assertEqual(solicitud.status, ApprovalRequest.Status.PENDING)

    def test_resolve_approval_aprobada(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member,
            requested_value=Decimal("50"),
        )
        resuelta = services.resolve_approval(solicitud, approved=True, user=self.owner, approved_value=Decimal("40"))
        self.assertEqual(resuelta.status, ApprovalRequest.Status.APPROVED)
        self.assertEqual(resuelta.approved_value, Decimal("40"))
        self.assertEqual(resuelta.approved_by, self.owner)
        self.assertIsNotNone(resuelta.decided_at)

    def test_resolve_approval_rechazada(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member, requested_value=Decimal("50"),
        )
        resuelta = services.resolve_approval(solicitud, approved=False, user=self.owner, decision_reason="No procede")
        self.assertEqual(resuelta.status, ApprovalRequest.Status.REJECTED)
        self.assertIsNone(resuelta.approved_value)

    def test_resolve_approval_sin_permiso_es_rechazado(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member, requested_value=Decimal("50"),
        )
        with self.assertRaises(services.InvalidApprovalOperation):
            services.resolve_approval(solicitud, approved=True, user=self.member)

    def test_resolve_approval_ya_resuelta_es_error_no_idempotente(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member, requested_value=Decimal("50"),
        )
        services.resolve_approval(solicitud, approved=True, user=self.owner, approved_value=Decimal("50"))
        with self.assertRaises(services.InvalidApprovalOperation):
            services.resolve_approval(solicitud, approved=False, user=self.owner)

    def test_cancel_approval_es_idempotente(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member, requested_value=Decimal("50"),
        )
        services.cancel_approval(solicitud, self.member)
        cancelada_otra_vez = services.cancel_approval(solicitud, self.member)
        self.assertEqual(cancelada_otra_vez.status, ApprovalRequest.Status.CANCELED)

    def test_mark_consumed_solo_funciona_sobre_aprobadas(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member, requested_value=Decimal("50"),
        )
        with self.assertRaises(services.InvalidApprovalOperation):
            services.mark_consumed(solicitud, self.owner)

    def test_mark_consumed_no_se_puede_repetir(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member, requested_value=Decimal("50"),
        )
        services.resolve_approval(solicitud, approved=True, user=self.owner, approved_value=Decimal("50"))
        services.mark_consumed(solicitud, self.member)
        with self.assertRaises(services.InvalidApprovalOperation):
            services.mark_consumed(solicitud, self.member)

    def test_get_usable_approved_request_solo_devuelve_no_consumidas(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member,
            requested_value=Decimal("50"), document_type="sale", document_id=1,
        )
        services.resolve_approval(solicitud, approved=True, user=self.owner, approved_value=Decimal("50"))
        encontrada = services.get_usable_approved_request(self.tenant, action_type="discount", document_type="sale", document_id=1)
        self.assertEqual(encontrada, solicitud)
        services.mark_consumed(solicitud, self.member)
        self.assertIsNone(services.get_usable_approved_request(self.tenant, action_type="discount", document_type="sale", document_id=1))


class ApprovalHttpViewTests(ApprovalsTestCase):
    def test_lista_de_pendientes_200(self):
        respuesta = self.client.get(reverse("approvals:pending_list"))
        self.assertEqual(respuesta.status_code, 200)

    def test_miembro_sin_permiso_no_puede_resolver_via_http(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member, requested_value=Decimal("50"),
        )
        respuesta = self.client.post(reverse("approvals:approval_resolve", args=[solicitud.pk]), {"decision": "approve"})
        self.assertEqual(respuesta.status_code, 403)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.status, ApprovalRequest.Status.PENDING)

    def test_propietario_puede_resolver_via_http(self):
        solicitud = services.request_approval(
            self.tenant, action_type=ApprovalRequest.ActionType.DISCOUNT, requested_by=self.member, requested_value=Decimal("50"),
        )
        respuesta = self.owner_client.post(reverse("approvals:approval_resolve", args=[solicitud.pk]), {
            "decision": "approve", "approved_value": "50", "decision_reason": "",
        })
        self.assertEqual(respuesta.status_code, 302)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.status, ApprovalRequest.Status.APPROVED)

    def test_miembro_no_puede_ver_politicas(self):
        respuesta = self.client.get(reverse("approvals:policy_list"))
        self.assertEqual(respuesta.status_code, 403)

    def test_propietario_puede_configurar_politica_de_rol(self):
        respuesta = self.owner_client.post(reverse("approvals:role_policy_set"), {
            "role": "member", "max_discount_percent": "10", "max_discount_amount": "100",
            "max_credit_overage": "0", "can_approve": "on", "notes": "",
        })
        self.assertEqual(respuesta.status_code, 302)
        from apps.approvals.models import ApprovalPolicy

        self.assertTrue(ApprovalPolicy.all_objects.filter(tenant=self.tenant, scope="role", role="member").exists())
