from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    # --- Clientes ---
    path("clientes/", views.CustomerListView.as_view(), name="customer_list"),
    path("clientes/nuevo/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("clientes/<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("clientes/<int:pk>/editar/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("clientes/<int:pk>/estado/", views.CustomerStatusView.as_view(), name="customer_status"),
    path(
        "clientes/<int:pk>/documentos/subir/",
        views.CustomerDocumentUploadView.as_view(),
        name="customer_document_upload",
    ),
    path(
        "clientes/<int:pk>/documentos/<int:document_pk>/eliminar/",
        views.CustomerDocumentDeleteView.as_view(),
        name="customer_document_delete",
    ),
    path(
        "clientes/<int:pk>/documentos/<int:document_pk>/descargar/",
        views.CustomerDocumentDownloadView.as_view(),
        name="customer_document_download",
    ),
    # --- Proveedores ---
    path("proveedores/", views.SupplierListView.as_view(), name="supplier_list"),
    path("proveedores/nuevo/", views.SupplierCreateView.as_view(), name="supplier_create"),
    path("proveedores/<int:pk>/", views.SupplierDetailView.as_view(), name="supplier_detail"),
    path("proveedores/<int:pk>/editar/", views.SupplierUpdateView.as_view(), name="supplier_update"),
    path("proveedores/<int:pk>/estado/", views.SupplierStatusView.as_view(), name="supplier_status"),
    path(
        "proveedores/<int:pk>/documentos/subir/",
        views.SupplierDocumentUploadView.as_view(),
        name="supplier_document_upload",
    ),
    path(
        "proveedores/<int:pk>/documentos/<int:document_pk>/eliminar/",
        views.SupplierDocumentDeleteView.as_view(),
        name="supplier_document_delete",
    ),
    path(
        "proveedores/<int:pk>/documentos/<int:document_pk>/descargar/",
        views.SupplierDocumentDownloadView.as_view(),
        name="supplier_document_download",
    ),
]
