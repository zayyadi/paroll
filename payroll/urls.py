from django.urls import path

from payroll import views
from payroll.views import payroll_view
from payroll.views.payroll_view import payslips, payslip_detail
from payroll.views import notification_view
from accounting import views as accounting_views

app_name = "payroll"

urlpatterns = [
    path("", views.index, name="index"),
    path("employee-profile/", views.update_employee_profile, name="employee_profile"),
    path("hr-dashboard/", views.hr_dashboard, name="hr_dashboard"),
    path("employees/", views.employee_list, name="employee_list"),
    path("add_employee", views.add_employee, name="add_employee"),  # Changed name
    path("delete_employee", views.delete_employee, name="delete_employee"),
    path("profile/<int:user_id>/", views.employee, name="profile"),
    path("employees/<int:id>/update/", views.update_employee, name="update_employee"),
    path("add_pay", views.add_pay, name="add_pay"),
    path("dashboard", views.dashboard, name="dashboard"),
    path(
        "settings/payroll/",
        views.company_payroll_settings,
        name="company_payroll_settings",
    ),
    path(
        "settings/payroll/edit/",
        views.company_payroll_settings_edit,
        name="company_payroll_settings_edit",
    ),
    path("list_payslip/<slug:emp_slug>/", views.list_payslip, name="list-payslip"),
    path("payslips/", payslips, name="payslips"),
    path("add_allowance/", views.create_allowance, name="add-allowance"),
    path("add_deduction/", payroll_view.AddDeduction.as_view(), name="add-deduction"),
    path("edit_allowance/<int:id>/", views.edit_allowance, name="edit-allowance"),
    path("delete-allowance", views.delete_allowance, name="delete-allowance"),
    path("varview/", views.varview, name="varview"),
    path(
        "varview/create-new/",
        payroll_view.payvar_create_new,
        name="payvar_create_new",
    ),  # New enhanced view with efficient employee selection
    path("varview/<str:paydays>/", views.varview_report, name="varview-report"),
    path(
        "varview/<str:paydays>/download/",
        views.varview_download,
        name="varviewDownload",
    ),
    path("pay-period/", views.pay_period_list, name="pay_period_list"),
    path(
        "pay-period/create/", views.AddPay.as_view(), name="payday"
    ),  # Existing create view, renamed for clarity if desired or keep as 'payday'
    path(
        "pay-period/create-new/",
        payroll_view.payday_create_new,
        name="payday_create_new",
    ),  # New enhanced view with efficient employee selection
    path("pay-periods/<slug:slug>/", views.pay_period_detail, name="pay_period_detail"),
    path(
        "pay-periods/<slug:slug>/update/",
        views.PayPeriodUpdateView.as_view(),
        name="pay_period_update",
    ),
    path(
        "pay-periods/<slug:slug>/delete/",
        views.PayPeriodDeleteView.as_view(),
        name="pay_period_delete",
    ),
    path("payslip/<int:id>/", payslip_detail, name="payslip"),
    path("payslip/pdf/<int:id>/", views.payslip_pdf, name="payslip_pdf"),
    path("bank", views.bank_reports, name="bank"),
    path("bank/<int:pay_id>/", views.bank_report, name="bankReport"),
    path(
        "bank/<int:pay_id>/download/",
        views.bank_report_download,
        name="bankReportDownload",
    ),
    path(
        "nhis",
        views.nhis_reports,
        name="nhis",
    ),
    path(
        "nhis/<int:pay_id>/",
        views.nhis_report,
        name="nhisreport",
    ),
    path(
        "nhis/<int:pay_id>/download/",
        views.nhis_report_download,
        name="nhisReportDownload",
    ),
    path(
        "nhf",
        views.nhf_reports,
        name="nhf",
    ),
    path(
        "nhf/<int:pay_id>/",
        views.nhf_report,
        name="nhfReport",
    ),
    path(
        "nhf/<int:pay_id>/download/",
        views.nhf_report_download,
        name="nhfReportDownload",
    ),
    path("payee", views.payee_reports, name="payee"),
    path("payee/<int:pay_id>/", views.payee_report, name="payeeReport"),
    path(
        "payee/<int:pay_id>/download/",
        views.payee_report_download,
        name="payeeReportDownload",
    ),
    path("pension", views.pension_reports, name="pension"),
    path("pension/<int:pay_id>/", views.pension_report, name="pensionReport"),
    path(
        "pension/<int:pay_id>/download/",
        views.pension_report_download,
        name="pensionReportDownload",
    ),
    path("apply-leave/", views.apply_leave, name="apply_leave"),
    path("leave-requests/", views.leave_requests, name="leave_requests"),
    path(
        "manage-leave-requests/",
        views.manage_leave_requests,
        name="manage_leave_requests",
    ),
    path("approve-leave/<int:pk>/", views.approve_leave, name="approve_leave"),
    path("reject-leave/<int:pk>/", views.reject_leave, name="reject_leave"),
    path("leave-policies/", views.leave_policies, name="leave_policies"),
    path(
        "edit-leave-request/<int:pk>/",
        views.edit_leave_request,
        name="edit_leave_request",
    ),
    path(
        "delete-leave-request/<int:pk>/",
        views.delete_leave_request,
        name="delete_leave_request",
    ),
    path(
        "view-leave-request/<int:pk>/",
        views.view_leave_request,
        name="view_leave_request",
    ),
    path("request-iou/", views.request_iou, name="request_iou"),
    path("approve-iou/<int:iou_id>/", views.approve_iou, name="approve_iou"),
    path("iou/<int:pk>/update/", views.IOUUpdateView.as_view(), name="iou_update"),
    path("iou/<int:pk>/delete/", views.IOUDeleteView.as_view(), name="iou_delete"),
    path("iou-history/", views.iou_history, name="iou_history"),
    path("my-iou-tracker/", views.my_iou_tracker, name="my_iou_tracker"),
    path(
        "iou/",
        views.iou_list,
        name="iou_list",
    ),
    path(
        "iou/<int:pk>/",
        views.iou_detail,
        name="iou_detail",
    ),
    path(
        "audit-trail/",
        views.audit_trail_list,
        name="audit_trail_list",
    ),
    path(
        "audit-trail/<int:id>/",
        views.audit_trail_detail,
        name="audit_trail_detail",
    ),
    path("appraisals/", views.AppraisalListView.as_view(), name="appraisal_list"),
    path(
        "appraisals/create/",
        views.AppraisalCreateView.as_view(),
        name="appraisal_create",
    ),
    path(
        "appraisals/<int:pk>/",
        views.AppraisalDetailView.as_view(),
        name="appraisal_detail",
    ),
    path(
        "appraisals/<int:pk>/update/",
        views.AppraisalUpdateView.as_view(),
        name="appraisal_update",
    ),
    path(
        "appraisals/<int:pk>/delete/",
        views.AppraisalDeleteView.as_view(),
        name="appraisal_delete",
    ),
    path(
        "appraisals/<int:appraisal_pk>/employees/<int:employee_pk>/reviews/create/",
        views.ReviewCreateView.as_view(),
        name="review_create",
    ),
    path("reviews/<int:pk>/", views.ReviewDetailView.as_view(), name="review_detail"),
    path(
        "reviews/<int:pk>/update/",
        views.ReviewUpdateView.as_view(),
        name="review_update",
    ),
    path(
        "reviews/<int:pk>/delete/",
        views.ReviewDeleteView.as_view(),
        name="review_delete",
    ),
    path(
        "appraisals/assign/",
        views.AssignAppraisalView.as_view(),
        name="appraisal_assign",
    ),
    # HR Disciplinary System (moved from accounting namespace)
    path(
        "hr/disciplinary-system/",
        accounting_views.disciplinary_system_view,
        name="disciplinary_system",
    ),
    path(
        "hr/disciplinary/cases/",
        accounting_views.DisciplinaryCaseListView.as_view(),
        name="discipline_case_list",
    ),
    path(
        "hr/disciplinary/cases/new/",
        accounting_views.DisciplinaryCaseCreateView.as_view(),
        name="discipline_case_create",
    ),
    path(
        "hr/disciplinary/cases/<int:pk>/",
        accounting_views.DisciplinaryCaseDetailView.as_view(),
        name="discipline_case_detail",
    ),
    path(
        "hr/disciplinary/cases/<int:pk>/edit/",
        accounting_views.DisciplinaryCaseUpdateView.as_view(),
        name="discipline_case_update",
    ),
    path(
        "hr/disciplinary/cases/<int:pk>/start-investigation/",
        accounting_views.disciplinary_case_start_investigation,
        name="discipline_case_start_investigation",
    ),
    path(
        "hr/disciplinary/cases/<int:pk>/evidence/add/",
        accounting_views.DisciplinaryEvidenceCreateView.as_view(),
        name="discipline_evidence_create",
    ),
    path(
        "hr/disciplinary/cases/<int:pk>/decision/",
        accounting_views.DisciplinaryDecisionUpdateView.as_view(),
        name="discipline_decision_update",
    ),
    path(
        "hr/disciplinary/cases/<int:pk>/sanction/add/",
        accounting_views.DisciplinarySanctionCreateView.as_view(),
        name="discipline_sanction_create",
    ),
    path(
        "hr/disciplinary/cases/<int:pk>/appeal/add/",
        accounting_views.DisciplinaryAppealCreateView.as_view(),
        name="discipline_appeal_create",
    ),
    path(
        "hr/disciplinary/appeals/<int:pk>/review/",
        accounting_views.DisciplinaryAppealReviewView.as_view(),
        name="discipline_appeal_review",
    ),
    # Notification URLs
    path("notifications/", notification_view.notification_list, name="notifications"),
    path(
        "notifications/enhanced/",
        notification_view.notification_list,
        name="notifications_enhanced",
    ),
    path(
        "notifications/dropdown/",
        notification_view.notification_dropdown,
        name="notification_dropdown",
    ),
    path(
        "notifications/<uuid:notification_id>/",
        notification_view.notification_detail,
        name="notification_detail",
    ),
    path(
        "notifications/<uuid:notification_id>/mark-read/",
        notification_view.mark_notification_read,
        name="mark_notification_read",
    ),
    path(
        "notifications/<uuid:notification_id>/mark-unread/",
        notification_view.mark_notification_unread,
        name="mark_notification_unread",
    ),
    path(
        "notifications/<uuid:notification_id>/delete/",
        notification_view.delete_notification,
        name="delete_notification",
    ),
    path(
        "notifications/mark-all-read/",
        notification_view.mark_all_read,
        name="mark_all_read",
    ),
    path(
        "notifications/count/",
        notification_view.notification_count,
        name="notification_count",
    ),
    # Notification Preferences URLs
    path(
        "notifications/preferences/",
        notification_view.notification_preferences,
        name="notification_preferences",
    ),
    path(
        "notifications/preferences/<str:notification_type>/",
        notification_view.notification_type_preferences,
        name="notification_type_preferences",
    ),
    # Aggregated Notifications URLs
    path(
        "notifications/aggregated/",
        notification_view.aggregated_notifications,
        name="aggregated_notifications",
    ),
    path(
        "notifications/<uuid:notification_id>/expand/",
        notification_view.expand_aggregated_notification,
        name="expand_aggregated_notification",
    ),
    # Notification Digest URLs
    path(
        "notifications/digests/",
        notification_view.notification_digests,
        name="notification_digests",
    ),
    path(
        "notifications/digests/settings/",
        notification_view.notification_digest_settings,
        name="notification_digest_settings",
    ),
    path(
        "notifications/digests/<uuid:notification_id>/",
        notification_view.notification_detail,
        name="notification_digest_detail",
    ),
    path(
        "notifications/digest/enable-daily/",
        notification_view.enable_daily_digest,
        name="enable_daily_digest",
    ),
    path(
        "notifications/digest/enable-weekly/",
        notification_view.enable_weekly_digest,
        name="enable_weekly_digest",
    ),
    path(
        "notifications/digest/disable/",
        notification_view.disable_digest,
        name="disable_digest",
    ),
    path(
        "notifications/digest/trigger/",
        notification_view.trigger_manual_digest,
        name="trigger_manual_digest",
    ),
]
