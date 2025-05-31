from payroll.forms import (
    EmployeeProfileForm,
    PerformanceReviewForm,
)
from payroll import models

from django.db.models import Q, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages

from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.http import (
    Http404,
    HttpResponseForbidden,
)  # Import Http404 and HttpResponseForbidden

import json  # Import json

from django.core.cache.backends.base import DEFAULT_TIMEOUT

# from django.views.decorators.cache import cache_page
from users import forms as user_forms

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)


def check_super(user):
    return user.is_superuser


@login_required
def index(request):
    pay = models.PayT.objects.all()
    pay_count = models.PayT.objects.all().count()
    emp = models.EmployeeProfile.emp_objects.all()
    count = emp.count()

    context = {
        "pay": pay,
        "emp": emp,
        "count": count,
        "pay_count": pay_count,
    }

    if request.user.is_superuser:
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

    if user.is_superuser:
        return render(request, "dashboard_admin.html")

    elif user.groups.filter(name="HR").exists():
        employee_count = models.EmployeeProfile.objects.count()
        leave_count = models.LeaveRequest.objects.filter(
            status="PENDING"
        ).count()  # Only pending leaves for HR dashboard
        iou_count = models.IOU.objects.filter(
            status="PENDING"
        ).count()  # Only pending IOUs for HR dashboard
        # disciplinary_count = DisciplinaryAction.objects.count()
        allowance_count = models.Allowance.objects.count()

        context = {
            "employee_count": employee_count,
            "leave_count": leave_count,
            "iou_count": iou_count,
            # 'disciplinary_count': disciplinary_count,
            "allowance_count": allowance_count,
        }
        return render(request, "dashboard_hr.html", context)

    else:
        return render(request, "dashboard_user.html")


@login_required
def hr_dashboard(request):
    total_employees = models.EmployeeProfile.objects.count()
    active_leave_requests = models.LeaveRequest.objects.filter(status="PENDING").count()
    recent_performance_reviews = models.PerformanceReview.objects.all().order_by(
        "-review_date"
    )[:5]

    # Employee Distribution by Department
    department_distribution = models.EmployeeProfile.objects.values(
        "department__name"
    ).annotate(count=Count("id"))
    department_labels = json.dumps(
        [item["department__name"] for item in department_distribution]
    )
    department_counts = json.dumps([item["count"] for item in department_distribution])

    # Leave Requests by Status
    leave_status_counts = json.dumps(
        [
            models.LeaveRequest.objects.filter(status="PENDING").count(),
            models.LeaveRequest.objects.filter(status="APPROVED").count(),
            models.LeaveRequest.objects.filter(status="REJECTED").count(),
        ]
    )

    context = {
        "total_employees": total_employees,
        "active_leave_requests": active_leave_requests,
        "recent_performance_reviews": recent_performance_reviews,
        "department_labels": department_labels,
        "department_counts": department_counts,
        "leave_status_counts": leave_status_counts,
    }
    return render(request, "employee/dashboard.html", context)


def employee_list(request):
    query = request.GET.get("q")
    department_filter = request.GET.get("department")
    employees = models.EmployeeProfile.objects.all()

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


def performance_reviews(request):
    query = request.GET.get("q")
    reviews = models.PerformanceReview.objects.all()

    if query:
        reviews = reviews.filter(
            Q(employee__user__first_name__icontains=query)
            | Q(employee__user__last_name__icontains=query)
            | Q(comments__icontains=query)
        )

    return render(request, "employee/performance_reviews.html", {"reviews": reviews})


@user_passes_test(check_super)
@login_required
def add_employee(request):
    if request.method == "POST":
        # Assuming CustomUserChangeForm is for the *new* user, not request.user
        # This part needs careful consideration if CustomUserChangeForm is meant for the logged-in user.
        # For adding a new employee, typically you'd create a new CustomUser instance.
        # For simplicity, I'll assume CustomUserChangeForm is for the new employee's user details.
        # However, the instance=request.user is problematic for adding a new user.
        # Let's assume for now that CustomUserChangeForm is for updating the *current* user's profile,
        # and EmployeeProfileForm is for creating a new employee profile. This is a common pattern.
        # But the current code tries to save EmployeeProfileForm without linking to a new user.

        # Re-evaluating: The original code seems to imply that `add_employee` is for a superuser
        # to add an employee, and it tries to update `request.user` (the superuser) and create
        # an `EmployeeProfile`. This is a logical flaw.

        # Let's refactor this to correctly add a new EmployeeProfile and optionally a new CustomUser.
        # The `EmployeeCreateView` is better suited for this.
        # I will make this `add_employee` function create a new EmployeeProfile and a new CustomUser.

        user_form = user_forms.CustomUserCreationForm(
            request.POST
        )  # Use creation form for new user
        employee_form = EmployeeProfileForm(request.POST, request.FILES)

        if user_form.is_valid() and employee_form.is_valid():
            user = user_form.save()
            employee_profile = employee_form.save(commit=False)
            employee_profile.user = user  # Link the new user to the employee profile
            employee_profile.email = user.email  # Ensure email is synced
            employee_profile.first_name = user.first_name
            employee_profile.last_name = user.last_name
            employee_profile.save()

            messages.success(request, "Employee added successfully!")
            return redirect(
                "payroll:employee_list"
            )  # Redirect to employee list after adding

    else:
        user_form = user_forms.CustomUserCreationForm()
        employee_form = EmployeeProfileForm()

    context = {
        "user_form": user_form,
        "employee_form": employee_form,
    }

    return render(request, "employee/add_employee.html", context)


def input_id(request):
    return render(request, "pay/input.html")


@user_passes_test(check_super)
def update_employee(request, id):
    employee = get_object_or_404(models.EmployeeProfile, id=id)
    form = EmployeeProfileForm(request.POST or None, instance=employee)

    if form.is_valid():
        form.save()
        messages.success(request, "Employee updated successfully!!")
        return redirect("payroll:index")

    else:
        form = EmployeeProfileForm(instance=employee)

    return render(request, "employee/update_employee.html", {"form": form})


class EmployeeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = models.EmployeeProfile
    form_class = EmployeeProfileForm
    template_name = "employee/add.html"
    success_url = reverse_lazy("payroll:employee_list")

    def form_valid(self, form):
        messages.success(self.request, "Employee created successfully.")
        return super().form_valid(form)

    def test_func(self):
        return check_super(self.request.user)


class EmployeeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = models.EmployeeProfile
    form_class = EmployeeProfileForm
    template_name = "employee/update.html"
    success_url = reverse_lazy("payroll:employee_list")

    def form_valid(self, form):
        messages.success(self.request, "Employee updated successfully.")
        return super().form_valid(form)

    def test_func(self):
        return check_super(self.request.user)


class EmployeeDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = models.EmployeeProfile
    template_name = "employee/delete.html"
    success_url = reverse_lazy("payroll:employee_list")

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Employee deleted successfully.")
        return super().delete(request, *args, **kwargs)

    def test_func(self):
        return check_super(self.request.user)


@user_passes_test(check_super)
def delete_employee(request, id):
    pay = get_object_or_404(models.EmployeeProfile, id=id)
    pay.delete()
    messages.success(request, "Employee deleted Successfully!!")


@login_required
def employee(request, user_id: int):
    # Allow superusers and HR to view any employee profile
    if request.user.is_superuser or request.user.groups.filter(name="HR").exists():
        try:
            employee_profile = get_object_or_404(
                models.EmployeeProfile, user_id=user_id
            )
        except Http404:
            raise Http404("Employee profile not found.")
    else:
        # Regular users can only view their own profile
        if user_id != request.user.id:
            raise HttpResponseForbidden("You are not authorized to view this page.")
        try:
            employee_profile = get_object_or_404(
                models.EmployeeProfile, user_id=request.user.id
            )
        except Http404:
            raise Http404("Your employee profile was not found.")

    pay = models.Payday.objects.filter(
        payroll_id__pays__user_id=employee_profile.user.id
    )

    context = {"emp": employee_profile, "pay": pay}
    return render(request, "employee/profile.html", context)


def performance_review_list(request):
    reviews = models.PerformanceReview.objects.all().order_by("-review_date")
    form = PerformanceReviewForm()
    return render(
        request,
        "reviews/performance_review_list.html",
        {"reviews": reviews, "form": form},
    )


def performance_review_detail(request, review_id):
    review = get_object_or_404(models.PerformanceReview, id=review_id)
    return render(request, "reviews/performance_review_detail.html", {"review": review})


def add_performance_review(request):
    if request.method == "POST":
        form = PerformanceReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            # Assuming employee_id is passed in the form data (e.g., a hidden input)
            employee_id = request.POST.get("employee")
            if employee_id:
                employee = get_object_or_404(models.EmployeeProfile, id=employee_id)
                review.employee = employee
            else:
                messages.error(
                    request, "Employee not specified for performance review."
                )
                return redirect("payroll:performance_review_list")

            review.save()
            messages.success(request, "Performance review added successfully.")
            return redirect("payroll:performance_review_list")
        else:
            messages.error(
                request, "Error adding performance review. Please check the form."
            )
    return redirect("payroll:performance_review_list")


def edit_performance_review(request, review_id):
    review = get_object_or_404(models.PerformanceReview, id=review_id)
    if request.method == "POST":
        form = PerformanceReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, "Review updated successfully.")
    return redirect("payroll:performance_review_list")


def delete_performance_review(request, review_id):
    review = get_object_or_404(models.PerformanceReview, id=review_id)
    review.delete()
    messages.success(request, "Review deleted successfully.")
    return redirect("payroll:performance_review_list")
