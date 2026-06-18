"""
Employee Crud views.
"""

from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q, Count, Sum, Avg
from django.views.generic.edit import FormView
from django.forms import inlineformset_factory
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import permission_required
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.http import Http404, HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
import json

from company.utils import get_user_company
from payroll import models
from users import forms as user_forms
from payroll.forms import EmployeeProfileForm
from payroll.services.access import visible_employee_profiles_for
from payroll.views.employee_utilities import _start_workflow_execution


EMPLOYEE_PROFILE_SENSITIVE_FIELDS = (
    "tin_no",
    "pension_rsa",
    "bank_account_name",
    "bank_account_number",
    "emergency_contact_phone",
    "next_of_kin_phone",
)


@login_required
def employee_list(request):
    company = get_user_company(request.user)
    query = request.GET.get("q")
    department_filter = request.GET.get("department")
    employees = visible_employee_profiles_for(request.user)
    if query:
        employees = employees.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(job_title__icontains=query)
        )
    if department_filter:
        employees = employees.filter(department__id=department_filter)
    departments = models.Department.objects.filter(company=company)
    active_employees_count = employees.filter(status="active").count()
    suspended_employees_count = employees.filter(status="suspended").count()
    terminated_employees_count = employees.filter(status="terminated").count()
    return render(
        request,
        "employee/employee_list_new.html",
        {
            "employees": employees,
            "departments": departments,
            "active_employees_count": active_employees_count,
            "suspended_employees_count": suspended_employees_count,
            "terminated_employees_count": terminated_employees_count,
        },
    )


@permission_required(
    ["payroll.add_employeeprofile", "users.add_customuser"], raise_exception=True
)

def add_employee(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        user_form = user_forms.CustomUserCreationForm(request.POST)
        employee_form = EmployeeProfileForm(request.POST, request.FILES, user=request.user)
        if user_form.is_valid() and employee_form.is_valid():
            with transaction.atomic():
                submitted_profile = employee_form.save(commit=False)
                user = user_form.save(commit=False)
                user.company = company
                user.active_company = company
                user.first_name = employee_form.cleaned_data.get("first_name", "")
                user.last_name = employee_form.cleaned_data.get("last_name", "")
                user.save()

                employee_profile = getattr(user, "employee_user", None)
                if employee_profile is None:
                    employee_profile = submitted_profile

                for field_name in employee_form.fields:
                    setattr(
                        employee_profile,
                        field_name,
                        getattr(submitted_profile, field_name),
                    )

                employee_profile.company = company
                employee_profile.user = user
                employee_profile.email = user.email
                employee_profile.first_name = user.first_name
                employee_profile.last_name = user.last_name
                employee_profile.save()

                _start_workflow_execution(
                    company=company,
                    employee_profile=employee_profile,
                    workflow_type=models.WorkflowTemplate.WorkflowType.ONBOARDING,
                    started_by=request.user,
                    trigger_event="employee.created",
                )
            messages.success(request, "Employee added successfully!")
            return redirect("payroll:employee_list")
    else:
        user_form = user_forms.CustomUserCreationForm()
        employee_form = EmployeeProfileForm(user=request.user)
    context = {"user_form": user_form, "employee_form": employee_form}
    return render(request, "employee/add_employee.html", context)



def input_id(request):  # No specific permissions, seems like a generic utility page
    return render(request, "pay/input.html")


@permission_required("payroll.change_employeeprofile", raise_exception=True)

def update_employee(request, id):
    company = get_user_company(request.user)
    employee = get_object_or_404(models.EmployeeProfile, id=id, company=company)
    form = EmployeeProfileForm(request.POST or None, instance=employee, user=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "Employee updated successfully!!")
        return redirect(
            "payroll:employee_list"
        )  # Consider redirecting to employee list or profile
    models.log_sensitive_employee_data_access(
        employee=employee,
        accessed_by=request.user,
        fields=EMPLOYEE_PROFILE_SENSITIVE_FIELDS,
        purpose="employee_profile_update_form",
        metadata={"view": "update_employee"},
    )
    return render(request, "employee/update_employee.html", {"form": form})


# class EmployeeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
#     model = models.EmployeeProfile
#     form_class = EmployeeProfileForm
#     template_name = (
#         "employee/add.html"  # This might conflict with FBV add_employee's template
#     )
#     success_url = reverse_lazy("payroll:employee_list")
#     permission_required = (
#         "payroll.add_employeeprofile",
#         "users.add_customuser",
#     )  # Assuming form also handles CustomUser creation

#     def form_valid(self, form):
#         messages.success(self.request, "Employee created successfully.")
#         return super().form_valid(form)


# class EmployeeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
#     model = models.EmployeeProfile
#     form_class = EmployeeProfileForm
#     template_name = (
#         "employee/update.html"  # May conflict with FBV update_employee template
#     )
#     success_url = reverse_lazy("payroll:employee_list")
#     permission_required = "payroll.change_employeeprofile"

#     def form_valid(self, form):
#         messages.success(self.request, "Employee updated successfully.")
#         return super().form_valid(form)


# class EmployeeDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
#     model = models.EmployeeProfile
#     template_name = "employee/delete.html"
#     success_url = reverse_lazy("payroll:employee_list")
#     permission_required = "payroll.delete_employeeprofile"

#     def delete(self, request, *args, **kwargs):
#         messages.success(self.request, "Employee deleted successfully.")
#         return super().delete(request, *args, **kwargs)


@permission_required("payroll.delete_employeeprofile", raise_exception=True)
@require_POST

def delete_employee(request, id=None):  # FBV for delete
    company = get_user_company(request.user)
    if id is None:
        raw_id = request.POST.get("id")
        try:
            id = int(raw_id) if raw_id is not None else None
        except (TypeError, ValueError):
            id = None
    if id is None:
        messages.error(request, "No employee selected for deletion.")
        return redirect("payroll:employee_list")
    employee_profile = get_object_or_404(models.EmployeeProfile, id=id, company=company)
    _start_workflow_execution(
        company=company,
        employee_profile=employee_profile,
        workflow_type=models.WorkflowTemplate.WorkflowType.OFFBOARDING,
        started_by=request.user,
        trigger_event="employee.deleted",
    )
    employee_profile.delete()
    messages.success(request, "Employee deleted Successfully!!")
    return redirect("payroll:employee_list")  # Ensure redirect after delete


@login_required

def employee(request, user_id: int):
    company = get_user_company(request.user)
    target_user_profile = get_object_or_404(
        models.EmployeeProfile, user_id=user_id, company=company
    )
    print(target_user_profile.user_id, request.user.id)

    # Check if request.user is viewing their own profile or has general view permission
    if request.user.id == user_id or request.user.has_perm(
        "payroll.view_employeeprofile"
    ):
        employee_profile_to_display = target_user_profile
    else:
        return HttpResponseForbidden("You are not authorized to view this profile.")

    pay = models.PayrollRunEntry.objects.filter(
        payroll_entry__pays__user_id=employee_profile_to_display.user.id,
        payroll_entry__company=company,
    )
    iou_slips = models.IOU.objects.filter(
        employee_id=employee_profile_to_display,
        employee_id__company=company,
    ).order_by("-created_at")
    models.log_sensitive_employee_data_access(
        employee=employee_profile_to_display,
        accessed_by=request.user,
        fields=EMPLOYEE_PROFILE_SENSITIVE_FIELDS,
        purpose="employee_profile_view",
        metadata={"view": "employee"},
    )
    context = {"emp": employee_profile_to_display, "pay": pay, "iou_slips": iou_slips}
    return render(request, "employee/profile_new.html", context)
