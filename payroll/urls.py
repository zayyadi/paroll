from django.urls import path

from payroll import views

app_name = "payroll"

urlpatterns = [
    path("", views.index, name="index"),
    path("input_emp_no", views.input_id, name="input"),
    path("add_employee", views.add_employee, name="employee"),
    # path("update_employee", views.delete_employee, name="update_employee"),
    path("delete_employee", views.delete_employee, name="delete_employee"),
    path("profile/<int:user_id>/", views.employee, name="profile"),
    path("add_pay", views.add_pay, name="add_pay"),
    path("dashboard", views.dashboard, name="dashboard"),
    path("list_payslip/<slug:emp_slug>/", views.list_payslip, name="list-payslip"),
    path("add_allowance/", views.create_allowance, name="add-allowance"),
    path("edit_allowance/<int:id>/", views.edit_allowance, name="edit-allowance"),
    path("delete-allowance", views.delete_allowance, name="delete-allowance"),
    path("add_allowance", views.create_allowance, name="add_allowance"),
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
]
