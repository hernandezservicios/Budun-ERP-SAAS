from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    # Gastos
    path("", views.ExpenseListView.as_view(), name="expense_list"),
    path("nuevo/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("<int:pk>/", views.ExpenseDetailView.as_view(), name="expense_detail"),
    path("<int:pk>/editar/", views.ExpenseEditView.as_view(), name="expense_edit"),
    path("<int:pk>/enviar/", views.ExpenseSubmitView.as_view(), name="expense_submit"),
    path("<int:pk>/aprobar/", views.ExpenseApproveView.as_view(), name="expense_approve"),
    path("<int:pk>/rechazar/", views.ExpenseRejectView.as_view(), name="expense_reject"),
    path("<int:pk>/cancelar/", views.ExpenseCancelView.as_view(), name="expense_cancel"),
    # Pagos
    path("<int:pk>/pagos/agregar/", views.ExpensePaymentAddView.as_view(), name="expense_payment_add"),
    path("<int:pk>/pagos/<int:payment_pk>/anular/", views.ExpensePaymentVoidView.as_view(), name="expense_payment_void"),
    # Documentos
    path("<int:pk>/documentos/subir/", views.ExpenseDocumentUploadView.as_view(), name="expense_document_upload"),
    path("<int:pk>/documentos/<int:document_pk>/eliminar/", views.ExpenseDocumentDeleteView.as_view(), name="expense_document_delete"),
    path("<int:pk>/documentos/<int:document_pk>/descargar/", views.ExpenseDocumentDownloadView.as_view(), name="expense_document_download"),
    # Categorías
    path("categorias/", views.ExpenseCategoryListView.as_view(), name="category_list"),
    path("categorias/sugeridas/", views.ExpenseCategorySeedDefaultsView.as_view(), name="category_seed_defaults"),
    path("categorias/<int:pk>/activar-desactivar/", views.ExpenseCategoryToggleView.as_view(), name="category_toggle"),
    # Gastos recurrentes
    path("recurrencias/", views.ExpenseRecurrenceListView.as_view(), name="recurrence_list"),
    path("recurrencias/generar/", views.ExpenseRecurrenceGenerateView.as_view(), name="recurrence_generate"),
    path("recurrencias/<int:pk>/pausar/", views.ExpenseRecurrencePauseView.as_view(), name="recurrence_pause"),
    path("recurrencias/<int:pk>/reanudar/", views.ExpenseRecurrenceResumeView.as_view(), name="recurrence_resume"),
    path("recurrencias/<int:pk>/cancelar/", views.ExpenseRecurrenceCancelView.as_view(), name="recurrence_cancel"),
]
