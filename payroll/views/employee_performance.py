"""
Performance views.
"""

from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Q, Count, Sum, Avg
from django.views.generic.edit import FormView
from django.forms import inlineformset_factory
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import permission_required
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView, ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.http import Http404, HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
import json

from company.utils import get_user_company
from payroll import models

def my_performance(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    goals = models.Goal.objects.filter(company=company, employee=employee_profile).order_by(
        "-created_at"
    )
    one_on_ones = models.OneOnOne.objects.filter(
        company=company,
        employee=employee_profile,
    ).order_by("-scheduled_for")

    return render(
        request,
        "employee/my_performance.html",
        {
            "page_title": "My Performance",
            "goals": goals,
            "one_on_ones": one_on_ones,
            "active_goal_count": goals.filter(status=models.Goal.Status.ACTIVE).count(),
            "scheduled_count": one_on_ones.filter(
                status=models.OneOnOne.Status.SCHEDULED
            ).count(),
        },
    )


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def performance_overview(request):
    company = get_user_company(request.user)
    goals = (
        models.Goal.objects.filter(company=company)
        .select_related("employee", "manager")
        .order_by("-created_at")
    )
    one_on_ones = (
        models.OneOnOne.objects.filter(company=company)
        .select_related("employee", "manager")
        .order_by("-scheduled_for")
    )

    return render(
        request,
        "employee/performance_overview.html",
        {
            "page_title": "Performance Hub",
            "goals": goals[:20],
            "one_on_ones": one_on_ones[:12],
            "goal_count": goals.count(),
            "active_goal_count": goals.filter(status=models.Goal.Status.ACTIVE).count(),
            "scheduled_count": one_on_ones.filter(
                status=models.OneOnOne.Status.SCHEDULED
            ).count(),
            "completed_count": one_on_ones.filter(
                status=models.OneOnOne.Status.COMPLETED
            ).count(),
        },
    )


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)

def complete_one_on_one(request, meeting_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    meeting = get_object_or_404(models.OneOnOne, id=meeting_id, company=company)
    if meeting.status != models.OneOnOne.Status.COMPLETED:
        meeting.status = models.OneOnOne.Status.COMPLETED
        meeting.completed_at = timezone.now()
        meeting.save(update_fields=["status", "completed_at", "updated_at"])
        messages.success(request, "1:1 marked as completed.")
    else:
        messages.info(request, "This 1:1 is already completed.")
    return redirect("payroll:performance_overview")

