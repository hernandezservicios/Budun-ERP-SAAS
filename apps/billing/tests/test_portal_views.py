from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.billing import services as billing_services
from apps.billing.models import (
    BankAccount,
    PaymentProof,
    PayPalTransaction,
    SaaSInvoice,
    SaaSPayment,
    SaaSPaymentAllocation,
    Subscription,
    Tenant,
)
from apps.billing.services import invoicing as invoicing_services
from apps.billing.services import subscriptions as subscription_services
from apps.tenants.models import Membership
from apps.sales.models import Payment as SalesPayment

from ._helpers import fake_provider
from ._helpers_saas import crear_plan_con_version, crear_saas_customer, crear_tenant_con_owner


def _comprobante_pdf(nombre="comprobante.pdf"):
    return SimpleUploadedFile(nombre, b"%PDF-1.4\n%%EOF", content_type="application/pdf")


class PortalStatusViewTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_sin_suscripcion_muestra_estado_vacio(self):
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Elegir un plan")

    def test_anonimo_redirige_a_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertEqual(respuesta.status_code, 302)


class SelectPlanViewTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        # FASE DE CORRECCIÓN 2 (Billing del Tenant): "transferencia
        # bancaria" solo está disponible si existe al menos una cuenta
        # activa (`services.transfers.is_bank_transfer_available`) —
        # sin esto, `SelectPlanForm` ya no ofrecería esa opción y
        # `test_elegir_plan_con_transferencia_crea_suscripcion_e_invoice`
        # fallaría por diseño (comportamiento correcto, no un bug).
        BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD", account_holder="Budun ERP", account_number="0000",
        )
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_elegir_plan_con_transferencia_crea_suscripcion_e_invoice(self):
        respuesta = self.client.post(reverse("billing_portal:select_plan"), {
            "plan_version": self.version.pk, "payment_method": "bank_transfer", "coupon_code": "",
        })
        self.assertEqual(Subscription.all_objects.filter(tenant=self.tenant).count(), 1)
        invoice = SaaSInvoice.all_objects.filter(tenant=self.tenant).first()
        self.assertIsNotNone(invoice)
        self.assertRedirects(respuesta, reverse("billing_portal:transfer_instructions", args=[invoice.pk]))

    def test_elegir_plan_con_paypal_redirige_a_iniciar_cobro(self):
        respuesta = self.client.post(reverse("billing_portal:select_plan"), {
            "plan_version": self.version.pk, "payment_method": "paypal", "coupon_code": "",
        })
        invoice = SaaSInvoice.all_objects.filter(tenant=self.tenant).first()
        # `fetch_redirect_response=False`: el destino en sí mismo es OTRO
        # redirect (a PayPal), nunca un 200 — no hay nada que renderizar ahí.
        self.assertRedirects(
            respuesta, reverse("billing_portal:checkout_paypal_initiate", args=[invoice.pk]), fetch_redirect_response=False,
        )

    def test_checkout_paypal_initiate_redirige_a_paypal(self):
        self.client.post(reverse("billing_portal:select_plan"), {
            "plan_version": self.version.pk, "payment_method": "paypal", "coupon_code": "",
        })
        invoice = SaaSInvoice.all_objects.filter(tenant=self.tenant).first()
        with fake_provider():
            respuesta = self.client.get(reverse("billing_portal:checkout_paypal_initiate", args=[invoice.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith("https://sandbox.paypal.test/approve/"))

    def test_checkout_paypal_return_confirma_pago_y_activa(self):
        with fake_provider():
            self.client.post(reverse("billing_portal:select_plan"), {
                "plan_version": self.version.pk, "payment_method": "paypal", "coupon_code": "",
            })
            invoice = SaaSInvoice.all_objects.filter(tenant=self.tenant).first()
            self.client.get(reverse("billing_portal:checkout_paypal_initiate", args=[invoice.pk]))
            from apps.billing.models import PayPalTransaction

            txn = PayPalTransaction.objects.filter(tenant=self.tenant).first()
            respuesta = self.client.get(
                reverse("billing_portal:checkout_paypal_return", args=[invoice.pk]), {"token": txn.external_order_id},
            )
        self.assertRedirects(respuesta, reverse("billing_portal:status"))
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, "active")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SaaSInvoice.Status.PAID)


class PaymentMethodAvailabilityTests(TestCase):
    """FASE DE CORRECCIÓN 2 (Billing del Tenant) — causa raíz: el Portal
    mostraba/ocultaba métodos de pago SIN mirar la configuración real
    (`services.is_paypal_available`/`services.transfers.
    is_bank_transfer_available`). Estas pruebas fijan el comportamiento
    correcto en ambos puntos donde el Portal decide qué mostrar: la
    tabla de facturas de `/facturacion/` y el formulario de
    `/facturacion/elegir-plan/`."""

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription)
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_paypal_visible_en_estado_cuando_el_gateway_esta_habilitado(self):
        # `PayPalGatewayStatus.is_enabled` es `True` por defecto (fila
        # creada al vuelo por `get_or_create`) — ningún setup adicional.
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertContains(respuesta, "Pagar con PayPal")

    def test_paypal_oculto_en_estado_cuando_el_gateway_esta_deshabilitado(self):
        billing_services.set_gateway_enabled(is_enabled=False, user=self.owner)
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertNotContains(respuesta, "Pagar con PayPal")

    def test_transferencia_oculta_en_estado_sin_ninguna_cuenta_bancaria_activa(self):
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertNotContains(respuesta, "Pagar mediante transferencia bancaria")

    def test_transferencia_visible_en_estado_con_una_cuenta_bancaria_activa(self):
        BankAccount.objects.create(bank_name="Banco de Prueba", currency="USD", account_holder="Budun ERP", account_number="0000")
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertContains(respuesta, "Pagar mediante transferencia bancaria")

    def test_sin_ningun_metodo_disponible_no_ofrece_ningun_boton_de_pago(self):
        billing_services.set_gateway_enabled(is_enabled=False, user=self.owner)
        respuesta = self.client.get(reverse("billing_portal:status"))
        self.assertNotContains(respuesta, "Pagar con PayPal")
        self.assertNotContains(respuesta, "Pagar mediante transferencia bancaria")
        self.assertContains(respuesta, "Sin métodos de pago disponibles")

    def test_elegir_plan_no_ofrece_paypal_si_el_gateway_esta_deshabilitado(self):
        billing_services.set_gateway_enabled(is_enabled=False, user=self.owner)
        respuesta = self.client.get(reverse("billing_portal:select_plan"))
        self.assertNotContains(respuesta, 'value="paypal"')

    def test_elegir_plan_no_ofrece_transferencia_sin_ninguna_cuenta_bancaria_activa(self):
        respuesta = self.client.get(reverse("billing_portal:select_plan"))
        self.assertNotContains(respuesta, 'value="bank_transfer"')

    def test_elegir_plan_ofrece_ambos_metodos_cuando_ambos_estan_configurados(self):
        BankAccount.objects.create(bank_name="Banco de Prueba", currency="USD", account_holder="Budun ERP", account_number="0000")
        respuesta = self.client.get(reverse("billing_portal:select_plan"))
        self.assertContains(respuesta, 'value="paypal"')
        self.assertContains(respuesta, 'value="bank_transfer"')


class PayPendingInvoiceFromStatusPageTests(TestCase):
    """Escenario nuevo de la Corrección 2: pagar una factura YA
    PENDIENTE desde `/facturacion/` (no recién creada por
    `select_plan`) — verifica el ciclo completo Invoice -> PayPal ->
    capture -> SaaSPayment -> Allocation -> Invoice PAID -> Subscription
    ACTIVE -> Tenant ACTIVE -> acceso al ERP, y que NUNCA se crea un
    `apps.sales.Payment` (dominio completamente separado)."""

    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription)
        # `crear_tenant_con_owner` deja `billing_status=ACTIVE` por
        # defecto (compatibilidad con tenants pre-FASE 17, ver el
        # modelo) — el escenario real que esta corrección soluciona es
        # un tenant creado por Venta Manual, que SÍ queda explícitamente
        # `PENDING_PAYMENT` con una factura real esperando pago.
        self.tenant.billing_status = Tenant.BillingStatus.PENDING_PAYMENT
        self.tenant.save(update_fields=["billing_status"])
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_pagar_con_paypal_una_factura_pendiente_completa_todo_el_ciclo(self):
        # El acceso al ERP sigue bloqueado ANTES de pagar (tenant
        # todavía no ACTIVE) — BillingStatusMiddleware, sin cambios.
        respuesta_antes = self.client.get(reverse("dashboard:panel"))
        self.assertRedirects(respuesta_antes, reverse("billing_portal:status"))

        with fake_provider():
            respuesta_iniciar = self.client.get(reverse("billing_portal:checkout_paypal_initiate", args=[self.invoice.pk]))
            self.assertEqual(respuesta_iniciar.status_code, 302)
            self.assertTrue(respuesta_iniciar.url.startswith("https://sandbox.paypal.test/approve/"))

            txn = PayPalTransaction.objects.get(tenant=self.tenant)
            respuesta_retorno = self.client.get(
                reverse("billing_portal:checkout_paypal_return", args=[self.invoice.pk]), {"token": txn.external_order_id},
            )
        self.assertRedirects(respuesta_retorno, reverse("billing_portal:status"))

        pago = SaaSPayment.all_objects.get(tenant=self.tenant)
        self.assertEqual(pago.status, SaaSPayment.Status.CONFIRMED)
        self.assertEqual(pago.method, SaaSPayment.Method.PAYPAL)
        self.assertTrue(SaaSPaymentAllocation.all_objects.filter(payment=pago, invoice=self.invoice).exists())

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PAID)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)

        # SaaS Billing y ERP Operational Payments son dominios
        # separados — este flujo NUNCA debe crear un apps.sales.Payment.
        self.assertEqual(SalesPayment.all_objects.count(), 0)

        # Ahora sí, acceso al ERP.
        respuesta_despues = self.client.get(reverse("dashboard:panel"))
        self.assertEqual(respuesta_despues.status_code, 200)

    def test_pagar_con_transferencia_una_factura_pendiente_completa_todo_el_ciclo(self):
        bank_account = BankAccount.objects.create(bank_name="Banco de Prueba", currency="USD", account_holder="Budun ERP", account_number="0000")
        respuesta_subir = self.client.post(reverse("billing_portal:transfer_instructions", args=[self.invoice.pk]), {
            "bank_account": bank_account.pk, "declared_amount": str(self.invoice.total), "declared_currency": "USD",
            "declared_bank_name": "Mi Banco", "file": _comprobante_pdf(),
        })
        self.assertRedirects(respuesta_subir, reverse("billing_portal:status"))

        proof = PaymentProof.all_objects.get(invoice=self.invoice)
        from apps.billing.services import transfers as transfer_services

        transfer_services.approve_payment_proof(proof)  # acción de Super Admin, sin cambios en esta corrección.

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SaaSInvoice.Status.PAID)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, Subscription.Status.ACTIVE)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_status, Tenant.BillingStatus.ACTIVE)
        self.assertEqual(SalesPayment.all_objects.count(), 0)

        respuesta_despues = self.client.get(reverse("dashboard:panel"))
        self.assertEqual(respuesta_despues.status_code, 200)

        # La factura pagada ya no ofrece ningún botón de pago.
        respuesta_estado = self.client.get(reverse("billing_portal:status"))
        self.assertNotContains(respuesta_estado, "Pagar con PayPal")
        self.assertNotContains(respuesta_estado, "Pagar mediante transferencia bancaria")


class TransferInstructionsViewTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription
        self.invoice, _creada = invoicing_services.generate_invoice_for_subscription(subscription)
        from apps.billing.models import BankAccount

        self.bank_account = BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD", account_holder="Budun ERP", account_number="0000",
        )
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_subir_comprobante_deja_pendiente_de_verificacion(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        respuesta = self.client.post(reverse("billing_portal:transfer_instructions", args=[self.invoice.pk]), {
            "bank_account": self.bank_account.pk, "declared_amount": "29.00", "declared_currency": "USD",
            "declared_bank_name": "Mi Banco", "file": SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        })
        self.assertRedirects(respuesta, reverse("billing_portal:status"))
        self.assertEqual(PaymentProof.all_objects.filter(tenant=self.tenant).count(), 1)

    def test_comprobante_con_archivo_disfrazado_es_rechazado(self):
        archivo_falso = SimpleUploadedFile("comprobante.pdf", b"MZ\x90\x00", content_type="application/pdf")
        respuesta = self.client.post(reverse("billing_portal:transfer_instructions", args=[self.invoice.pk]), {
            "bank_account": self.bank_account.pk, "declared_amount": "29.00", "declared_currency": "USD",
            "declared_bank_name": "Mi Banco", "file": archivo_falso,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(PaymentProof.all_objects.filter(tenant=self.tenant).count(), 0)

    def test_monto_declarado_invalido_es_rechazado(self):
        respuesta = self.client.post(reverse("billing_portal:transfer_instructions", args=[self.invoice.pk]), {
            "bank_account": self.bank_account.pk, "declared_amount": "0.00", "declared_currency": "USD",
            "declared_bank_name": "Mi Banco", "file": _comprobante_pdf(),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["form"].is_valid())
        self.assertEqual(PaymentProof.all_objects.filter(tenant=self.tenant).count(), 0)

    def test_moneda_declarada_invalida_es_rechazada(self):
        respuesta = self.client.post(reverse("billing_portal:transfer_instructions", args=[self.invoice.pk]), {
            "bank_account": self.bank_account.pk, "declared_amount": "29.00", "declared_currency": "EUR",
            "declared_bank_name": "Mi Banco", "file": _comprobante_pdf(),
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(PaymentProof.all_objects.filter(tenant=self.tenant).count(), 0)

    def test_factura_inexistente_da_404(self):
        respuesta = self.client.get(reverse("billing_portal:transfer_instructions", args=[999999]))
        self.assertEqual(respuesta.status_code, 404)

    def test_no_permite_un_segundo_comprobante_mientras_uno_sigue_pendiente(self):
        self.client.post(reverse("billing_portal:transfer_instructions", args=[self.invoice.pk]), {
            "bank_account": self.bank_account.pk, "declared_amount": "29.00", "declared_currency": "USD",
            "declared_bank_name": "Mi Banco", "file": _comprobante_pdf(),
        })
        respuesta_duplicada = self.client.post(reverse("billing_portal:transfer_instructions", args=[self.invoice.pk]), {
            "bank_account": self.bank_account.pk, "declared_amount": "29.00", "declared_currency": "USD",
            "declared_bank_name": "Mi Banco", "file": _comprobante_pdf(),
        })
        self.assertEqual(respuesta_duplicada.status_code, 200)
        self.assertEqual(PaymentProof.all_objects.filter(tenant=self.tenant).count(), 1)

    def test_un_miembro_sin_permiso_de_gestionar_billing_no_puede_subir_comprobante(self):
        miembro = self._crear_miembro_admin()
        self.client.logout()
        self.client.login(username=miembro.email, password="clave-de-prueba-987")
        respuesta = self.client.post(reverse("billing_portal:transfer_instructions", args=[self.invoice.pk]), {
            "bank_account": self.bank_account.pk, "declared_amount": "29.00", "declared_currency": "USD",
            "declared_bank_name": "Mi Banco", "file": _comprobante_pdf(),
        })
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(PaymentProof.all_objects.filter(tenant=self.tenant).count(), 0)

    def _crear_miembro_admin(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        miembro = User.objects.create_user(email="admin.sin.billing@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=miembro, tenant=self.tenant, role=Membership.Role.ADMIN)
        return miembro


class ChangePlanAndCancelViewTests(TestCase):
    def setUp(self):
        self.tenant, self.owner = crear_tenant_con_owner()
        self.plan, self.version = crear_plan_con_version(precio=Decimal("29.00"))
        self.saas_customer = crear_saas_customer()
        subscription = subscription_services.create_subscription(self.tenant, saas_customer=self.saas_customer, plan_version=self.version)
        self.subscription = subscription_services.activate_subscription(subscription)
        self.client.login(username=self.owner.email, password="clave-de-prueba-987")

    def test_cambiar_plan(self):
        _plan2, version2 = crear_plan_con_version(slug="otro-plan", precio=Decimal("60.00"))
        respuesta = self.client.post(reverse("billing_portal:change_plan"), {"plan_version": version2.pk})
        self.assertRedirects(respuesta, reverse("billing_portal:status"))
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version, version2)

    def test_cancelar_al_finalizar_periodo(self):
        respuesta = self.client.post(reverse("billing_portal:cancel"), {"reason": "prueba"})
        self.assertRedirects(respuesta, reverse("billing_portal:status"))
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.cancel_at_period_end)


class PortalMultiTenantIsolationTests(TestCase):
    """FASE 18 — Security Hardening. Ninguno de los endpoints del
    Portal de Facturación que reciben `invoice_id` en la URL existía
    con una prueba explícita de aislamiento Multi-Tenant — se agrega
    aquí: el tenant B nunca debe poder ver ni operar sobre una factura
    del tenant A manipulando el ID en la URL (IDOR)."""

    def setUp(self):
        self.tenant_a, self.owner_a = crear_tenant_con_owner(
            name="Empresa Portal A", slug="empresa-portal-a", email="portal.a@example.com"
        )
        self.tenant_b, self.owner_b = crear_tenant_con_owner(
            name="Empresa Portal B", slug="empresa-portal-b", email="portal.b@example.com"
        )
        self.plan, self.version = crear_plan_con_version()
        self.saas_customer = crear_saas_customer()
        subscription_a = subscription_services.create_subscription(
            self.tenant_a, saas_customer=self.saas_customer, plan_version=self.version
        )
        self.invoice_a, _creada = invoicing_services.generate_invoice_for_subscription(subscription_a)

        from apps.billing.models import BankAccount

        self.bank_account = BankAccount.objects.create(
            bank_name="Banco de Prueba", country="RD", currency="USD",
            account_holder="Budun ERP", account_number="0000",
        )
        # Autenticado como el OWNER del tenant B — intenta acceder a
        # recursos de la factura del tenant A.
        self.client.login(username=self.owner_b.email, password="clave-de-prueba-987")

    def test_ver_instrucciones_de_transferencia_de_factura_de_otro_tenant_da_404(self):
        respuesta = self.client.get(
            reverse("billing_portal:transfer_instructions", args=[self.invoice_a.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_subir_comprobante_para_factura_de_otro_tenant_da_404_y_no_crea_nada(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        respuesta = self.client.post(
            reverse("billing_portal:transfer_instructions", args=[self.invoice_a.pk]),
            {
                "bank_account": self.bank_account.pk, "declared_amount": "29.00",
                "declared_currency": "USD", "declared_bank_name": "Mi Banco",
                "file": SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
            },
        )
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(PaymentProof.all_objects.filter(invoice=self.invoice_a).count(), 0)

    def test_iniciar_cobro_paypal_de_factura_de_otro_tenant_da_404(self):
        respuesta = self.client.get(
            reverse("billing_portal:checkout_paypal_initiate", args=[self.invoice_a.pk])
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_retorno_paypal_de_factura_de_otro_tenant_da_404(self):
        respuesta = self.client.get(
            reverse("billing_portal:checkout_paypal_return", args=[self.invoice_a.pk]),
            {"token": "cualquier-token"},
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_cancelar_pago_paypal_de_factura_de_otro_tenant_da_404(self):
        respuesta = self.client.get(
            reverse("billing_portal:checkout_paypal_cancel", args=[self.invoice_a.pk]),
            {"token": "cualquier-token"},
        )
        self.assertEqual(respuesta.status_code, 404)
