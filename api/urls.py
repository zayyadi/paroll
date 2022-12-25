from django.urls import path

from api.views import CreateEmployeeView, CreatePayrollView,ListAllEmployee, ListPayrollView, PaydayView

app_name = 'api'


urlpatterns = [
    path('create_employee', CreateEmployeeView.as_view(), name='create_employee'),
    path('list_employee', ListAllEmployee.as_view(), name='list_employee'),
    path('create_payroll', CreatePayrollView.as_view(), name='create_payroll'),
    path('list_payroll', ListPayrollView.as_view(), name='list_payroll'),
    path('payday', PaydayView.as_view(), name='payday')

]
