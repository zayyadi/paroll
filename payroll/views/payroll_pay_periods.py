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
from payroll.forms import PayrollRunForm
from payroll.views.payroll_helpers import (
    _get_payroll_close_journal_transaction_number,
    payroll_runs_distinct_by_period,
)

def varview(request):  # Lists PayrollRun objects (Pay Periods)
    company = get_user_company(request.user)
    var = payroll_runs_distinct_by_period(company)
    dates = [
        utils.convert_month_to_word(str(varss.paydays)) for varss in var
    ]  # Access .paydays attribute
    context = {"pay_var": var, "dates": dates}
    return render(request, "pay/var_view.html", context)


# New Views for PayrollRun (Pay Periods)


@permission_required("payroll.view_payrollrun", raise_exception=True)

def pay_period_list(request):
    company = get_user_company(request.user)
    pay_periods = PayrollRun.objects.filter(company=company).order_by("-paydays")
    paginator = Paginator(pay_periods, 15)  # Show 15 pay periods per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "pay/pay_period_list.html", {"page_obj": page_obj})


@permission_required("payroll.view_payrollrun", raise_exception=True)

def pay_period_detail(request, slug):
    company = get_user_company(request.user)
    pay_period = get_object_or_404(PayrollRun, slug=slug, company=company)
    # Fetch related PayrollRunEntry entries if needed for detail view
    payday_entries = PayrollRunEntry.objects.filter(
        payroll_run=pay_period,
        payroll_entry__company=company,
    )
    context = {
        "pay_period": pay_period,
        "payday_entries": payday_entries,
    }
    return render(request, "pay/pay_period_detail.html", context)



class PayPeriodUpdateView(
    LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView
):
    model = PayrollRun
    form_class = PayrollRunForm
    template_name = "pay/pay_period_form.html"  # Generic form template
    success_url = reverse_lazy("payroll:pay_period_list")
    permission_required = "payroll.change_payrollrun"
    success_message = "Pay Period updated successfully."

    def get_queryset(self):
        return PayrollRun.objects.filter(company=get_user_company(self.request.user))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        was_closed = self.get_object().closed
        response = super().form_valid(form)
        now_closed = self.object.closed
        if not was_closed and now_closed:
            txn = _get_payroll_close_journal_transaction_number(self.object)
            if txn:
                messages.success(
                    self.request,
                    f"Payroll period closed and posted to ledger (Journal: {txn}).",
                )
            else:
                messages.warning(
                    self.request,
                    "Payroll period marked closed, but no journal was found. Check Unposted Events report.",
                )
        return response



class PayPeriodDeleteView(
    LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, DeleteView
):
    model = PayrollRun
    template_name = "pay/pay_period_confirm_delete.html"
    success_url = reverse_lazy("payroll:pay_period_list")
    permission_required = "payroll.delete_payrollrun"
    success_message = "Pay Period deleted successfully."

    def get_queryset(self):
        return PayrollRun.objects.filter(company=get_user_company(self.request.user))

