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

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)
logger = logging.getLogger(__name__)
from payroll.forms import AllowanceForm
from payroll.models import Allowance

def create_allowance(request):
    # Check if user can modify payroll data (auditors have view-only access)
    if not can_modify_payroll_data(request.user):
        return HttpResponseForbidden(
            "You don't have permission to modify payroll data."
        )

    a_form = AllowanceForm(request.POST or None)
    if a_form.is_valid():
        a_form.save()
        messages.success(request, "Allowance created successfully")
        return redirect("payroll:index")
    context = {"form": a_form}
    return render(request, "pay/add_allowance.html", context)


@permission_required("payroll.change_allowance", raise_exception=True)

def edit_allowance(request, id):
    # Check if user can modify payroll data (auditors have view-only access)
    if not can_modify_payroll_data(request.user):
        return HttpResponseForbidden(
            "You don't have permission to modify payroll data."
        )

    company = get_user_company(request.user)
    var = get_object_or_404(Allowance, id=id, employee__company=company)
    form = AllowanceForm(request.POST or None, instance=var)
    if form.is_valid():
        form.save()
        messages.success(request, "Allowance updated successfully!!")
        return redirect("payroll:dashboard")  # Or a list view for allowances
    context = {"form": form, "var": var}
    return render(
        request, "pay/var.html", context
    )  # var.html seems generic, consider renaming template


@permission_required("payroll.delete_allowance", raise_exception=True)

def delete_allowance(request, id):
    # Check if user can modify payroll data (auditors have view-only access)
    if not can_modify_payroll_data(request.user):
        return HttpResponseForbidden(
            "You don't have permission to modify payroll data."
        )

    company = get_user_company(request.user)
    allowance_obj = get_object_or_404(
        Allowance, id=id, employee__company=company
    )  # Renamed variable
    allowance_obj.delete()
    messages.success(request, "Allowance deleted Successfully!!")
    return redirect("payroll:dashboard")  # Or a list view for allowances


# @permission_required("payroll.add_deduction", raise_exception=True)

