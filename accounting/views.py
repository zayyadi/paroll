from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.views.generic.edit import FormView
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.urls import reverse_lazy
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from weasyprint import HTML, CSS

from .models import (
    Account,
    Journal,
    JournalEntry,
    FiscalYear,
    AccountingPeriod,
    AccountingAuditTrail,
    TransactionNumber,
)
from .forms import (
    JournalForm,
    JournalEntryForm,
    AccountForm,
    FiscalYearForm,
    AccountingPeriodForm,
    JournalApprovalForm,
    JournalReversalForm,
    JournalEntryFormSet,
    JournalReversalInitiationForm,
    JournalPartialReversalForm,
    JournalCorrectionForm,
    CorrectionEntryForm,
    CorrectionEntryFormSet,
    BatchJournalReversalForm,
    JournalReversalConfirmationForm,
)
from .utils import (
    get_trial_balance,
    get_account_balance_as_of,
    post_journal,
    reverse_journal,
    reverse_journal_partial,
    reverse_journal_with_correction,
    batch_reverse_journals,
    close_accounting_period,
    close_fiscal_year,
)
from .permissions import (
    is_auditor,
    is_accountant,
    is_payroll_processor,
    can_approve_journal,
    can_reverse_journal,
    can_close_period,
)
from .decorators import (
    auditor_required,
    accountant_required,
    payroll_processor_required,
    accounting_role_required,
    auditor_or_accountant_required,
)
from .mixins import (
    AuditorRequiredMixin,
    AccountantRequiredMixin,
    PayrollProcessorRequiredMixin,
    AccountingRoleRequiredMixin,
    AuditorOrAccountantRequiredMixin,
    JournalApprovalMixin,
    JournalReversalMixin,
    PeriodClosingMixin,
    SelfModificationMixin,
)

User = get_user_model()


# Dashboard Views
@login_required
@accounting_role_required
def accounting_dashboard(request):
    """
    Main dashboard for accounting users
    """
    # Get counts for dashboard
    draft_journals_count = Journal.objects.filter(
        status=Journal.JournalStatus.DRAFT
    ).count()
    pending_journals_count = Journal.objects.filter(
        status=Journal.JournalStatus.PENDING_APPROVAL
    ).count()
    posted_journals_count = Journal.objects.filter(
        status=Journal.JournalStatus.POSTED
    ).count()

    # Get recent journals
    recent_journals = Journal.objects.all().order_by("-created_at")[:10]

    # Get active periods
    active_periods = AccountingPeriod.objects.filter(is_active=True).order_by(
        "-start_date"
    )[:5]

    context = {
        "draft_journals_count": draft_journals_count,
        "pending_journals_count": pending_journals_count,
        "posted_journals_count": posted_journals_count,
        "recent_journals": recent_journals,
        "active_periods": active_periods,
        "is_auditor": is_auditor(request.user),
        "is_accountant": is_accountant(request.user),
        "is_payroll_processor": is_payroll_processor(request.user),
    }

    return render(request, "accounting/dashboard.html", context)


# Account Views
class AccountListView(LoginRequiredMixin, AccountingRoleRequiredMixin, ListView):
    """
    List all accounts
    """

    model = Account
    template_name = "accounting/account_list.html"
    context_object_name = "accounts"
    paginate_by = 20

    def get_queryset(self):
        queryset = Account.objects.all().order_by("account_number")
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(account_number__icontains=search)
            )
        return queryset


class AccountDetailView(LoginRequiredMixin, AccountingRoleRequiredMixin, DetailView):
    """
    View account details with balance
    """

    model = Account
    template_name = "accounting/account_detail.html"
    context_object_name = "account"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.get_object()

        # Get current balance
        context["current_balance"] = account.get_balance()

        # Get recent entries
        context["recent_entries"] = account.entries.all().order_by(
            "-journal__created_at"
        )[:20]

        # Get balance as of specific date if provided
        as_of_date = self.request.GET.get("as_of_date")
        if as_of_date:
            try:
                from datetime import datetime

                date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
                context["as_of_balance"] = get_account_balance_as_of(account, date_obj)
                context["as_of_date"] = as_of_date
            except ValueError:
                pass

        return context


class AccountCreateView(LoginRequiredMixin, AccountantRequiredMixin, CreateView):
    """
    Create a new account (accountants only)
    """

    model = Account
    form_class = AccountForm
    template_name = "accounting/account_form.html"
    success_url = reverse_lazy("accounting:account_list")

    def form_valid(self, form):
        messages.success(self.request, "Account created successfully.")
        return super().form_valid(form)


# Journal Views
class JournalListView(LoginRequiredMixin, AccountingRoleRequiredMixin, ListView):
    """
    List all journals with filtering
    """

    model = Journal
    template_name = "accounting/journal_list.html"
    context_object_name = "journals"
    paginate_by = 20

    def get_queryset(self):
        queryset = Journal.objects.all().order_by("-created_at")

        # Filter by status
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # Filter by date range
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        # Search
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search)
                | Q(transaction_number__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = Journal.JournalStatus.choices
        return context


class JournalDetailView(LoginRequiredMixin, AccountingRoleRequiredMixin, DetailView):
    """
    View journal details with entries
    """

    model = Journal
    template_name = "accounting/journal_detail.html"
    context_object_name = "journal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.get_object()

        # Get entries
        context["entries"] = journal.entries.all().order_by("account__name")

        # Calculate totals
        total_debits = (
            journal.entries.filter(entry_type="DEBIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )
        total_credits = (
            journal.entries.filter(entry_type="CREDIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )
        context["total_debits"] = total_debits
        context["total_credits"] = total_credits
        context["is_balanced"] = total_debits == total_credits

        # Permission checks
        context["can_approve"] = can_approve_journal(self.request.user, journal)
        context["can_reverse"] = can_reverse_journal(self.request.user, journal)
        context["can_edit"] = (
            is_accountant(self.request.user)
            and journal.status
            in [Journal.JournalStatus.DRAFT, Journal.JournalStatus.PENDING_APPROVAL]
            and journal.created_by == self.request.user
        )

        # Reversal status and history
        context["is_reversed"] = journal.reversed_journal is not None
        context["is_reversal"] = (
            hasattr(journal, "reversal_of") and journal.reversal_of is not None
        )
        context["reversal_journal"] = journal.reversed_journal
        context["reversal_of"] = getattr(journal, "reversal_of", None)
        context["reversal_reason"] = journal.reversal_reason

        # Get audit trail entries for this journal
        audit_entries = AccountingAuditTrail.objects.filter(
            content_type=ContentType.objects.get_for_model(Journal),
            object_id=journal.pk,
        ).order_by("-timestamp")[
            :10
        ]  # Get last 10 entries

        context["audit_entries"] = audit_entries

        return context


class JournalCreateView(LoginRequiredMixin, AccountantRequiredMixin, CreateView):
    """
    Create a new journal (accountants only)
    """

    model = Journal
    form_class = JournalForm
    template_name = "accounting/journal_form.html"
    success_url = reverse_lazy("accounting:journal_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["entry_formset"] = JournalEntryFormSet(self.request.POST)
        else:
            context["entry_formset"] = JournalEntryFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        entry_formset = context["entry_formset"]

        with transaction.atomic():
            form.instance.created_by = self.request.user
            form.instance.status = Journal.JournalStatus.DRAFT
            self.object = form.save()

            if entry_formset.is_valid():
                entry_formset.instance = self.object
                entry_formset.save()

                messages.success(self.request, "Journal created successfully.")
                return redirect(self.get_success_url())
            else:
                return self.form_invalid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


class JournalApprovalView(LoginRequiredMixin, JournalApprovalMixin, FormView):
    """
    Approve or reject a journal (auditors only)
    """

    template_name = "accounting/journal_approval.html"
    form_class = JournalApprovalForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        context["journal"] = journal
        context["entries"] = journal.entries.all().order_by("account__name")
        return context

    def form_valid(self, form):
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        action = form.cleaned_data["action"]
        reason = form.cleaned_data["reason"]

        if action == "approve":
            journal.approve(self.request.user)
            post_journal(journal, self.request.user)
            messages.success(self.request, "Journal approved and posted successfully.")
        else:  # reject
            journal.status = Journal.JournalStatus.CANCELLED
            journal.save()
            messages.success(self.request, "Journal rejected.")

        # Log the action
        AccountingAuditTrail.log_action(
            user=self.request.user,
            action=(
                AccountingAuditTrail.ActionType.APPROVE
                if action == "approve"
                else AccountingAuditTrail.ActionType.REJECT
            ),
            instance=journal,
            reason=reason,
            ip_address=self.request.META.get("REMOTE_ADDR"),
            user_agent=self.request.META.get("HTTP_USER_AGENT"),
        )

        return redirect("accounting:journal_detail", pk=journal.pk)


class JournalReversalView(LoginRequiredMixin, JournalReversalMixin, FormView):
    """
    Reverse a posted journal (auditors only)
    """

    template_name = "accounting/journal_reversal.html"
    form_class = JournalReversalForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        context["journal"] = journal
        context["entries"] = journal.entries.all().order_by("account__name")
        return context

    def form_valid(self, form):
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        reason = form.cleaned_data["reason"]

        try:
            reversal_journal = reverse_journal(
                journal,
                self.request.user,
                reason,
                ip_address=self.request.META.get("REMOTE_ADDR"),
                user_agent=self.request.META.get("HTTP_USER_AGENT"),
            )
            messages.success(self.request, "Journal reversed successfully.")
            return redirect("accounting:journal_detail", pk=reversal_journal.pk)
        except Exception as e:
            messages.error(self.request, f"Error reversing journal: {str(e)}")
            return self.form_invalid(form)


# Fiscal Year Views
class FiscalYearListView(
    LoginRequiredMixin, AuditorOrAccountantRequiredMixin, ListView
):
    """
    List all fiscal years
    """

    model = FiscalYear
    template_name = "accounting/fiscal_year_list.html"
    context_object_name = "fiscal_years"
    ordering = ["-year"]


class FiscalYearDetailView(
    LoginRequiredMixin, AuditorOrAccountantRequiredMixin, DetailView
):
    """
    View fiscal year details
    """

    model = FiscalYear
    template_name = "accounting/fiscal_year_detail.html"
    context_object_name = "fiscal_year"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fiscal_year = self.get_object()

        # Get periods
        context["periods"] = fiscal_year.periods.all().order_by("period_number")

        # Get journal counts
        context["journal_count"] = Journal.objects.filter(
            period__fiscal_year=fiscal_year
        ).count()

        return context


# Accounting Period Views
class AccountingPeriodListView(
    LoginRequiredMixin, AccountingRoleRequiredMixin, ListView
):
    """
    List all accounting periods
    """

    model = AccountingPeriod
    template_name = "accounting/period_list.html"
    context_object_name = "periods"
    paginate_by = 20

    def get_queryset(self):
        return AccountingPeriod.objects.all().order_by("-fiscal_year", "-period_number")


class AccountingPeriodDetailView(
    LoginRequiredMixin, AccountingRoleRequiredMixin, DetailView
):
    """
    View accounting period details
    """

    model = AccountingPeriod
    template_name = "accounting/period_detail.html"
    context_object_name = "period"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period = self.get_object()

        # Get journals for this period
        context["journals"] = Journal.objects.filter(period=period).order_by("-date")

        # Get trial balance
        context["trial_balance"] = get_trial_balance(period=period)

        # Permission checks
        context["can_close"] = can_close_period(self.request.user, period)

        return context


class AccountingPeriodCloseView(LoginRequiredMixin, PeriodClosingMixin, FormView):
    """
    Close an accounting period (auditors only)
    """

    template_name = "accounting/period_close.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period = get_object_or_404(AccountingPeriod, pk=self.kwargs["pk"])
        context["period"] = period
        context["journal_count"] = Journal.objects.filter(period=period).count()
        return context

    def post(self, request, *args, **kwargs):
        period = get_object_or_404(AccountingPeriod, pk=self.kwargs["pk"])
        reason = request.POST.get("reason", "")

        try:
            close_accounting_period(
                period,
                request.user,
                reason=reason,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT"),
            )
            messages.success(request, f"Period {period} closed successfully.")
            return redirect("accounting:period_detail", pk=period.pk)
        except Exception as e:
            messages.error(request, f"Error closing period: {str(e)}")
            return redirect("accounting:period_close", pk=period.pk)


# Audit Trail Views
class AuditTrailListView(LoginRequiredMixin, AuditorRequiredMixin, ListView):
    """
    List all audit trail entries (auditors only)
    """

    model = AccountingAuditTrail
    template_name = "accounting/audit_trail_list.html"
    context_object_name = "audit_logs"
    paginate_by = 20

    def get_queryset(self):
        queryset = AccountingAuditTrail.objects.all().order_by("-timestamp")

        # Filter by user
        user_id = self.request.GET.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by action
        action = self.request.GET.get("action")
        if action:
            queryset = queryset.filter(action=action)

        # Filter by date range
        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action_choices"] = AccountingAuditTrail.ActionType.choices
        context["users"] = User.objects.all()
        return context


class AuditTrailDetailView(LoginRequiredMixin, AuditorRequiredMixin, DetailView):
    """
    View audit trail entry details (auditors only)
    """

    model = AccountingAuditTrail
    template_name = "accounting/audit_trail_detail.html"
    context_object_name = "audit_log"


# Reports Views
@login_required
@auditor_or_accountant_required
def trial_balance_report(request):
    """
    Generate trial balance report
    """
    period_id = request.GET.get("period")
    as_of_date = request.GET.get("as_of_date")

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id)
        trial_balance = get_trial_balance(period=period)
        context = {
            "trial_balance": trial_balance,
            "period": period,
            "report_title": f"Trial Balance - {period}",
        }
    elif as_of_date:
        try:
            from datetime import datetime

            date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            trial_balance = get_trial_balance(as_of_date=date_obj)
            context = {
                "trial_balance": trial_balance,
                "as_of_date": as_of_date,
                "report_title": f"Trial Balance as of {as_of_date}",
            }
        except ValueError:
            messages.error(request, "Invalid date format")
            return redirect("accounting:reports")
    else:
        # Default to current date
        trial_balance = get_trial_balance()
        context = {
            "trial_balance": trial_balance,
            "report_title": "Trial Balance - Current",
        }

    return render(request, "accounting/reports/trial_balance.html", context)


@login_required
@auditor_or_accountant_required
def account_activity_report(request):
    """
    Generate account activity report
    """
    account_id = request.GET.get("account")
    if not account_id:
        messages.error(request, "Please select an account")
        return redirect("accounting:reports")

    account = get_object_or_404(Account, pk=account_id)

    # Get date range
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    entries = account.entries.all()

    if start_date:
        entries = entries.filter(journal__date__gte=start_date)
    if end_date:
        entries = entries.filter(journal__date__lte=end_date)

    entries = entries.order_by("-journal__date")

    context = {
        "account": account,
        "entries": entries,
        "start_date": start_date,
        "end_date": end_date,
        "opening_balance": account.get_balance()
        - sum(e.amount if e.entry_type == "DEBIT" else -e.amount for e in entries),
    }

    return render(request, "accounting/reports/account_activity.html", context)


@login_required
@auditor_required
def reports_index(request):
    """
    Index page for accounting reports (auditors only)
    """
    # Get available periods for report generation
    periods = AccountingPeriod.objects.filter(is_closed=True).order_by(
        "-fiscal_year", "-period_number"
    )

    context = {
        "periods": periods,
        "accounts": Account.objects.all().order_by("account_number"),
    }

    return render(request, "accounting/reports/index.html", context)


# PDF Export Views
@login_required
@auditor_or_accountant_required
def trial_balance_pdf(request):
    """
    Generate PDF version of trial balance report
    """
    period_id = request.GET.get("period")
    as_of_date = request.GET.get("as_of_date")

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id)
        trial_balance = get_trial_balance(period=period)
        context = {
            "trial_balance": trial_balance,
            "period": period,
            "report_title": f"Trial Balance - {period}",
        }
    elif as_of_date:
        try:
            from datetime import datetime

            date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            trial_balance = get_trial_balance(as_of_date=date_obj)
            context = {
                "trial_balance": trial_balance,
                "as_of_date": as_of_date,
                "report_title": f"Trial Balance as of {as_of_date}",
            }
        except ValueError:
            messages.error(request, "Invalid date format")
            return redirect("accounting:trial_balance")
    else:
        trial_balance = get_trial_balance()
        context = {
            "trial_balance": trial_balance,
            "report_title": "Trial Balance - Current",
        }

    # Generate PDF
    html_string = render_to_string(
        "accounting/reports/pdf/trial_balance_pdf.html", context
    )
    html = HTML(string=html_string)
    css = CSS(
        string="""
        @page { size: A4 landscape; margin: 1cm; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; font-weight: bold; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        .font-bold { font-weight: bold; }
        .text-danger { color: #dc2626; }
        .text-success { color: #059669; }
    """
    )

    pdf = html.write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="trial_balance_{timezone.now().date()}.pdf"'
    return response


@login_required
@auditor_or_accountant_required
def account_activity_pdf(request):
    """
    Generate PDF version of account activity report
    """
    account_id = request.GET.get("account")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if not account_id:
        messages.error(request, "Please select an account")
        return redirect("accounting:account_activity")

    account = get_object_or_404(Account, pk=account_id)

    entries = account.entries.all()

    if start_date:
        entries = entries.filter(journal__date__gte=start_date)
    if end_date:
        entries = entries.filter(journal__date__lte=end_date)

    entries = entries.order_by("-journal__date")

    # Calculate opening balance
    opening_balance = account.get_balance() - sum(
        e.amount if e.entry_type == "DEBIT" else -e.amount for e in entries
    )

    context = {
        "account": account,
        "entries": entries,
        "start_date": start_date,
        "end_date": end_date,
        "opening_balance": opening_balance,
    }

    # Generate PDF
    html_string = render_to_string(
        "accounting/reports/pdf/account_activity_pdf.html", context
    )
    html = HTML(string=html_string)
    css = CSS(
        string="""
        @page { size: A4 landscape; margin: 1cm; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; font-weight: bold; }
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        .font-bold { font-weight: bold; }
        .text-danger { color: #dc2626; }
        .text-success { color: #059669; }
    """
    )

    pdf = html.write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="account_activity_{account.name}_{timezone.now().date()}.pdf"'
    return response


# Additional Report Views
@login_required
@auditor_or_accountant_required
def general_ledger_report(request):
    """
    Generate general ledger report
    """
    period_id = request.GET.get("period")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    entries = JournalEntry.objects.filter(journal__status=Journal.JournalStatus.POSTED)

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id)
        entries = entries.filter(journal__period=period)
        context = {
            "period": period,
            "report_title": f"General Ledger - {period}",
        }
    elif start_date and end_date:
        entries = entries.filter(
            journal__date__gte=start_date, journal__date__lte=end_date
        )
        context = {
            "start_date": start_date,
            "end_date": end_date,
            "report_title": f"General Ledger - {start_date} to {end_date}",
        }
    else:
        context = {
            "report_title": "General Ledger - Current",
        }

    entries = entries.order_by("journal__date", "account__name")

    # Group entries by account
    ledger_data = {}
    for entry in entries:
        if entry.account_id not in ledger_data:
            ledger_data[entry.account_id] = {"account": entry.account, "entries": []}
        ledger_data[entry.account_id]["entries"].append(entry)

    context["ledger_data"] = ledger_data
    context["entries"] = entries

    return render(request, "accounting/reports/general_ledger.html", context)


@login_required
@auditor_or_accountant_required
def balance_sheet_report(request):
    """
    Generate balance sheet report
    """
    period_id = request.GET.get("period")
    as_of_date = request.GET.get("as_of_date")

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id)
        trial_balance = get_trial_balance(period=period)
        context = {
            "period": period,
            "report_title": f"Balance Sheet - {period}",
        }
    elif as_of_date:
        try:
            from datetime import datetime

            date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            trial_balance = get_trial_balance(as_of_date=date_obj)
            context = {
                "as_of_date": as_of_date,
                "report_title": f"Balance Sheet as of {as_of_date}",
            }
        except ValueError:
            messages.error(request, "Invalid date format")
            return redirect("accounting:balance_sheet")
    else:
        trial_balance = get_trial_balance()
        context = {
            "report_title": "Balance Sheet - Current",
        }

    # Organize accounts by type
    assets = []
    liabilities = []
    equity = []

    for account_id, account_data in trial_balance.items():
        account = account_data["account"]
        balance = account_data["balance"]

        if account.type == Account.AccountType.ASSET:
            assets.append(account_data)
        elif account.type == Account.AccountType.LIABILITY:
            liabilities.append(account_data)
        elif account.type == Account.AccountType.EQUITY:
            equity.append(account_data)

    context["assets"] = assets
    context["liabilities"] = liabilities
    context["equity"] = equity
    context["total_assets"] = sum(item["balance"] for item in assets)
    context["total_liabilities"] = sum(item["balance"] for item in liabilities)
    context["total_equity"] = sum(item["balance"] for item in equity)

    return render(request, "accounting/reports/balance_sheet.html", context)


@login_required
@auditor_or_accountant_required
def income_statement_report(request):
    """
    Generate income statement report
    """
    period_id = request.GET.get("period")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id)
        trial_balance = get_trial_balance(period=period)
        context = {
            "period": period,
            "report_title": f"Income Statement - {period}",
        }
    elif start_date and end_date:
        trial_balance = get_trial_balance(as_of_date=end_date)
        context = {
            "start_date": start_date,
            "end_date": end_date,
            "report_title": f"Income Statement - {start_date} to {end_date}",
        }
    else:
        trial_balance = get_trial_balance()
        context = {
            "report_title": "Income Statement - Current",
        }

    # Organize revenue and expense accounts
    revenue = []
    expenses = []

    for account_id, account_data in trial_balance.items():
        account = account_data["account"]
        balance = account_data["balance"]

        if account.type == Account.AccountType.REVENUE:
            revenue.append(account_data)
        elif account.type == Account.AccountType.EXPENSE:
            expenses.append(account_data)

    context["revenue"] = revenue
    context["expenses"] = expenses
    context["total_revenue"] = sum(item["balance"] for item in revenue)
    context["total_expenses"] = sum(item["balance"] for item in expenses)
    context["net_income"] = context["total_revenue"] - context["total_expenses"]

    return render(request, "accounting/reports/income_statement.html", context)


# Transaction Reversal Views
class JournalReversalInitiationView(LoginRequiredMixin, JournalReversalMixin, FormView):
    """
    View to initiate a journal reversal
    """

    template_name = "accounting/journal_reversal_initiation.html"
    form_class = JournalReversalInitiationForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        context["journal"] = journal
        context["entries"] = journal.entries.all().order_by("account__name")
        return context

    def form_valid(self, form):
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        reversal_type = form.cleaned_data["reversal_type"]
        reason = form.cleaned_data["reason"]

        # Store form data in session for next step
        self.request.session["reversal_data"] = {
            "journal_id": journal.pk,
            "reversal_type": reversal_type,
            "reason": reason,
        }

        # Redirect to appropriate reversal form
        if reversal_type == "full":
            return redirect("accounting:journal_reversal_confirm", pk=journal.pk)
        elif reversal_type == "partial":
            return redirect("accounting:journal_partial_reversal", pk=journal.pk)
        elif reversal_type == "correction":
            return redirect(
                "accounting:journal_reversal_with_correction", pk=journal.pk
            )

        return redirect("accounting:journal_detail", pk=journal.pk)


class JournalPartialReversalView(LoginRequiredMixin, JournalReversalMixin, FormView):
    """
    View to handle partial journal reversals
    """

    template_name = "accounting/journal_partial_reversal.html"

    def get_form_class(self):
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        return lambda *args, **kwargs: JournalPartialReversalForm(
            journal.entries.all(), *args, **kwargs
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        context["journal"] = journal
        context["entries"] = journal.entries.all().order_by("account__name")

        # Get reversal data from session
        reversal_data = self.request.session.get("reversal_data", {})
        context["reason"] = reversal_data.get("reason", "")

        return context

    def form_valid(self, form):
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        reversal_data = self.request.session.get("reversal_data", {})
        reason = reversal_data.get("reason", "")

        # Prepare entry data for partial reversal
        entry_ids = []
        amounts = {}

        for entry in journal.entries.all():
            field_name = f"entry_{entry.id}"
            if form.cleaned_data.get(field_name):
                entry_ids.append(entry.id)

                amount_field_name = f"amount_{entry.id}"
                amount = form.cleaned_data.get(amount_field_name)
                if amount:
                    amounts[entry.id] = amount

        try:
            reversal_journal = reverse_journal_partial(
                journal,
                self.request.user,
                reason,
                entry_ids=entry_ids,
                amounts=amounts,
                ip_address=self.request.META.get("REMOTE_ADDR"),
                user_agent=self.request.META.get("HTTP_USER_AGENT"),
            )

            # Clear session data
            if "reversal_data" in self.request.session:
                del self.request.session["reversal_data"]

            messages.success(self.request, "Journal partially reversed successfully.")
            return redirect("accounting:journal_detail", pk=reversal_journal.pk)
        except Exception as e:
            messages.error(self.request, f"Error reversing journal: {str(e)}")
            return self.form_invalid(form)


class JournalReversalWithCorrectionView(
    LoginRequiredMixin, JournalReversalMixin, FormView
):
    """
    View to handle reversals with corrections
    """

    template_name = "accounting/journal_reversal_with_correction.html"
    form_class = JournalCorrectionForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        context["journal"] = journal
        context["entries"] = journal.entries.all().order_by("account__name")

        # Get reversal data from session
        reversal_data = self.request.session.get("reversal_data", {})
        context["reason"] = reversal_data.get("reason", "")

        # Add correction entry formset
        if self.request.POST:
            context["correction_formset"] = CorrectionEntryFormSet(self.request.POST)
        else:
            context["correction_formset"] = CorrectionEntryFormSet()

        return context

    def form_valid(self, form):
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        reversal_data = self.request.session.get("reversal_data", {})
        reason = reversal_data.get("reason", "")

        context = self.get_context_data()
        correction_formset = context["correction_formset"]

        if correction_formset.is_valid():
            # Prepare correction entries
            correction_entries = []
            for correction_form in correction_formset:
                if (
                    correction_form.cleaned_data
                    and not correction_form.cleaned_data.get("DELETE")
                ):
                    correction_entries.append(
                        {
                            "account": correction_form.cleaned_data["account"],
                            "entry_type": correction_form.cleaned_data["entry_type"],
                            "amount": correction_form.cleaned_data["amount"],
                            "memo": correction_form.cleaned_data.get("memo", ""),
                        }
                    )

            try:
                reversal_journal, correction_journal = reverse_journal_with_correction(
                    journal,
                    self.request.user,
                    reason,
                    correction_entries,
                    ip_address=self.request.META.get("REMOTE_ADDR"),
                    user_agent=self.request.META.get("HTTP_USER_AGENT"),
                )

                # Clear session data
                if "reversal_data" in self.request.session:
                    del self.request.session["reversal_data"]

                messages.success(
                    self.request, "Journal reversed with correction successfully."
                )
                return redirect("accounting:journal_detail", pk=correction_journal.pk)
            except Exception as e:
                messages.error(
                    self.request, f"Error reversing journal with correction: {str(e)}"
                )
                return self.form_invalid(form)
        else:
            return self.form_invalid(form)


class JournalReversalConfirmationView(
    LoginRequiredMixin, JournalReversalMixin, FormView
):
    """
    View to confirm and execute journal reversal
    """

    template_name = "accounting/journal_reversal_confirmation.html"
    form_class = JournalReversalConfirmationForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        context["journal"] = journal
        context["entries"] = journal.entries.all().order_by("account__name")

        # Get reversal data from session
        reversal_data = self.request.session.get("reversal_data", {})
        context["reason"] = reversal_data.get("reason", "")

        return context

    def form_valid(self, form):
        journal = get_object_or_404(Journal, pk=self.kwargs["pk"])
        reversal_data = self.request.session.get("reversal_data", {})
        original_reason = reversal_data.get("reason", "")
        final_reason = form.cleaned_data["final_reason"]

        try:
            reversal_journal = reverse_journal(
                journal,
                self.request.user,
                final_reason,
                ip_address=self.request.META.get("REMOTE_ADDR"),
                user_agent=self.request.META.get("HTTP_USER_AGENT"),
            )

            # Clear session data
            if "reversal_data" in self.request.session:
                del self.request.session["reversal_data"]

            messages.success(self.request, "Journal reversed successfully.")
            return redirect("accounting:journal_detail", pk=reversal_journal.pk)
        except Exception as e:
            messages.error(self.request, f"Error reversing journal: {str(e)}")
            return self.form_invalid(form)


class BatchJournalReversalView(LoginRequiredMixin, JournalReversalMixin, FormView):
    """
    View to handle batch journal reversals
    """

    template_name = "accounting/batch_journal_reversal.html"
    form_class = BatchJournalReversalForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add additional context for batch reversal
        context["total_journals"] = Journal.objects.filter(
            status=Journal.JournalStatus.POSTED, reversed_journal__isnull=True
        ).count()
        return context

    def form_valid(self, form):
        journals = form.cleaned_data["journals"]
        reason = form.cleaned_data["reason"]

        try:
            reversal_journals = batch_reverse_journals(
                journals,
                self.request.user,
                reason,
                ip_address=self.request.META.get("REMOTE_ADDR"),
                user_agent=self.request.META.get("HTTP_USER_AGENT"),
            )

            messages.success(
                self.request,
                f"Successfully reversed {len(reversal_journals)} journals.",
            )
            return redirect("accounting:journal_list")
        except Exception as e:
            messages.error(self.request, f"Error in batch reversal: {str(e)}")
            return self.form_invalid(form)


class JournalReversalHistoryView(
    LoginRequiredMixin, AccountingRoleRequiredMixin, DetailView
):
    """
    View to show reversal history for a journal
    """

    model = Journal
    template_name = "accounting/journal_reversal_history.html"
    context_object_name = "journal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.get_object()

        # Get reversal history
        reversal_history = []

        # Check if this journal has been reversed
        if journal.reversed_journal:
            reversal_history.append(
                {
                    "type": "reversed_by",
                    "journal": journal.reversed_journal,
                    "reason": journal.reversed_journal.reversal_reason,
                    "timestamp": journal.reversed_journal.created_at,
                    "user": journal.reversed_journal.created_by,
                }
            )

        # Check if this journal is a reversal of another journal
        if hasattr(journal, "reversal_of") and journal.reversal_of:
            reversal_history.append(
                {
                    "type": "reversal_of",
                    "journal": journal.reversal_of,
                    "reason": journal.reversal_reason,
                    "timestamp": journal.created_at,
                    "user": journal.created_by,
                }
            )

        # Get audit trail entries for this journal
        audit_entries = AccountingAuditTrail.objects.filter(
            content_type=ContentType.objects.get_for_model(Journal),
            object_id=journal.pk,
            action__in=[
                AccountingAuditTrail.ActionType.REVERSE,
                AccountingAuditTrail.ActionType.UPDATE,
            ],
        ).order_by("-timestamp")

        context["reversal_history"] = reversal_history
        context["audit_entries"] = audit_entries

        return context
