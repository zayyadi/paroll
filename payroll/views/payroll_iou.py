"""Payroll views module."""

from decimal import Decimal
import logging

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
from payroll.models import EmployeeProfile, PayrollRun, PayrollRunEntry, Payroll, IOU, AuditTrail

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)
logger = logging.getLogger(__name__)
from payroll.forms import IOUApprovalForm, IOURequestForm, IOUUpdateForm
from payroll.models import IOU
from payroll.views.payroll_helpers import _can_manage_employee_requests

def request_iou(request):
    # Try to get the employee profile linked to the current user
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

    monthly_salary = employee_profile.net_pay or Decimal("0.00")
    if monthly_salary <= 0 and employee_profile.employee_pay:
        monthly_salary = employee_profile.employee_pay.basic_salary or Decimal("0.00")
    outstanding_balance = (
        IOU.objects.filter(employee_id=employee_profile)
        .exclude(status__in=["REJECTED", "PAID"])
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )
    max_iou_amount = max(monthly_salary - outstanding_balance, Decimal("0.00"))
    enforce_max_iou_amount = max_iou_amount if max_iou_amount > 0 else None

    if request.method == "POST":
        form = IOURequestForm(request.POST, max_iou_amount=enforce_max_iou_amount)
        if form.is_valid():
            iou = form.save(commit=False)
            iou.employee_id = employee_profile  # Assign the EmployeeProfile instance
            iou.save()
            messages.success(request, "IOU request submitted successfully.")
            return redirect("payroll:iou_history")
    else:
        # Pass the employee_profile to the form if you want to pre-fill or hide the employee field
        # This depends on how IOURequestForm is defined.
        # If 'employee_id' is a field in your form, you might want to make it read-only
        # or exclude it if it's always the current user.
        form = IOURequestForm(max_iou_amount=enforce_max_iou_amount)
        # Or, if you exclude 'employee_id' from the form:
        # form = IOURequestForm()
    context = {
        "form": form,
        "employee_profile": employee_profile,  # Pass the profile for context
        "monthly_salary": monthly_salary,
        "outstanding_balance": outstanding_balance,
        "max_iou_amount": max_iou_amount,
    }

    return render(request, "iou/request_iou_new.html", context)


@login_required

def approve_iou(request, iou_id):
    if not _can_manage_employee_requests(request.user):
        return HttpResponseForbidden("You are not authorized to approve IOU requests.")

    company = get_user_company(request.user)
    iou = get_object_or_404(IOU, id=iou_id, employee_id__company=company)
    if request.method == "POST":
        form = IOUApprovalForm(request.POST, instance=iou)
        if form.is_valid():
            form.save()
            messages.success(request, "IOU approved successfully.")
            return redirect(
                "payroll:iou_history"
            )  # Assuming iou_history is the correct name
    else:
        form = IOUApprovalForm(instance=iou)
    return render(request, "iou/approve_iou.html", {"form": form, "iou": iou})



class IOUUpdateView(
    LoginRequiredMixin,
    SuccessMessageMixin,
    UpdateView,
):
    model = IOU
    form_class = IOUUpdateForm
    template_name = "iou/iou_update_form.html"  # Path to your update template
    context_object_name = "iou"  # To match {{ iou }} in your template
    success_url = reverse_lazy("payroll:iou_history")
    success_message = "IOU request updated successfully."

    def get_queryset(self):
        company = get_user_company(self.request.user)
        if _can_manage_employee_requests(self.request.user):
            return IOU.objects.filter(employee_id__company=company)

        try:
            employee_profile = EmployeeProfile.objects.get(
                user=self.request.user,
                company=company,
            )
        except EmployeeProfile.DoesNotExist:
            return IOU.objects.none()
        return IOU.objects.filter(
            employee_id=employee_profile,
            employee_id__company=company,
            status="PENDING",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The 'iou' object (the instance being updated) is already in context
        # You can add more context if needed
        # context['page_title'] = f"Update IOU: {self.object.id}"
        return context

    # Optional: If you need to perform actions before/after form validation/saving
    # def form_valid(self, form):
    #     # For example, log who updated the IOU
    #     # form.instance.last_modified_by = self.request.user
    #     return super().form_valid(form)



class IOUDeleteView(
    LoginRequiredMixin,
    SuccessMessageMixin,
    DeleteView,
):
    model = IOU
    template_name = (
        "iou/iou_confirm_delete.html"  # Path to your delete confirmation template
    )
    context_object_name = "iou"
    success_url = reverse_lazy("payroll:iou_history")
    success_message = "IOU request deleted successfully."

    def get_queryset(self):
        company = get_user_company(self.request.user)
        if _can_manage_employee_requests(self.request.user):
            return IOU.objects.filter(employee_id__company=company)

        try:
            employee_profile = EmployeeProfile.objects.get(
                user=self.request.user,
                company=company,
            )
        except EmployeeProfile.DoesNotExist:
            return IOU.objects.none()
        return IOU.objects.filter(
            employee_id=employee_profile,
            employee_id__company=company,
            status="PENDING",
        )


@login_required  # Shows user's own IOUs or all if staff/has permission

def iou_history(request):
    company = get_user_company(request.user)
    try:
        employee_profile = EmployeeProfile.objects.get(
            user=request.user,
            company=company,
        )
        if _can_manage_employee_requests(request.user) or request.user.has_perm(
            "payroll.view_iou"
        ):
            ious = IOU.objects.filter(employee_id__company=company).order_by(
                "-created_at"
            )
        else:
            ious = IOU.objects.filter(
                employee_id=employee_profile,
                employee_id__company=company,
            ).order_by("-created_at")
    except EmployeeProfile.DoesNotExist:
        if _can_manage_employee_requests(request.user) or can_view_payroll_data(
            request.user
        ):
            ious = IOU.objects.filter(employee_id__company=company).order_by(
                "-created_at"
            )
        else:
            ious = IOU.objects.none()
            messages.info(
                request, "Your user account is not linked to an employee profile."
            )

    pending_count = ious.filter(status="PENDING").count()
    approved_amount = (
        ious.filter(status="APPROVED").aggregate(total=Sum("amount")).get("total") or 0
    )
    outstanding_balance = (
        ious.exclude(status__in=["REJECTED", "PAID"])
        .aggregate(total=Sum("amount"))
        .get("total")
        or 0
    )

    context = {
        "ious": ious,
        "pending_count": pending_count,
        "approved_amount": approved_amount,
        "outstanding_balance": outstanding_balance,
        "is_auditor": is_auditor(request.user),  # Add auditor flag for template
        "can_manage_requests": _can_manage_employee_requests(request.user),
    }
    return render(request, "iou/iou_history_new.html", context)


@login_required

def my_iou_tracker(request):
    try:
        company = get_user_company(request.user)
        employee_profile = EmployeeProfile.objects.get(
            user=request.user,
            company=company,
        )
    except EmployeeProfile.DoesNotExist:
        messages.info(
            request, "Your user account is not linked to an employee profile."
        )
        return render(
            request,
            "iou/my_iou_tracker.html",
            {
                "ious": IOU.objects.none(),
                "pending_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "paid_count": 0,
                "outstanding_balance": Decimal("0.00"),
            },
        )

    ious = IOU.objects.filter(
        employee_id=employee_profile,
        employee_id__company=company,
    ).order_by("-created_at")
    pending_count = ious.filter(status="PENDING").count()
    approved_count = ious.filter(status="APPROVED").count()
    rejected_count = ious.filter(status="REJECTED").count()
    paid_count = ious.filter(status="PAID").count()
    outstanding_balance = ious.exclude(status__in=["REJECTED", "PAID"]).aggregate(
        total=Sum("amount")
    ).get("total") or Decimal("0.00")

    context = {
        "ious": ious,
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "paid_count": paid_count,
        "outstanding_balance": outstanding_balance,
    }
    return render(request, "iou/my_iou_tracker.html", context)


# log_audit_trail is a utility, no permission needed directly on it

def iou_list(request):  # This is a general list, should be protected
    # If this is for admins/HR to see all IOUs:
    # if not request.user.has_perm('payroll.view_iou'):
    #     # If it's for users to see their own, redirect to iou_history or filter by own
    #     # For now, let's assume this is an admin/HR view of ALL IOUs
    #     raise HttpResponseForbidden("You are not authorized to view this list.")
    company = get_user_company(request.user)
    ious = (
        IOU.objects.filter(employee_id__company=company)
        .annotate(
            status_priority=Case(
                When(status="PENDING", then=0),
                When(status="APPROVED", then=1),
                When(status="PAID", then=2),
                When(status="REJECTED", then=3),
                default=9,
                output_field=IntegerField(),
            )
        )
        .order_by("status_priority", "-created_at")
    )
    return render(request, "iou/iou_list.html", {"ious": ious})


@login_required  # Object-level permission logic inside

def iou_detail(request, pk):
    company = get_user_company(request.user)
    iou = get_object_or_404(IOU, pk=pk, employee_id__company=company)
    if not (
        request.user == iou.employee_id.user
        or _can_manage_employee_requests(request.user)
        or request.user.has_perm("payroll.view_iou")
    ):
        return HttpResponseForbidden("You are not authorized to view this IOU.")
    return render(
        request,
        "iou/iou_detail.html",
        {
            "iou": iou,
            "can_manage_requests": _can_manage_employee_requests(request.user),
        },
    )


@login_required

def iou_payment_slip(request, pk):
    company = get_user_company(request.user)
    iou = get_object_or_404(IOU, pk=pk, employee_id__company=company)
    if not (
        request.user == iou.employee_id.user
        or _can_manage_employee_requests(request.user)
        or request.user.has_perm("payroll.view_iou")
        or request.user.has_perm("payroll.change_iou")
    ):
        return HttpResponseForbidden(
            "You are not authorized to view this IOU payment slip."
        )

    deductions = iou.deductions.select_related("payday").order_by("payday__paydays")
    repaid_amount = iou.repaid_amount
    outstanding_amount = iou.outstanding_amount
    monthly_expected = Decimal("0.00")
    if iou.employee_id:
        monthly_netpay = Decimal(iou.employee_id.net_pay or Decimal("0.00"))
        if monthly_netpay > 0:
            monthly_expected = (
                monthly_netpay * Decimal(iou.repayment_deduction_percentage or 0)
            ) / Decimal("100")

    context = {
        "iou": iou,
        "deductions": deductions,
        "repaid_amount": repaid_amount,
        "outstanding_amount": outstanding_amount,
        "monthly_expected": monthly_expected,
    }
    return render(request, "iou/iou_payment_slip.html", context)


# New Views for Enhanced PayrollRunEntry and PayrollEntry Creation

