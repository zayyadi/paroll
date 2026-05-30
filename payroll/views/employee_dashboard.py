"""
Dashboard views.
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
from payroll.services.access import visible_employee_profiles_for
from datetime import datetime, date, time
from monthyear import Month

def index(request):
    company = get_user_company(request.user)
    # Check if user is HR/Admin (superuser or has payroll permissions)
    if request.user.is_superuser or request.user.has_perm(
        "payroll.view_employeeprofile"
    ):
        # HR/Admin gets the current dashboard
        pay = models.PayrollRun.objects.filter(company=company, closed=True)

        closed_pay_periods = models.PayrollRun.objects.filter(
            company=company,
            closed=True,
        ).order_by("-paydays")

        # Use latest closed pay period for dashboard totals to avoid inflating values
        # with all historical payroll runs.
        recent_pay_period = closed_pay_periods.first()
        pending_leave_requests = models.LeaveRequest.objects.filter(
            employee__company=company,
            status="PENDING",
        )
        pending_iou_requests = models.IOU.objects.filter(
            employee_id__company=company,
            status="PENDING",
        )
        # Calculate totals for the most recent closed month
        if recent_pay_period:
            recent_period_entries = models.PayrollRunEntry.objects.filter(
                payroll_run=recent_pay_period,
                payroll_entry__company=company,
            )
            recent_month_total = (
                recent_period_entries.aggregate(total=Sum("payroll_entry__netpay"))["total"]
                or Decimal("0.00")
            )
            pay_count = recent_month_total
            processed_payments_count = recent_period_entries.count()
        else:
            recent_month_total = Decimal("0.00")
            pay_count = Decimal("0.00")
            processed_payments_count = 0

        previous_pay_period = closed_pay_periods[1:2].first()
        if previous_pay_period:
            previous_month_total = models.PayrollRunEntry.objects.filter(
                payroll_run=previous_pay_period,
                payroll_entry__company=company,
            ).aggregate(total=Sum("payroll_entry__netpay"))["total"] or Decimal("0.00")

            if previous_month_total > 0:
                percentage_increase = (
                    (recent_month_total - previous_month_total) / previous_month_total
                ) * 100
            else:
                percentage_increase = Decimal("0.00")
        else:
            previous_month_total = Decimal("0.00")
            percentage_increase = Decimal("0.00")

        pay_periods = models.PayrollRun.objects.filter(
            company=company,
            closed=True,
        ).order_by("paydays")
        pay_period_data = []
        pay_period_labels = []

        for period in pay_periods:
            total = models.PayrollRunEntry.objects.filter(
                payroll_run=period,
                payroll_entry__company=company,
            ).aggregate(
                total=Sum("payroll_entry__netpay")
            )["total"] or Decimal("0.00")

            if period.paydays:
                month_label = period.paydays.strftime("%b %Y")  # e.g., 'Jan 2025'

            pay_period_labels.append(month_label)
            pay_period_data.append(float(total))

        pay_period_trend_data = {
            "labels": json.dumps(pay_period_labels),
            "data": json.dumps(pay_period_data),
        }

        # Calculate total payee (tax) paid in the most recent pay period
        if recent_pay_period:
            total_payee_paid = models.PayrollRunEntry.objects.filter(
                payroll_run=recent_pay_period,
                payroll_entry__company=company,
            ).aggregate(total=Sum("payroll_entry__pays__employee_pay__payee"))[
                "total"
            ] or Decimal(
                "0.00"
            )
        else:
            total_payee_paid = Decimal("0.00")

        # Calculate total payee paid (net pay) in the most recent pay period
        if recent_pay_period:
            total_payee_net_paid = models.PayrollRunEntry.objects.filter(
                payroll_run=recent_pay_period,
                payroll_entry__company=company,
            ).aggregate(total=Sum("payroll_entry__netpay"))["total"] or Decimal("0.00")
        else:
            total_payee_net_paid = Decimal("0.00")

        # Calculate department distribution for the department chart
        department_distribution = models.EmployeeProfile.emp_objects.filter(
            company=company
        ).values("department__name").annotate(count=Count("id"))
        department_labels = json.dumps(
            [
                item["department__name"] if item["department__name"] else "Unassigned"
                for item in department_distribution
            ]
        )
        department_counts = json.dumps(
            [item["count"] for item in department_distribution]
        )

        emp = models.EmployeeProfile.emp_objects.filter(company=company)
        leave = models.LeaveRequest.objects.filter(employee__company=company)
        # iou = models.IOU.objects.all()
        count = emp.count()

        # print(f" leave: {leave.count()}")
        # print(f" graph data: {pay_period_data}")

        context = {
            "pay": pay,
            "emp": emp,
            "count": count,
            "pay_count": pay_count,
            "processed_payments_count": processed_payments_count,
            "leave": leave.count(),
            "recent_month_total": recent_month_total,
            "recent_pay_period": recent_pay_period,
            "previous_month_total": previous_month_total,
            "percentage_increase": percentage_increase,
            "total_payee_paid": total_payee_paid,
            "total_payee_net_paid": total_payee_net_paid,
            "pending": pending_leave_requests.count(),
            "pending_leave_requests_count": pending_leave_requests.count(),
            "pending_iou_requests_count": pending_iou_requests.count(),
            "pending_approvals_count": pending_leave_requests.count()
            + pending_iou_requests.count(),
            "pay_period_data": pay_period_trend_data["data"],
            "pay_period_labels": pay_period_trend_data["labels"],
            "department_labels": department_labels,
            "department_counts": department_counts,
            "recent_activities": get_recent_activities(limit=10, company=company),
        }
        return render(request, "index.html", context)
    else:
        # Regular employee gets their personal dashboard
        try:
            employee_profile = models.EmployeeProfile.emp_objects.get(user=request.user)

            # Get recent payslips for this employee
            recent_payslips = models.PayrollRunEntry.objects.filter(
                payroll_entry__pays__user=request.user,
                payroll_entry__company=company,
            ).order_by("-payroll_run__paydays")[:5]

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

def dashboard(request):
    user = request.user
    company = get_user_company(user)

    if user.is_superuser:  # Superuser gets admin dashboard
        return render(request, "dashboard_admin_new.html")
    # Changed from group check to permission check for HR dashboard
    elif request.user.has_perm(
        "payroll.view_employeeprofile"
    ):  # Representative permission for HR
        employee_count = models.EmployeeProfile.objects.filter(company=company).count()
        leave_count = models.LeaveRequest.objects.filter(
            employee__company=company, status="PENDING"
        ).count()
        iou_count = models.IOU.objects.filter(
            employee_id__company=company, status="PENDING"
        ).count()
        allowance_count = models.Allowance.objects.filter(
            employee__company=company
        ).count()
        context = {
            "employee_count": employee_count,
            "leave_count": leave_count,
            "iou_count": iou_count,
            "allowance_count": allowance_count,
            "empty_list": [],  # For empty for loop handling in templates
        }
        return render(request, "employee/dashboard_new.html", context)
    else:  # Regular user dashboard
        reviewer_profile = getattr(request.user, "employee_user", None)
        assignments = models.AppraisalAssignment.objects.none()
        pending_assignment_count = 0
        completed_assignment_count = 0
        next_assignment = None
        recent_payslips = models.PayrollRunEntry.objects.none()
        recent_leaves = models.LeaveRequest.objects.none()
        pending_requests_count = 0
        net_salary = 0

        if reviewer_profile:
            recent_payslips = models.PayrollRunEntry.objects.filter(
                payroll_entry__pays=reviewer_profile,
                payroll_entry__company=company,
            ).order_by("-payroll_run__paydays")[:5]
            recent_leaves = models.LeaveRequest.objects.filter(
                employee=reviewer_profile
            ).order_by("-start_date")[:5]
            pending_requests_count = (
                models.LeaveRequest.objects.filter(
                    employee=reviewer_profile,
                    status="PENDING",
                ).count()
                + models.IOU.objects.filter(
                    employee_id=reviewer_profile,
                    status="PENDING",
                ).count()
            )
            net_salary = reviewer_profile.net_pay or 0
            assignments = (
                models.AppraisalAssignment.objects.filter(
                    appraiser=reviewer_profile,
                    appraisal__company=company,
                )
                .select_related("appraisal", "appraisee")
                .order_by("appraisal__end_date", "id")
            )
            reviewed_pairs = set(
                models.Review.objects.filter(
                    reviewer=reviewer_profile,
                    appraisal__company=company,
                ).values_list("appraisal_id", "employee_id")
            )

            pending_assignments = []
            for assignment in assignments:
                assignment.has_review = (
                    assignment.appraisal_id,
                    assignment.appraisee_id,
                ) in reviewed_pairs
                if not assignment.has_review:
                    pending_assignments.append(assignment)

            completed_assignment_count = assignments.count() - len(pending_assignments)
            pending_assignment_count = len(pending_assignments)
            next_assignment = pending_assignments[0] if pending_assignments else assignments.first()

        context = {
            "assignments": assignments,
            "pending_assignment_count": pending_assignment_count,
            "completed_assignment_count": completed_assignment_count,
            "next_assignment": next_assignment,
            "recent_payslips": recent_payslips,
            "recent_leaves": recent_leaves,
            "pending_requests": pending_requests_count,
            "net_salary": net_salary,
            "empty_list": [],  # For empty for loop handling in templates
        }
        return render(request, "dashboard_user_new.html", context)


@login_required

def standup_dashboard(request):
    return render(request, "standup/dashboard.html")


@permission_required(
    "payroll.view_employeeprofile", raise_exception=True
)  # Example permission for HR dashboard

def hr_dashboard(request):
    company = get_user_company(request.user)
    cache_key = f"hr-dashboard:{company.pk if company else 'none'}:{request.user.pk}"
    cached_context = cache.get(cache_key)
    if cached_context is not None:
        return render(request, "employee/dashboard_new.html", cached_context)
    # Counts for new "Approvals" section links
    pending_leave_requests_count = models.LeaveRequest.objects.filter(
        employee__company=company,
        status="PENDING",
    ).count()
    pending_iou_requests_count = models.IOU.objects.filter(
        employee_id__company=company,
        status="PENDING",
    ).count()

    employee_qs = visible_employee_profiles_for(request.user)
    total_employees = employee_qs.count()
    active_employees_count = employee_qs.filter(status="active").count()
    suspended_employees_count = employee_qs.filter(status="suspended").count()
    terminated_employees_count = employee_qs.filter(status="terminated").count()
    recent_performance_reviews = models.Appraisal.objects.order_by("-end_date")[:5]
    appraisal_qs = models.Appraisal.objects.filter(company=company)
    today = timezone.now().date()
    active_appraisal_count = appraisal_qs.filter(
        start_date__lte=today, end_date__gte=today
    ).count()
    total_appraisal_assignments = models.AppraisalAssignment.objects.filter(
        appraisal__company=company
    ).count()
    completed_appraisal_reviews = (
        models.Review.objects.filter(appraisal__company=company)
        .values("appraisal_id", "employee_id", "reviewer_id")
        .distinct()
        .count()
    )
    pending_appraisal_reviews = max(
        total_appraisal_assignments - completed_appraisal_reviews, 0
    )
    department_distribution = employee_qs.values(
        "department__name"
    ).annotate(count=Count("id"))
    department_labels = json.dumps(
        [item["department__name"] for item in department_distribution]
    )
    department_counts = json.dumps([item["count"] for item in department_distribution])

    leave_status_chart_data = json.dumps(
        [
            pending_leave_requests_count,  # Use already computed value
            models.LeaveRequest.objects.filter(
                employee__company=company, status="APPROVED"
            ).count(),
            models.LeaveRequest.objects.filter(
                employee__company=company, status="REJECTED"
            ).count(),
        ]
    )

    # Calculate total salary amount paid
    from payroll.models import PayrollRunEntry

    total_salary_paid = (
        PayrollRunEntry.objects.filter(payroll_entry__company=company).aggregate(
            total=Sum("payroll_entry__netpay")
        )["total"]
        or 0
    )

    context = {
        "total_employees": total_employees,
        "active_employees_count": active_employees_count,
        "suspended_employees_count": suspended_employees_count,
        "terminated_employees_count": terminated_employees_count,
        "active_leave_requests": pending_leave_requests_count,  # Original name, kept for compatibility
        "leave_count": pending_leave_requests_count,  # Compatibility with dashboard template fallback
        "pending_leave_requests_count_for_link": pending_leave_requests_count,  # Explicit for new section
        "iou_count": pending_iou_requests_count,  # Compatibility with dashboard template fallback
        "pending_iou_requests_count_for_link": pending_iou_requests_count,  # Explicit for new section
        "allowance_count": models.Allowance.objects.filter(
            employee__company=company
        ).count(),  # Compatibility with HR widgets
        "recent_performance_reviews": recent_performance_reviews,
        "appraisal_count": appraisal_qs.count(),
        "active_appraisal_count": active_appraisal_count,
        "pending_appraisal_reviews": pending_appraisal_reviews,
        "department_labels": department_labels,
        "department_counts": department_counts,
        "leave_status_counts": leave_status_chart_data,  # For chart
        "iou_status_counts": pending_iou_requests_count,  # Original name, kept for compatibility
        "total_salary_paid": total_salary_paid,  # New field for total salary paid
        "empty_list": [],  # For empty for loop handling in templates
    }
    cache.set(cache_key, context, 300)
    return render(request, "employee/dashboard_new.html", context)

