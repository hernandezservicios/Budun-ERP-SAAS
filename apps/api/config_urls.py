from django.urls import path

from . import config_views

app_name = "api_config"

urlpatterns = [
    path("", config_views.ApiKeyConfigView.as_view(), name="config"),
    path("generar/", config_views.ApiKeyGenerateView.as_view(), name="generate"),
    path("rotar/", config_views.ApiKeyRotateView.as_view(), name="rotate"),
    path("revocar/", config_views.ApiKeyRevokeView.as_view(), name="revoke"),
    path("scopes/", config_views.ApiKeyScopesUpdateView.as_view(), name="update_scopes"),
    path("probar-conexion/", config_views.ApiKeyTestConnectionView.as_view(), name="test_connection"),
]
