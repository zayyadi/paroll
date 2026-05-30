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
from payroll.forms import DeductionForm
from payroll.models import Deduction

class AddDeduction(PermissionRequiredMixin, CreateView):
    model = Deduction
    form_class = DeductionForm
    template_name = "pay/add_deduction.html"  # New template for deductions
    success_url = reverse_lazy(
        "payroll:hr_dashboard"
    )  # Redirect to HR dashboard or a list of deductions
    permission_required = "payroll.add_deduction"

    def dispatch(self, request, *args, **kwargs):
        # Check if user can modify payroll data (auditors have view-only access)
        if not can_modify_payroll_data(request.user):
            return HttpResponseForbidden(
                "You don't have permission to modify payroll data."
            )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        deduction = form.instance
        print(
            "[DEDUCTION_DEBUG] Deduction form submit: "
            f"employee_id={deduction.employee_id}, type={deduction.deduction_type}, "
            f"amount={deduction.amount}, reason={deduction.reason or ''}."
        )
        messages.success(self.request, "Deduction created successfully!!")
        return super().form_valid(form)

