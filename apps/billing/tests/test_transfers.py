from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.billing.models import BankAccount, PaymentProof
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import subscriptions as subscription_services
from apps.billing.services import transfers as services
from apps.tenants.models import Tenant

from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


def _comprobante_pdf(nombre="comprobante.pdf"):
    return SimpleUploadedFile(nombre, b"%PDF-1.4\n%%EOF", content_type="application/pdf")


class PaymentProofFlowTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription  # todavía PENDING — el flujo de transferencia activa después de aprobar.
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(self.subscription)
        self.bank_account = BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD", account_holder="Budun ERP", account_number="0000111122223333",
        )

    def test_enviar_comprobante_deja_tenant_pending_payment(self):
        proof = services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(),
        )
        self.assertEqual(proof.status, PaymentProof.Status.SUBMITTED)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.PENDING_PAYMENT)
        self.assertTrue(self.tenant.billing_status_blocks_operation)

    def test_aprobar_comprobante_activa_suscripcion_y_tenant(self):
        proof = services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(),
        )
        proof, payment = services.approve_payment_proof(proof)
        self.assertEqual(proof.status, PaymentProof.Status.APPROVED)
        self.assertIsNotNone(payment)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "paid")
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, "active")
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)

    def test_rechazar_comprobante_nunca_activa_el_tenant(self):
        proof = services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(),
        )
        proof = services.reject_payment_proof(proof, reason="comprobante ilegible")
        self.assertEqual(proof.status, PaymentProof.Status.REJECTED)
        self.tenant.refresh_from_db()
        self.assertNotEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)

    def test_referencias_son_unicas_por_tenant(self):
        referencia = services.generate_transfer_reference(self.tenant)
        proof = services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(), reference=referencia,
        )
        self.assertEqual(proof.reference, referencia)
        with self.assertRaises(Exception):
            services.submit_payment_proof(
                subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
                declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(), reference=referencia,
            )

    def test_archivo_disfrazado_es_rechazado(self):
        archivo_falso = SimpleUploadedFile("comprobante.pdf", b"MZ\x90\x00", content_type="application/pdf")
        with self.assertRaises(Exception):
            services.submit_payment_proof(
                subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
                declared_amount=self.invoice.total, declared_currency="USD", file=archivo_falso,
            )

    def test_list_pending_proofs_solo_lista_enviados_o_en_revision(self):
        proof = services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(),
        )
        self.assertIn(proof, list(services.list_pending_proofs()))
        services.approve_payment_proof(proof)
        self.assertNotIn(proof, list(services.list_pending_proofs()))
