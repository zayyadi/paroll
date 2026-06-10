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
        "accounts/<int:pk>/edit/",
        views.AccountUpdateView.as_view(),
        name="account_update",
    ),
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
        "journals/<int:pk>/delete/",
        views.JournalDeleteView.as_view(),
        name="journal_delete",
    ),
    path(
        "journals/<int:pk>/submit/",
        views.journal_submit_view,
        name="journal_submit",
    ),
    path(
        "journals/<int:pk>/", views.JournalDetailView.as_view(), name="journal_detail"
    ),
    path(
        "journals/<int:pk>/approve/",
        views.JournalApprovalView.as_view(),
        name="journal_approve",
    ),
    path(
        "journals/<int:pk>/post/",
        views.journal_post_view,
        name="journal_post",
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
        "journals/<int:pk>/reversal/confirmation/",
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
        "fiscal-years/create/",
        views.FiscalYearCreateView.as_view(),
        name="fiscal_year_create",
    ),
    path(
        "fiscal-years/<int:pk>/",
        views.FiscalYearDetailView.as_view(),
        name="fiscal_year_detail",
    ),
    # Accounting Period URLs
    path("periods/", views.AccountingPeriodListView.as_view(), name="period_list"),
    path("periods/create/", views.AccountingPeriodCreateView.as_view(), name="period_create"),
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
    path("audit-trail/", views.AuditTrailListView.as_view(), name="audit_trail_list"),
    path("audit/<int:pk>/", views.AuditTrailDetailView.as_view(), name="audit_detail"),
    path(
        "audit-trail/<int:pk>/",
        views.AuditTrailDetailView.as_view(),
        name="audit_trail_detail",
    ),
    # Report URLs
    path("reports/", views.reports_index, name="reports"),
    path(
        "reports/designer/",
        views.FinancialReportListView.as_view(),
        name="financial_report_list",
    ),
    path(
        "reports/designer/new/",
        views.FinancialReportCreateView.as_view(),
        name="financial_report_create",
    ),
    path(
        "reports/designer/<int:pk>/",
        views.FinancialReportDetailView.as_view(),
        name="financial_report_detail",
    ),
    path(
        "reports/designer/<int:pk>/lines/new/",
        views.FinancialReportLineCreateView.as_view(),
        name="financial_report_line_create",
    ),
    path("reports/trial-balance/", views.trial_balance_report, name="trial_balance"),
    path(
        "reports/trial-balance/legacy/",
        views.trial_balance_report,
        name="report_trial_balance",
    ),
    path(
        "reports/account-activity/",
        views.account_activity_report,
        name="account_activity",
    ),
    path(
        "reports/account-activity/<int:pk>/",
        views.account_activity_report_for_account,
        name="report_account_activity",
    ),
    path("reports/general-ledger/", views.general_ledger_report, name="general_ledger"),
    path(
        "reports/general-ledger/legacy/",
        views.general_ledger_report,
        name="report_general_ledger",
    ),
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
        "reports/trial-balance/pdf/legacy/",
        views.trial_balance_pdf,
        name="report_trial_balance_pdf",
    ),
    path(
        "reports/account-activity/pdf/",
        views.account_activity_pdf,
        name="account_activity_pdf",
    ),
    path(
        "reports/account-activity/<int:pk>/pdf/",
        views.account_activity_pdf_for_account,
        name="report_account_activity_pdf",
    ),
    # Reconciliation URLs
    path("reconciliation/", views.ReconciliationListView.as_view(), name="reconciliation_list"),
    path("reconciliation/create/", views.ReconciliationCreateView.as_view(), name="reconciliation_create"),
    path("reconciliation/<int:pk>/", views.ReconciliationDetailView.as_view(), name="reconciliation_detail"),
    path("reconciliation/<int:pk>/match/", views.ReconciliationMatchView.as_view(), name="reconciliation_match"),
    path("reconciliation/<int:pk>/approve/", views.reconciliation_approve, name="reconciliation_approve"),
    path("reconciliation/import/", views.reconciliation_import, name="reconciliation_import"),
    # Async Report URLs
    path("reports/async/<str:report_type>/", views.queue_async_report, name="queue_async_report"),
    path("reports/jobs/", views.report_job_list, name="report_job_list"),
    path("reports/jobs/<int:pk>/", views.report_job_status, name="report_job_status"),
    path("reports/jobs/<int:pk>/download/", views.report_job_download, name="report_job_download"),
    # MFA step-up verification for sensitive accounting operations
    path("mfa/verify/", views.mfa_verify_view, name="mfa_verify"),
    # Phase 2 Reports
    path("reports/cash-flow/", views.cash_flow_report, name="cash_flow"),
    path("reports/financial-ratios/", views.financial_ratios_report, name="financial_ratios"),
    path("reports/ar-aging/", views.ar_aging_report, name="ar_aging"),
    path("reports/ap-aging/", views.ap_aging_report, name="ap_aging"),
    path("reports/inventory-turnover/", views.inventory_turnover_report, name="inventory_turnover"),
    path("reports/gross-margin/", views.gross_margin_report, name="gross_margin"),
    path("reports/month-end-checklist/", views.month_end_checklist_view, name="month_end_checklist"),
    path("reports/executive/", views.executive_dashboard, name="executive_dashboard"),
    # External Accounting Connectors
    path("reports/export/journals/", views.export_journals_csv_view, name="export_journals_csv"),
    path("reports/export/chart-of-accounts/", views.export_chart_of_accounts_csv_view, name="export_chart_of_accounts_csv"),
    path("reports/export/suppliers/", views.export_suppliers_csv_view, name="export_suppliers_csv"),
    path("reports/export/customers/", views.export_customers_csv_view, name="export_customers_csv"),
]
