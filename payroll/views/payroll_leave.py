"""Payroll views module."""

from decimal import Decimal
import logging
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Case, When, IntegerField
from django.db import transaction
from django.views.generic import CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.conf import settings
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from django.utils import timezone

from company.utils import get_user_company
from accounting.permissions import is_auditor
from payroll import utils
from payroll import models
from payroll.models import EmployeeProfile, PayrollRun, PayrollRunEntry, Payroll, IOU, AuditTrail, Allowance

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)
logger = logging.getLogger(__name__)
from payroll.forms import LeaveRequestForm
from payroll.models import LeavePolicy, LeaveRequest
from payroll.models.payroll import get_leave_balance
from payroll.views.payroll_helpers import _can_manage_employee_requests

def apply_leave(request):
    try:
        company = get_user_company(request.user)
        employee_profile = EmployeeProfile.objects.get(
            user=request.user,
            company=company,
        )
    except EmployeeProfile.DoesNotExist:
        # This can happen if the OneToOneField relation from User to EmployeeProfile
        # is not yet created for this user, or if the related_name is different.
        # Or, if EmployeeProfile has a ForeignKey to User, and no profile exists.
        messages.error(
            request,
            "Your user account is not linked to an employee profile. Please contact HR.",
        )
        # Redirect to a relevant page, perhaps the main dashboard or a profile creation page
        return redirect("payroll:dashboard")
    if request.method == "POST":
        form = LeaveRequestForm(request.POST)
        form.instance.employee = employee_profile
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = employee_profile
            # Pass the current user to the save method for audit logging
            leave_request.save(user=request.user)
            messages.success(request, "Leave request submitted successfully.")
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm()
    return render(request, "employee/apply_leave_new.html", {"form": form})


# def calculate_days(start_date: date, end_date: date) -> int:
#     """
#     Returns number of days between two dates (inclusive).
#     """
#     if start_date > end_date:
#         raise ValueError("Start date cannot be after end date")

#     return (end_date - start_date).days + 1


@login_required

def leave_requests(request):
    user = request.user
    current_year = date.today().year
    company = get_user_company(user)

    try:
        employee_profile = user.employee_user

        # HR / managers / admins can see all company requests; employees see their own.
        if _can_manage_employee_requests(user) or user.has_perm(
            "payroll.view_leaverequest"
        ):
            leave_requests_qs = (
                LeaveRequest.objects.select_related("employee", "approved_by")
                .select_related("processed_leave_allowance")
                .filter(employee__company=company)
                .order_by("-created_at")
            )
        else:
            leave_requests_qs = LeaveRequest.objects.select_related(
                "processed_leave_allowance"
            ).filter(employee=employee_profile)

        # Get leave balance for logged-in user (for dashboard display)
        leave_balance = get_leave_balance(employee_profile, current_year)

        # Calculate total leave taken in the current year
        approved_leaves = LeaveRequest.objects.filter(
            employee=employee_profile,
            status="APPROVED",
        )

        # pending_days = leave_requests_qs.

        # Calculate total days taken by summing durations of approved leaves
        leave_taken = sum(leave.duration for leave in approved_leaves)

        # Calculate pending requests count
        pending_count = LeaveRequest.objects.filter(
            employee=employee_profile, status="PENDING"
        ).count()

        # Calculate available days for each leave type
        if leave_balance:
            leave_balances = {
                "annual": leave_balance.annual_leave,
                "sick": leave_balance.sick_leave,
                "casual": leave_balance.casual_leave,
                "maternity": leave_balance.maternity_leave,
                "paternity": leave_balance.paternity_leave,
            }
        else:
            leave_balances = {}

    except EmployeeProfile.DoesNotExist:
        leave_requests_qs = LeaveRequest.objects.none()
        leave_balance = None
        leave_taken = 0
        pending_count = 0
        leave_balances = {}

        messages.info(
            request, "Your user account is not linked to an employee profile."
        )

    context = {
        "requests": leave_requests_qs,
        "leave_balance": leave_balance,
        "leave_balances": leave_balances,
        "leave_taken": leave_taken,
        "pending_count": pending_count,
        "current_year": current_year,
        "is_hr": _can_manage_employee_requests(user),
    }

    return render(request, "employee/leave_requests_new.html", context)


@login_required
def leave_calendar(request):
    company = get_user_company(request.user)
    if _can_manage_employee_requests(request.user) or request.user.has_perm(
        "payroll.view_leaverequest"
    ):
        leave_requests_qs = LeaveRequest.objects.select_related(
            "employee",
            "employee__department",
            "approved_by",
        ).filter(employee__company=company)
    else:
        try:
            employee_profile = request.user.employee_user
        except EmployeeProfile.DoesNotExist:
            leave_requests_qs = LeaveRequest.objects.none()
        else:
            leave_requests_qs = LeaveRequest.objects.select_related(
                "employee",
                "employee__department",
                "approved_by",
            ).filter(employee=employee_profile)

    leave_requests_qs = leave_requests_qs.filter(status="APPROVED").order_by(
        "start_date",
        "employee__first_name",
    )
    events = [
        {
            "title": str(leave.employee),
            "leave_type": leave.leave_type,
            "start": leave.start_date.isoformat(),
            "end": leave.end_date.isoformat(),
            "duration": leave.duration,
        }
        for leave in leave_requests_qs
    ]
    return render(
        request,
        "employee/leave_calendar.html",
        {
            "leave_requests": leave_requests_qs,
            "calendar_events": events,
        },
    )


@login_required

def manage_leave_requests(request):
    if not _can_manage_employee_requests(request.user):
        return HttpResponseForbidden("You are not authorized to manage leave requests.")

    company = get_user_company(request.user)
    requests = LeaveRequest.objects.filter(
        employee__company=company, status="PENDING"
    )  # Shows only PENDING for action
    return render(
        request, "employee/manage_leave_requests.html", {"requests": requests}
    )


@login_required
@require_POST

def approve_leave(request, pk):
    if not _can_manage_employee_requests(request.user):
        return HttpResponseForbidden(
            "You are not authorized to approve leave requests."
        )

    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
    leave_request.status = "APPROVED"
    leave_request.approved_by = request.user
    # Pass the current user to the save method for audit logging
    try:
        leave_request.save(user=request.user)
    except ValidationError as exc:
        message = "; ".join(exc.messages) if exc.messages else str(exc)
        messages.error(request, message)
        return redirect("payroll:manage_leave_requests")
    messages.success(request, "Leave request approved.")
    return redirect("payroll:manage_leave_requests")


@login_required
@require_POST

def reject_leave(request, pk):
    if not _can_manage_employee_requests(request.user):
        return HttpResponseForbidden("You are not authorized to reject leave requests.")

    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
    leave_request.status = "REJECTED"
    leave_request.approved_by = request.user
    # Pass current user to the save method for audit logging
    leave_request.save(user=request.user)
    messages.success(request, "Leave request rejected.")
    return redirect("payroll:manage_leave_requests")


@permission_required("payroll.view_leavepolicy", raise_exception=True)

def leave_policies(request):
    company = get_user_company(request.user)
    policies = LeavePolicy.objects.filter(company=company)
    return render(request, "employee/leave_policies.html", {"policies": policies})


@login_required  # Combined with object-level check

def edit_leave_request(request, pk):
    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
    # User must be owner or have general change permission
    can_manage = _can_manage_employee_requests(request.user)
    is_owner = request.user == leave_request.employee.user
    if not (is_owner or can_manage):
        return HttpResponseForbidden(
            "You are not authorized to edit this leave request."
        )
    if is_owner and not can_manage and leave_request.status != "PENDING":
        return HttpResponseForbidden(
            "You can only edit leave requests that are still pending."
        )

    if request.method == "POST":
        form = LeaveRequestForm(request.POST, instance=leave_request)
        if form.is_valid():
            # Pass the current user to the save method for audit logging
            leave_request = form.save(commit=False)
            leave_request.save(user=request.user)
            messages.success(request, "Leave request updated successfully.")
            return redirect("payroll:leave_requests")
    else:
        form = LeaveRequestForm(instance=leave_request)
    return render(request, "employee/edit_leave_request.html", {"form": form})


@login_required  # Combined with object-level check

def delete_leave_request(request, pk):
    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
    # User must be owner or have general delete permission
    can_manage = _can_manage_employee_requests(request.user)
    is_owner = request.user == leave_request.employee.user
    if not (is_owner or can_manage):
        return HttpResponseForbidden(
            "You are not authorized to delete this leave request."
        )
    if is_owner and not can_manage and leave_request.status != "PENDING":
        return HttpResponseForbidden(
            "You can only delete leave requests that are still pending."
        )
    leave_request.delete()
    messages.success(request, "Leave request deleted successfully.")
    return redirect("payroll:leave_requests")


@login_required  # Combined with object-level check

def view_leave_request(request, pk):
    company = get_user_company(request.user)
    leave_request = get_object_or_404(LeaveRequest, pk=pk, employee__company=company)
    # User must be owner or have general view permission
    if not (
        request.user == leave_request.employee.user
        or _can_manage_employee_requests(request.user)
        or request.user.has_perm("payroll.view_leaverequest")
    ):
        return HttpResponseForbidden(
            "You are not authorized to view this leave request."
        )
    return render(
        request, "employee/view_leave_request.html", {"leave_request": leave_request}
    )



def _can_view_leave_allowance_slip(user, allowance):
    employee = allowance.employee
    return (
        user == employee.user
        or _can_manage_employee_requests(user)
        or user.has_perm("payroll.view_allowance")
        or is_auditor(user)
    )


@login_required

def leave_allowance_slip(request, pk):
    allowance = get_object_or_404(
        Allowance.objects.select_related(
            "employee__user",
            "employee__company",
            "source_leave_request",
        ),
        pk=pk,
        source_leave_request__isnull=False,
    )
    if not _can_view_leave_allowance_slip(request.user, allowance):
        return HttpResponseForbidden(
            "You are not authorized to view this leave allowance slip."
        )

    return render(
        request,
        "pay/leave_allowance_slip.html",
        {
            "allowance": allowance,
            "leave_request": allowance.source_leave_request,
            "employee": allowance.employee,
            "company": allowance.employee.company,
        },
    )


@login_required

def leave_allowance_slip_pdf(request, pk):
    allowance = get_object_or_404(
        Allowance.objects.select_related(
            "employee__user",
            "employee__company",
            "source_leave_request",
        ),
        pk=pk,
        source_leave_request__isnull=False,
    )
    if not _can_view_leave_allowance_slip(request.user, allowance):
        return HttpResponseForbidden(
            "You are not authorized to view this leave allowance slip."
        )

    employee = allowance.employee
    leave_request = allowance.source_leave_request
    pdf_content = generate_payslip_pdf(
        {
            "allowance": allowance,
            "amount": allowance.amount,
            "employee": employee,
            "employee_name": (
                f"{employee.first_name or ''} {employee.last_name or ''}".strip()
                or employee.email
            ),
            "leave_request": leave_request,
            "company": employee.company,
        },
        template_path="pay/leave_allowance_slip_pdf.html",
    )
    if not pdf_content:
        raise Http404("Unable to generate leave allowance slip PDF.")

    filename = f"leave_allowance_slip_{employee.emp_id or employee.pk}_{leave_request.start_date:%Y_%m_%d}.pdf"
    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
