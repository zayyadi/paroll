from django.urls import path

from rest_framework.routers import DefaultRouter

from api.views import (
    CreateEmployeeView,
    CreatePayrollView,
    ListAllEmployee,
    ListEmployee,
    ListPayrollView,
    PayrollRunEntryView,
)

app_name = "api"


pay_list = PayrollRunEntryView.as_view({"get": "list"})
pay_detail = PayrollRunEntryView.as_view({"get": "retrieve"})

router = DefaultRouter()
router.register(r"payday", PayrollRunEntryView, basename="payday")

urlpatterns = (router.urls,)

urlpatterns = [
    path("create_employee", CreateEmployeeView.as_view(), name="create_employee"),
    path("list_employees", ListAllEmployee.as_view(), name="list_employees"),
    path("list_employee", ListEmployee.as_view(), name="list_employee"),
    path("create_payroll", CreatePayrollView.as_view(), name="create_payroll"),
    path("list_payroll", ListPayrollView.as_view(), name="list_payroll"),
    path("payday/<int:pk>", PayrollRunEntryView.as_view({"get": "retrieve"})),
    path("payday", PayrollRunEntryView.as_view({"get": "list"})),
]
