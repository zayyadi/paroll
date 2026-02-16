from django.urls import path
from . import views

app_name = "accounting"

urlpatterns = [
    # Dashboard
    path("", views.accounting_dashboard, name="dashboard"),
    # Account URLs
    path("accounts/", views.AccountListView.as_view(), name="account_list"),
    path("accounts/create/", views.AccountCreateView.as_view(), name="account_create"),
    path(
        "accounts/opening-balances/import/",
        views.OpeningBalanceImportView.as_view(),
        name="opening_balance_import",
    ),
    path(
        "accounts/<int:pk>/", views.AccountDetailView.as_view(), name="account_detail"
    ),
    path(
        "accounts/adjust-balance/",
        views.BalanceAdjustmentView.as_view(),
        name="balance_adjustment",
    ),
    # Journal URLs
    path("journals/", views.JournalListView.as_view(), name="journal_list"),
    path("journals/create/", views.JournalCreateView.as_view(), name="journal_create"),
    path("journals/<int:pk>/edit/", views.JournalEditView.as_view(), name="journal_edit"),
    path(
        "journals/<int:pk>/", views.JournalDetailView.as_view(), name="journal_detail"
    ),
    path(
        "journals/<int:pk>/approve/",
        views.JournalApprovalView.as_view(),
        name="journal_approve",
    ),
    path(
        "journals/<int:pk>/reverse/",
        views.JournalReversalView.as_view(),
        name="journal_reverse",
    ),
    path(
        "journals/<int:pk>/reversal/initiate/",
        views.JournalReversalInitiationView.as_view(),
        name="journal_reversal_initiation",
    ),
    path(
        "journals/<int:pk>/reversal/confirm/",
        views.JournalReversalConfirmationView.as_view(),
        name="journal_reversal_confirm",
    ),
    path(
        "journals/<int:pk>/reversal/confirm/",
        views.JournalReversalConfirmationView.as_view(),
        name="journal_reversal_confirmation",
    ),
    path(
        "journals/<int:pk>/reversal/partial/",
        views.JournalPartialReversalView.as_view(),
        name="journal_partial_reversal",
    ),
    path(
        "journals/<int:pk>/reversal/correction/",
        views.JournalReversalWithCorrectionView.as_view(),
        name="journal_reversal_with_correction",
    ),
    path(
        "journals/<int:pk>/reversal/history/",
        views.JournalReversalHistoryView.as_view(),
        name="journal_reversal_history",
    ),
    path(
        "journals/reversal/batch/",
        views.BatchJournalReversalView.as_view(),
        name="batch_journal_reversal",
    ),
    # Fiscal Year URLs
    path("fiscal-years/", views.FiscalYearListView.as_view(), name="fiscal_year_list"),
    path(
        "fiscal-years/<int:pk>/",
        views.FiscalYearDetailView.as_view(),
        name="fiscal_year_detail",
    ),
    # Accounting Period URLs
    path("periods/", views.AccountingPeriodListView.as_view(), name="period_list"),
    path(
        "periods/<int:pk>/",
        views.AccountingPeriodDetailView.as_view(),
        name="period_detail",
    ),
    path(
        "periods/<int:pk>/close/",
        views.AccountingPeriodCloseView.as_view(),
        name="period_close",
    ),
    # Audit Trail URLs
    path("audit/", views.AuditTrailListView.as_view(), name="audit_list"),
    path("audit/<int:pk>/", views.AuditTrailDetailView.as_view(), name="audit_detail"),
    # Report URLs
    path("reports/", views.reports_index, name="reports"),
    path("reports/trial-balance/", views.trial_balance_report, name="trial_balance"),
    path(
        "reports/account-activity/",
        views.account_activity_report,
        name="account_activity",
    ),
    path("reports/general-ledger/", views.general_ledger_report, name="general_ledger"),
    path("reports/balance-sheet/", views.balance_sheet_report, name="balance_sheet"),
    path(
        "reports/income-statement/",
        views.income_statement_report,
        name="income_statement",
    ),
    path("reports/account-balance/", views.account_balance_report, name="account_balance"),
    path(
        "reports/unposted-events/",
        views.unposted_financial_events_report,
        name="unposted_events",
    ),
    path("reports/export/", views.export_reports, name="export_reports"),
    path(
        "reports/trial-balance/pdf/", views.trial_balance_pdf, name="trial_balance_pdf"
    ),
    path(
        "reports/account-activity/pdf/",
        views.account_activity_pdf,
        name="account_activity_pdf",
    ),
]
