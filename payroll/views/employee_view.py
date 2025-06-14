from payroll.forms import (
    EmployeeProfileForm,
    PerformanceReviewForm,
)
from payroll import models

from django.db.models import Q, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)  # Added permission_required
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)  # Added PermissionRequiredMixin, removed UserPassesTestMixin
from django.contrib import messages

# Removed user_passes_test as it's replaced by permission_required or custom logic in views
from django.conf import settings
from django.http import (
    Http404,
    HttpResponseForbidden,
)

import json

from django.core.cache.backends.base import DEFAULT_TIMEOUT

from users import forms as user_forms

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)

# Removed is_hr_user and check_super helper functions as their use is replaced


@login_required  # index and dashboard remain login_required for now, internal logic dictates content
def index(request):
    pay = models.PayT.objects.all()
    pay_count = models.PayT.objects.all().count()
    emp = (
        models.EmployeeProfile.emp_objects.all()
    )  # Consider if this should be permission limited
    count = emp.count()

    context = {
        "pay": pay,
        "emp": emp,
        "count": count,
        "pay_count": pay_count,
    }

    if request.user.is_superuser:  # Superuser still gets a specific template
        return render(request, "index.html", context)
    else:
        try:
            employee_profile = models.EmployeeProfile.emp_objects.get(user=request.user)
            context["employee_slug"] = employee_profile.slug
        except models.EmployeeProfile.DoesNotExist:
            context["employee_slug"] = None
        return render(request, "home_normal.html", context)


@login_required
def dashboard(request):
    user = request.user

    if user.is_superuser:  # Superuser gets admin dashboard
        return render(request, "dashboard_admin.html")
    # Changed from group check to permission check for HR dashboard
    elif request.user.has_perm(
        "payroll.view_employeeprofile"
    ):  # Representative permission for HR
        employee_count = models.EmployeeProfile.objects.count()
        leave_count = models.LeaveRequest.objects.filter(status="PENDING").count()
        iou_count = models.IOU.objects.filter(status="PENDING").count()
        allowance_count = models.Allowance.objects.count()
        context = {
            "employee_count": employee_count,
            "leave_count": leave_count,
            "iou_count": iou_count,
            "allowance_count": allowance_count,
        }
        return render(request, "dashboard_hr.html", context)
    else:  # Regular user dashboard
        return render(request, "dashboard_user.html")


@permission_required(
    "payroll.view_employeeprofile", raise_exception=True
)  # Example permission for HR dashboard
def hr_dashboard(request):
    # Counts for the new "Approvals" section links
    pending_leave_requests_count = models.LeaveRequest.objects.filter(
        status="PENDING"
    ).count()
    pending_iou_requests_count = models.IOU.objects.filter(status="PENDING").count()

    total_employees = models.EmployeeProfile.objects.count()
    recent_performance_reviews = models.PerformanceReview.objects.all().order_by(
        "-review_date"
    )[:5]
    department_distribution = models.EmployeeProfile.objects.values(
        "department__name"
    ).annotate(count=Count("id"))
    department_labels = json.dumps(
        [item["department__name"] for item in department_distribution]
    )
    department_counts = json.dumps([item["count"] for item in department_distribution])

    leave_status_chart_data = json.dumps(
        [
            pending_leave_requests_count,  # Use already computed value
            models.LeaveRequest.objects.filter(status="APPROVED").count(),
            models.LeaveRequest.objects.filter(status="REJECTED").count(),
        ]
    )
    # iou_status_counts = json.dumps(
    #     [
    #         models.IOU.objects.filter(status="PENDING").count(),
    #         models.IOU.objects.filter(status="APPROVED").count(),
    #         models.IOU.objects.filter(status="REJECTED").count(),
    #         models.IOU.objects.filter(status="PAID").count(),
    #     ]
    # )
    context = {
        "total_employees": total_employees,
        "active_leave_requests": pending_leave_requests_count,  # Original name, kept for compatibility
        "pending_leave_requests_count_for_link": pending_leave_requests_count,  # Explicit for new section
        "pending_iou_requests_count_for_link": pending_iou_requests_count,  # Explicit for new section
        "recent_performance_reviews": recent_performance_reviews,
        "department_labels": department_labels,
        "department_counts": department_counts,
        "leave_status_counts": leave_status_chart_data,  # For chart
        "iou_status_counts": pending_iou_requests_count,  # Original name, kept for compatibility
    }
    return render(request, "dashboard_hr.html", context)


@permission_required("payroll.view_employeeprofile", raise_exception=True)
def employee_list(request):
    query = request.GET.get("q")
    department_filter = request.GET.get("department")
    employees = (
        models.EmployeeProfile.objects.all()
    )  # Further filtering by query params
    if query:
        employees = employees.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(job_title__icontains=query)
        )
    if department_filter:
        employees = employees.filter(department__id=department_filter)
    departments = models.Department.objects.all()
    return render(
        request,
        "employee/employee_list.html",
        {"employees": employees, "departments": departments},
    )


@permission_required(
    ["payroll.add_employeeprofile", "users.add_customuser"], raise_exception=True
)
def add_employee(request):
    if request.method == "POST":
        user_form = user_forms.CustomUserCreationForm(request.POST)
        employee_form = EmployeeProfileForm(request.POST, request.FILES)
        if user_form.is_valid() and employee_form.is_valid():
            user = user_form.save()
            employee_profile = employee_form.save(commit=False)
            employee_profile.user = user
            employee_profile.email = user.email
            employee_profile.first_name = (
                user.first_name
            )  # Assuming CustomUser has these fields
            employee_profile.last_name = user.last_name
            employee_profile.save()
            messages.success(request, "Employee added successfully!")
            return redirect("payroll:employee_list")
    else:
        user_form = user_forms.CustomUserCreationForm()
        employee_form = EmployeeProfileForm()
    context = {"user_form": user_form, "employee_form": employee_form}
    return render(request, "employee/add_employee.html", context)


def input_id(request):  # No specific permissions, seems like a generic utility page
    return render(request, "pay/input.html")


@permission_required("payroll.change_employeeprofile", raise_exception=True)
def update_employee(request, id):
    employee = get_object_or_404(models.EmployeeProfile, id=id)
    form = EmployeeProfileForm(request.POST or None, instance=employee)
    if form.is_valid():
        form.save()
        messages.success(request, "Employee updated successfully!!")
        return redirect(
            "payroll:index"
        )  # Consider redirecting to employee list or profile
    return render(request, "employee/update_employee.html", {"form": form})


class EmployeeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = models.EmployeeProfile
    form_class = EmployeeProfileForm
    template_name = (
        "employee/add.html"  # This might conflict with the FBV add_employee's template
    )
    success_url = reverse_lazy("payroll:employee_list")
    permission_required = (
        "payroll.add_employeeprofile",
        "users.add_customuser",
    )  # Assuming form also handles CustomUser creation

    def form_valid(self, form):
        messages.success(self.request, "Employee created successfully.")
        return super().form_valid(form)


class EmployeeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = models.EmployeeProfile
    form_class = EmployeeProfileForm
    template_name = (
        "employee/update.html"  # May conflict with FBV update_employee template
    )
    success_url = reverse_lazy("payroll:employee_list")
    permission_required = "payroll.change_employeeprofile"

    def form_valid(self, form):
        messages.success(self.request, "Employee updated successfully.")
        return super().form_valid(form)


class EmployeeDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = models.EmployeeProfile
    template_name = "employee/delete.html"
    success_url = reverse_lazy("payroll:employee_list")
    permission_required = "payroll.delete_employeeprofile"

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Employee deleted successfully.")
        return super().delete(request, *args, **kwargs)


@permission_required("payroll.delete_employeeprofile", raise_exception=True)
def delete_employee(request, id):  # FBV for delete
    employee_profile = get_object_or_404(models.EmployeeProfile, id=id)
    employee_profile.delete()
    messages.success(request, "Employee deleted Successfully!!")
    return redirect("payroll:employee_list")  # Ensure redirect after delete


@login_required  # Object-level permission logic inside
def employee(request, user_id: int):  # user_id here is CustomUser.id
    target_user_profile = get_object_or_404(models.EmployeeProfile, user_id=user_id)

    # Check if the request.user is viewing their own profile or has general view permission
    if request.user.id == user_id or request.user.has_perm(
        "payroll.view_employeeprofile"
    ):
        employee_profile_to_display = target_user_profile
    else:
        raise HttpResponseForbidden("You are not authorized to view this profile.")

    pay = models.Payday.objects.filter(
        payroll_id__pays__user_id=employee_profile_to_display.user.id
    )
    context = {"emp": employee_profile_to_display, "pay": pay}
    return render(request, "employee/profile.html", context)


@permission_required("payroll.view_performancereview", raise_exception=True)
def performance_reviews(request):  # List all reviews
    query = request.GET.get("q")
    reviews = models.PerformanceReview.objects.all()
    if query:
        reviews = reviews.filter(
            Q(employee__user__first_name__icontains=query)
            | Q(employee__user__last_name__icontains=query)
            | Q(comments__icontains=query)
        )
    return render(request, "employee/performance_reviews.html", {"reviews": reviews})


@permission_required("payroll.view_performancereview", raise_exception=True)
def performance_review_list(
    request,
):  # This view lists all reviews, so general perm is fine
    reviews = models.PerformanceReview.objects.all().order_by("-review_date")
    form = PerformanceReviewForm()  # For adding new review from the list page perhaps
    return render(
        request,
        "reviews/performance_review_list.html",
        {"reviews": reviews, "form": form},
    )


@login_required  # Object-level permission logic inside
def performance_review_detail(request, review_id):
    review = get_object_or_404(models.PerformanceReview, id=review_id)
    # User can view if it's their review, or if they have general view perm for all reviews (e.g., HR)
    if not (
        request.user == review.employee.user
        or request.user.has_perm("payroll.view_performancereview")
    ):
        raise HttpResponseForbidden(
            "You are not authorized to view this performance review."
        )
    return render(request, "reviews/performance_review_detail.html", {"review": review})


@permission_required("payroll.add_performancereview", raise_exception=True)
def add_performance_review(request):
    if request.method == "POST":
        form = PerformanceReviewForm(request.POST)
        if form.is_valid():
            # review = form.save(commit=False) # If employee needs to be set based on logged in user or other logic
            # employee_id = request.POST.get("employee") # This is fine if form includes employee selector
            # if employee_id:
            #     employee_instance = get_object_or_404(models.EmployeeProfile, id=employee_id)
            #     review.employee = employee_instance
            # else: # Should not happen if field is required
            #     messages.error(request, "Employee not specified.")
            #     return redirect("payroll:performance_review_list")
            form.save()  # Assuming form correctly handles employee assignment
            messages.success(request, "Performance review added successfully.")
            return redirect("payroll:performance_review_list")
        else:
            messages.error(
                request, "Error adding performance review. Please check the form."
            )
    # If GET or form invalid, redirecting to list. Consider rendering form on this page.
    # For now, sticking to original logic of redirecting.
    return redirect("payroll:performance_review_list")


@permission_required("payroll.change_performancereview", raise_exception=True)
def edit_performance_review(request, review_id):
    review = get_object_or_404(models.PerformanceReview, id=review_id)
    # Add object-level permission here if only owner/manager can edit, e.g.
    # if not (request.user == review.employee.user or request.user.has_perm('payroll.manage_all_reviews')):
    #     raise HttpResponseForbidden("You cannot edit this review.")
    if request.method == "POST":
        form = PerformanceReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, "Review updated successfully.")
            return redirect("payroll:performance_review_list")  # Or detail view
    # If GET or form invalid, redirecting. Consider rendering form on this page.
    return redirect("payroll:performance_review_list")


@permission_required("payroll.delete_performancereview", raise_exception=True)
def delete_performance_review(request, review_id):
    review = get_object_or_404(models.PerformanceReview, id=review_id)
    # Add object-level permission here similar to edit
    review.delete()
    messages.success(request, "Review deleted successfully.")
    return redirect("payroll:performance_review_list")
