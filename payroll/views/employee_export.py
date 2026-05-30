"""
Export views.
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
from payroll.services.employee_data_export import build_employee_export
from payroll.services.employee_data_export import build_employee_export

def employee_data_export(request):
    employee_profile = getattr(request.user, "employee_user", None)
    if employee_profile is None:
        return HttpResponseForbidden("Your account is not linked to an employee profile.")
    export = build_employee_export(
        employee_profile,
        request.GET.get("format", "json"),
    )
    response = HttpResponse(export.body, content_type=export.content_type)
    response["Content-Disposition"] = f'attachment; filename="{export.filename}"'
    return response

