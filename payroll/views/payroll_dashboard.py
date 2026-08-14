"""Payroll views module."""

from decimal import Decimal
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Case, When, IntegerField, Count
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
from payroll import utils
from payroll import models
from payroll.models import EmployeeProfile, PayrollRun, PayrollRunEntry, Payroll, IOU, AuditTrail
from payroll.services.compliance import compliance_summary

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)
logger = logging.getLogger(__name__)
from accounting.permissions import can_view_payroll_data, can_modify_payroll_data, is_auditor


def _payroll_ready_ids(employee_qs):
    """Ids of employees whose payroll profile is ready (salary + bank details)."""
    return set(
        employee_qs.filter(employee_pay__isnull=False)
        .exclude(bank_account_number__isnull=True)
        .exclude(bank_account_number="")
        .values_list("id", flat=True)
    )


def dashboard(request):  # payroll admin dashboard
    # Check if user can view payroll data (auditors have view-only access)
    if not can_view_payroll_data(request.user):
        return HttpResponseForbidden("You don't have permission to view payroll data.")

    company = get_user_company(request.user)
    emp = EmployeeProfile.objects.filter(company=company) if company else EmployeeProfile.objects.none()
    total_employees = emp.count()

    ready_ids = _payroll_ready_ids(emp)
    payroll_ready_percent = round(len(ready_ids) / total_employees * 100) if total_employees else 0

    # Real salary roster for the breakdown table (monthly figures).
    roster = []
    for employee in emp.select_related("employee_pay", "department")[:6]:
        pay = employee.employee_pay
        if pay and pay.gross_income:
            gross = Decimal(pay.gross_income) / 12
        else:
            gross = Decimal("0.00")
        roster.append(
            {
                "name": f"{employee.first_name} {employee.last_name}".strip(),
                "initials": (
                    (employee.first_name[:1] + employee.last_name[:1]).upper()
                    if employee.first_name or employee.last_name
                    else "?"
                ),
                "job_title": (
                    employee.get_job_title_display() or employee.job_title or "Employee"
                ),
                "department": employee.department.name if employee.department else "—",
                "gross": gross,
                "net": employee.net_pay or Decimal("0.00"),
                "ready": employee.pk in ready_ids,
            }
        )

    # Real payment-method distribution: employees grouped by their bank.
    bank_distribution = []
    bank_rows = (
        emp.exclude(bank__isnull=True)
        .exclude(bank="")
        .values("bank")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    banked_total = sum(row["count"] for row in bank_rows) or 1
    for row in bank_rows:
        bank_distribution.append(
            {
                "label": EmployeeProfile(bank=row["bank"]).get_bank_display(),
                "count": row["count"],
                "percent": round(row["count"] / banked_total * 100),
            }
        )

    # Real cost-of-employment summary for the company (monthly figures,
    # matching the Cost of Employment report): total employer cost vs total
    # net pay, with the employer-levy split from the stored fields (NSITF is
    # monthly; the annual ITF is divided by 12 like the other levies).
    cost_summary = {
        "employees": 0,
        "gross": Decimal("0.00"),
        "net_pay": Decimal("0.00"),
        "employer_pension": Decimal("0.00"),
        "employer_nhia": Decimal("0.00"),
        "employer_nsitf": Decimal("0.00"),
        "employer_itf": Decimal("0.00"),
        "employer_cost": Decimal("0.00"),
    }
    for employee in emp.select_related("employee_pay"):
        pay = employee.employee_pay
        if pay is None or not pay.gross_income:
            continue
        breakdown = utils.monthly_cost_breakdown(pay)
        for key in (
            "gross",
            "net_pay",
            "employer_pension",
            "employer_nhia",
            "employer_nsitf",
            "employer_itf",
            "employer_cost",
        ):
            cost_summary[key] += breakdown[key]
        cost_summary["employees"] += 1

    # Statutory exposure at a glance: overdue count/amount and the next open
    # deadline, shared with the compliance calendar so both surfaces agree.
    compliance = compliance_summary(company)
    next_due_obligation = next(
        (
            o
            for o in compliance["obligations"]
            if o["status"] in ("due_soon", "upcoming")
        ),
        None,
    )

    context = {
        "emp": emp,
        "empty_list": [],  # For empty for loop handling in templates
        "is_auditor": is_auditor(request.user),  # Add auditor flag for template
        "total_employees": total_employees,
        "payroll_ready_count": len(ready_ids),
        "payroll_ready_percent": payroll_ready_percent,
        "payroll_ready_ids": ready_ids,
        "payroll_roster": roster,
        "bank_distribution": bank_distribution,
        "cost_summary": cost_summary,
        "employer_levy_rows": [
            {"label": "Pension (ER)", "amount": cost_summary["employer_pension"]},
            {"label": "NHIA (ER)", "amount": cost_summary["employer_nhia"]},
            {"label": "NSITF", "amount": cost_summary["employer_nsitf"]},
            {"label": "ITF", "amount": cost_summary["employer_itf"]},
        ],
        "overdue_count": compliance["overdue_count"],
        "overdue_amount": compliance["overdue_amount"],
        "next_due_obligation": next_due_obligation,
    }
    return render(request, "pay/dashboard_new.html", context)
