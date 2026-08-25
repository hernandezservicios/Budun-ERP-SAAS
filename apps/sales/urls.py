from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    # --- Cotizaciones ---
    path("cotizaciones/", views.QuotationListView.as_view(), name="quotation_list"),
    path("cotizaciones/nueva/", views.QuotationCreateView.as_view(), name="quotation_create"),
    path("cotizaciones/<int:pk>/", views.QuotationDetailView.as_view(), name="quotation_detail"),
    path("cotizaciones/<int:pk>/lineas/agregar/", views.QuotationItemAddView.as_view(), name="quotation_item_add"),
    path("cotizaciones/<int:pk>/lineas/<int:item_pk>/eliminar/", views.QuotationItemDeleteView.as_view(), name="quotation_item_delete"),
    path("cotizaciones/<int:pk>/estado/", views.QuotationStatusView.as_view(), name="quotation_status"),
    path("cotizaciones/<int:pk>/convertir-proforma/", views.QuotationConvertToProformaView.as_view(), name="quotation_convert_proforma"),
    path("cotizaciones/<int:pk>/convertir-venta/", views.QuotationConvertToSaleView.as_view(), name="quotation_convert_sale"),
    path("cotizaciones/<int:pk>/duplicar/", views.QuotationDuplicateView.as_view(), name="quotation_duplicate"),
    path("cotizaciones/<int:pk>/imprimir/", views.QuotationPrintView.as_view(), name="quotation_print"),
    path("cotizaciones/<int:pk>/adjuntos/subir/", views.QuotationAttachmentUploadView.as_view(), name="quotation_attachment_upload"),
    path("cotizaciones/<int:pk>/adjuntos/<int:attachment_pk>/eliminar/", views.QuotationAttachmentDeleteView.as_view(), name="quotation_attachment_delete"),
    path("cotizaciones/<int:pk>/adjuntos/<int:attachment_pk>/descargar/", views.QuotationAttachmentDownloadView.as_view(), name="quotation_attachment_download"),

    # --- Proformas ---
    path("proformas/", views.ProformaListView.as_view(), name="proforma_list"),
    path("proformas/nueva/", views.ProformaCreateView.as_view(), name="proforma_create"),
    path("proformas/<int:pk>/", views.ProformaDetailView.as_view(), name="proforma_detail"),
    path("proformas/<int:pk>/lineas/agregar/", views.ProformaItemAddView.as_view(), name="proforma_item_add"),
    path("proformas/<int:pk>/lineas/<int:item_pk>/eliminar/", views.ProformaItemDeleteView.as_view(), name="proforma_item_delete"),
    path("proformas/<int:pk>/estado/", views.ProformaStatusView.as_view(), name="proforma_status"),
    path("proformas/<int:pk>/reservar-stock/", views.ProformaReserveStockView.as_view(), name="proforma_reserve_stock"),
    path("proformas/<int:pk>/convertir-venta/", views.ProformaConvertToSaleView.as_view(), name="proforma_convert_sale"),
    path("proformas/<int:pk>/imprimir/", views.ProformaPrintView.as_view(), name="proforma_print"),
    path("proformas/<int:pk>/adjuntos/subir/", views.ProformaAttachmentUploadView.as_view(), name="proforma_attachment_upload"),
    path("proformas/<int:pk>/adjuntos/<int:attachment_pk>/eliminar/", views.ProformaAttachmentDeleteView.as_view(), name="proforma_attachment_delete"),
    path("proformas/<int:pk>/adjuntos/<int:attachment_pk>/descargar/", views.ProformaAttachmentDownloadView.as_view(), name="proforma_attachment_download"),

    # --- Ventas / Facturas ---
    path("ventas/", views.SaleListView.as_view(), name="sale_list"),
    path("ventas/nueva/", views.SaleCreateView.as_view(), name="sale_create"),
    path("ventas/<int:pk>/", views.SaleDetailView.as_view(), name="sale_detail"),
    path("ventas/<int:pk>/lineas/agregar/", views.SaleItemAddView.as_view(), name="sale_item_add"),
    path("ventas/<int:pk>/lineas/<int:item_pk>/eliminar/", views.SaleItemDeleteView.as_view(), name="sale_item_delete"),
    path("ventas/<int:pk>/confirmar/", views.SaleConfirmView.as_view(), name="sale_confirm"),
    path("ventas/<int:pk>/cancelar/", views.SaleCancelView.as_view(), name="sale_cancel"),
    path("ventas/<int:pk>/pagos/agregar/", views.SalePaymentAddView.as_view(), name="sale_payment_add"),
    path("ventas/<int:pk>/pagos/<int:payment_pk>/anular/", views.SalePaymentVoidView.as_view(), name="sale_payment_void"),
    path("ventas/<int:pk>/devolucion/nueva/", views.SaleReturnCreateView.as_view(), name="sale_return_create"),
    path("ventas/<int:pk>/recibo/", views.SaleReceiptView.as_view(), name="sale_receipt"),
    path("ventas/<int:pk>/adjuntos/subir/", views.SaleAttachmentUploadView.as_view(), name="sale_attachment_upload"),
    path("ventas/<int:pk>/adjuntos/<int:attachment_pk>/eliminar/", views.SaleAttachmentDeleteView.as_view(), name="sale_attachment_delete"),
    path("ventas/<int:pk>/adjuntos/<int:attachment_pk>/descargar/", views.SaleAttachmentDownloadView.as_view(), name="sale_attachment_download"),

    # --- Reservas ---
    path("reservas/", views.ReservationListView.as_view(), name="reservation_list"),
    path("reservas/<int:pk>/liberar/", views.ReservationReleaseView.as_view(), name="reservation_release"),
]
