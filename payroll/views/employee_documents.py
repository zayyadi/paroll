"""
Documents views.
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


@login_required
def my_documents(request):
    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    documents = models.EmployeeDocument.objects.filter(
        company=company,
        employee=employee_profile,
    ).order_by("-created_at", "title")

    return render(
        request,
        "employee/my_documents.html",
        {
            "page_title": "My Documents",
            "documents": documents,
            "pending_count": documents.filter(
                acknowledgement_required=True,
                is_acknowledged=False,
            ).count(),
        },
    )


@login_required

def acknowledge_document(request, document_id):
    if request.method != "POST":
        raise Http404()

    company = get_user_company(request.user)
    employee_profile = get_object_or_404(
        models.EmployeeProfile.objects.select_related("user"),
        user=request.user,
        company=company,
    )
    document = get_object_or_404(
        models.EmployeeDocument,
        id=document_id,
        company=company,
        employee=employee_profile,
    )

    if document.acknowledgement_required and not document.is_acknowledged:
        document.is_acknowledged = True
        document.acknowledged_at = timezone.now()
        document.save(update_fields=["is_acknowledged", "acknowledged_at", "updated_at"])
        messages.success(request, "Document acknowledged successfully.")
    else:
        messages.info(request, "This document is already acknowledged.")

    return redirect("payroll:my_documents")


@login_required
@permission_required("payroll.view_employeeprofile", raise_exception=True)

def document_overview(request):
    company = get_user_company(request.user)
    documents = (
        models.EmployeeDocument.objects.filter(company=company)
        .select_related("employee", "employee__user")
        .order_by("-created_at", "title")
    )

    return render(
        request,
        "employee/document_overview.html",
        {
            "page_title": "Document Operations",
            "documents": documents[:20],
            "document_count": documents.count(),
            "pending_count": documents.filter(
                acknowledgement_required=True,
                is_acknowledged=False,
            ).count(),
            "acknowledged_count": documents.filter(is_acknowledged=True).count(),
        },
    )
