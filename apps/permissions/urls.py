from django.urls import path

from . import views

app_name = "permissions"

urlpatterns = [
    path("", views.RolesIndexView.as_view(), name="index"),
    path("roles/<str:role>/", views.RolePermissionsView.as_view(), name="role_permissions"),
    path("usuarios/<int:user_id>/", views.UserOverridesView.as_view(), name="user_overrides"),
]
