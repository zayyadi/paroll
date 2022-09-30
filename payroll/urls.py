from django.urls import path

from payroll import views

app_name = "payroll"

urlpatterns = [
    path("", views.index, name="index"),
    path("add_pay", views.add_pay, name="add_pay"),
    path("dashboard", views.dashboard, name="dashboard"),
    path("var", views.add_var, name="var"),
    # path("varview/<int:pk>", views.VarView.as_view(), name="varview"),
    path("varview/<int:pay_id>", views.varview, name="varview"),
    path("payday", views.AddPay.as_view()),
    path("payslip/<int:id>/", views.payslip, name="payslip"),
    path("payslip/pdf/<int:id>/", views.payslip_pdf, name="payslip_pdf")
]