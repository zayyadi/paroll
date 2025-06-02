from django.urls import path
from . import views
from .views import (
    BaseListView,
    BaseCreateView,
    BaseUpdateView,
    BaseDeleteView,
    EmployeeProfileListView,
    EmployeeProfileCreateView,
    EmployeeProfileUpdateView,
    EmployeeProfileDeleteView,
    PayrollListView,
    PayrollCreateView,
    PayrollUpdateView,
    PayrollDeleteView,
    PayVarListView,
    PayVarCreateView,
    PayVarUpdateView,
    PayVarDeleteView,  # Added PayVar views
)

app_name = "custom_admin"


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # EmployeeProfile specific URLs
    path(
        "payroll/employeeprofile/",
        EmployeeProfileListView.as_view(),
        name="payroll_employeeprofile_list",
    ),
    path(
        "payroll/employeeprofile/add/",
        EmployeeProfileCreateView.as_view(),
        name="payroll_employeeprofile_create",
    ),
    path(
        "payroll/employeeprofile/<path:pk>/edit/",
        EmployeeProfileUpdateView.as_view(),
        name="payroll_employeeprofile_update",
    ),
    path(
        "payroll/employeeprofile/<path:pk>/delete/",
        EmployeeProfileDeleteView.as_view(),
        name="payroll_employeeprofile_delete",
    ),
    # Payroll specific URLs
    path("payroll/payroll/", PayrollListView.as_view(), name="payroll_payroll_list"),
    path(
        "payroll/payroll/add/",
        PayrollCreateView.as_view(),
        name="payroll_payroll_create",
    ),
    path(
        "payroll/payroll/<int:pk>/edit/",
        PayrollUpdateView.as_view(),
        name="payroll_payroll_update",
    ),
    path(
        "payroll/payroll/<int:pk>/delete/",
        PayrollDeleteView.as_view(),
        name="payroll_payroll_delete",
    ),
    # PayVar specific URLs
    path("payroll/payvar/", PayVarListView.as_view(), name="payroll_payvar_list"),
    path(
        "payroll/payvar/add/", PayVarCreateView.as_view(), name="payroll_payvar_create"
    ),
    path(
        "payroll/payvar/<int:pk>/edit/",
        PayVarUpdateView.as_view(),
        name="payroll_payvar_update",
    ),
    path(
        "payroll/payvar/<int:pk>/delete/",
        PayVarDeleteView.as_view(),
        name="payroll_payvar_delete",
    ),
    # Generic catch-all URLs (These should come AFTER specific ones)
    path(
        "<str:app_label>/<str:model_name>/", BaseListView.as_view(), name="generic_list"
    ),
    path(
        "<str:app_label>/<str:model_name>/add/",
        BaseCreateView.as_view(),
        name="generic_create",
    ),
    path(
        "<str:app_label>/<str:model_name>/<path:pk>/edit/",
        BaseUpdateView.as_view(),
        name="generic_update",
    ),
    path(
        "<str:app_label>/<str:model_name>/<path:pk>/delete/",
        BaseDeleteView.as_view(),
        name="generic_delete",
    ),
]
