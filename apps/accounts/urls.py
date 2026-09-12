from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("registro/", views.RegisterView.as_view(), name="registro"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.AccountLogoutView.as_view(), name="logout"),
    path("onboarding/", views.OnboardingView.as_view(), name="onboarding"),
    path("perfil/", views.ProfileView.as_view(), name="perfil"),
    path(
        "password/reset/",
        views.AccountPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password/reset/enviado/",
        views.AccountPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "password/reset/confirmar/<uidb64>/<token>/",
        views.AccountPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/completado/",
        views.AccountPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path(
        "password/cambiar/",
        views.AccountPasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "password/cambiar/completado/",
        views.AccountPasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path(
        "activacion/<uidb64>/<token>/",
        views.AccountActivationConfirmView.as_view(),
        name="activacion_confirmar",
    ),
    path(
        "activacion/completada/",
        views.AccountActivationCompleteView.as_view(),
        name="activacion_completada",
    ),
]
