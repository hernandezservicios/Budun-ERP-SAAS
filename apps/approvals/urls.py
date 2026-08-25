from django.urls import path

from . import views

app_name = "approvals"

urlpatterns = [
    path("autorizaciones/", views.PendingApprovalsView.as_view(), name="pending_list"),
    path("autorizaciones/<int:pk>/resolver/", views.ApprovalResolveView.as_view(), name="approval_resolve"),
    path("autorizaciones/<int:pk>/cancelar/", views.ApprovalCancelView.as_view(), name="approval_cancel"),
    path("autorizaciones/politicas/", views.PolicyListView.as_view(), name="policy_list"),
    path("autorizaciones/politicas/rol/guardar/", views.RolePolicySetView.as_view(), name="role_policy_set"),
]
