from django.urls import path

from payroll import views

app_name = "payroll"

urlpatterns = [
    path("", views.index, name="index"),
    path("hr-dashboard/", views.hr_dashboard, name="hr_dashboard"),
    path("employees/", views.employee_list, name="employee_list"),
    path("performance-reviews/", views.performance_reviews, name="performance_reviews"),
    # path("input_emp_no", views.input_id, name="input"),
    path("add_employee", views.add_employee, name="add_employee"),  # Changed name
    # path("update_employee", views.delete_employee, name="update_employee"),
    path("delete_employee", views.delete_employee, name="delete_employee"),
    path("profile/<int:user_id>/", views.employee, name="profile"),
    path("add_pay", views.add_pay, name="add_pay"),
    path("dashboard", views.dashboard, name="dashboard"),
    path("list_payslip/<slug:emp_slug>/", views.list_payslip, name="list-payslip"),
    path("add_allowance/", views.create_allowance, name="add-allowance"),
    path("edit_allowance/<int:id>/", views.edit_allowance, name="edit-allowance"),
    path("delete-allowance", views.delete_allowance, name="delete-allowance"),
    # Removed duplicate: path("add_allowance", views.create_allowance, name="add_allowance"),
    path("varview/", views.varview, name="varview"),
    path("varview/<str:paydays>/", views.varview_report, name="varview-report"),
    path(
        "varview/<str:paydays>/download/",
        views.varview_download,
        name="varviewDownload",
    ),
    path("payday", views.AddPay.as_view(), name="payday"),
    path("payslip/<int:id>/", views.payslip, name="payslip"),
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
    path("iou-history/", views.iou_history, name="iou_history"),
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
        "reviews/",
        views.performance_review_list,
        name="performance_review_list",
    ),
    path(
        "reviews/add/",
        views.add_performance_review,
        name="add_performance_review",
    ),
    path(
        "reviews/edit/<int:review_id>/",
        views.edit_performance_review,
        name="edit_performance_review",
    ),
    path(
        "reviews/delete/<int:review_id>/",
        views.delete_performance_review,
        name="delete_performance_review",
    ),
    path(
        "reviews/detail/<int:review_id>/",
        views.performance_review_detail,
        name="performance_review_detail",
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
]
