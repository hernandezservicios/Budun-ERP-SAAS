from django.urls import path

from . import integration_views

app_name = "api_integrations"

urlpatterns = [
    path("", integration_views.IntegrationListView.as_view(), name="list"),
    path("nueva/", integration_views.IntegrationCreateView.as_view(), name="create"),
    path("<int:pk>/", integration_views.IntegrationDetailView.as_view(), name="detail"),
    path("<int:pk>/rotar/", integration_views.IntegrationRotateView.as_view(), name="rotate"),
    path("<int:pk>/revocar/", integration_views.IntegrationRevokeView.as_view(), name="revoke"),
    path("<int:pk>/alternar/", integration_views.IntegrationToggleView.as_view(), name="toggle"),
    path("<int:pk>/scopes/", integration_views.IntegrationScopesUpdateView.as_view(), name="update_scopes"),
    path("<int:pk>/probar-conexion/", integration_views.IntegrationTestConnectionView.as_view(), name="test_connection"),
]
