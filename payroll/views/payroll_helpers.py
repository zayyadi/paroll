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

from accounting.models import Journal
from company.utils import get_user_company
from payroll import utils
from payroll import models
from payroll.models import EmployeeProfile, PayrollRun, PayrollRunEntry, Payroll, IOU, AuditTrail

CACHE_TTL = getattr(settings, "CACHE_TTL", DEFAULT_TIMEOUT)
logger = logging.getLogger(__name__)


def payroll_runs_distinct_by_period(company):
    """PayrollRun rows deduplicated by pay period, SQLite-portable.

    ``DISTINCT ON (paydays)`` is Postgres-only and raises under the SQLite
    test settings; dedupe in Python instead, keeping the first run per period
    in ``paydays`` order. Used by the report period-list pages.
    """
    runs = []
    seen = set()
    for run in PayrollRun.objects.filter(company=company).order_by("paydays"):
        if run.paydays in seen:
            continue
        seen.add(run.paydays)
        runs.append(run)
    return runs


def _can_manage_employee_requests(user):
    """Request management authority is scoped to the selected company."""
    from approvals.permissions import user_in_company, has_company_permission
    company = get_user_company(user)
    if not user_in_company(user, company):
        return False
    if (has_company_permission(user, company, "payroll.change_leaverequest")
            or has_company_permission(user, company, "payroll.change_iou")):
        return True
    return user.company_id == company.pk and (
        user.is_superuser
        or user.groups.filter(name="HR").exists()
        or getattr(user, "is_manager", False)
    )



def _get_payroll_close_journal_transaction_number(payroll_run):
    if not payroll_run or not getattr(payroll_run, "pk", None):
        return None
    payroll_ct = ContentType.objects.get_for_model(PayrollRun)
    journal = (
        Journal.objects.filter(
            company=payroll_run.company,
            content_type=payroll_ct,
            object_id=payroll_run.pk,
            description__startswith="Payroll for period:",
        )
        .order_by("-created_at")
        .first()
    )
    return journal.transaction_number if journal else None
