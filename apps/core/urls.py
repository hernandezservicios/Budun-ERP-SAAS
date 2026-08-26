from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("estilo/", views.design_system, name="design_system"),
    path("configuracion/", views.SettingsHomeView.as_view(), name="settings"),
]
