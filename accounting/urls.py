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
        "accounts/<int:pk>/", views.AccountDetailView.as_view(), name="account_detail"
    ),
    # Journal URLs
    path("journals/", views.JournalListView.as_view(), name="journal_list"),
    path("journals/create/", views.JournalCreateView.as_view(), name="journal_create"),
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
    path(
        "reports/trial-balance/pdf/", views.trial_balance_pdf, name="trial_balance_pdf"
    ),
    path(
        "reports/account-activity/pdf/",
        views.account_activity_pdf,
        name="account_activity_pdf",
    ),
]
