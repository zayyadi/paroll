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
from payroll.forms import PayrollForm, PayrollRunForm
from accounting.models import Account, Journal
from accounting.utils import create_journal_entry
from payroll.views.payroll_helpers import _get_payroll_close_journal_transaction_number

def add_pay(request):
    form = PayrollForm(request.POST or None, user=request.user)
    company = get_user_company(request.user)
    if form.is_valid():
        employee = form.cleaned_data["employee"]
        basic_salary = form.cleaned_data["basic_salary"]

        payroll_instance = Payroll.objects.create(
            basic_salary=basic_salary,
            company=company,
        )
        employee.employee_pay = payroll_instance
        employee.save()

        messages.success(request, "Pay created successfully")

        # Create Journal Entries
        try:
            salary_expense_account = Account.objects.get(
                company=company, name="Salary Expense"
            )
            pension_expense_account = Account.objects.get(
                company=company, name="Pension Expense"
            )
            salaries_payable_account = Account.objects.get(
                company=company, name="Salaries Payable"
            )
            pension_payable_account = Account.objects.get(
                company=company, name="Pension Payable"
            )
            tax_payable_account = Account.objects.get(
                company=company, name="PAYE Tax Payable"
            )
            nsitf_payable_account = Account.objects.get(
                company=company, name="NSITF Payable"
            )

            entries = [
                {
                    "account": salary_expense_account,
                    "entry_type": "DEBIT",
                    "amount": payroll_instance.gross_income,
                },
                {
                    "account": pension_expense_account,
                    "entry_type": "DEBIT",
                    "amount": payroll_instance.pension_employer,
                },
                {
                    "account": salaries_payable_account,
                    "entry_type": "CREDIT",
                    "amount": employee.net_pay,
                },
                {
                    "account": pension_payable_account,
                    "entry_type": "CREDIT",
                    "amount": payroll_instance.pension,
                },
                {
                    "account": tax_payable_account,
                    "entry_type": "CREDIT",
                    "amount": payroll_instance.payee,
                },
                {
                    "account": nsitf_payable_account,
                    "entry_type": "CREDIT",
                    "amount": payroll_instance.nsitf,
                },
            ]
            create_journal_entry(
                company=company,
                date=timezone.now().date(),
                description=f"Payroll for {employee.first_name} {employee.last_name}",
                entries=entries,
            )
            messages.success(request, "Journal entries created successfully.")
        except Account.DoesNotExist as e:
            messages.error(request, f"Failed to create journal entries: {e}")
        except Exception as e:
            messages.error(request, f"An unexpected error occurred: {e}")

        # Payslip email leaves the request immediately: PDF rendering and
        # SMTP delivery run in Celery so slow providers never block payroll.
        if employee and employee.user and employee.user.email:
            from core.messaging import publish
            from payroll.tasks.payslip_tasks import send_single_payslip_task

            transaction.on_commit(
                lambda: publish(
                    send_single_payslip_task,
                    payroll_instance.id,
                    employee.id,
                    queue="notifications_normal",
                )
            )
            messages.info(
                request,
                f"Payslip is being sent to {employee.user.email} in the background.",
            )
        else:
            messages.warning(request, "Employee email not found, payslip not sent.")

        return redirect("payroll:index")
    context = {"form": form}
    return render(request, "pay/add_pay.html", context)


@permission_required("payroll.delete_payroll", raise_exception=True)

def delete_pay(
    request, id
):  # This function was missing from the plan but existed in file, applying perm
    company = get_user_company(request.user)
    pay = get_object_or_404(Payroll, id=id, company=company)
    pay.delete()
    messages.success(request, "Pay deleted Successfully!!")
    return redirect(
        "payroll:index"
    )  # Assuming redirect to index or a relevant list view


@permission_required(
    "payroll.view_payroll", raise_exception=True
)  # Or a more specific dashboard permission

class AddPay(
    PermissionRequiredMixin, CreateView
):  # Removed LoginRequiredMixin, UserPassesTestMixin
    model = PayrollRun
    form_class = PayrollRunForm
    template_name = "pay/add_payday.html"
    success_url = reverse_lazy("payroll:pay_period_list")
    permission_required = "payroll.add_payrollrun"

    # Removed get and post methods if standard CreateView behavior is sufficient with form_class
    # If custom logic within get/post is needed beyond form_valid, it can be kept.
    # For now, assuming standard CreateView. If issues arise, these can be re-evaluated.
    def form_valid(self, form):
        # Delegate persistence to form.save() so closure-posting sequencing and
        # M2M handling remain consistent.
        self.object = form.save()

        messages.success(
            self.request, "PayrollRunEntry (PayrollRun) created successfully!!"
        )
        if self.object.closed:
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
        return redirect(self.success_url)

