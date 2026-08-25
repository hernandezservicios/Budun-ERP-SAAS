from django.urls import path

from . import views

app_name = "pos"

urlpatterns = [
    # Cajas
    path("cajas/", views.CashRegisterListView.as_view(), name="register_list"),
    path("caja/abrir/", views.CashSessionOpenView.as_view(), name="session_open"),
    path("caja/cerrar/", views.CashSessionCloseView.as_view(), name="session_close"),
    path("caja/sesiones/<int:pk>/", views.CashSessionSummaryView.as_view(), name="session_summary"),
    path("caja/movimiento/", views.CashMovementCreateView.as_view(), name="cash_movement_create"),
    # Terminal (venta)
    path("terminal/", views.TerminalStartView.as_view(), name="terminal_start"),
    path("terminal/<int:pk>/", views.TerminalDetailView.as_view(), name="terminal_detail"),
    path("terminal/<int:pk>/agregar/", views.AddItemView.as_view(), name="add_item"),
    path("terminal/<int:pk>/lineas/<int:item_pk>/eliminar/", views.RemoveItemView.as_view(), name="remove_item"),
    path("terminal/<int:pk>/cliente/", views.SetCustomerView.as_view(), name="set_customer"),
    path("terminal/<int:pk>/descuento/", views.SetGlobalDiscountView.as_view(), name="set_global_discount"),
    path("terminal/<int:pk>/cancelar/", views.CancelCartView.as_view(), name="cancel_cart"),
    path("terminal/<int:pk>/cobrar/", views.CheckoutView.as_view(), name="checkout"),
    # Cobros (cuentas por cobrar)
    path("cobros/", views.CollectionsSearchView.as_view(), name="collections_search"),
    path("cobros/<int:customer_pk>/", views.CustomerCollectionsView.as_view(), name="customer_collections"),
    path("cobros/<int:customer_pk>/cobrar/", views.CollectPaymentView.as_view(), name="collect_payment"),
    path("cobros/<int:customer_pk>/anticipo/", views.AdvanceView.as_view(), name="register_advance"),
    path("cobros/<int:customer_pk>/ventas/<int:sale_pk>/aplicar-saldo/", views.ApplyCreditView.as_view(), name="apply_credit"),
    path("cobros/<int:customer_pk>/nota-credito/emitir/", views.IssueCreditNoteView.as_view(), name="issue_credit_note"),
    path("cobros/<int:customer_pk>/pagos/<int:payment_pk>/reembolsar/", views.RefundView.as_view(), name="refund_payment"),
]
