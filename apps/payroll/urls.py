from django.urls import path

from . import views

app_name = "payroll"

urlpatterns = [
    path("periodos/", views.PayrollPeriodListView.as_view(), name="period_list"),
    path("periodos/<int:pk>/", views.PayrollPeriodDetailView.as_view(), name="period_detail"),
    path("periodos/<int:pk>/aprobar/", views.PayrollPeriodApproveView.as_view(), name="period_approve"),
    path("periodos/<int:pk>/cancelar/", views.PayrollPeriodCancelView.as_view(), name="period_cancel"),
    path("periodos/<int:pk>/cerrar/", views.PayrollPeriodCloseView.as_view(), name="period_close"),
    path("periodos/<int:pk>/calcular/", views.PayrollCalculateView.as_view(), name="payroll_calculate"),
    path("nominas/<int:pk>/", views.PayrollDetailView.as_view(), name="payroll_detail"),
    path("nominas/<int:pk>/lineas/agregar/", views.PayrollLineAddView.as_view(), name="payroll_line_add"),
    path("nominas/<int:pk>/pagos/agregar/", views.PayrollPaymentAddView.as_view(), name="payroll_payment_add"),
    path("nominas/<int:pk>/pagos/<int:payment_pk>/anular/", views.PayrollPaymentVoidView.as_view(), name="payroll_payment_void"),
]
