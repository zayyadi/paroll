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
from accounting.permissions import can_view_payroll_data, can_modify_payroll_data, is_auditor

def dashboard(request):  # payroll admin dashboard
    # Check if user can view payroll data (auditors have view-only access)
    if not can_view_payroll_data(request.user):
        return HttpResponseForbidden("You don't have permission to view payroll data.")

    company = get_user_company(request.user)
    emp = EmployeeProfile.objects.filter(company=company) if company else []
    context = {
        "emp": emp,
        "empty_list": [],  # For empty for loop handling in templates
        "is_auditor": is_auditor(request.user),  # Add auditor flag for template
    }
    return render(request, "pay/dashboard_new.html", context)

