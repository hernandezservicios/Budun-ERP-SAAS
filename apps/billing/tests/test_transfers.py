from datetime import timedelta
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
        # FASE DE CORRECCIÓN 2: usa una SEGUNDA factura del mismo tenant
        # (período distinto) a propósito — reenviar sobre la MISMA
        # factura ya lo bloquea el nuevo guard de "comprobante pendiente
        # duplicado" (ver `test_no_permite_un_segundo_comprobante_
        # mientras_uno_sigue_pendiente` más abajo), y esta prueba
        # necesita aislar específicamente la unicidad de referencia
        # (`UniqueConstraint(tenant, reference)`), no esa otra regla.
        segunda_factura, _creada = invoicing_services.generate_invoice_for_subscription(
            self.subscription, period_start=self.invoice.period_end, period_end=self.invoice.period_end + timedelta(days=30),
        )
        referencia = services.generate_transfer_reference(self.tenant)
        proof = services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(), reference=referencia,
        )
        self.assertEqual(proof.reference, referencia)
        with self.assertRaises(Exception):
            services.submit_payment_proof(
                subscription=self.subscription, invoice=segunda_factura, bank_account=self.bank_account,
                declared_amount=segunda_factura.total, declared_currency="USD", file=_comprobante_pdf(), reference=referencia,
            )

    def test_no_permite_un_segundo_comprobante_mientras_uno_sigue_pendiente(self):
        services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(),
        )
        with self.assertRaises(services.InvalidTransferOperation):
            services.submit_payment_proof(
                subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
                declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(),
            )
        self.assertEqual(PaymentProof.all_objects.filter(invoice=self.invoice).count(), 1)

    def test_no_permite_comprobante_para_factura_ya_pagada(self):
        proof = services.submit_payment_proof(
            subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
            declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(),
        )
        services.approve_payment_proof(proof)
        self.invoice.refresh_from_db()
        with self.assertRaises(services.InvalidTransferOperation):
            services.submit_payment_proof(
                subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
                declared_amount=self.invoice.total, declared_currency="USD", file=_comprobante_pdf(),
            )

    def test_rechaza_monto_declarado_invalido(self):
        with self.assertRaises(services.InvalidTransferOperation):
            services.submit_payment_proof(
                subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
                declared_amount=Decimal("0"), declared_currency="USD", file=_comprobante_pdf(),
            )

    def test_rechaza_moneda_declarada_que_no_coincide_con_la_cuenta(self):
        with self.assertRaises(services.InvalidTransferOperation):
            services.submit_payment_proof(
                subscription=self.subscription, invoice=self.invoice, bank_account=self.bank_account,
                declared_amount=self.invoice.total, declared_currency="EUR", file=_comprobante_pdf(),
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

    def test_aprobar_comprobante_sobre_suscripcion_suspendida_reactiva_no_activa(self):
        # FASE DE CORRECCIÓN 3: `ACTIVATE != REACTIVATE` — aprobar un
        # comprobante de transferencia sobre una suscripción SUSPENDED
        # debe usar `reactivate_subscription` (restaura el período si ya
        # venció), nunca el primitivo de activación INICIAL.
        from datetime import date

        subscription_services.activate_subscription(self.subscription)
        self.subscription.current_period_start = date(2026, 1, 1)
        self.subscription.current_period_end = date(2026, 1, 31)
        self.subscription.save(update_fields=["current_period_start", "current_period_end"])
        subscription_services.suspend_subscription(self.subscription)
        vencida, _creada = invoicing_services.generate_invoice_for_subscription(
            self.subscription, period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        )

        proof = services.submit_payment_proof(
            subscription=self.subscription, invoice=vencida, bank_account=self.bank_account,
            declared_amount=vencida.total, declared_currency="USD", file=_comprobante_pdf(),
        )
        services.approve_payment_proof(proof)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, "active")
        # El período se restauró a partir de hoy — ya no es el vencido de enero 2026.
        self.assertNotEqual(self.subscription.current_period_end, date(2026, 1, 31))
