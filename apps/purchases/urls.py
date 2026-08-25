from django.urls import path

from . import views

app_name = "purchases"

urlpatterns = [
    # Órdenes de compra
    path("ordenes/", views.PurchaseOrderListView.as_view(), name="purchase_order_list"),
    path("ordenes/nueva/", views.PurchaseOrderCreateView.as_view(), name="purchase_order_create"),
    path("ordenes/<int:pk>/", views.PurchaseOrderDetailView.as_view(), name="purchase_order_detail"),
    path("ordenes/<int:pk>/editar/", views.PurchaseOrderHeaderEditView.as_view(), name="purchase_order_header_edit"),
    path("ordenes/<int:pk>/lineas/agregar/", views.PurchaseOrderItemAddView.as_view(), name="purchase_order_item_add"),
    path("ordenes/<int:pk>/lineas/<int:item_pk>/eliminar/", views.PurchaseOrderItemRemoveView.as_view(), name="purchase_order_item_remove"),
    path("ordenes/<int:pk>/enviar/", views.PurchaseOrderSendView.as_view(), name="purchase_order_send"),
    path("ordenes/<int:pk>/cancelar/", views.PurchaseOrderCancelView.as_view(), name="purchase_order_cancel"),
    path("ordenes/<int:pk>/cerrar/", views.PurchaseOrderCloseView.as_view(), name="purchase_order_close"),
    # Recepción
    path("ordenes/<int:pk>/lineas/<int:item_pk>/recibir/", views.ReceivePurchaseOrderItemView.as_view(), name="receive_item"),
    # Devolución a proveedor
    path("ordenes/<int:pk>/devolucion/", views.SupplierReturnCreateView.as_view(), name="supplier_return_create"),
    # Documentos de orden de compra
    path("ordenes/<int:pk>/documentos/subir/", views.PurchaseOrderAttachmentUploadView.as_view(), name="purchase_order_attachment_upload"),
    path("ordenes/<int:pk>/documentos/<int:attachment_pk>/eliminar/", views.PurchaseOrderAttachmentDeleteView.as_view(), name="purchase_order_attachment_delete"),
    path("ordenes/<int:pk>/documentos/<int:attachment_pk>/descargar/", views.PurchaseOrderAttachmentDownloadView.as_view(), name="purchase_order_attachment_download"),
    # Facturas de proveedor / Cuentas por Pagar
    path("facturas/", views.SupplierInvoiceListView.as_view(), name="supplier_invoice_list"),
    path("facturas/nueva/", views.SupplierInvoiceCreateView.as_view(), name="supplier_invoice_create"),
    path("facturas/<int:pk>/", views.SupplierInvoiceDetailView.as_view(), name="supplier_invoice_detail"),
    path("facturas/<int:pk>/lineas/agregar/", views.SupplierInvoiceItemAddView.as_view(), name="supplier_invoice_item_add"),
    path("facturas/<int:pk>/confirmar/", views.SupplierInvoiceConfirmView.as_view(), name="supplier_invoice_confirm"),
    path("facturas/<int:pk>/cancelar/", views.SupplierInvoiceCancelView.as_view(), name="supplier_invoice_cancel"),
    path("facturas/<int:pk>/pagar/", views.SupplierInvoicePaymentView.as_view(), name="supplier_invoice_pay"),
    path("facturas/<int:pk>/aplicar-anticipo/", views.SupplierInvoiceApplyAdvanceView.as_view(), name="supplier_invoice_apply_advance"),
    path("facturas/<int:pk>/asignaciones/<int:allocation_pk>/reversar/", views.SupplierPaymentAllocationReverseView.as_view(), name="supplier_payment_allocation_reverse"),
    # Documentos de factura de proveedor
    path("facturas/<int:pk>/documentos/subir/", views.SupplierInvoiceAttachmentUploadView.as_view(), name="supplier_invoice_attachment_upload"),
    path("facturas/<int:pk>/documentos/<int:attachment_pk>/eliminar/", views.SupplierInvoiceAttachmentDeleteView.as_view(), name="supplier_invoice_attachment_delete"),
    path("facturas/<int:pk>/documentos/<int:attachment_pk>/descargar/", views.SupplierInvoiceAttachmentDownloadView.as_view(), name="supplier_invoice_attachment_download"),
    # Anticipos a proveedor
    path("proveedores/<int:supplier_pk>/anticipo/", views.SupplierAdvanceCreateView.as_view(), name="supplier_advance_create"),
]
