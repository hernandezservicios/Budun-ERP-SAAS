from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("registro/", views.RegisterView.as_view(), name="registro"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.AccountLogoutView.as_view(), name="logout"),
    path("onboarding/", views.OnboardingView.as_view(), name="onboarding"),
    path("perfil/", views.ProfileView.as_view(), name="perfil"),
]
