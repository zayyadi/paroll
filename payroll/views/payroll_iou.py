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
from payroll.services.ewa import ew_advance_limits
from payroll.views.payroll_helpers import _can_manage_employee_requests


@login_required
def request_iou(request, kind="iou"):
    """
    Self-service advance request.

    ``kind="iou"`` keeps the legacy flow (cap = monthly net minus
    outstanding). ``kind="ewa"`` is the productized earned-wage-access flow
    governed by the company EWA policy (see ``payroll.services.ewa``):
    advance caps against earned-but-unpaid wages, per-cycle frequency rules,
    and a net-pay take-home guardrail.
    """
    is_ewa = kind == "ewa"
    try:
        company = get_user_company(request.user)
        employee_profile = EmployeeProfile.objects.get(
            user=request.user,
            company=company,
        )
    except EmployeeProfile.DoesNotExist:
        messages.error(
            request,
            "Your user account is not linked to an employee profile. Please contact HR.",
        )
        return redirect("payroll:dashboard")

    monthly_salary = employee_profile.net_pay or Decimal("0.00")
    if monthly_salary <= 0 and employee_profile.employee_pay:
        monthly_salary = employee_profile.employee_pay.basic_salary or Decimal("0.00")
    outstanding_balance = (
        IOU.objects.filter(employee_id=employee_profile)
        .exclude(status__in=["REJECTED", "PAID"])
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0.00")
    )

    if is_ewa:
        ew_limits = ew_advance_limits(employee_profile)
        max_amount = ew_limits["max_available"]
    else:
        ew_limits = None
        max_amount = max(monthly_salary - outstanding_balance, Decimal("0.00"))
    enforce_max = max_amount if max_amount > 0 else None

    if request.method == "POST":
        if is_ewa:
            if not ew_limits["eligible"]:
                # Surface an over-cap amount explicitly before the eligibility
                # reasons: if the user asked for more than the maximum, hiding
                # that behind a timing reason ("next advance from ...") makes
                # them retry the same amount and fail again.
                try:
                    requested = Decimal(request.POST.get("amount") or "0")
                except (ArithmeticError, ValueError, TypeError):
                    requested = Decimal("0")
                if max_amount and requested > max_amount:
                    messages.error(
                        request,
                        f"Your requested amount of ₦{requested:,.0f} exceeds the "
                        f"maximum available (₦{max_amount:,.0f}).",
                    )
                for reason in ew_limits["reasons"]:
                    messages.error(request, reason)
                return redirect("payroll:request_ewa")
            data = request.POST.copy()
            # EWA advances are repaid from the next pay cycle.
            data["tenor"] = "1"
            form = IOURequestForm(data, max_iou_amount=enforce_max)
        else:
            form = IOURequestForm(request.POST, max_iou_amount=enforce_max)
        if form.is_valid():
            iou = form.save(commit=False)
            iou.employee_id = employee_profile
            iou.is_ewa = is_ewa
            if is_ewa:
                iou.tenor = 1
            iou.save()
            messages.success(
                request,
                "Advance request submitted for approval."
                if is_ewa
                else "IOU request submitted successfully.",
            )
            return redirect("payroll:iou_history")
    else:
        form = IOURequestForm(max_iou_amount=enforce_max)

    context = {
        "form": form,
        "employee_profile": employee_profile,
        "monthly_salary": monthly_salary,
        "outstanding_balance": outstanding_balance,
        "max_iou_amount": max_amount,
        "is_ewa": is_ewa,
        "ew_limits": ew_limits,
    }
    template = "iou/request_ewa_new.html" if is_ewa else "iou/request_iou_new.html"
    return render(request, template, context)


@login_required
def request_ewa(request):
    """Self-service earned wage access (EWA) advance request."""
    return request_iou(request, kind="ewa")


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

@login_required
def iou_list(request):  # This is a general list, should be protected
    if not (
        _can_manage_employee_requests(request.user)
        or request.user.has_perm("payroll.view_iou")
    ):
        return HttpResponseForbidden("You are not authorized to view this list.")

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
