"""
Assets views.
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

def my_assets(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    assets = (
        models.EmployeeAsset.objects.filter(company=company, employee=employee_profile)
        .select_related("category")
        .order_by("asset_tag")
    )

    return render(
        request,
        "employee/my_assets.html",
        {
            "page_title": "My Assets",
            "assets": assets,
            "in_use_count": assets.filter(status=models.EmployeeAsset.Status.IN_USE).count(),
        },
    )


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def asset_overview(request):
    company = get_user_company(request.user)
    assets = (
        models.EmployeeAsset.objects.filter(company=company)
        .select_related("employee", "category")
        .order_by("asset_tag")
    )

    return render(
        request,
        "employee/asset_overview.html",
        {
            "page_title": "Asset Operations",
            "assets": assets[:25],
            "asset_count": assets.count(),
            "in_use_count": assets.filter(status=models.EmployeeAsset.Status.IN_USE).count(),
            "available_count": assets.filter(
                status=models.EmployeeAsset.Status.AVAILABLE
            ).count(),
            "returned_count": assets.filter(
                status=models.EmployeeAsset.Status.RETURNED
            ).count(),
        },
    )


@login_required
@permission_required("payroll.change_employeeprofile", raise_exception=True)

def return_asset(request, asset_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    asset = get_object_or_404(models.EmployeeAsset, id=asset_id, company=company)
    asset.status = models.EmployeeAsset.Status.RETURNED
    asset.returned_at = timezone.now()
    asset.employee = None
    asset.save(update_fields=["status", "returned_at", "employee", "updated_at"])
    messages.success(request, "Asset marked as returned.")
    return redirect("payroll:asset_overview")

