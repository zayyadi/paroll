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
from payroll import utils
from payroll import models
from payroll.models import EmployeeProfile, PayrollRun, PayrollRunEntry, Payroll, IOU, AuditTrail
from payroll.views.payroll_payslips import _queue_payslip_emails_for_payroll_run

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)
logger = logging.getLogger(__name__)
from payroll.forms import PayrollRunForm, PayrollRunCreateForm, PayrollEntryCreateForm

def payday_create_new(request):
    """
    Enhanced view for creating PayrollRun (Pay Period) with efficient employee selection.
    Supports search, filtering, and bulk selection of employees.
    """
    from django.http import JsonResponse
    import json

    # Get all active employees with their related data
    company = get_user_company(request.user)
    employees = (
        EmployeeProfile.objects.filter(status="active", company=company)
        .select_related("user", "employee_pay", "department")
        .prefetch_related("allowances", "deductions")
    )

    # Prepare employee data for JSON serialization
    employees_data = []
    for emp in employees:
        employees_data.append(
            {
                "id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "email": emp.email or emp.user.email if emp.user else "",
                "emp_id": emp.emp_id,
                "department": emp.department.name if emp.department else "N/A",
                "department_id": str(emp.department.id) if emp.department else "",
                "job_title": emp.job_title,
                "job_title_display": emp.get_job_title_display(),
                "net_pay": float(emp.net_pay) if emp.net_pay else 0,
                "photo": emp.photo.url if emp.photo else "default.png",
                "initials": f"{(emp.first_name or '')[:1]}{(emp.last_name or '')[:1]}".upper(),
                "selected": False,
            }
        )

    # Get unique departments and job titles for filters
    from payroll.models import Department

    departments = Department.objects.filter(company=company)
    job_titles = EmployeeProfile._meta.get_field("job_title").choices

    if request.method == "POST":
        logger.info(f"Pay period create POST request received")
        logger.debug(f"POST data: {request.POST}")

        form = PayrollRunCreateForm(request.POST, user=request.user)
        if not form.is_valid():
            logger.error(f"Form validation errors: {form.errors}")
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        else:
            logger.info("Form is valid, proceeding to save")
            # Use the custom save method that creates PayrollRun, PayrollEntry, and PayrollRunEntry entries
            payt = form.save()

            # Get the number of employees added
            employee_count = payt.payroll_payday.count()

            logger.info(
                f"Pay period '{payt.name}' created successfully with {employee_count} employees"
            )

            messages.success(
                request,
                f"Pay period '{payt.name}' created successfully with {employee_count} employees.",
            )
            if _queue_payslip_emails_for_payroll_run(payt):
                messages.success(
                    request,
                    "Payslip emails are being sent in the background.",
                )
            skipped = getattr(payt, "_skipped_employee_reasons", [])
            if skipped:
                messages.warning(
                    request,
                    "Skipped non-eligible employees: " + ", ".join(skipped),
                )
            if payt.closed:
                txn = _get_payroll_close_journal_transaction_number(payt)
                if txn:
                    messages.success(
                        request,
                        f"Payroll period closed and posted to ledger (Journal: {txn}).",
                    )
                else:
                    messages.warning(
                        request,
                        "Payroll period marked closed, but no journal was found. Check Unposted Events report.",
                    )
            return redirect("payroll:pay_period_detail", slug=payt.slug)
    else:
        form = PayrollRunCreateForm(user=request.user)

    context = {
        "form": form,
        "employees_json": json.dumps(employees_data),
        "total_employees": len(employees_data),
        "departments": departments,
        "job_titles": job_titles,
    }
    return render(request, "payroll/payday_create_new.html", context)


@permission_required("payroll.add_payrollrun", raise_exception=True)

def payday_create(request):
    """
    Enhanced view for creating PayrollRun (Pay Period) with efficient employee selection.
    Uses the original PayrollRunForm with proper ManyToMany handling.
    Supports search, filtering, and bulk selection of employees.
    """
    from django.http import JsonResponse
    import json

    # Get all active employees with their related data
    company = get_user_company(request.user)
    employees = (
        EmployeeProfile.objects.filter(status="active", company=company)
        .select_related("user", "employee_pay", "department")
        .prefetch_related("allowances", "deductions")
    )

    # Prepare employee data for JSON serialization
    employees_data = []
    for emp in employees:
        employees_data.append(
            {
                "id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "email": emp.email or emp.user.email if emp.user else "",
                "emp_id": emp.emp_id,
                "department": emp.department.name if emp.department else "N/A",
                "department_id": str(emp.department.id) if emp.department else "",
                "job_title": emp.job_title,
                "job_title_display": emp.get_job_title_display(),
                "net_pay": float(emp.net_pay) if emp.net_pay else 0,
                "photo": emp.photo.url if emp.photo else "default.png",
                "initials": f"{(emp.first_name or '')[:1]}{(emp.last_name or '')[:1]}".upper(),
                "selected": False,
            }
        )

    # Get unique departments and job titles for filters
    from payroll.models import Department

    departments = Department.objects.filter(company=company)
    job_titles = EmployeeProfile._meta.get_field("job_title").choices

    if request.method == "POST":
        form = PayrollRunForm(request.POST, user=request.user)
        if not form.is_valid():
            logger.error(f"Form validation errors: {form.errors}")
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
        else:
            # Save the PayrollRun instance - the form handles ManyToMany automatically
            payt = form.save()

            # Count how many employees were added
            employee_count = payt.payroll_payday.count()

            messages.success(
                request,
                f"Pay period '{payt.name}' created successfully with {employee_count} employees.",
            )
            if _queue_payslip_emails_for_payroll_run(payt):
                messages.success(
                    request,
                    "Payslip emails are being sent in the background.",
                )
            if payt.closed:
                txn = _get_payroll_close_journal_transaction_number(payt)
                if txn:
                    messages.success(
                        request,
                        f"Payroll period closed and posted to ledger (Journal: {txn}).",
                    )
                else:
                    messages.warning(
                        request,
                        "Payroll period marked closed, but no journal was found. Check Unposted Events report.",
                    )
            return redirect("payroll:pay_period_detail", slug=payt.slug)
    else:
        form = PayrollRunForm(user=request.user)

    context = {
        "form": form,
        "employees_json": json.dumps(employees_data),
        "total_employees": len(employees_data),
        "departments": departments,
        "job_titles": job_titles,
    }
    return render(request, "payroll/payday_create.html", context)


@permission_required("payroll.add_payvar", raise_exception=True)

def payvar_create_new(request):
    """
    Enhanced view for creating PayrollEntry (Payroll Variables) for multiple employees.
    Supports search, filtering, and bulk selection of employees.
    """
    from django.http import JsonResponse
    import json

    # Get all active employees with their related data
    company = get_user_company(request.user)
    employees = (
        EmployeeProfile.objects.filter(status="active", company=company)
        .select_related("user", "employee_pay", "department")
        .prefetch_related("allowances", "deductions")
    )

    # Prepare employee data for JSON serialization
    employees_data = []
    for emp in employees:
        employees_data.append(
            {
                "id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "email": emp.email or emp.user.email if emp.user else "",
                "emp_id": emp.emp_id,
                "department": emp.department.name if emp.department else "N/A",
                "department_id": str(emp.department.id) if emp.department else "",
                "job_title": emp.job_title,
                "job_title_display": emp.get_job_title_display(),
                "net_pay": float(emp.net_pay) if emp.net_pay else 0,
                "photo": emp.photo.url if emp.photo else "default.png",
                "initials": f"{(emp.first_name or '')[:1]}{(emp.last_name or '')[:1]}".upper(),
                "selected": False,
            }
        )

    # Get unique departments and job titles for filters
    from payroll.models import Department

    departments = Department.objects.filter(company=company)
    job_titles = EmployeeProfile._meta.get_field("job_title").choices

    if request.method == "POST":
        form = PayrollEntryCreateForm(request.POST, user=request.user)
        if form.is_valid():
            # Use the custom save method that creates PayrollEntry entries
            payvars = form.save()

            # Count how many PayrollEntry entries were created
            payvar_count = len(payvars)

            messages.success(
                request,
                f"Payroll variables created successfully for {payvar_count} employees.",
            )
            return redirect("payroll:varview")
    else:
        form = PayrollEntryCreateForm(user=request.user)

    context = {
        "form": form,
        "employees_json": json.dumps(employees_data),
        "total_employees": len(employees_data),
        "departments": departments,
        "job_titles": job_titles,
    }
    return render(request, "payroll/payvar_create_new.html", context)
