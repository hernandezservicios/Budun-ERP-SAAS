from datetime import date, timedelta
from decimal import Decimal

from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.customers.tests._helpers import PDF_VALIDO
from apps.expenses import services
from apps.expenses.models import Expense, ExpenseCategory, ExpenseDocument, ExpenseRecurrence
from apps.tenants.models import Membership, Tenant

from ._helpers import ExpensesTestCase


class ExpenseHttpFlowTests(ExpensesTestCase):
    def test_flujo_completo_via_http(self):
        respuesta = self.owner_client.post(reverse("expenses:expense_create"), {
            "category": self.categoria.pk, "supplier": "", "description": "Internet oficina",
            "expense_date": date.today().isoformat(), "due_date": "", "currency": "USD",
            "amount": "100", "tax_amount": "18", "discount_amount": "0",
            "preferred_payment_method": "transfer", "is_exceptional": "", "exceptional_reason": "", "notes": "",
        })
        gasto = Expense.all_objects.get(tenant=self.tenant, description="Internet oficina")
        self.assertRedirects(respuesta, reverse("expenses:expense_detail", args=[gasto.pk]))
        self.assertEqual(gasto.total, Decimal("118"))

        respuesta = self.owner_client.get(reverse("expenses:expense_detail", args=[gasto.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, gasto.number)

        respuesta = self.owner_client.post(reverse("expenses:expense_submit", args=[gasto.pk]))
        self.assertRedirects(respuesta, reverse("expenses:expense_detail", args=[gasto.pk]))
        gasto.refresh_from_db()
        self.assertEqual(gasto.status, Expense.Status.PENDING_APPROVAL)

        respuesta = self.owner_client.post(reverse("expenses:expense_approve", args=[gasto.pk]))
        gasto.refresh_from_db()
        self.assertEqual(gasto.status, Expense.Status.APPROVED)

        respuesta = self.owner_client.post(reverse("expenses:expense_payment_add", args=[gasto.pk]), {
            "method": "transfer", "amount": "118", "reference": "", "notes": "",
        })
        self.assertRedirects(respuesta, reverse("expenses:expense_detail", args=[gasto.pk]))
        gasto.refresh_from_db()
        self.assertEqual(gasto.status, Expense.Status.PAID)

    def test_miembro_sin_politica_recibe_advertencia_de_autorizacion(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.empleado, description="x",
            expense_date=date.today(), amount=Decimal("50"),
        )
        gasto = services.submit_expense_for_approval(gasto, self.empleado)
        respuesta = self.client.post(reverse("expenses:expense_approve", args=[gasto.pk]))
        self.assertRedirects(respuesta, reverse("expenses:expense_detail", args=[gasto.pk]))
        gasto.refresh_from_db()
        self.assertEqual(gasto.status, Expense.Status.PENDING_APPROVAL)
        mensajes = [str(m) for m in get_messages(respuesta.wsgi_request)]
        self.assertTrue(any("autorización" in m for m in mensajes), mensajes)

    def test_rechazar_gasto_via_http(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="x",
            expense_date=date.today(), amount=Decimal("10"),
        )
        gasto = services.submit_expense_for_approval(gasto, self.owner)
        self.owner_client.post(reverse("expenses:expense_reject", args=[gasto.pk]), {"reason": "sin comprobante"})
        gasto.refresh_from_db()
        self.assertEqual(gasto.status, Expense.Status.REJECTED)

    def test_cancelar_gasto_via_http(self):
        gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="x",
            expense_date=date.today(), amount=Decimal("10"),
        )
        self.owner_client.post(reverse("expenses:expense_cancel", args=[gasto.pk]), {"reason": "duplicado"})
        gasto.refresh_from_db()
        self.assertEqual(gasto.status, Expense.Status.CANCELED)



class ExpenseDocumentHttpTests(ExpensesTestCase):
    def setUp(self):
        super().setUp()
        self.gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="Con recibo",
            expense_date=date.today(), amount=Decimal("50"),
        )

    def test_subir_descargar_y_eliminar_documento(self):
        archivo = SimpleUploadedFile("recibo.pdf", PDF_VALIDO, content_type="application/pdf")
        respuesta = self.owner_client.post(reverse("expenses:expense_document_upload", args=[self.gasto.pk]), {
            "file": archivo, "category": "comprobante", "notes": "",
        })
        self.assertRedirects(respuesta, reverse("expenses:expense_detail", args=[self.gasto.pk]))
        documento = ExpenseDocument.all_objects.get(tenant=self.tenant, expense=self.gasto)
        self.assertEqual(documento.original_filename, "recibo.pdf")

        respuesta = self.owner_client.get(
            reverse("expenses:expense_document_download", args=[self.gasto.pk, documento.pk])
        )
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.owner_client.post(
            reverse("expenses:expense_document_delete", args=[self.gasto.pk, documento.pk])
        )
        self.assertRedirects(respuesta, reverse("expenses:expense_detail", args=[self.gasto.pk]))
        self.assertFalse(ExpenseDocument.all_objects.filter(pk=documento.pk).exists())

    def test_archivo_disfrazado_es_rechazado(self):
        archivo = SimpleUploadedFile("virus.pdf", b"MZ\x90\x00", content_type="application/pdf")
        self.owner_client.post(reverse("expenses:expense_document_upload", args=[self.gasto.pk]), {
            "file": archivo, "category": "comprobante", "notes": "",
        })
        self.assertEqual(ExpenseDocument.all_objects.filter(tenant=self.tenant, expense=self.gasto).count(), 0)


class ExpenseCategoryHttpTests(ExpensesTestCase):
    def test_crear_categoria_via_http(self):
        respuesta = self.owner_client.post(reverse("expenses:category_list"), {"name": "Viáticos", "description": ""})
        self.assertRedirects(respuesta, reverse("expenses:category_list"))
        self.assertTrue(ExpenseCategory.all_objects.filter(tenant=self.tenant, name="Viáticos").exists())

    def test_generar_categorias_sugeridas_via_http(self):
        respuesta = self.owner_client.post(reverse("expenses:category_seed_defaults"))
        self.assertRedirects(respuesta, reverse("expenses:category_list"))
        self.assertEqual(
            ExpenseCategory.all_objects.filter(tenant=self.tenant).count(), len(services.DEFAULT_EXPENSE_CATEGORIES)
        )

    def test_activar_desactivar_categoria_via_http(self):
        respuesta = self.owner_client.post(reverse("expenses:category_toggle", args=[self.categoria.pk]))
        self.assertRedirects(respuesta, reverse("expenses:category_list"))
        self.categoria.refresh_from_db()
        self.assertFalse(self.categoria.is_active)


class ExpenseRecurrenceHttpTests(ExpensesTestCase):
    def test_crear_y_generar_recurrencia_via_http(self):
        respuesta = self.owner_client.post(reverse("expenses:recurrence_list"), {
            "category": self.categoria.pk, "supplier": "", "description": "Internet mensual", "amount": "50",
            "currency": "USD", "frequency": "monthly", "start_date": (date.today() - timedelta(days=1)).isoformat(),
            "end_date": "", "notes": "",
        })
        self.assertRedirects(respuesta, reverse("expenses:recurrence_list"))
        recurrencia = ExpenseRecurrence.all_objects.get(tenant=self.tenant, description="Internet mensual")

        respuesta = self.owner_client.post(reverse("expenses:recurrence_generate"))
        self.assertRedirects(respuesta, reverse("expenses:recurrence_list"))
        self.assertTrue(Expense.all_objects.filter(tenant=self.tenant, source_recurrence=recurrencia).exists())

    def test_pausar_y_reanudar_recurrencia_via_http(self):
        recurrencia = services.create_expense_recurrence(
            self.tenant, category=self.categoria, description="x", amount=Decimal("10"),
            frequency=ExpenseRecurrence.Frequency.WEEKLY, start_date=date.today(), user=self.owner,
        )
        self.owner_client.post(reverse("expenses:recurrence_pause", args=[recurrencia.pk]))
        recurrencia.refresh_from_db()
        self.assertEqual(recurrencia.status, ExpenseRecurrence.Status.PAUSED)
        self.owner_client.post(reverse("expenses:recurrence_resume", args=[recurrencia.pk]))
        recurrencia.refresh_from_db()
        self.assertEqual(recurrencia.status, ExpenseRecurrence.Status.ACTIVE)


class ExpenseMultiTenantHttpTests(ExpensesTestCase):
    def setUp(self):
        super().setUp()
        self.gasto = services.create_expense(
            self.tenant, category=self.categoria, user=self.owner, description="Gasto A",
            expense_date=date.today(), amount=Decimal("10"),
        )
        self.tenant_b = Tenant.objects.create(name="Empresa Gastos B", slug="empresa-gastos-b")
        self.owner_b = self._crear_owner_b()

    def _crear_owner_b(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        owner_b = User.objects.create_user(email="owner.gastos.b@example.com", password="clave-de-prueba-987")
        Membership.objects.create(user=owner_b, tenant=self.tenant_b, role=Membership.Role.OWNER)
        return owner_b

    def test_tenant_b_no_puede_ver_gasto_de_tenant_a(self):
        client_b = self.client_class()
        client_b.login(username="owner.gastos.b@example.com", password="clave-de-prueba-987")
        respuesta = client_b.get(reverse("expenses:expense_detail", args=[self.gasto.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_tenant_b_no_puede_aprobar_gasto_de_tenant_a(self):
        gasto = services.submit_expense_for_approval(self.gasto, self.owner)
        client_b = self.client_class()
        client_b.login(username="owner.gastos.b@example.com", password="clave-de-prueba-987")
        respuesta = client_b.post(reverse("expenses:expense_approve", args=[gasto.pk]))
        self.assertEqual(respuesta.status_code, 404)
