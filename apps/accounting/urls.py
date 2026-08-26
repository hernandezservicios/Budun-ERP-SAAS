from django.urls import path

from . import views

app_name = "accounting"

urlpatterns = [
    # Plan de cuentas
    path("cuentas/", views.AccountListView.as_view(), name="account_list"),
    path("cuentas/<int:pk>/activar-desactivar/", views.AccountToggleView.as_view(), name="account_toggle"),
    # Períodos contables
    path("periodos/", views.AccountingPeriodListView.as_view(), name="period_list"),
    path("periodos/<int:pk>/", views.AccountingPeriodDetailView.as_view(), name="period_detail"),
    path("periodos/<int:pk>/cerrar/", views.AccountingPeriodCloseView.as_view(), name="period_close"),
    path("periodos/<int:pk>/reabrir/", views.AccountingPeriodReopenView.as_view(), name="period_reopen"),
    # Asientos contables
    path("asientos/", views.JournalEntryListView.as_view(), name="journal_entry_list"),
    path("asientos/nuevo/", views.JournalEntryCreateView.as_view(), name="journal_entry_create"),
    path("asientos/<int:pk>/", views.JournalEntryDetailView.as_view(), name="journal_entry_detail"),
    path("asientos/<int:pk>/reversar/", views.JournalEntryReverseView.as_view(), name="journal_entry_reverse"),
    # Mapeo de cuentas de control
    path("mapeos/", views.AccountMappingListView.as_view(), name="mapping_list"),
    # Reportes contables
    path("reportes/balance-comprobacion/", views.TrialBalanceView.as_view(), name="trial_balance"),
    path("reportes/mayor/", views.GeneralLedgerView.as_view(), name="general_ledger"),
    path("reportes/diario/", views.GeneralJournalView.as_view(), name="general_journal"),
    path("reportes/balance-general/", views.BalanceSheetView.as_view(), name="balance_sheet"),
    path("reportes/estado-resultados/", views.IncomeStatementView.as_view(), name="income_statement"),
]
