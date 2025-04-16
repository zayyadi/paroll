from payroll.forms import (
    EmployeeProfileForm,
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
from django.core.cache.backends.base import DEFAULT_TIMEOUT

# from django.views.decorators.cache import cache_page
from users import forms as user_forms

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)


def check_super(user):
    return user.is_superuser


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
    department_labels = [item["department__name"] for item in department_distribution]
    department_counts = [item["count"] for item in department_distribution]

    # Leave Requests by Status
    leave_status_counts = [
        models.LeaveRequest.objects.filter(status="PENDING").count(),
        models.LeaveRequest.objects.filter(status="APPROVED").count(),
        models.LeaveRequest.objects.filter(status="REJECTED").count(),
    ]

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
    # created = EmployeeProfile.objects.get_or_create(user=request.user)  # noqa: F841
    if request.method == "POST":
        u_form = user_forms.CustomUserChangeForm(request.POST, instance=request.user)
        e_form = EmployeeProfileForm(
            request.POST or None,
            request.FILES or None,
        )

        if u_form.is_valid and e_form.is_valid():
            e_form.save()

            messages.success(request, f"Your account has been updated!")  # noqa: F541
            return redirect("payroll:index")

    else:
        # u_form = UserEditForm(instance=request.user)
        e_form = EmployeeProfileForm(instance=request.user)

    context = {
        "e_form": e_form,
        # "u_form": u_form,
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
        form = EmployeeProfileForm()

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
    try:
        user_id = request.user.id
        print(user_id)
        if user_id:
            user = get_object_or_404(models.EmployeeProfile, user_id=user_id)

            pay = models.Payday.objects.all().filter(payroll_id__pays__user_id=user_id)
            print(f"payroll_id:{pay}")
        else:
            raise Exception("You are not the owner")

    except Exception as e:
        raise (e, "You re Not Authorized to view this page")

    context = {"emp": user, "pay": pay}
    return render(request, "employee/profile.html", context)
