from django.urls import path
from . import views

app_name = 'custom_admin'
from .views import (
from .views import (
from .views import (
from .views import (
from .views import (
from .views import (
from .views import (
from .views import (
from .views import (
    BaseListView, BaseCreateView, BaseUpdateView, BaseDeleteView,
    EmployeeProfileListView, EmployeeProfileCreateView,
    EmployeeProfileUpdateView, EmployeeProfileDeleteView,
    PayrollListView, PayrollCreateView, PayrollUpdateView, PayrollDeleteView,
    PayVarListView, PayVarCreateView, PayVarUpdateView, PayVarDeleteView,
    LeaveRequestListView, LeaveRequestCreateView, LeaveRequestUpdateView, LeaveRequestDeleteView,
    IOUListView, IOUCreateView, IOUUpdateView, IOUDeleteView,
    DepartmentListView, DepartmentCreateView, DepartmentUpdateView, DepartmentDeleteView,
    AllowanceListView, AllowanceCreateView, AllowanceUpdateView, AllowanceDeleteView,
    DeductionListView, DeductionCreateView, DeductionUpdateView, DeductionDeleteView,
    LeavePolicyListView, LeavePolicyCreateView, LeavePolicyUpdateView, LeavePolicyDeleteView,
    PayTListView, PayTCreateView, PayTUpdateView, PayTDeleteView # PayT CRUD
)

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # EmployeeProfile specific URLs
    path('payroll/employeeprofile/', EmployeeProfileListView.as_view(), name='payroll_employeeprofile_list'),
    path('payroll/employeeprofile/add/', EmployeeProfileCreateView.as_view(), name='payroll_employeeprofile_create'),
    path('payroll/employeeprofile/<path:pk>/edit/', EmployeeProfileUpdateView.as_view(), name='payroll_employeeprofile_update'),
    path('payroll/employeeprofile/<path:pk>/delete/', EmployeeProfileDeleteView.as_view(), name='payroll_employeeprofile_delete'),

    # Payroll specific URLs
    path('payroll/payroll/', PayrollListView.as_view(), name='payroll_payroll_list'),
    path('payroll/payroll/add/', PayrollCreateView.as_view(), name='payroll_payroll_create'),
    path('payroll/payroll/<int:pk>/edit/', PayrollUpdateView.as_view(), name='payroll_payroll_update'),
    path('payroll/payroll/<int:pk>/delete/', PayrollDeleteView.as_view(), name='payroll_payroll_delete'),

    # PayVar specific URLs
    path('payroll/payvar/', PayVarListView.as_view(), name='payroll_payvar_list'),
    path('payroll/payvar/add/', PayVarCreateView.as_view(), name='payroll_payvar_create'),
    path('payroll/payvar/<int:pk>/edit/', PayVarUpdateView.as_view(), name='payroll_payvar_update'),
    path('payroll/payvar/<int:pk>/delete/', PayVarDeleteView.as_view(), name='payroll_payvar_delete'),

    # LeaveRequest specific list URL
    path('payroll/leaverequest/', LeaveRequestListView.as_view(), name='payroll_leaverequest_list'),
    path('payroll/leaverequest/add/', LeaveRequestCreateView.as_view(), name='payroll_leaverequest_create'),
    path('payroll/leaverequest/<int:pk>/edit/', LeaveRequestUpdateView.as_view(), name='payroll_leaverequest_update'),
    path('payroll/leaverequest/<int:pk>/delete/', LeaveRequestDeleteView.as_view(), name='payroll_leaverequest_delete'),

    # IOU specific list URL
    path('payroll/iou/', IOUListView.as_view(), name='payroll_iou_list'),
    path('payroll/iou/add/', IOUCreateView.as_view(), name='payroll_iou_create'),
    path('payroll/iou/<int:pk>/edit/', IOUUpdateView.as_view(), name='payroll_iou_update'),
    path('payroll/iou/<int:pk>/delete/', IOUDeleteView.as_view(), name='payroll_iou_delete'),

    # Department specific URLs
    path('payroll/department/', DepartmentListView.as_view(), name='payroll_department_list'),
    path('payroll/department/add/', DepartmentCreateView.as_view(), name='payroll_department_create'),
    path('payroll/department/<int:pk>/edit/', DepartmentUpdateView.as_view(), name='payroll_department_update'),
    path('payroll/department/<int:pk>/delete/', DepartmentDeleteView.as_view(), name='payroll_department_delete'),

    # Allowance specific URLs
    path('payroll/allowance/', AllowanceListView.as_view(), name='payroll_allowance_list'),
    path('payroll/allowance/add/', AllowanceCreateView.as_view(), name='payroll_allowance_create'),
    path('payroll/allowance/<int:pk>/edit/', AllowanceUpdateView.as_view(), name='payroll_allowance_update'),
    path('payroll/allowance/<int:pk>/delete/', AllowanceDeleteView.as_view(), name='payroll_allowance_delete'),

    # Deduction specific URLs
    path('payroll/deduction/', DeductionListView.as_view(), name='payroll_deduction_list'),
    path('payroll/deduction/add/', DeductionCreateView.as_view(), name='payroll_deduction_create'),
    path('payroll/deduction/<int:pk>/edit/', DeductionUpdateView.as_view(), name='payroll_deduction_update'),
    path('payroll/deduction/<int:pk>/delete/', DeductionDeleteView.as_view(), name='payroll_deduction_delete'),

    # LeavePolicy specific URLs
    path('payroll/leavepolicy/', LeavePolicyListView.as_view(), name='payroll_leavepolicy_list'),
    path('payroll/leavepolicy/add/', LeavePolicyCreateView.as_view(), name='payroll_leavepolicy_create'),
    path('payroll/leavepolicy/<int:pk>/edit/', LeavePolicyUpdateView.as_view(), name='payroll_leavepolicy_update'),
    path('payroll/leavepolicy/<int:pk>/delete/', LeavePolicyDeleteView.as_view(), name='payroll_leavepolicy_delete'),

    # PayT specific URLs
    path('payroll/payt/', PayTListView.as_view(), name='payroll_payt_list'),
    path('payroll/payt/add/', PayTCreateView.as_view(), name='payroll_payt_create'),
    path('payroll/payt/<int:pk>/edit/', PayTUpdateView.as_view(), name='payroll_payt_update'),
    path('payroll/payt/<int:pk>/delete/', PayTDeleteView.as_view(), name='payroll_payt_delete'),

    # Generic catch-all URLs (These should come AFTER specific ones)
    path('<str:app_label>/<str:model_name>/', BaseListView.as_view(), name='generic_list'),
    path('<str:app_label>/<str:model_name>/add/', BaseCreateView.as_view(), name='generic_create'),
    path('<str:app_label>/<str:model_name>/<path:pk>/edit/', BaseUpdateView.as_view(), name='generic_update'),
    path('<str:app_label>/<str:model_name>/<path:pk>/delete/', BaseDeleteView.as_view(), name='generic_delete'),
]
