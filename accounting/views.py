from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.views.generic.edit import FormView
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.urls import reverse_lazy
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.contrib.auth.mixins import LoginRequiredMixin
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from weasyprint import HTML, CSS
import csv
from decimal import Decimal, InvalidOperation

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
    BalanceAdjustmentForm,
    OpeningBalanceImportForm,
)
from .utils import (
    get_trial_balance,
    get_account_balance_as_of,
    create_journal_with_entries,
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


class OpeningBalanceImportView(LoginRequiredMixin, AccountantRequiredMixin, FormView):
    """
    Bulk import opening balances from CSV and post a single balanced journal.
    """

    template_name = "accounting/opening_balance_import.html"
    form_class = OpeningBalanceImportForm
    success_url = reverse_lazy("accounting:account_list")

    def _parse_balance(self, value):
        normalized = str(value or "").strip().replace(",", "")
        if not normalized:
            raise InvalidOperation("blank")
        return Decimal(normalized)

    def _get_entry_type_from_signed_balance(self, account, signed_balance):
        debit_normal = account.type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE]
        if signed_balance >= 0:
            return "DEBIT" if debit_normal else "CREDIT"
        return "CREDIT" if debit_normal else "DEBIT"

    def form_valid(self, form):
        offset_account = form.cleaned_data["offset_account"]
        opening_date = form.cleaned_data["opening_date"]
        base_description = (form.cleaned_data.get("description") or "").strip()
        csv_file = form.cleaned_data["csv_file"]

        try:
            decoded = csv_file.read().decode("utf-8-sig")
        except Exception:
            form.add_error("csv_file", "Could not read CSV file. Use UTF-8 CSV format.")
            return self.form_invalid(form)

        reader = csv.DictReader(decoded.splitlines())
        required_columns = {"account_number", "balance"}
        if not reader.fieldnames or not required_columns.issubset(set(reader.fieldnames)):
            form.add_error(
                "csv_file",
                "CSV must include columns: account_number,balance (optional: memo,account_name).",
            )
            return self.form_invalid(form)

        entries = []
        row_errors = []
        total_debits = Decimal("0.00")
        total_credits = Decimal("0.00")
        processed_rows = 0

        for index, row in enumerate(reader, start=2):
            account_number = (row.get("account_number") or "").strip()
            account_name = (row.get("account_name") or "").strip()
            memo = (row.get("memo") or "").strip()

            if not account_number and not account_name:
                continue

            account = None
            if account_number:
                account = Account.objects.filter(account_number=account_number).first()
            if not account and account_name:
                account = Account.objects.filter(name=account_name).first()
            if not account:
                row_errors.append(f"Row {index}: account not found ({account_number or account_name}).")
                continue

            try:
                signed_balance = self._parse_balance(row.get("balance"))
            except InvalidOperation:
                row_errors.append(f"Row {index}: invalid balance value '{row.get('balance')}'.")
                continue

            if signed_balance == 0:
                continue

            entry_type = self._get_entry_type_from_signed_balance(account, signed_balance)
            amount = abs(signed_balance)

            entry_memo = memo or f"Opening balance import for {account.name}"
            entries.append(
                {
                    "account": account,
                    "entry_type": entry_type,
                    "amount": amount,
                    "memo": entry_memo,
                }
            )
            processed_rows += 1
            if entry_type == "DEBIT":
                total_debits += amount
            else:
                total_credits += amount

        if row_errors:
            form.add_error("csv_file", " | ".join(row_errors[:5]))
            if len(row_errors) > 5:
                form.add_error("csv_file", f"... and {len(row_errors) - 5} more row errors.")
            return self.form_invalid(form)

        if not entries:
            form.add_error("csv_file", "No valid non-zero rows found to import.")
            return self.form_invalid(form)

        difference = total_debits - total_credits
        if difference > 0:
            entries.append(
                {
                    "account": offset_account,
                    "entry_type": "CREDIT",
                    "amount": difference,
                    "memo": "Opening balances offset entry",
                }
            )
        elif difference < 0:
            entries.append(
                {
                    "account": offset_account,
                    "entry_type": "DEBIT",
                    "amount": abs(difference),
                    "memo": "Opening balances offset entry",
                }
            )

        description = base_description or "Opening balances import"
        journal = create_journal_with_entries(
            date=opening_date,
            description=description,
            entries=entries,
            user=self.request.user,
            auto_post=True,
            validate_balances=False,
        )

        messages.success(
            self.request,
            f"Imported {processed_rows} account balances. Journal {journal.transaction_number} posted.",
        )
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


class JournalEditView(LoginRequiredMixin, AccountantRequiredMixin, UpdateView):
    """
    Edit a draft/pending journal header details.
    """

    model = Journal
    form_class = JournalForm
    template_name = "accounting/journal_form.html"
    success_url = reverse_lazy("accounting:journal_list")

    def dispatch(self, request, *args, **kwargs):
        journal = self.get_object()
        if journal.status not in [
            Journal.JournalStatus.DRAFT,
            Journal.JournalStatus.PENDING_APPROVAL,
        ]:
            messages.error(request, "Only draft or pending journals can be edited.")
            return redirect("accounting:journal_detail", pk=journal.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Journal updated successfully.")
        return super().form_valid(form)


class BalanceAdjustmentView(LoginRequiredMixin, AccountantRequiredMixin, FormView):
    """
    Create an auditable, journal-backed balance adjustment.
    """

    template_name = "accounting/balance_adjustment.html"
    form_class = BalanceAdjustmentForm
    success_url = reverse_lazy("accounting:account_list")

    def form_valid(self, form):
        entries = form.build_entries()
        description = form.cleaned_data["description"].strip()
        account = form.cleaned_data["account"]
        adjustment_type = form.cleaned_data["adjustment_type"].lower()

        try:
            create_journal_with_entries(
                date=timezone.now().date(),
                description=(
                    f"Balance {adjustment_type} for {account.name}. "
                    f"Reason: {description}"
                ),
                entries=entries,
                user=self.request.user,
                auto_post=True,
                # Balance adjustments are authorized override entries used to
                # set or correct balances, so they bypass operational balance gates.
                validate_balances=False,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            messages.error(self.request, "Balance adjustment failed. Check details and retry.")
            return self.form_invalid(form)

        messages.success(
            self.request, "Balance adjustment posted successfully and auto-posted."
        )
        return super().form_valid(form)


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

    def get_queryset(self):
        return (
            FiscalYear.objects.annotate(journal_count=Count("periods__journals", distinct=True))
            .order_by("-year")
        )


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

    entries_qs = account.entries.select_related("journal").all()

    if start_date:
        entries_qs = entries_qs.filter(journal__date__gte=start_date)
    if end_date:
        entries_qs = entries_qs.filter(journal__date__lte=end_date)

    entries_qs = entries_qs.order_by("journal__date", "journal__created_at", "pk")

    filtered_delta = sum(
        entry.amount if entry.entry_type == "DEBIT" else -entry.amount
        for entry in entries_qs
    )
    opening_balance = account.get_balance() - filtered_delta

    running_balance = opening_balance
    entries = list(entries_qs)
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")
    for entry in entries:
        if entry.entry_type == "DEBIT":
            total_debits += entry.amount
            running_balance += entry.amount
        else:
            total_credits += entry.amount
            running_balance -= entry.amount
        entry.running_balance = running_balance

    context = {
        "account": account,
        "entries": entries,
        "start_date": start_date,
        "end_date": end_date,
        "opening_balance": opening_balance,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "accounts": Account.objects.all().order_by("account_number", "name"),
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


@login_required
@auditor_or_accountant_required
def unposted_financial_events_report(request):
    """
    Show financial source events that do not yet have a corresponding ledger journal.
    """
    from payroll.models import PayrollRun, IOU

    payroll_ct = ContentType.objects.get_for_model(PayrollRun)
    iou_ct = ContentType.objects.get_for_model(IOU)

    posted_payroll_ids = set(
        Journal.objects.filter(
            content_type=payroll_ct,
            description__startswith="Payroll for period:",
        ).values_list("object_id", flat=True)
    )
    posted_iou_approval_ids = set(
        Journal.objects.filter(
            content_type=iou_ct,
            description__startswith="IOU approved for",
        ).values_list("object_id", flat=True)
    )
    posted_iou_direct_paid_ids = set(
        Journal.objects.filter(
            content_type=iou_ct,
            description__startswith="IOU paid (direct) by",
        ).values_list("object_id", flat=True)
    )

    unposted_closed_payroll = PayrollRun.objects.filter(closed=True).exclude(
        pk__in=posted_payroll_ids
    ).order_by("-paydays")
    unposted_iou_approved = IOU.objects.filter(status="APPROVED").exclude(
        pk__in=posted_iou_approval_ids
    ).order_by("-approved_at", "-created_at")
    unposted_iou_direct_paid = IOU.objects.filter(
        status="PAID", payment_method="DIRECT_PAYMENT"
    ).exclude(pk__in=posted_iou_direct_paid_ids).order_by("-due_date", "-created_at")

    context = {
        "unposted_closed_payroll": unposted_closed_payroll,
        "unposted_iou_approved": unposted_iou_approved,
        "unposted_iou_direct_paid": unposted_iou_direct_paid,
        "total_unposted": (
            unposted_closed_payroll.count()
            + unposted_iou_approved.count()
            + unposted_iou_direct_paid.count()
        ),
    }
    return render(request, "accounting/reports/unposted_events.html", context)


@login_required
@auditor_or_accountant_required
def account_balance_report(request):
    """
    Show account balances as of today or a selected date.
    """
    account_id = request.GET.get("account")
    as_of_date = request.GET.get("as_of_date")

    accounts = Account.objects.all().order_by("account_number", "name")
    selected_account = None
    selected_balance = None

    if account_id:
        selected_account = get_object_or_404(Account, pk=account_id)
        if as_of_date:
            try:
                from datetime import datetime

                date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
                selected_balance = get_account_balance_as_of(selected_account, date_obj)
            except ValueError:
                messages.error(request, "Invalid date format")
                return redirect("accounting:account_balance")
        else:
            selected_balance = selected_account.get_balance()

    context = {
        "accounts": accounts,
        "selected_account": selected_account,
        "selected_balance": selected_balance,
        "as_of_date": as_of_date,
    }
    return render(request, "accounting/reports/account_balance.html", context)


@login_required
@auditor_or_accountant_required
def export_reports(request):
    """
    Export account balances.
    format=excel returns CSV for spreadsheet use.
    format=pdf redirects to trial balance PDF.
    """
    export_format = (request.GET.get("format") or "").lower()

    if export_format == "pdf":
        query_parts = []
        period = request.GET.get("period")
        as_of_date = request.GET.get("as_of_date")
        if period:
            query_parts.append(f"period={period}")
        if as_of_date:
            query_parts.append(f"as_of_date={as_of_date}")
        query = f"?{'&'.join(query_parts)}" if query_parts else ""
        return redirect(f"{reverse_lazy('accounting:trial_balance_pdf')}{query}")

    if export_format in {"excel", "csv"}:
        as_of_date = request.GET.get("as_of_date")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="account_balances_{timezone.now().date()}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(["Account Number", "Account Name", "Type", "Balance"])

        accounts = Account.objects.all().order_by("account_number", "name")
        for account in accounts:
            balance = account.get_balance()
            if as_of_date:
                try:
                    from datetime import datetime

                    date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
                    balance = get_account_balance_as_of(account, date_obj)
                except ValueError:
                    messages.error(request, "Invalid date format")
                    return redirect("accounting:reports")
            writer.writerow(
                [account.account_number, account.name, account.get_type_display(), balance]
            )
        return response

    messages.error(request, "Unsupported export format")
    return redirect("accounting:reports")


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

    entries_qs = account.entries.select_related("journal").all()

    if start_date:
        entries_qs = entries_qs.filter(journal__date__gte=start_date)
    if end_date:
        entries_qs = entries_qs.filter(journal__date__lte=end_date)

    entries_qs = entries_qs.order_by("journal__date", "journal__created_at", "pk")

    filtered_delta = sum(
        entry.amount if entry.entry_type == "DEBIT" else -entry.amount
        for entry in entries_qs
    )
    opening_balance = account.get_balance() - filtered_delta

    running_balance = opening_balance
    entries = list(entries_qs)
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")
    for entry in entries:
        if entry.entry_type == "DEBIT":
            total_debits += entry.amount
            running_balance += entry.amount
        else:
            total_credits += entry.amount
            running_balance -= entry.amount
        entry.running_balance = running_balance

    context = {
        "account": account,
        "entries": entries,
        "start_date": start_date,
        "end_date": end_date,
        "opening_balance": opening_balance,
        "total_debits": total_debits,
        "total_credits": total_credits,
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
