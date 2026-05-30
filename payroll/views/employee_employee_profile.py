"""
Employee Profile views.
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
from payroll.forms import EmployeeProfileUpdateForm

def update_employee_profile(request):
    try:
        employee_profile = request.user.employee_user
    except models.EmployeeProfile.DoesNotExist:
        raise Http404("Employee profile not found.")

    if request.method == "POST":
        form = EmployeeProfileUpdateForm(
            request.POST, request.FILES, instance=employee_profile
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("payroll:employee_profile")
    else:
        form = EmployeeProfileUpdateForm(instance=employee_profile)

    return render(request, "employee/update_profile.html", {"form": form})

