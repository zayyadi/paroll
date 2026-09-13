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

def log_audit_trail(user, action, content_object, changes=None):
    if changes is None:
        changes = {}
    company = get_user_company(user)
    AuditTrail.objects.create(
        user=user, action=action, content_object=content_object, changes=changes,
        company=company,
    )


@permission_required("payroll.view_audittrail", raise_exception=True)
def audit_trail_list(request):
    # ... (rest of the view logic remains the same)
    query = request.GET.get("q")
    user_filter = request.GET.get("user")
    action_filter = request.GET.get("action")
    company = get_user_company(request.user)
    if company is None:
        logs = AuditTrail.objects.none()
    else:
        logs = AuditTrail.objects.filter(company=company).order_by("-timestamp")
    if query:
        logs = logs.filter(
            Q(user__email__icontains=query)
            | Q(action__icontains=query)
            | Q(content_type__model__icontains=query)
            | Q(content_object__icontains=query)
        )
    if user_filter:
        logs = logs.filter(user__email__icontains=user_filter)
    if action_filter:
        logs = logs.filter(action__icontains=action_filter)
    action_choices = (
        logs.exclude(action__isnull=True)
        .exclude(action__exact="")
        .values_list("action", flat=True)
        .distinct()
        .order_by("action")
    )
    total_logs = logs.count()
    changed_logs_count = logs.exclude(changes={}).exclude(changes__isnull=True).count()
    users_count = logs.values("user").distinct().count()

    params = request.GET.copy()
    if "page" in params:
        params.pop("page")
    filters_querystring = params.urlencode()

    paginator = Paginator(logs, 10)
    page_number = request.GET.get("page")
    audit_logs = paginator.get_page(page_number)
    context = {
        "audit_logs": audit_logs,
        "query": query,
        "user_filter": user_filter,
        "action_filter": action_filter,
        "action_choices": action_choices,
        "total_logs": total_logs,
        "changed_logs_count": changed_logs_count,
        "users_count": users_count,
        "filters_querystring": filters_querystring,
    }
    return render(request, "pay/audit_trail_list.html", context)


@permission_required("payroll.view_audittrail", raise_exception=True)
def audit_trail_detail(request, id=None, pk=None):
    log_id = pk if pk is not None else id
    company = get_user_company(request.user)
    if company is None:
        raise Http404("No active company is configured for this account.")
    log = get_object_or_404(AuditTrail, pk=log_id, company=company)
    return render(request, "pay/audit_trail_detail.html", {"log": log})
