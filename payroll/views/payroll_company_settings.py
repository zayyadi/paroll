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
from payroll.forms import CompanyPayrollSettingForm, CompanyHealthInsuranceTierFormSet
from payroll.models import CompanyPayrollSetting

def company_payroll_settings(request):
    company = get_user_company(request.user)
    if not company:
        messages.error(request, "No active company found for your account.")
        return redirect("payroll:dashboard")

    settings_obj, created = CompanyPayrollSetting.objects.get_or_create(company=company)
    if created:
        settings_obj.create_default_health_tiers()
    tiers = settings_obj.health_insurance_tiers.all()

    context = {
        "company": company,
        "settings_obj": settings_obj,
        "tiers": tiers,
    }
    return render(request, "payroll/company_payroll_settings.html", context)


@permission_required("payroll.change_companypayrollsetting", raise_exception=True)

def company_payroll_settings_edit(request):
    company = get_user_company(request.user)
    if not company:
        messages.error(request, "No active company found for your account.")
        return redirect("payroll:dashboard")

    settings_obj, created = CompanyPayrollSetting.objects.get_or_create(company=company)
    if created:
        settings_obj.create_default_health_tiers()

    if request.method == "POST":
        form = CompanyPayrollSettingForm(request.POST, instance=settings_obj)
        formset = CompanyHealthInsuranceTierFormSet(
            request.POST, instance=settings_obj, prefix="tiers"
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, "Payroll settings updated successfully.")
            return redirect("payroll:company_payroll_settings")
    else:
        form = CompanyPayrollSettingForm(instance=settings_obj)
        formset = CompanyHealthInsuranceTierFormSet(
            instance=settings_obj, prefix="tiers"
        )

    context = {
        "company": company,
        "form": form,
        "formset": formset,
    }
    return render(request, "payroll/company_payroll_settings_form.html", context)

