"""
Vistas de Gastos (FASE 13). Deliberadamente delgadas: toda la lógica
vive en `apps.expenses.services`, que a su vez consume literalmente
`apps.approvals`/`apps.pos`/`apps.customers` — esta capa solo arma el
request/response. Gasto sobre el límite o excepcional captura la
excepción correspondiente, genera automáticamente la `ApprovalRequest`
y le pide al usuario reintentar una vez que un supervisor la resuelva —
mismo patrón que `apps.pos.views`/`apps.purchases.views`, nunca un
bypass silencioso.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.approvals import services as approvals_services
from apps.approvals.models import ApprovalRequest
from apps.customers.file_validation import nombre_original_seguro
from apps.tenants.permissions import TenantRequiredMixin

from . import services
from .forms import (
    CancelExpenseForm,
    ExpenseCategoryForm,
    ExpenseDocumentForm,
    ExpenseForm,
    ExpensePaymentForm,
    ExpenseRecurrenceForm,
    RejectExpenseForm,
)
from .models import Expense, ExpenseCategory, ExpenseDocument, ExpenseRecurrence


def _mensaje_error(error):
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


# ------------------------------------------------------------------
# Gastos
# ------------------------------------------------------------------


class ExpenseListView(LoginRequiredMixin, TenantRequiredMixin, ListView):
    template_name = "expenses/expense_list.html"
    context_object_name = "gastos"
    paginate_by = 20

    def get_queryset(self):
        return services.list_expenses(
            self.request.tenant,
            status=self.request.GET.get("estado", ""),
            search=self.request.GET.get("q", "").strip(),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["estados"] = Expense.Status.choices
        context["q"] = self.request.GET.get("q", "")
        context["estado"] = self.request.GET.get("estado", "")
        return context


class ExpenseCreateView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        form = ExpenseForm(tenant=request.tenant)
        return render(request, "expenses/expense_form.html", {"form": form})

    def post(self, request):
        form = ExpenseForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                gasto = services.create_expense(request.tenant, user=request.user, **form.cleaned_data)
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
                return render(request, "expenses/expense_form.html", {"form": form})
            messages.success(request, f"Gasto «{gasto.number}» creado en borrador.")
            return redirect("expenses:expense_detail", pk=gasto.pk)
        return render(request, "expenses/expense_form.html", {"form": form})


class ExpenseDetailView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        context = {
            "gasto": gasto,
            "puede_editar": gasto.status in (Expense.Status.DRAFT, Expense.Status.REJECTED),
            "edit_form": ExpenseForm(tenant=request.tenant, initial={
                "category": gasto.category_id, "supplier": gasto.supplier_id, "description": gasto.description,
                "expense_date": gasto.expense_date, "due_date": gasto.due_date, "currency": gasto.currency,
                "amount": gasto.amount, "tax_amount": gasto.tax_amount, "discount_amount": gasto.discount_amount,
                "preferred_payment_method": gasto.preferred_payment_method, "notes": gasto.notes,
                "is_exceptional": gasto.is_exceptional, "exceptional_reason": gasto.exceptional_reason,
            }),
            "reject_form": RejectExpenseForm(),
            "cancel_form": CancelExpenseForm(),
            "payment_form": ExpensePaymentForm(),
            "document_form": ExpenseDocumentForm(),
            "pagos": services.get_expense_payments(gasto),
            "saldo_pendiente": services.get_expense_balance_due(gasto),
            "documentos": services.get_expense_documents(gasto),
            "activity_log": services.get_activity_log(request.tenant, entity_type="expense", entity_id=gasto.pk),
        }
        return render(request, "expenses/expense_detail.html", context)


class ExpenseEditView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        form = ExpenseForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            try:
                services.update_expense(gasto, request.user, **form.cleaned_data)
                messages.success(request, "Gasto actualizado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del gasto.")
        return redirect("expenses:expense_detail", pk=gasto.pk)


class ExpenseSubmitView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        try:
            services.submit_expense_for_approval(gasto, request.user)
            messages.success(request, "Gasto enviado a aprobación.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("expenses:expense_detail", pk=gasto.pk)


class ExpenseApproveView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Aprobar es la acción de negocio en sí (como "enviar" una orden de
    compra o "confirmar" una venta en POS) — cualquier miembro del
    tenant puede intentarla; `services.approve_expense` decide, según
    el límite autorizado de ESTE usuario, si se completa directamente o
    si primero exige una `ApprovalRequest` resuelta por alguien con
    permiso de aprobar (`can_user_approve`, ver `apps.approvals.views`
    — un permiso distinto, para RESOLVER esa solicitud, no para
    intentar esta acción). Mismo criterio que `apps.pos.views`/
    `apps.purchases.views`: nunca se gatea la acción en sí, solo el
    monto que excede el límite propio."""

    def post(self, request, pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        try:
            services.approve_expense(gasto, request.user)
            messages.success(request, f"Gasto «{gasto.number}» aprobado.")
        except services.ExpenseOverThresholdRequiresApproval as error:
            solicitud = approvals_services.request_approval(
                request.tenant, action_type=ApprovalRequest.ActionType.EXPENSE_OVER_THRESHOLD,
                requested_by=request.user, requested_value=gasto.total, allowed_limit=error.limit,
                document_type="expense", document_id=gasto.pk,
                reason=f"Gasto {gasto.number} excede el límite autorizado.",
            )
            messages.warning(
                request,
                f"Este gasto excede tu límite autorizado — se solicitó autorización (#{solicitud.pk}). "
                "Pide a un supervisor que la apruebe en Autorizaciones y vuelve a intentarlo.",
            )
        except services.ExpenseExceptionalRequiresApproval as error:
            solicitud = approvals_services.request_approval(
                request.tenant, action_type=ApprovalRequest.ActionType.EXPENSE_EXCEPTIONAL,
                requested_by=request.user, document_type="expense", document_id=gasto.pk,
                reason=f"Gasto excepcional: {error.reason}",
            )
            messages.warning(
                request,
                f"Este gasto es excepcional/sensible — se solicitó autorización (#{solicitud.pk}). "
                "Pide a un supervisor que la apruebe en Autorizaciones y vuelve a intentarlo.",
            )
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("expenses:expense_detail", pk=gasto.pk)


class ExpenseRejectView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        form = RejectExpenseForm(request.POST)
        reason = form.cleaned_data["reason"] if form.is_valid() else ""
        try:
            services.reject_expense(gasto, request.user, reason=reason)
            messages.success(request, "Gasto rechazado.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("expenses:expense_detail", pk=gasto.pk)


class ExpenseCancelView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        form = CancelExpenseForm(request.POST)
        reason = form.cleaned_data["reason"] if form.is_valid() else ""
        try:
            services.cancel_expense(gasto, request.user, reason=reason)
            messages.success(request, "Gasto cancelado.")
        except ValidationError as error:
            messages.error(request, _mensaje_error(error))
        return redirect("expenses:expense_detail", pk=gasto.pk)


class ExpensePaymentAddView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        form = ExpensePaymentForm(request.POST)
        if form.is_valid():
            try:
                services.record_expense_payment(request.tenant, gasto, user=request.user, **form.cleaned_data)
                messages.success(request, "Pago registrado correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa los datos del pago.")
        return redirect("expenses:expense_detail", pk=gasto.pk)


class ExpensePaymentVoidView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, payment_pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        pago = get_object_or_404(gasto.payments.model, pk=payment_pk, tenant=request.tenant, expense=gasto)
        services.void_expense_payment(pago, request.user)
        messages.success(request, "Pago anulado.")
        return redirect("expenses:expense_detail", pk=gasto.pk)


# ------------------------------------------------------------------
# Documentos adjuntos
# ------------------------------------------------------------------


class ExpenseDocumentUploadView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        form = ExpenseDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                services.register_expense_document(
                    gasto, archivo=form.cleaned_data["file"], category=form.cleaned_data["category"],
                    user=request.user, notes=form.cleaned_data["notes"],
                )
                messages.success(request, "Documento subido correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            for error_list in form.errors.values():
                for error in error_list:
                    messages.error(request, error)
        return redirect("expenses:expense_detail", pk=gasto.pk)


class ExpenseDocumentDeleteView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk, document_pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        documento = get_object_or_404(ExpenseDocument, pk=document_pk, tenant=request.tenant, expense=gasto)
        services.delete_expense_document(documento, request.user)
        messages.success(request, "Documento eliminado correctamente.")
        return redirect("expenses:expense_detail", pk=gasto.pk)


class ExpenseDocumentDownloadView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request, pk, document_pk):
        gasto = get_object_or_404(Expense, pk=pk, tenant=request.tenant)
        documento = get_object_or_404(ExpenseDocument, pk=document_pk, tenant=request.tenant, expense=gasto)
        return FileResponse(documento.file.open("rb"), as_attachment=True, filename=nombre_original_seguro(documento.original_filename))


# ------------------------------------------------------------------
# Categorías
# ------------------------------------------------------------------


class ExpenseCategoryListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {
            "categorias": services.list_expense_categories(request.tenant, only_active=False),
            "form": ExpenseCategoryForm(),
        }
        return render(request, "expenses/category_list.html", context)

    def post(self, request):
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            try:
                services.create_expense_category(request.tenant, **form.cleaned_data)
                messages.success(request, "Categoría creada correctamente.")
            except ValidationError as error:
                messages.error(request, _mensaje_error(error))
        else:
            messages.error(request, "Revisa el nombre de la categoría.")
        return redirect("expenses:category_list")


class ExpenseCategorySeedDefaultsView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request):
        creadas = services.create_default_expense_categories(request.tenant)
        if creadas:
            messages.success(request, f"Se crearon {len(creadas)} categorías sugeridas.")
        else:
            messages.info(request, "Ya existían todas las categorías sugeridas.")
        return redirect("expenses:category_list")


class ExpenseCategoryToggleView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        categoria = get_object_or_404(ExpenseCategory, pk=pk, tenant=request.tenant)
        services.set_category_active(categoria, is_active=not categoria.is_active)
        messages.success(request, "Categoría actualizada.")
        return redirect("expenses:category_list")


# ------------------------------------------------------------------
# Gastos recurrentes
# ------------------------------------------------------------------


class ExpenseRecurrenceListView(LoginRequiredMixin, TenantRequiredMixin, View):
    def get(self, request):
        context = {
            "recurrencias": ExpenseRecurrence.objects.select_related("category", "supplier").order_by("next_run_date"),
            "vencidas": services.list_due_recurrences(request.tenant),
            "form": ExpenseRecurrenceForm(tenant=request.tenant),
        }
        return render(request, "expenses/recurrence_list.html", context)

    def post(self, request):
        form = ExpenseRecurrenceForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            services.create_expense_recurrence(request.tenant, user=request.user, **form.cleaned_data)
            messages.success(request, "Gasto recurrente creado.")
        else:
            messages.error(request, "Revisa los datos de la recurrencia.")
        return redirect("expenses:recurrence_list")


class ExpenseRecurrencePauseView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        recurrencia = get_object_or_404(ExpenseRecurrence, pk=pk, tenant=request.tenant)
        services.pause_recurrence(recurrencia, request.user)
        messages.success(request, "Recurrencia pausada.")
        return redirect("expenses:recurrence_list")


class ExpenseRecurrenceResumeView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        recurrencia = get_object_or_404(ExpenseRecurrence, pk=pk, tenant=request.tenant)
        services.resume_recurrence(recurrencia, request.user)
        messages.success(request, "Recurrencia reanudada.")
        return redirect("expenses:recurrence_list")


class ExpenseRecurrenceCancelView(LoginRequiredMixin, TenantRequiredMixin, View):
    def post(self, request, pk):
        recurrencia = get_object_or_404(ExpenseRecurrence, pk=pk, tenant=request.tenant)
        services.cancel_recurrence(recurrencia, request.user)
        messages.success(request, "Recurrencia cancelada.")
        return redirect("expenses:recurrence_list")


class ExpenseRecurrenceGenerateView(LoginRequiredMixin, TenantRequiredMixin, View):
    """Genera manualmente los gastos de todas las recurrencias vencidas
    — sin infraestructura de tareas en segundo plano todavía (ver
    `CLAUDE.md`: Redis/Celery solo si una fase futura demuestra
    necesidad real), este botón es la vía profesional disponible hoy."""

    def post(self, request):
        vencidas = list(services.list_due_recurrences(request.tenant))
        generados = 0
        for recurrencia in vencidas:
            try:
                services.generate_due_expense(recurrencia, request.user)
                generados += 1
            except ValidationError:
                continue
        if generados:
            messages.success(request, f"Se generaron {generados} gasto(s) de recurrencias vencidas.")
        else:
            messages.info(request, "No hay recurrencias vencidas por generar.")
        return redirect("expenses:recurrence_list")
