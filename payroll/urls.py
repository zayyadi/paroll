from django.urls import path

from payroll import views

app_name = "payroll"

urlpatterns = [
    path("", views.index, name="index"),
    path('add_employee', views.add_employee, name='employee'),
    path('update_employee', views.add_employee, name='update_employee'),
    path('delete_employee', views.add_employee, name='delete_employee'),
    
    path("add_pay", views.add_pay, name="add_pay"),
    path("dashboard", views.dashboard, name="dashboard"),
    path("var", views.add_var, name="var"),
    # path("varview/<int:pk>", views.VarView.as_view(), name="varview"),
    path("varview/<int:pay_id>/", views.varview, name="varview"),
    path("varview/<int:pay_id>/download/", views.varview_download, name="varviewDownload"),
    path("payday", views.AddPay.as_view()),
    path("payslip/<int:id>/", views.payslip, name="payslip"),
    path("payslip/pdf/<int:id>/", views.payslip_pdf, name="payslip_pdf"),
    path("bank", views.bank_reports, name="bank"),
    path('bank/<int:pay_id>/', views.bank_report, name='bankReport'),
    path("bank/<int:pay_id>/download/", views.bank_report_download, name="bankReportDownload"),
    path("payee", views.payee_reports, name="payee"),
    path("payee/<int:pay_id>/", views.payee_report, name="payeeReport" ),
    path("payee/<int:pay_id>/download/", views.payee_report_download, name="payeeReportDownload"),
    path("pension", views.pension_reports, name="pension"),
    path("pension/<int:pay_id>/", views.pension_report, name="pensionReport" ),
    path("pension/<int:pay_id>/download/", views.pension_report_download, name="pensionReportDownload")
]