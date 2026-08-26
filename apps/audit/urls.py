from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.AuditSearchView.as_view(), name="search"),
    path("exportar/", views.AuditExportView.as_view(), name="export"),
    path("<str:source>/<int:row_id>/", views.AuditDetailView.as_view(), name="detail"),
]
