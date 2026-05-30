"""
Benefits views.
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

def my_benefits(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    plans = list(
        models.BenefitPlan.objects.filter(company=company, is_active=True).order_by("name")
    )
    enrollments = {
        enrollment.plan_id: enrollment
        for enrollment in models.BenefitEnrollment.objects.filter(
            company=company,
            employee=employee_profile,
        ).select_related("plan")
    }
    for plan in plans:
        plan.employee_enrollment = enrollments.get(plan.id)

    return render(
        request,
        "employee/my_benefits.html",
        {
            "page_title": "My Benefits",
            "plans": plans,
        },
    )


@login_required

def enroll_benefit(request, plan_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    plan = get_object_or_404(models.BenefitPlan, id=plan_id, company=company, is_active=True)
    models.BenefitEnrollment.objects.update_or_create(
        company=company,
        plan=plan,
        employee=employee_profile,
        defaults={
            "status": models.BenefitEnrollment.Status.ENROLLED,
            "effective_date": timezone.localdate(),
        },
    )
    messages.success(request, "Benefit enrollment updated.")
    return redirect("payroll:my_benefits")


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def benefit_overview(request):
    company = get_user_company(request.user)
    plans = (
        models.BenefitPlan.objects.filter(company=company)
        .prefetch_related("enrollments")
        .order_by("name")
    )

    return render(
        request,
        "employee/benefit_overview.html",
        {
            "page_title": "Benefits Center",
            "plans": plans,
            "plan_count": plans.count(),
            "active_count": plans.filter(is_active=True).count(),
            "enrollment_count": models.BenefitEnrollment.objects.filter(company=company).count(),
        },
    )

