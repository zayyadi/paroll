from decimal import Decimal
from payroll.forms import (
    AppraisalAssignmentForm,
    EmployeeProfileForm,
    EmployeeProfileUpdateForm,
    AppraisalForm,
    ReviewForm,
    BaseRatingFormSet,
)
from payroll import models
from django.contrib.auth.decorators import login_required


from django.db.models import Q, Count, Sum
from django.views.generic.edit import FormView

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import (
    permission_required,
)  # Added permission_required
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    UpdateView,
    DeleteView,
    ListView,
    DetailView,
)
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)  # Added PermissionRequiredMixin, removed UserPassesTestMixin
from django.contrib import messages
from django.views.decorators.cache import cache_page

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


def get_employee_notifications(employee_profile):
    """
    Get notifications for an employee from the Notification model
    """
    # Get notifications from the database model
    notifications = models.Notification.objects.filter(
        recipient=employee_profile
    ).select_related("leave_request", "iou", "payroll", "appraisal")[
        :10
    ]  # Get 10 most recent notifications

    return notifications


@login_required  # index and dashboard remain login_required for now, internal logic dictates content
def index(request):
    # Check if user is HR/Admin (superuser or has payroll permissions)
    if request.user.is_superuser or request.user.has_perm(
        "payroll.view_employeeprofile"
    ):
        # HR/Admin gets the current dashboard
        pay = models.PayT.objects.all()
        pay_count = models.PayVar.objects.aggregate(total=Sum("netpay"))[
            "total"
        ] or Decimal("0.00")

        # Get the most recent pay period
        recent_pay_period = models.PayT.objects.order_by("-paydays").first()
        pending_leaves = models.LeaveRequest.objects.all().filter(
            status="APPROVED",
        )
        # Calculate total for the most recent month
        if recent_pay_period:
            recent_month_total = models.Payday.objects.filter(
                paydays_id=recent_pay_period
            ).aggregate(total=Sum("payroll_id__netpay"))["total"] or Decimal("0.00")
        else:
            recent_month_total = Decimal("0.00")

        previous_pay_period = models.PayT.objects.order_by("-paydays")[1:2].first()
        if previous_pay_period:
            previous_month_total = models.Payday.objects.filter(
                paydays_id=previous_pay_period
            ).aggregate(total=Sum("payroll_id__netpay"))["total"] or Decimal("0.00")

            if previous_month_total > 0:
                percentage_increase = (
                    (recent_month_total - previous_month_total) / previous_month_total
                ) * 100
            else:
                percentage_increase = Decimal("0.00")
        else:
            previous_month_total = Decimal("0.00")
            percentage_increase = Decimal("0.00")

        pay_periods = models.PayT.objects.order_by("paydays")
        pay_period_data = []
        pay_period_labels = []

        for period in pay_periods:
            total = models.Payday.objects.filter(paydays_id=period).aggregate(
                total=Sum("payroll_id__netpay")
            )["total"] or Decimal("0.00")

            if period.paydays:
                month_label = period.paydays.strftime("%b %Y")  # e.g., 'Jan 2025'

            pay_period_labels.append(month_label)
            pay_period_data.append(float(total))

        pay_period_trend_data = {
            "labels": json.dumps(pay_period_labels),
            "data": json.dumps(pay_period_data),
        }

        # Calculate total payee (tax) paid in most recent pay period
        if recent_pay_period:
            total_payee_paid = models.Payday.objects.filter(
                paydays_id=recent_pay_period
            ).aggregate(total=Sum("payroll_id__pays__employee_pay__payee"))[
                "total"
            ] or Decimal(
                "0.00"
            )
        else:
            total_payee_paid = Decimal("0.00")

        # Calculate total payee paid (net pay) in most recent pay period
        if recent_pay_period:
            total_payee_net_paid = models.Payday.objects.filter(
                paydays_id=recent_pay_period
            ).aggregate(total=Sum("payroll_id__netpay"))["total"] or Decimal("0.00")
        else:
            total_payee_net_paid = Decimal("0.00")

        # Calculate department distribution for the department chart
        department_distribution = models.EmployeeProfile.emp_objects.values(
            "department__name"
        ).annotate(count=Count("id"))
        department_labels = json.dumps(
            [
                item["department__name"] if item["department__name"] else "Unassigned"
                for item in department_distribution
            ]
        )
        department_counts = json.dumps(
            [item["count"] for item in department_distribution]
        )

        emp = models.EmployeeProfile.emp_objects.all()
        leave = models.LeaveRequest.objects.all()
        # iou = models.IOU.objects.all()
        count = emp.count()

        print(f" leave: {leave.count()}")
        print(f" graph data: {pay_period_data}")

        context = {
            "pay": pay,
            "emp": emp,
            "count": count,
            "pay_count": pay_count,
            "leave": leave.count(),
            "recent_month_total": recent_month_total,
            "recent_pay_period": recent_pay_period,
            "previous_month_total": previous_month_total,
            "percentage_increase": percentage_increase,
            "total_payee_paid": total_payee_paid,
            "total_payee_net_paid": total_payee_net_paid,
            "pending": pending_leaves.count(),
            "pay_period_data": pay_period_trend_data["data"],
            "pay_period_labels": pay_period_trend_data["labels"],
            "department_labels": department_labels,
            "department_counts": department_counts,
        }
        return render(request, "index.html", context)
    else:
        # Regular employee gets their personal dashboard
        try:
            employee_profile = models.EmployeeProfile.emp_objects.get(user=request.user)

            # Get recent payslips for this employee
            recent_payslips = models.Payday.objects.filter(
                payroll_id__pays__user=request.user
            ).order_by("-paydays_id__paydays")[:5]

            # Get notifications for this employee
            notifications = get_employee_notifications(employee_profile)

            # Get unread count
            unread_count = models.Notification.objects.filter(
                recipient=employee_profile, is_read=False
            ).count()

            # Count pending requests
            pending_requests_count = (
                models.LeaveRequest.objects.filter(
                    employee=employee_profile, status="PENDING"
                ).count()
                + models.IOU.objects.filter(
                    employee_id=employee_profile, status="PENDING"
                ).count()
            )

            context = {
                "emp": employee_profile,
                "recent_payslips": recent_payslips,
                "notifications": notifications,
                "pending_requests_count": pending_requests_count,
                "unread_count": unread_count,
            }
            return render(request, "employee_home.html", context)
        except models.EmployeeProfile.DoesNotExist:
            # If user has no employee profile, show a simple home page
            return render(request, "home_normal.html", {"employee_slug": None})


@login_required
def update_employee_profile(request):
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        raise Http404("Employee profile not found.")

    if request.method == "POST":
        form = EmployeeProfileUpdateForm(
            request.POST, request.FILES, instance=employee_profile
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("payroll:employee_profile")
    else:
        form = EmployeeProfileUpdateForm(instance=employee_profile)

    return render(request, "employee/update_profile.html", {"form": form})


@login_required
def dashboard(request):
    user = request.user

    if user.is_superuser:  # Superuser gets admin dashboard
        return render(request, "dashboard_admin_new.html")
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
            "empty_list": [],  # For empty for loop handling in templates
        }
        return render(request, "employee/dashboard_new.html", context)
    else:  # Regular user dashboard
        assignments = models.AppraisalAssignment.objects.filter(
            appraiser=request.user.employee_user
        )
        context = {
            "assignments": assignments,
            "empty_list": [],  # For empty for loop handling in templates
        }
        return render(request, "dashboard_user_new.html", context)


@permission_required(
    "payroll.view_employeeprofile", raise_exception=True
)  # Example permission for HR dashboard
@cache_page(CACHE_TTL)
def hr_dashboard(request):
    # Counts for the new "Approvals" section links
    pending_leave_requests_count = models.LeaveRequest.objects.filter(
        status="PENDING"
    ).count()
    pending_iou_requests_count = models.IOU.objects.filter(status="PENDING").count()

    total_employees = models.EmployeeProfile.objects.count()
    recent_performance_reviews = models.Appraisal.objects.all().order_by("-end_date")[
        :5
    ]
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

    # Calculate total salary amount paid
    from payroll.models import Payday

    total_salary_paid = (
        Payday.objects.aggregate(total=Sum("payroll_id__netpay"))["total"] or 0
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
        "total_salary_paid": total_salary_paid,  # New field for total salary paid
        "empty_list": [],  # For empty for loop handling in templates
    }
    return render(request, "employee/dashboard_new.html", context)


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
        "employee/employee_list_new.html",
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
            "payroll:employee_list"
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
@cache_page(CACHE_TTL)
def employee(request, user_id: int):  # user_id here is CustomUser.id
    target_user_profile = get_object_or_404(models.EmployeeProfile, user_id=user_id)
    print(target_user_profile.user_id, request.user.id)

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
    return render(request, "employee/profile_new.html", context)


class AppraisalListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = models.Appraisal
    template_name = "reviews/appraisal_list_new.html"
    permission_required = "payroll.view_appraisal"


class AppraisalDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = models.Appraisal
    template_name = "reviews/appraisal_detail.html"
    permission_required = "payroll.view_appraisal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        appraisal = self.get_object()
        reviews = models.Review.objects.filter(appraisal=appraisal)
        assignments = models.AppraisalAssignment.objects.filter(appraisal=appraisal)

        completed_reviews = reviews.count()
        pending_reviews = assignments.count() - completed_reviews

        ratings = models.Rating.objects.filter(review__in=reviews)
        metrics = models.Metric.objects.all()

        metric_ratings = {}
        for metric in metrics:
            metric_ratings[metric.name] = {"ratings": [], "avg": 0}

        for rating in ratings:
            metric_ratings[rating.metric.name]["ratings"].append(rating.rating)

        for metric_name, data in metric_ratings.items():
            if data["ratings"]:
                data["avg"] = sum(data["ratings"]) / len(data["ratings"])

        overall_avg = 0
        if ratings:
            overall_avg = sum([rating.rating for rating in ratings]) / ratings.count()

        context["completed_reviews"] = completed_reviews
        context["pending_reviews"] = pending_reviews
        context["metric_ratings"] = metric_ratings
        context["overall_avg"] = overall_avg

        return context


class AppraisalCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = models.Appraisal
    form_class = AppraisalForm
    template_name = "reviews/appraisal_form.html"
    success_url = reverse_lazy("payroll:appraisal_list")
    permission_required = "payroll.add_appraisal"


class AppraisalUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = models.Appraisal
    form_class = AppraisalForm
    template_name = "reviews/appraisal_form.html"
    success_url = reverse_lazy("payroll:appraisal_list")
    permission_required = "payroll.change_appraisal"


class AppraisalDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = models.Appraisal
    template_name = "reviews/appraisal_confirm_delete.html"
    success_url = reverse_lazy("payroll:appraisal_list")
    permission_required = "payroll.delete_appraisal"


class ReviewCreateView(LoginRequiredMixin, CreateView):
    model = models.Review
    form_class = ReviewForm
    template_name = "reviews/review_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["rating_formset"] = BaseRatingFormSet(self.request.POST)
        else:
            context["rating_formset"] = BaseRatingFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        rating_formset = context["rating_formset"]
        if rating_formset.is_valid():
            review = form.save(commit=False)
            review.appraisal = get_object_or_404(
                models.Appraisal, pk=self.kwargs["appraisal_pk"]
            )
            review.employee = get_object_or_404(
                models.EmployeeProfile, pk=self.kwargs["employee_pk"]
            )
            review.reviewer = self.request.user.employee_user
            review.save()
            rating_formset.instance = review
            rating_formset.save()
            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse_lazy(
            "payroll:appraisal_detail", kwargs={"pk": self.kwargs["appraisal_pk"]}
        )


class ReviewUpdateView(LoginRequiredMixin, UpdateView):
    model = models.Review
    form_class = ReviewForm
    template_name = "reviews/review_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["rating_formset"] = BaseRatingFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context["rating_formset"] = BaseRatingFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        rating_formset = context["rating_formset"]
        if rating_formset.is_valid():
            rating_formset.instance = self.object
            rating_formset.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "payroll:appraisal_detail", kwargs={"pk": self.object.appraisal.pk}
        )


class ReviewDetailView(LoginRequiredMixin, DetailView):
    model = models.Review
    template_name = "reviews/review_detail.html"


class ReviewDeleteView(LoginRequiredMixin, DeleteView):
    model = models.Review
    template_name = "reviews/review_confirm_delete.html"

    def get_success_url(self):
        return reverse_lazy(
            "payroll:appraisal_detail", kwargs={"pk": self.object.appraisal.pk}
        )


class AssignAppraisalView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    form_class = AppraisalAssignmentForm
    template_name = "reviews/appraisal_assign.html"
    success_url = reverse_lazy("payroll:appraisal_list")
    permission_required = "payroll.add_appraisalassignment"

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Appraisal assignment successful.")
        return super().form_valid(form)
