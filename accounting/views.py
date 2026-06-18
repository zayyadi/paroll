from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
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
from datetime import datetime, timedelta
try:
    from weasyprint import HTML, CSS
except ImportError:  # pragma: no cover - optional PDF dependency.
    HTML = CSS = None
import csv
from decimal import Decimal, InvalidOperation

from company.utils import get_user_company

from .models import (
    Account,
    FinancialReportDefinition,
    FinancialReportLine,
    Journal,
    JournalEntry,
    FiscalYear,
    AccountingPeriod,
    AccountingAuditTrail,
    DisciplinaryCase,
    DisciplinaryEvidence,
    DisciplinarySanction,
    DisciplinaryAppeal,
    DisciplinaryCaseAudit,
    AccountReconciliation,
    BankTransaction,
    ReconciliationItem,
    log_disciplinary_case_audit,
    CostCenter,
    Budget,
    BudgetLine,
    AccrualTemplate,
    ExchangeRate,
    CurrencyRevaluation,
    TaxReturn,
    TaxReturnLine,
    JournalAttachment,
    RecurringJournalTemplate,
)
from .forms import (
    JournalForm,
    AccountForm,
    FinancialReportDefinitionForm,
    FinancialReportLineForm,
    JournalApprovalForm,
    JournalReversalForm,
    JournalEntryFormSet,
    JournalReversalInitiationForm,
    JournalPartialReversalForm,
    JournalCorrectionForm,
    CorrectionEntryFormSet,
    BatchJournalReversalForm,
    JournalReversalConfirmationForm,
    BalanceAdjustmentForm,
    OpeningBalanceImportForm,
    FiscalYearForm,
    AccountingPeriodForm,
    DisciplinaryCaseForm,
    DisciplinaryEvidenceForm,
    DisciplinaryDecisionForm,
    DisciplinarySanctionForm,
    DisciplinaryAppealForm,
    DisciplinaryAppealReviewForm,
    CostCenterForm,
    BudgetForm,
    BudgetLineForm,
    BudgetVsActualForm,
    AccrualTemplateForm,
    ExchangeRateForm,
    CurrencyRevaluationForm,
    TaxReturnForm,
    TaxReturnLineForm,
    JournalAttachmentForm,
    RecurringJournalTemplateForm,
)
from .reporting import build_financial_report
from .utils import (
    get_trial_balance,
    get_trial_balance_totals,
    get_account_balance_as_of,
    create_journal_with_entries,
    post_journal,
    reverse_journal,
    reverse_journal_partial,
    reverse_journal_with_correction,
    batch_reverse_journals,
    close_accounting_period,
    get_dashboard_metrics,
    get_cash_flow_statement,
    get_financial_ratios,
    get_month_end_checklist,
    get_inventory_turnover,
    get_gross_margin_by_product,
)
from .permissions import (
    is_auditor,
    is_accountant,
    is_payroll_processor,
    is_hr_staff,
    can_manage_disciplinary_case,
    can_approve_journal,
    can_reverse_journal,
    can_close_period,
)
from .decorators import (
    accountant_required,
    auditor_required,
    accounting_role_required,
    auditor_or_accountant_required,
    discipline_access_required,
)
from .mixins import (
    AuditorRequiredMixin,
    AccountantRequiredMixin,
    AccountingRoleRequiredMixin,
    AuditorOrAccountantRequiredMixin,
    DisciplineAccessRequiredMixin,
    DisciplineManagerRequiredMixin,
    JournalApprovalMixin,
    JournalReversalMixin,
    PeriodClosingMixin,
)

User = get_user_model()

DISCIPLINARY_SYSTEM_DATA = {
    "overview": (
        "A scalable disciplinary framework for SMEs that combines strict"
        " accountability with a rehabilitation-first approach. The system is"
        " designed for consistency, due process, and operational continuity,"
        " while remaining aligned with Nigerian labour law expectations."
    ),
    "core_principles": [
        "Legality and fair hearing in line with employment contracts and Nigerian labour law.",
        "Proportionality: sanctions reflect severity, intent, impact, and recurrence.",
        "Consistency and transparency through standardized criteria and records.",
        "Due process: notice, response opportunity, impartial review, and written decisions.",
        "Rehabilitation-first for correctable behavior, with escalation for persistent risk.",
        "Non-retaliation and protection for complainants, witnesses, and respondents.",
        "Bias mitigation via conflict checks, structured decision factors, and audit reviews.",
    ],
    "violation_categories": [
        {
            "level": "Level 1",
            "category": "Minor",
            "examples": "Isolated lateness, minor policy lapses, low-impact errors.",
            "risk_posture": "Coaching and correction",
        },
        {
            "level": "Level 2",
            "category": "Moderate",
            "examples": "Repeated minor issues, disrespect, moderate negligence.",
            "risk_posture": "Formal warning and action plan",
        },
        {
            "level": "Level 3",
            "category": "Serious",
            "examples": "Significant insubordination, data/privacy breaches, harassment allegations.",
            "risk_posture": "Panel review and stronger sanctions",
        },
        {
            "level": "Level 4",
            "category": "Major",
            "examples": "Retaliation, theft indicators, severe discrimination, serious confidentiality breaches.",
            "risk_posture": "Suspension and termination review",
        },
        {
            "level": "Level 5",
            "category": "Critical",
            "examples": "Violence, credible threats, bribery/corruption, major fraud.",
            "risk_posture": "Immediate protective action",
        },
    ],
    "investigation_workflow": [
        "Intake and triage within 48 hours, including immediate risk assessment.",
        "Conflict-of-interest screening and investigator recusal where necessary.",
        "Written notice to respondent with allegation summary and process rights.",
        "Evidence preservation and collection (documents, logs, witness accounts, records).",
        "Structured interviews with documented statements and rebuttal opportunity.",
        "Findings based on balance of probabilities; heightened corroboration for severe sanctions.",
        "Decision memo documenting facts, credibility, policy mapping, and rationale.",
        "Written outcome communication with sanction details and appeal pathway.",
    ],
    "sanction_matrix": [
        {
            "level": "Level 1",
            "first_incident": "Coaching and documented note",
            "second_incident": "Written warning and training",
            "third_incident": "Final warning or short performance plan",
        },
        {
            "level": "Level 2",
            "first_incident": "Written warning and corrective plan",
            "second_incident": "Final warning and performance plan",
            "third_incident": "Suspension or role restriction",
        },
        {
            "level": "Level 3",
            "first_incident": "Final warning and/or suspension with remediation",
            "second_incident": "Long suspension or demotion",
            "third_incident": "Termination review",
        },
        {
            "level": "Level 4",
            "first_incident": "Investigatory suspension; demotion/final warning or termination",
            "second_incident": "Termination likely",
            "third_incident": "Termination",
        },
        {
            "level": "Level 5",
            "first_incident": "Immediate protective suspension and termination review",
            "second_incident": "Termination",
            "third_incident": "Termination",
        },
    ],
    "appeals_process": [
        "Appeal submission within 5 to 10 business days from decision date.",
        "Allowed grounds: procedural unfairness, new evidence, bias/conflict, disproportionality.",
        "Review by an independent and more senior authority.",
        "Possible outcomes: uphold, modify, overturn, or order reinvestigation.",
        "Final internal determination is documented with reasons.",
    ],
    "implementation_checklist": [
        "Approve disciplinary policy text, SOP workflow, and sanction matrix.",
        "Assign intake officers, investigators, panel members, and appeal authority.",
        "Deploy standardized templates: intake, investigation log, decision memo, appeal form.",
        "Enable secure case documentation with role-based access controls.",
        "Train managers and investigators before go-live.",
        "Run a 60 to 90 day pilot and calibrate thresholds and timelines.",
        "Launch quarterly governance review cadence and annual policy audit.",
    ],
}


@login_required
@accounting_role_required
def accounting_dashboard(request):
    company = get_user_company(request.user)
    period_id = request.GET.get("period")
    period = None
    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)

    metrics = get_dashboard_metrics(company, period=period)
    ratios = get_financial_ratios(company, as_of_date=metrics["as_of_date"])
    recent_journals = Journal.objects.filter(company=company).order_by("-created_at")[:10]
    active_periods = AccountingPeriod.objects.filter(
        company=company, is_active=True
    ).order_by("-start_date")[:6]

    # AR/AP summaries
    try:
        from inventory.services import get_accounts_receivable_aging, get_accounts_payable_aging
        ar = get_accounts_receivable_aging(company)
        ap = get_accounts_payable_aging(company)
        total_ar = sum(row["outstanding"] for row in ar)
        total_ap = sum(row["outstanding"] for row in ap)
        overdue_ar = sum(row["outstanding"] for row in ar if row["days_overdue"] > 30)
    except Exception:
        total_ar = Decimal("0.00")
        total_ap = Decimal("0.00")
        overdue_ar = Decimal("0.00")

    context = {
        "draft_journals_count": metrics["draft_journals"],
        "pending_journals_count": metrics["pending_journals"],
        "posted_journals_count": metrics["posted_journals"],
        "recent_journals": recent_journals,
        "active_periods": active_periods,
        "is_auditor": is_auditor(request.user),
        "is_accountant": is_accountant(request.user),
        "is_payroll_processor": is_payroll_processor(request.user),
        "metrics": metrics,
        "ratios": ratios,
        "total_ar": total_ar,
        "total_ap": total_ap,
        "overdue_ar": overdue_ar,
    }

    return render(request, "accounting/dashboard.html", context)


class AccountListView(LoginRequiredMixin, AccountingRoleRequiredMixin, ListView):
    """
    List all accounts
    """

    model = Account
    template_name = "accounting/account_list.html"
    context_object_name = "accounts"
    paginate_by = 20

    def get_queryset(self):
        queryset = Account.objects.filter(
            company=get_user_company(self.request.user)
        ).order_by("account_number")
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

    def get_queryset(self):
        return Account.objects.filter(company=get_user_company(self.request.user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.get_object()

        context["current_balance"] = account.get_balance()

        context["recent_entries"] = account.entries.all().order_by(
            "-journal__created_at"
        )[:20]

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
        form.instance.company = get_user_company(self.request.user)
        messages.success(self.request, "Account created successfully.")
        return super().form_valid(form)


class AccountUpdateView(LoginRequiredMixin, AccountantRequiredMixin, UpdateView):
    model = Account
    form_class = AccountForm
    template_name = "accounting/account_form.html"

    def get_queryset(self):
        return Account.objects.filter(company=get_user_company(self.request.user))

    def get_success_url(self):
        return reverse_lazy("accounting:account_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        form.instance.company = get_user_company(self.request.user)
        messages.success(self.request, "Account updated successfully.")
        return super().form_valid(form)


class FinancialReportListView(
    LoginRequiredMixin, AuditorOrAccountantRequiredMixin, ListView
):
    model = FinancialReportDefinition
    template_name = "accounting/reports/designer_list.html"
    context_object_name = "reports"

    def get_queryset(self):
        return FinancialReportDefinition.objects.filter(
            company=get_user_company(self.request.user)
        ).order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Report Designer",
                "is_auditor": is_auditor(self.request.user),
                "is_accountant": is_accountant(self.request.user),
                "is_payroll_processor": is_payroll_processor(self.request.user),
            }
        )
        return context


class FinancialReportCreateView(LoginRequiredMixin, AccountantRequiredMixin, CreateView):
    model = FinancialReportDefinition
    form_class = FinancialReportDefinitionForm
    template_name = "accounting/reports/designer_form.html"

    def form_valid(self, form):
        form.instance.company = get_user_company(self.request.user)
        messages.success(self.request, "Financial report design created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "accounting:financial_report_detail", kwargs={"pk": self.object.pk}
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "New Report Design",
                "is_auditor": is_auditor(self.request.user),
                "is_accountant": is_accountant(self.request.user),
                "is_payroll_processor": is_payroll_processor(self.request.user),
            }
        )
        return context


class FinancialReportDetailView(
    LoginRequiredMixin, AuditorOrAccountantRequiredMixin, DetailView
):
    model = FinancialReportDefinition
    template_name = "accounting/reports/designer_detail.html"
    context_object_name = "report_definition"

    def get_queryset(self):
        return FinancialReportDefinition.objects.filter(
            company=get_user_company(self.request.user)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rendered_report = build_financial_report(self.object)
        context.update(
            {
                "page_title": self.object.name,
                "rendered_report": rendered_report,
                "is_auditor": is_auditor(self.request.user),
                "is_accountant": is_accountant(self.request.user),
                "is_payroll_processor": is_payroll_processor(self.request.user),
            }
        )
        return context


class FinancialReportLineCreateView(LoginRequiredMixin, AccountantRequiredMixin, CreateView):
    model = FinancialReportLine
    form_class = FinancialReportLineForm
    template_name = "accounting/reports/designer_line_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.report_definition = get_object_or_404(
            FinancialReportDefinition,
            pk=kwargs["pk"],
            company=get_user_company(request.user),
        )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = self.report_definition.company
        return kwargs

    def form_valid(self, form):
        form.instance.report = self.report_definition
        messages.success(self.request, "Report line added.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "accounting:financial_report_detail",
            kwargs={"pk": self.report_definition.pk},
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "page_title": "Add Report Line",
                "report_definition": self.report_definition,
                "is_auditor": is_auditor(self.request.user),
                "is_accountant": is_accountant(self.request.user),
                "is_payroll_processor": is_payroll_processor(self.request.user),
            }
        )
        return context


class OpeningBalanceImportView(LoginRequiredMixin, AccountantRequiredMixin, FormView):
    """
    Bulk import opening balances from CSV and post a single balanced journal.
    """

    template_name = "accounting/opening_balance_import.html"
    form_class = OpeningBalanceImportForm
    success_url = reverse_lazy("accounting:account_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = get_user_company(self.request.user)
        return kwargs

    def _parse_balance(self, value):
        normalized = str(value or "").strip().replace(",", "")
        if not normalized:
            raise InvalidOperation("blank")
        return Decimal(normalized)

    def _get_entry_type_from_signed_balance(self, account, signed_balance):
        debit_normal = account.type in [
            Account.AccountType.ASSET,
            Account.AccountType.EXPENSE,
        ]
        if signed_balance >= 0:
            return "DEBIT" if debit_normal else "CREDIT"
        return "CREDIT" if debit_normal else "DEBIT"

    def form_valid(self, form):
        company = get_user_company(self.request.user)
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
        if not reader.fieldnames or not required_columns.issubset(
            set(reader.fieldnames)
        ):
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
                account = Account.objects.filter(
                    company=company, account_number=account_number
                ).first()
            if not account and account_name:
                account = Account.objects.filter(company=company, name=account_name).first()
            if not account:
                row_errors.append(
                    f"Row {index}: account not found ({account_number or account_name})."
                )
                continue

            try:
                signed_balance = self._parse_balance(row.get("balance"))
            except InvalidOperation:
                row_errors.append(
                    f"Row {index}: invalid balance value '{row.get('balance')}'."
                )
                continue

            if signed_balance == 0:
                continue

            entry_type = self._get_entry_type_from_signed_balance(
                account, signed_balance
            )
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
                form.add_error(
                    "csv_file", f"... and {len(row_errors) - 5} more row errors."
                )
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
            company=company,
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


class JournalListView(LoginRequiredMixin, AccountingRoleRequiredMixin, ListView):
    """
    List all journals with filtering
    """

    model = Journal
    template_name = "accounting/journal_list.html"
    context_object_name = "journals"
    paginate_by = 20

    def paginate_queryset(self, queryset, page_size):
        page = (
            self.kwargs.get(self.page_kwarg)
            or self.request.GET.get(self.page_kwarg)
            or 1
        )
        try:
            page_number = int(page)
        except (TypeError, ValueError):
            return super().paginate_queryset(queryset, page_size)

        if page_number >= 1:
            return super().paginate_queryset(queryset, page_size)

        paginator = self.get_paginator(
            queryset,
            page_size,
            allow_empty_first_page=self.get_allow_empty(),
        )
        page = paginator.page(1)
        return paginator, page, page.object_list, page.has_other_pages()

    def get_queryset(self):
        queryset = Journal.objects.filter(
            company=get_user_company(self.request.user)
        ).order_by("-created_at")

        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        start_date = self.request.GET.get("start_date")
        end_date = self.request.GET.get("end_date")
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

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
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        return context


class JournalDetailView(LoginRequiredMixin, AccountingRoleRequiredMixin, DetailView):

    model = Journal
    template_name = "accounting/journal_detail.html"
    context_object_name = "journal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.get_object()

        context["entries"] = journal.entries.all().order_by("account__name")

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

        context["can_approve"] = can_approve_journal(self.request.user, journal)
        context["can_reverse"] = can_reverse_journal(self.request.user, journal)
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["can_edit"] = (
            is_accountant(self.request.user)
            and journal.status
            in [Journal.JournalStatus.DRAFT, Journal.JournalStatus.PENDING_APPROVAL]
        )
        context["can_delete"] = (
            is_accountant(self.request.user)
            and journal.status
            in [Journal.JournalStatus.DRAFT, Journal.JournalStatus.PENDING_APPROVAL]
        )
        context["can_submit"] = (
            is_accountant(self.request.user)
            and journal.status == Journal.JournalStatus.DRAFT
        )

        context["is_reversed"] = journal.reversed_journal is not None
        context["is_reversal"] = (
            hasattr(journal, "reversal_of") and journal.reversal_of is not None
        )
        context["reversal_journal"] = journal.reversed_journal
        context["reversal_of"] = getattr(journal, "reversal_of", None)
        context["reversal_reason"] = journal.reversal_reason

        audit_entries = AccountingAuditTrail.objects.filter(
            content_type=ContentType.objects.get_for_model(Journal),
            object_id=journal.pk,
        ).order_by("-timestamp")[:10]

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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = get_user_company(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = get_user_company(self.request.user)
        if self.request.POST:
            context["entry_formset"] = JournalEntryFormSet(
                self.request.POST, form_kwargs={"company": company}
            )
        else:
            context["entry_formset"] = JournalEntryFormSet(
                form_kwargs={"company": company}
            )
        context["accounts"] = Account.objects.filter(company=company).order_by(
            "account_number", "name"
        )
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        entry_formset = context["entry_formset"]
        if not entry_formset.is_valid():
            return self.form_invalid(form)

        with transaction.atomic():
            form.instance.company = get_user_company(self.request.user)
            form.instance.created_by = self.request.user
            form.instance.status = Journal.JournalStatus.DRAFT
            self.object = form.save()

            entry_formset.instance = self.object
            entry_formset.save()

            messages.success(self.request, "Journal created successfully.")
            return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


class JournalEditView(LoginRequiredMixin, AccountantRequiredMixin, UpdateView):

    model = Journal
    form_class = JournalForm
    template_name = "accounting/journal_form.html"
    success_url = reverse_lazy("accounting:journal_list")

    def get_queryset(self):
        return Journal.objects.filter(company=get_user_company(self.request.user))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = get_user_company(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = get_user_company(self.request.user)
        if self.request.POST:
            context["entry_formset"] = JournalEntryFormSet(
                self.request.POST,
                instance=self.object,
                form_kwargs={"company": company},
            )
        else:
            context["entry_formset"] = JournalEntryFormSet(
                instance=self.object,
                form_kwargs={"company": company},
            )
        context["accounts"] = Account.objects.filter(company=company).order_by(
            "account_number", "name"
        )
        return context

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
        context = self.get_context_data()
        entry_formset = context["entry_formset"]
        if not entry_formset.is_valid():
            return self.form_invalid(form)

        with transaction.atomic():
            self.object = form.save()
            entry_formset.instance = self.object
            entry_formset.save()
        messages.success(self.request, "Journal updated successfully.")
        return redirect(self.get_success_url())


class JournalDeleteView(LoginRequiredMixin, AccountantRequiredMixin, DeleteView):
    model = Journal
    template_name = "accounting/journal_confirm_delete.html"
    context_object_name = "journal"
    success_url = reverse_lazy("accounting:journal_list")

    def get_queryset(self):
        return Journal.objects.filter(company=get_user_company(self.request.user))

    def dispatch(self, request, *args, **kwargs):
        journal = self.get_object()
        if journal.status not in [
            Journal.JournalStatus.DRAFT,
            Journal.JournalStatus.PENDING_APPROVAL,
        ]:
            messages.error(
                request,
                "Only draft or pending journals can be deleted. Post a reversal for finalized journals.",
            )
            return redirect("accounting:journal_detail", pk=journal.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        transaction_number = self.object.transaction_number
        response = super().form_valid(form)
        messages.success(self.request, f"Journal {transaction_number} deleted successfully.")
        return response


@login_required
@accountant_required
def journal_submit_view(request, pk):
    journal = get_object_or_404(
        Journal, pk=pk, company=get_user_company(request.user)
    )
    if request.method != "POST":
        return redirect("accounting:journal_detail", pk=journal.pk)

    if journal.status != Journal.JournalStatus.DRAFT:
        messages.error(request, "Only draft journals can be submitted for approval.")
        return redirect("accounting:journal_detail", pk=journal.pk)

    try:
        journal.validate_entries()
        journal.submit_for_approval()
        messages.success(request, "Journal submitted for approval.")
    except ValidationError as exc:
        messages.error(request, ", ".join(exc.messages))
    return redirect("accounting:journal_detail", pk=journal.pk)


class BalanceAdjustmentView(LoginRequiredMixin, AccountantRequiredMixin, FormView):
    """
    Create an auditable, journal-backed balance adjustment.
    """

    template_name = "accounting/balance_adjustment.html"
    form_class = BalanceAdjustmentForm
    success_url = reverse_lazy("accounting:account_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = get_user_company(self.request.user)
        return kwargs

    def form_valid(self, form):
        entries = form.build_entries()
        description = form.cleaned_data["description"].strip()
        account = form.cleaned_data["account"]
        adjustment_type = form.cleaned_data["adjustment_type"].lower()

        try:
            create_journal_with_entries(
                company=get_user_company(self.request.user),
                date=timezone.now().date(),
                description=(
                    f"Balance {adjustment_type} for {account.name}. "
                    f"Reason: {description}"
                ),
                entries=entries,
                user=self.request.user,
                auto_post=True,
                validate_balances=False,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
            messages.error(
                self.request, "Balance adjustment failed. Check details and retry."
            )
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
    permission_object_model = Journal

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.get_permission_object()
        entries = journal.entries.all().order_by("account__name")
        context["journal"] = journal
        context["entries"] = entries
        context["total_debits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.DEBIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        context["total_credits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.CREDIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        return context

    def form_valid(self, form):
        journal = self.get_permission_object()
        action = form.cleaned_data["action"]
        reason = form.cleaned_data["reason"]

        if journal.status != Journal.JournalStatus.PENDING_APPROVAL:
            messages.error(
                self.request,
                f"Only pending journals can be reviewed. Current status: {journal.get_status_display()}.",
            )
            return redirect("accounting:journal_detail", pk=journal.pk)

        try:
            if action == "approve":
                journal.approve(self.request.user)
                messages.success(self.request, "Journal approved successfully.")
            else:
                journal.status = Journal.JournalStatus.CANCELLED
                journal.save()
                messages.success(self.request, "Journal rejected.")
        except ValidationError as exc:
            messages.error(self.request, ", ".join(exc.messages))
            return redirect("accounting:journal_detail", pk=journal.pk)

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


@login_required
@accountant_required
def journal_post_view(request, pk):
    journal = get_object_or_404(
        Journal, pk=pk, company=get_user_company(request.user)
    )
    if request.method != "POST":
        return redirect("accounting:journal_detail", pk=journal.pk)

    try:
        post_journal(journal, request.user)
        messages.success(request, "Journal posted successfully.")
    except ValidationError as exc:
        messages.error(request, ", ".join(exc.messages))
    return redirect("accounting:journal_detail", pk=journal.pk)


class JournalReversalView(LoginRequiredMixin, JournalReversalMixin, FormView):

    template_name = "accounting/journal_reversal.html"
    form_class = JournalReversalForm
    permission_object_model = Journal

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.get_permission_object()
        entries = journal.entries.all().order_by("account__name")
        context["journal"] = journal
        context["entries"] = entries
        context["total_debits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.DEBIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        context["total_credits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.CREDIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        return context

    def form_valid(self, form):
        journal = self.get_permission_object()
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


class FiscalYearListView(
    LoginRequiredMixin, AuditorOrAccountantRequiredMixin, ListView
):

    model = FiscalYear
    template_name = "accounting/fiscal_year_list.html"
    context_object_name = "fiscal_years"
    ordering = ["-year"]

    def get_queryset(self):
        return FiscalYear.objects.filter(
            company=get_user_company(self.request.user)
        ).annotate(
            journal_count=Count("periods__journals", distinct=True)
        ).order_by("-year")


class FiscalYearCreateView(LoginRequiredMixin, AccountantRequiredMixin, CreateView):
    model = FiscalYear
    form_class = FiscalYearForm
    template_name = "accounting/fiscal_year_form.html"
    success_url = reverse_lazy("accounting:fiscal_year_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = get_user_company(self.request.user)
        return kwargs

    def form_valid(self, form):
        form.instance.company = get_user_company(self.request.user)
        messages.success(self.request, "Fiscal year created successfully.")
        return super().form_valid(form)


class FiscalYearDetailView(
    LoginRequiredMixin, AuditorOrAccountantRequiredMixin, DetailView
):
    """
    View fiscal year details
    """

    model = FiscalYear
    template_name = "accounting/fiscal_year_detail.html"
    context_object_name = "fiscal_year"

    def get_queryset(self):
        return FiscalYear.objects.filter(company=get_user_company(self.request.user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fiscal_year = self.get_object()

        context["periods"] = fiscal_year.periods.all().order_by("period_number")

        context["journal_count"] = Journal.objects.filter(
            company=fiscal_year.company,
            period__fiscal_year=fiscal_year
        ).count()

        return context


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
        return AccountingPeriod.objects.filter(
            company=get_user_company(self.request.user)
        ).order_by("-fiscal_year", "-period_number")


class AccountingPeriodCreateView(LoginRequiredMixin, AccountantRequiredMixin, CreateView):
    model = AccountingPeriod
    form_class = AccountingPeriodForm
    template_name = "accounting/period_form.html"
    success_url = reverse_lazy("accounting:period_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        company = get_user_company(self.request.user)
        kwargs["company"] = company
        if self.request.method == "GET" and self.request.GET.get("fiscal_year"):
            kwargs.setdefault("initial", {})["fiscal_year"] = self.request.GET[
                "fiscal_year"
            ]
        return kwargs

    def form_valid(self, form):
        form.instance.company = get_user_company(self.request.user)
        messages.success(self.request, "Accounting period created successfully.")
        return super().form_valid(form)


class AccountingPeriodDetailView(
    LoginRequiredMixin, AccountingRoleRequiredMixin, DetailView
):
    """
    View accounting period details
    """

    model = AccountingPeriod
    template_name = "accounting/period_detail.html"
    context_object_name = "period"

    def get_queryset(self):
        return AccountingPeriod.objects.filter(company=get_user_company(self.request.user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period = self.get_object()

        context["journals"] = Journal.objects.filter(period=period).order_by("-date")

        context["trial_balance"] = get_trial_balance(period=period, company=period.company)
        context.update(get_trial_balance_totals(context["trial_balance"]))

        context["can_close"] = can_close_period(self.request.user, period)

        return context


class AccountingPeriodCloseView(LoginRequiredMixin, PeriodClosingMixin, FormView):
    """
    Close an accounting period (auditors only)
    """

    template_name = "accounting/period_close.html"
    permission_object_model = AccountingPeriod

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

        user_id = self.request.GET.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        action = self.request.GET.get("action")
        if action:
            queryset = queryset.filter(action=action)

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


@login_required
@discipline_access_required
def disciplinary_system_view(request):
    context = {
        "page_title": "Disciplinary System",
        "breadcrumbs": [{"title": "Disciplinary System"}],
        "framework": DISCIPLINARY_SYSTEM_DATA,
        "is_auditor": is_auditor(request.user),
        "is_accountant": is_accountant(request.user),
        "is_payroll_processor": is_payroll_processor(request.user),
        "is_hr_staff": is_hr_staff(request.user),
    }
    return render(request, "accounting/disciplinary_system.html", context)


def _disciplinary_case_queryset_for_user(user):
    company = get_user_company(user)
    return DisciplinaryCase.objects.filter(company=company)


def _get_disciplinary_case_for_user(user, pk):
    return get_object_or_404(_disciplinary_case_queryset_for_user(user), pk=pk)


class DisciplinaryCaseListView(
    LoginRequiredMixin, DisciplineAccessRequiredMixin, ListView
):
    model = DisciplinaryCase
    template_name = "accounting/discipline/case_list.html"
    context_object_name = "cases"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            _disciplinary_case_queryset_for_user(self.request.user)
            .select_related(
                "respondent", "reporter", "investigator", "decided_by"
            )
            .prefetch_related("sanctions", "appeals")
            .order_by("-created_at")
        )

        search = self.request.GET.get("search")
        status = self.request.GET.get("status")
        level = self.request.GET.get("level")

        if search:
            queryset = queryset.filter(
                Q(case_number__icontains=search)
                | Q(allegation_summary__icontains=search)
                | Q(respondent__email__icontains=search)
            )
        if status:
            queryset = queryset.filter(status=status)
        if level:
            queryset = queryset.filter(violation_level=level)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = DisciplinaryCase.Status.choices
        context["level_choices"] = DisciplinaryCase.ViolationLevel.choices
        context["page_title"] = "Disciplinary Cases"
        context["breadcrumbs"] = [{"title": "Disciplinary Cases"}]
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["is_hr_staff"] = is_hr_staff(self.request.user)
        return context


class DisciplinaryCaseDetailView(
    LoginRequiredMixin, DisciplineAccessRequiredMixin, DetailView
):
    model = DisciplinaryCase
    template_name = "accounting/discipline/case_detail.html"
    context_object_name = "disciplinary_case"

    def get_queryset(self):
        return _disciplinary_case_queryset_for_user(self.request.user).select_related(
            "respondent", "reporter", "investigator", "decided_by"
        ).prefetch_related(
            "evidence_items", "sanctions", "appeals", "appeals__reviewed_by"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        disciplinary_case = self.object
        context["page_title"] = f"Case {disciplinary_case.case_number}"
        context["breadcrumbs"] = [
            {
                "title": "Disciplinary Cases",
                "url": reverse_lazy("payroll:discipline_case_list"),
            },
            {"title": disciplinary_case.case_number},
        ]
        context["can_decide"] = can_manage_disciplinary_case(self.request.user)
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["is_hr_staff"] = is_hr_staff(self.request.user)
        return context


class DisciplinaryCaseCreateView(
    LoginRequiredMixin, DisciplineAccessRequiredMixin, CreateView
):
    model = DisciplinaryCase
    form_class = DisciplinaryCaseForm
    template_name = "accounting/discipline/case_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = get_user_company(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Report Disciplinary Case"
        context["breadcrumbs"] = [
            {
                "title": "Disciplinary Cases",
                "url": reverse_lazy("payroll:discipline_case_list"),
            },
            {"title": "New Case"},
        ]
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["is_hr_staff"] = is_hr_staff(self.request.user)
        return context

    def form_valid(self, form):
        form.instance.company = get_user_company(self.request.user)
        form.instance.reporter = self.request.user
        response = super().form_valid(form)
        self.object.mark_due_process_notice()
        messages.success(self.request, "Disciplinary case created successfully.")
        return response

    def get_success_url(self):
        return reverse_lazy(
            "payroll:discipline_case_detail",
            kwargs={"pk": self.object.pk},
        )


@login_required
@auditor_or_accountant_required
def export_journals_csv_view(request):
    company = get_user_company(request.user)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=90)
    if request.GET.get("start_date"):
        start_date = datetime.strptime(request.GET["start_date"], "%Y-%m-%d").date()
    if request.GET.get("end_date"):
        end_date = datetime.strptime(request.GET["end_date"], "%Y-%m-%d").date()

    from integrations.export_connectors import export_journals_to_csv
    csv_data = export_journals_to_csv(company, start_date, end_date)
    response = HttpResponse(csv_data, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="paroll_journals_{start_date}_{end_date}.csv"'
    return response


@login_required
@auditor_or_accountant_required
def export_chart_of_accounts_csv_view(request):
    company = get_user_company(request.user)
    from integrations.export_connectors import export_chart_of_accounts_csv
    csv_data = export_chart_of_accounts_csv(company)
    response = HttpResponse(csv_data, content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="paroll_chart_of_accounts.csv"'
    return response


@login_required
@auditor_or_accountant_required
def export_suppliers_csv_view(request):
    company = get_user_company(request.user)
    from integrations.export_connectors import export_suppliers_csv
    csv_data = export_suppliers_csv(company)
    response = HttpResponse(csv_data, content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="paroll_suppliers.csv"'
    return response


@login_required
@auditor_or_accountant_required
def export_customers_csv_view(request):
    company = get_user_company(request.user)
    from integrations.export_connectors import export_customers_csv
    csv_data = export_customers_csv(company)
    response = HttpResponse(csv_data, content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="paroll_customers.csv"'
    return response


@login_required
@auditor_or_accountant_required
def cash_flow_report(request):
    company = get_user_company(request.user)
    end_date = timezone.now().date()
    start_date = end_date.replace(day=1)
    period_id = request.GET.get("period")
    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
        start_date = period.start_date
        end_date = period.end_date

    if request.GET.get("start_date"):
        start_date = datetime.strptime(request.GET["start_date"], "%Y-%m-%d").date()
    if request.GET.get("end_date"):
        end_date = datetime.strptime(request.GET["end_date"], "%Y-%m-%d").date()

    cf = get_cash_flow_statement(company, start_date, end_date)
    return render(request, "accounting/reports/cash_flow.html", cf)


@login_required
@auditor_or_accountant_required
def financial_ratios_report(request):
    company = get_user_company(request.user)
    period_id = request.GET.get("period")
    as_of_date = None
    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
        as_of_date = period.end_date
    ratios = get_financial_ratios(company, as_of_date=as_of_date)
    return render(request, "accounting/reports/financial_ratios.html", {"ratios": ratios})


@login_required
@auditor_or_accountant_required
def ar_aging_report(request):
    company = get_user_company(request.user)
    from inventory.services import get_accounts_receivable_aging
    aging = get_accounts_receivable_aging(company)
    total = sum(row["outstanding"] for row in aging)
    return render(request, "accounting/reports/ar_aging.html", {
        "aging": aging, "total_outstanding": total,
    })


@login_required
@auditor_or_accountant_required
def ap_aging_report(request):
    company = get_user_company(request.user)
    from inventory.services import get_accounts_payable_aging
    aging = get_accounts_payable_aging(company)
    total = sum(row["outstanding"] for row in aging)
    return render(request, "accounting/reports/ap_aging.html", {
        "aging": aging, "total_outstanding": total,
    })


@login_required
@auditor_or_accountant_required
def inventory_turnover_report(request):
    company = get_user_company(request.user)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=365)
    period_id = request.GET.get("period")
    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
        start_date = period.start_date
        end_date = period.end_date
    data = get_inventory_turnover(company, start_date, end_date)
    return render(request, "accounting/reports/inventory_turnover.html", data)


@login_required
@auditor_or_accountant_required
def gross_margin_report(request):
    company = get_user_company(request.user)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=365)
    period_id = request.GET.get("period")
    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
        start_date = period.start_date
        end_date = period.end_date
    products = get_gross_margin_by_product(company, start_date, end_date)
    return render(request, "accounting/reports/gross_margin.html", {
        "products": products, "start_date": start_date, "end_date": end_date,
    })


@login_required
@auditor_or_accountant_required
def month_end_checklist_view(request):
    company = get_user_company(request.user)
    period_id = request.GET.get("period")
    period = None
    checklist = None
    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
        checklist = get_month_end_checklist(company, period)
    periods = AccountingPeriod.objects.filter(company=company, is_closed=False).order_by("-end_date")
    return render(request, "accounting/reports/month_end_checklist.html", {
        "checklist": checklist, "periods": periods, "selected_period": period,
    })


@login_required
@auditor_or_accountant_required
def executive_dashboard(request):
    company = get_user_company(request.user)
    metrics = get_dashboard_metrics(company)
    ratios = get_financial_ratios(company, as_of_date=metrics["as_of_date"])
    try:
        from inventory.services import get_accounts_receivable_aging, get_accounts_payable_aging
        ar = get_accounts_receivable_aging(company)
        ap = get_accounts_payable_aging(company)
        total_ar = sum(row["outstanding"] for row in ar)
        total_ap = sum(row["outstanding"] for row in ap)
    except Exception:
        total_ar = Decimal("0.00")
        total_ap = Decimal("0.00")

    return render(request, "accounting/reports/executive_dashboard.html", {
        "metrics": metrics,
        "ratios": ratios,
        "total_ar": total_ar,
        "total_ap": total_ap,
    })


@login_required
def mfa_verify_view(request):
    """Step-up MFA verification for sensitive accounting operations."""
    if request.method == "POST":
        password = request.POST.get("password", "")
        if request.user.check_password(password):
            from accounting.mfa import mark_mfa_verified
            mark_mfa_verified(request.user)
            messages.success(request, "Verification successful.")
            return_url = request.session.pop("mfa_return_url", None) or "/"
            return redirect(return_url)
        else:
            messages.error(request, "Incorrect password.")

    return render(request, "accounting/mfa_verify.html")

    def get_success_url(self):
        return reverse_lazy(
            "payroll:discipline_case_detail", kwargs={"pk": self.object.pk}
        )


class DisciplinaryCaseUpdateView(
    LoginRequiredMixin, DisciplineAccessRequiredMixin, UpdateView
):
    model = DisciplinaryCase
    form_class = DisciplinaryCaseForm
    template_name = "accounting/discipline/case_form.html"

    def get_queryset(self):
        return _disciplinary_case_queryset_for_user(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = get_user_company(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Update Case {self.object.case_number}"
        context["breadcrumbs"] = [
            {
                "title": "Disciplinary Cases",
                "url": reverse_lazy("payroll:discipline_case_list"),
            },
            {
                "title": self.object.case_number,
                "url": reverse_lazy(
                    "payroll:discipline_case_detail", kwargs={"pk": self.object.pk}
                ),
            },
            {"title": "Edit"},
        ]
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["is_hr_staff"] = is_hr_staff(self.request.user)
        return context

    def form_valid(self, form):
        messages.success(self.request, "Disciplinary case updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy(
            "payroll:discipline_case_detail", kwargs={"pk": self.object.pk}
        )


@login_required
@discipline_access_required
def disciplinary_case_start_investigation(request, pk):
    disciplinary_case = _get_disciplinary_case_for_user(request.user, pk)
    if request.method != "POST":
        return HttpResponseForbidden("Invalid request method.")

    old_status = disciplinary_case.status
    disciplinary_case.investigator = request.user
    disciplinary_case.move_to_investigation()
    disciplinary_case.save(update_fields=["investigator", "updated_at"])
    log_disciplinary_case_audit(
        disciplinary_case,
        DisciplinaryCaseAudit.Action.INVESTIGATION_STARTED,
        actor=request.user,
        details={
            "old_status": old_status,
            "new_status": disciplinary_case.status,
            "investigator_id": request.user.id,
        },
    )
    messages.success(request, "Case moved to investigation.")
    return redirect("payroll:discipline_case_detail", pk=disciplinary_case.pk)


class DisciplinaryEvidenceCreateView(
    LoginRequiredMixin, DisciplineAccessRequiredMixin, CreateView
):
    model = DisciplinaryEvidence
    form_class = DisciplinaryEvidenceForm
    template_name = "accounting/discipline/evidence_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.disciplinary_case = _get_disciplinary_case_for_user(
            request.user, kwargs["pk"]
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.case = self.disciplinary_case
        form.instance.submitted_by = self.request.user
        messages.success(self.request, "Evidence added to case.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["disciplinary_case"] = self.disciplinary_case
        context["page_title"] = f"Add Evidence - {self.disciplinary_case.case_number}"
        context["breadcrumbs"] = [
            {
                "title": "Disciplinary Cases",
                "url": reverse_lazy("payroll:discipline_case_list"),
            },
            {
                "title": self.disciplinary_case.case_number,
                "url": reverse_lazy(
                    "payroll:discipline_case_detail",
                    kwargs={"pk": self.disciplinary_case.pk},
                ),
            },
            {"title": "Add Evidence"},
        ]
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["is_hr_staff"] = is_hr_staff(self.request.user)
        return context

    def get_success_url(self):
        return reverse_lazy(
            "payroll:discipline_case_detail",
            kwargs={"pk": self.disciplinary_case.pk},
        )


class DisciplinaryDecisionUpdateView(
    LoginRequiredMixin, DisciplineManagerRequiredMixin, UpdateView
):
    model = DisciplinaryCase
    form_class = DisciplinaryDecisionForm
    template_name = "accounting/discipline/decision_form.html"

    def get_queryset(self):
        return _disciplinary_case_queryset_for_user(self.request.user)

    def form_valid(self, form):
        disciplinary_case = form.save(commit=False)
        old_status = disciplinary_case.status
        disciplinary_case.decide(
            finding=form.cleaned_data["finding"],
            decided_by=self.request.user,
            rationale=form.cleaned_data["decision_rationale"],
        )
        disciplinary_case.findings_summary = form.cleaned_data["findings_summary"]
        disciplinary_case.save(update_fields=["findings_summary", "updated_at"])
        log_disciplinary_case_audit(
            disciplinary_case,
            DisciplinaryCaseAudit.Action.DECISION_RECORDED,
            actor=self.request.user,
            details={
                "old_status": old_status,
                "new_status": disciplinary_case.status,
                "finding": disciplinary_case.finding,
                "required_review_level": disciplinary_case.required_review_level,
            },
        )
        messages.success(self.request, "Case decision recorded.")
        return redirect("payroll:discipline_case_detail", pk=disciplinary_case.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Decision - {self.object.case_number}"
        context["breadcrumbs"] = [
            {
                "title": "Disciplinary Cases",
                "url": reverse_lazy("payroll:discipline_case_list"),
            },
            {
                "title": self.object.case_number,
                "url": reverse_lazy(
                    "payroll:discipline_case_detail", kwargs={"pk": self.object.pk}
                ),
            },
            {"title": "Decision"},
        ]
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["is_hr_staff"] = is_hr_staff(self.request.user)
        return context


class DisciplinarySanctionCreateView(
    LoginRequiredMixin, DisciplineManagerRequiredMixin, CreateView
):
    model = DisciplinarySanction
    form_class = DisciplinarySanctionForm
    template_name = "accounting/discipline/sanction_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.disciplinary_case = _get_disciplinary_case_for_user(
            request.user, kwargs["pk"]
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.case = self.disciplinary_case
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_disciplinary_case_audit(
            self.disciplinary_case,
            DisciplinaryCaseAudit.Action.SANCTION_CREATED,
            actor=self.request.user,
            details={
                "sanction_id": self.object.id,
                "sanction_type": self.object.sanction_type,
                "status": self.object.status,
            },
        )
        messages.success(self.request, "Sanction recorded.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["disciplinary_case"] = self.disciplinary_case
        context["page_title"] = f"Add Sanction - {self.disciplinary_case.case_number}"
        context["breadcrumbs"] = [
            {
                "title": "Disciplinary Cases",
                "url": reverse_lazy("payroll:discipline_case_list"),
            },
            {
                "title": self.disciplinary_case.case_number,
                "url": reverse_lazy(
                    "payroll:discipline_case_detail",
                    kwargs={"pk": self.disciplinary_case.pk},
                ),
            },
            {"title": "Add Sanction"},
        ]
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["is_hr_staff"] = is_hr_staff(self.request.user)
        return context

    def get_success_url(self):
        return reverse_lazy(
            "payroll:discipline_case_detail",
            kwargs={"pk": self.disciplinary_case.pk},
        )


class DisciplinaryAppealCreateView(
    LoginRequiredMixin, DisciplineAccessRequiredMixin, CreateView
):
    model = DisciplinaryAppeal
    form_class = DisciplinaryAppealForm
    template_name = "accounting/discipline/appeal_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.disciplinary_case = _get_disciplinary_case_for_user(
            request.user, kwargs["pk"]
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.case = self.disciplinary_case
        form.instance.appellant = self.request.user
        old_status = self.disciplinary_case.status
        self.disciplinary_case.status = DisciplinaryCase.Status.APPEALED
        self.disciplinary_case.save(update_fields=["status", "updated_at"])
        response = super().form_valid(form)
        log_disciplinary_case_audit(
            self.disciplinary_case,
            DisciplinaryCaseAudit.Action.APPEAL_SUBMITTED,
            actor=self.request.user,
            details={
                "appeal_id": self.object.id,
                "grounds": self.object.grounds,
                "old_status": old_status,
                "new_status": self.disciplinary_case.status,
            },
        )
        messages.success(self.request, "Appeal submitted.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["disciplinary_case"] = self.disciplinary_case
        context["page_title"] = f"Submit Appeal - {self.disciplinary_case.case_number}"
        context["breadcrumbs"] = [
            {
                "title": "Disciplinary Cases",
                "url": reverse_lazy("payroll:discipline_case_list"),
            },
            {
                "title": self.disciplinary_case.case_number,
                "url": reverse_lazy(
                    "payroll:discipline_case_detail",
                    kwargs={"pk": self.disciplinary_case.pk},
                ),
            },
            {"title": "Submit Appeal"},
        ]
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["is_hr_staff"] = is_hr_staff(self.request.user)
        return context

    def get_success_url(self):
        return reverse_lazy(
            "payroll:discipline_case_detail",
            kwargs={"pk": self.disciplinary_case.pk},
        )


class DisciplinaryAppealReviewView(
    LoginRequiredMixin, DisciplineManagerRequiredMixin, UpdateView
):
    model = DisciplinaryAppeal
    form_class = DisciplinaryAppealReviewForm
    template_name = "accounting/discipline/appeal_review_form.html"
    context_object_name = "appeal"

    def get_queryset(self):
        return DisciplinaryAppeal.objects.select_related("case").filter(
            case__company=get_user_company(self.request.user)
        )

    def form_valid(self, form):
        appeal = form.save(commit=False)
        old_case_status = appeal.case.status
        old_appeal_status = self.get_object().status
        appeal.reviewed_by = self.request.user
        appeal.reviewed_at = timezone.now()
        appeal.save()

        if appeal.status in [
            DisciplinaryAppeal.Status.UPHELD,
            DisciplinaryAppeal.Status.MODIFIED,
            DisciplinaryAppeal.Status.OVERTURNED,
            DisciplinaryAppeal.Status.REJECTED,
        ]:
            appeal.case.close_case()
        elif appeal.status == DisciplinaryAppeal.Status.REINVESTIGATION_ORDERED:
            appeal.case.status = DisciplinaryCase.Status.UNDER_INVESTIGATION
            appeal.case.save(update_fields=["status", "updated_at"])

        log_disciplinary_case_audit(
            appeal.case,
            DisciplinaryCaseAudit.Action.APPEAL_REVIEWED,
            actor=self.request.user,
            details={
                "appeal_id": appeal.id,
                "old_appeal_status": old_appeal_status,
                "new_appeal_status": appeal.status,
                "old_case_status": old_case_status,
                "new_case_status": appeal.case.status,
                "outcome_notes": appeal.outcome_notes,
            },
        )

        messages.success(self.request, "Appeal review recorded.")
        return redirect("payroll:discipline_case_detail", pk=appeal.case.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["disciplinary_case"] = self.object.case
        context["page_title"] = f"Review Appeal - {self.object.case.case_number}"
        context["breadcrumbs"] = [
            {
                "title": "Disciplinary Cases",
                "url": reverse_lazy("payroll:discipline_case_list"),
            },
            {
                "title": self.object.case.case_number,
                "url": reverse_lazy(
                    "payroll:discipline_case_detail",
                    kwargs={"pk": self.object.case.pk},
                ),
            },
            {"title": "Review Appeal"},
        ]
        context["is_auditor"] = is_auditor(self.request.user)
        context["is_accountant"] = is_accountant(self.request.user)
        context["is_payroll_processor"] = is_payroll_processor(self.request.user)
        context["is_hr_staff"] = is_hr_staff(self.request.user)
        return context


@login_required
@auditor_or_accountant_required
def trial_balance_report(request):
    """
    Generate trial balance report
    """
    company = get_user_company(request.user)
    period_id = request.GET.get("period")
    as_of_date = request.GET.get("as_of_date")

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
        trial_balance = get_trial_balance(period=period, company=company)
        totals = get_trial_balance_totals(trial_balance)
        context = {
            "trial_balance": trial_balance,
            "period": period,
            "report_title": f"Trial Balance - {period}",
            **totals,
        }
    elif as_of_date:
        try:
            from datetime import datetime

            date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            trial_balance = get_trial_balance(as_of_date=date_obj, company=company)
            totals = get_trial_balance_totals(trial_balance)
            context = {
                "trial_balance": trial_balance,
                "as_of_date": as_of_date,
                "report_title": f"Trial Balance as of {as_of_date}",
                **totals,
            }
        except ValueError:
            messages.error(request, "Invalid date format")
            return redirect("accounting:reports")
    else:

        trial_balance = get_trial_balance(company=company)
        totals = get_trial_balance_totals(trial_balance)
        context = {
            "trial_balance": trial_balance,
            "report_title": "Trial Balance - Current",
            **totals,
        }

    return render(request, "accounting/reports/trial_balance.html", context)


@login_required
@auditor_or_accountant_required
def account_activity_report(request):
    """
    Generate account activity report
    """
    company = get_user_company(request.user)
    account_id = request.GET.get("account")
    if not account_id:
        messages.error(request, "Please select an account")
        return redirect("accounting:reports")

    account = get_object_or_404(Account, pk=account_id, company=company)

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
        "accounts": Account.objects.filter(company=company).order_by("account_number", "name"),
    }

    return render(request, "accounting/reports/account_activity.html", context)


@login_required
@auditor_or_accountant_required
def account_activity_report_for_account(request, pk):
    query = request.GET.copy()
    query["account"] = str(pk)
    request.GET = query
    return account_activity_report(request)


@login_required
@auditor_required
def reports_index(request):
    """
    Index page for accounting reports (auditors only)
    """

    company = get_user_company(request.user)
    periods = AccountingPeriod.objects.filter(company=company, is_closed=True).order_by(
        "-fiscal_year", "-period_number"
    )

    context = {
        "periods": periods,
        "accounts": Account.objects.filter(company=company).order_by("account_number"),
    }

    return render(request, "accounting/reports/index.html", context)


@login_required
@auditor_or_accountant_required
def unposted_financial_events_report(request):
    """
    Show financial source events that do not yet have a corresponding ledger journal.
    """
    from payroll.models import PayrollRun, IOU
    company = get_user_company(request.user)

    payroll_ct = ContentType.objects.get_for_model(PayrollRun)
    iou_ct = ContentType.objects.get_for_model(IOU)

    posted_payroll_ids = set(
        Journal.objects.filter(
            company=company,
            content_type=payroll_ct,
            description__startswith="Payroll for period:",
        ).values_list("object_id", flat=True)
    )
    posted_iou_approval_ids = set(
        Journal.objects.filter(
            company=company,
            content_type=iou_ct,
            description__startswith="IOU approved for",
        ).values_list("object_id", flat=True)
    )
    posted_iou_direct_paid_ids = set(
        Journal.objects.filter(
            company=company,
            content_type=iou_ct,
            description__startswith="IOU paid (direct) by",
        ).values_list("object_id", flat=True)
    )

    unposted_closed_payroll = (
        PayrollRun.objects.filter(company=company, closed=True)
        .exclude(pk__in=posted_payroll_ids)
        .order_by("-paydays")
    )
    unposted_iou_approved = (
        IOU.objects.filter(employee_id__company=company, status="APPROVED")
        .exclude(pk__in=posted_iou_approval_ids)
        .order_by("-approved_at", "-created_at")
    )
    unposted_iou_direct_paid = (
        IOU.objects.filter(
            employee_id__company=company, status="PAID", payment_method="DIRECT_PAYMENT"
        )
        .exclude(pk__in=posted_iou_direct_paid_ids)
        .order_by("-due_date", "-created_at")
    )

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
    company = get_user_company(request.user)

    accounts = Account.objects.filter(company=company).order_by("account_number", "name")
    selected_account = None
    selected_balance = None

    if account_id:
        selected_account = get_object_or_404(Account, pk=account_id, company=company)
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
        company = get_user_company(request.user)
        as_of_date = request.GET.get("as_of_date")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="account_balances_{timezone.now().date()}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(["Account Number", "Account Name", "Type", "Balance"])

        accounts = Account.objects.filter(company=company).order_by(
            "account_number", "name"
        )
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
                [
                    account.account_number,
                    account.name,
                    account.get_type_display(),
                    balance,
                ]
            )
        return response

    messages.error(request, "Unsupported export format")
    return redirect("accounting:reports")


@login_required
@auditor_or_accountant_required
def trial_balance_pdf(request):
    """
    Generate PDF version of trial balance report
    """
    company = get_user_company(request.user)
    period_id = request.GET.get("period")
    as_of_date = request.GET.get("as_of_date")

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
        trial_balance = get_trial_balance(period=period, company=company)
        totals = get_trial_balance_totals(trial_balance)
        context = {
            "trial_balance": trial_balance,
            "period": period,
            "report_title": f"Trial Balance - {period}",
            **totals,
        }
    elif as_of_date:
        try:
            from datetime import datetime

            date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            trial_balance = get_trial_balance(as_of_date=date_obj, company=company)
            totals = get_trial_balance_totals(trial_balance)
            context = {
                "trial_balance": trial_balance,
                "as_of_date": as_of_date,
                "report_title": f"Trial Balance as of {as_of_date}",
                **totals,
            }
        except ValueError:
            messages.error(request, "Invalid date format")
            return redirect("accounting:trial_balance")
    else:
        trial_balance = get_trial_balance(company=company)
        totals = get_trial_balance_totals(trial_balance)
        context = {
            "trial_balance": trial_balance,
            "report_title": "Trial Balance - Current",
            **totals,
        }

    html_string = render_to_string(
        "accounting/reports/pdf/trial_balance_pdf.html", context
    )
    html = HTML(string=html_string)
    css = CSS(
        string="""
        @page { size: A4 landscape; margin: 1cm; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid 
        th { background-color: 
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        .font-bold { font-weight: bold; }
        .text-danger { color: 
        .text-success { color: 
    """
    )

    pdf = html.write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="trial_balance_{timezone.now().date()}.pdf"'
    )
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

    account = get_object_or_404(
        Account,
        pk=account_id,
        company=get_user_company(request.user),
    )

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

    html_string = render_to_string(
        "accounting/reports/pdf/account_activity_pdf.html", context
    )
    html = HTML(string=html_string)
    css = CSS(
        string="""
        @page { size: A4 landscape; margin: 1cm; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid 
        th { background-color: 
        .text-right { text-align: right; }
        .text-center { text-align: center; }
        .font-bold { font-weight: bold; }
        .text-danger { color: 
        .text-success { color: 
    """
    )

    pdf = html.write_pdf()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="account_activity_{account.name}_{timezone.now().date()}.pdf"'
    )
    return response


@login_required
@auditor_or_accountant_required
def account_activity_pdf_for_account(request, pk):
    query = request.GET.copy()
    query["account"] = str(pk)
    request.GET = query
    return account_activity_pdf(request)


@login_required
@auditor_or_accountant_required
def general_ledger_report(request):
    """
    Generate general ledger report
    """
    period_id = request.GET.get("period")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    company = get_user_company(request.user)

    entries = JournalEntry.objects.filter(
        journal__company=company, journal__status=Journal.JournalStatus.POSTED
    )

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
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
    company = get_user_company(request.user)
    period_id = request.GET.get("period")
    as_of_date = request.GET.get("as_of_date")

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
        trial_balance = get_trial_balance(period=period, company=company)
        context = {
            "period": period,
            "report_title": f"Balance Sheet - {period}",
        }
    elif as_of_date:
        try:
            from datetime import datetime

            date_obj = datetime.strptime(as_of_date, "%Y-%m-%d").date()
            trial_balance = get_trial_balance(as_of_date=date_obj, company=company)
            context = {
                "as_of_date": as_of_date,
                "report_title": f"Balance Sheet as of {as_of_date}",
            }
        except ValueError:
            messages.error(request, "Invalid date format")
            return redirect("accounting:balance_sheet")
    else:
        trial_balance = get_trial_balance(company=company)
        context = {
            "report_title": "Balance Sheet - Current",
        }

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
    company = get_user_company(request.user)
    period_id = request.GET.get("period")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if period_id:
        period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)
        trial_balance = get_trial_balance(period=period, company=company)
        context = {
            "period": period,
            "report_title": f"Income Statement - {period}",
        }
    elif start_date and end_date:
        trial_balance = get_trial_balance(as_of_date=end_date, company=company)
        context = {
            "start_date": start_date,
            "end_date": end_date,
            "report_title": f"Income Statement - {start_date} to {end_date}",
        }
    else:
        trial_balance = get_trial_balance(company=company)
        context = {
            "report_title": "Income Statement - Current",
        }

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


class JournalReversalInitiationView(LoginRequiredMixin, JournalReversalMixin, FormView):
    """
    View to initiate a journal reversal
    """

    template_name = "accounting/journal_reversal_initiation.html"
    form_class = JournalReversalInitiationForm
    permission_object_model = Journal

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.get_permission_object()
        context["journal"] = journal
        context["entries"] = journal.entries.all().order_by("account__name")
        context["total_debits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.DEBIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        context["total_credits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.CREDIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        return context

    def form_valid(self, form):
        journal = self.get_permission_object()
        reversal_type = form.cleaned_data["reversal_type"]
        reason = form.cleaned_data["reason"]

        self.request.session["reversal_data"] = {
            "journal_id": journal.pk,
            "reversal_type": reversal_type,
            "reason": reason,
        }

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
    permission_object_model = Journal

    def get_form_class(self):
        journal = self.get_permission_object()
        return lambda *args, **kwargs: JournalPartialReversalForm(
            journal.entries.all(), *args, **kwargs
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.get_permission_object()
        entries = journal.entries.all().order_by("account__name")
        context["journal"] = journal
        context["entries"] = entries
        context["total_debits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.DEBIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        context["total_credits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.CREDIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        reversal_data = self.request.session.get("reversal_data", {})
        context["reason"] = reversal_data.get("reason", "")

        return context

    def form_valid(self, form):
        journal = self.get_permission_object()
        reversal_data = self.request.session.get("reversal_data", {})
        reason = reversal_data.get("reason", "")

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
    permission_object_model = Journal

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.get_permission_object()
        context["journal"] = journal
        context["entries"] = journal.entries.all().order_by("account__name")
        context["total_debits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.DEBIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        context["total_credits"] = (
            journal.entries.filter(entry_type=JournalEntry.EntryType.CREDIT).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        reversal_data = self.request.session.get("reversal_data", {})
        context["reason"] = reversal_data.get("reason", "")

        if self.request.POST:
            context["correction_formset"] = CorrectionEntryFormSet(self.request.POST)
        else:
            context["correction_formset"] = CorrectionEntryFormSet()

        return context

    def form_valid(self, form):
        journal = self.get_permission_object()
        reversal_data = self.request.session.get("reversal_data", {})
        reason = reversal_data.get("reason", "")

        context = self.get_context_data()
        correction_formset = context["correction_formset"]

        if correction_formset.is_valid():

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
    permission_object_model = Journal

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journal = self.get_permission_object()
        context["journal"] = journal
        context["entries"] = journal.entries.all().order_by("account__name")

        reversal_data = self.request.session.get("reversal_data", {})
        context["reason"] = reversal_data.get("reason", "")

        return context

    def form_valid(self, form):
        journal = self.get_permission_object()
        reversal_data = self.request.session.get("reversal_data", {})
        original_reason = reversal_data.get("reason", "")
        final_reason = (
            form.cleaned_data.get("final_reason")
            or self.request.POST.get("reason")
            or original_reason
            or "Journal reversal"
        )

        try:
            reversal_journal = reverse_journal(
                journal,
                self.request.user,
                final_reason,
                ip_address=self.request.META.get("REMOTE_ADDR"),
                user_agent=self.request.META.get("HTTP_USER_AGENT"),
            )

            if "reversal_data" in self.request.session:
                del self.request.session["reversal_data"]

            messages.success(self.request, "Journal reversed successfully.")
            return redirect("accounting:journal_detail", pk=reversal_journal.pk)
        except Exception as e:
            messages.error(self.request, f"Error reversing journal: {str(e)}")
            return self.form_invalid(form)


class BatchJournalReversalView(LoginRequiredMixin, AccountingRoleRequiredMixin, FormView):
    """
    View to handle batch journal reversals
    """

    template_name = "accounting/batch_journal_reversal.html"
    form_class = BatchJournalReversalForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

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

        reversal_history = []

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


# ── Bank Reconciliation Views ────────────────────────────────────────────────

class ReconciliationListView(LoginRequiredMixin, AccountingRoleRequiredMixin, ListView):
    model = AccountReconciliation
    template_name = "accounting/reconciliation_list.html"
    context_object_name = "reconciliations"
    paginate_by = 25

    def get_queryset(self):
        company = get_user_company(self.request.user)
        qs = AccountReconciliation.objects.filter(company=company).select_related(
            "account", "period", "approved_by"
        ).prefetch_related("items", "bank_transactions")
        account_id = self.request.GET.get("account")
        if account_id:
            qs = qs.filter(account_id=account_id)
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = get_user_company(self.request.user)
        context["asset_accounts"] = Account.objects.filter(
            company=company, type=Account.AccountType.ASSET, status=Account.AccountStatus.ACTIVE
        )
        return context


class ReconciliationCreateView(LoginRequiredMixin, AccountingRoleRequiredMixin, FormView):
    template_name = "accounting/reconciliation_create.html"

    def get_form_class(self):
        from .forms import ReconciliationCreateForm
        return ReconciliationCreateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = get_user_company(self.request.user)
        return kwargs

    def form_valid(self, form):
        company = get_user_company(self.request.user)
        bank_txs = None
        if form.cleaned_data.get("bank_transactions"):
            bank_txs = form.cleaned_data["bank_transactions"]

        from .utils import create_bank_reconciliation
        recon = create_bank_reconciliation(
            company=company,
            account=form.cleaned_data["account"],
            period=form.cleaned_data.get("period"),
            user=self.request.user,
            bank_transactions_data=bank_txs,
        )
        messages.success(self.request, f"Reconciliation created for {recon.account.name}.")
        return redirect("accounting:reconciliation_detail", pk=recon.pk)


class ReconciliationDetailView(LoginRequiredMixin, AccountingRoleRequiredMixin, DetailView):
    model = AccountReconciliation
    template_name = "accounting/reconciliation_detail.html"
    context_object_name = "reconciliation"

    def get_queryset(self):
        return AccountReconciliation.objects.filter(
            company=get_user_company(self.request.user)
        ).select_related("account", "period", "approved_by").prefetch_related(
            "items__bank_transaction", "items__journal_entry", "bank_transactions"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recon = self.object
        company = get_user_company(self.request.user)

        # Journal entries for the account in this period
        from .utils import get_account_balance_as_of
        context["ledger_entries"] = JournalEntry.objects.filter(
            account=recon.account,
            journal__company=company,
            journal__status=Journal.JournalStatus.POSTED,
        ).select_related("journal").order_by("journal__date")

        if recon.period:
            context["ledger_entries"] = context["ledger_entries"].filter(
                journal__date__gte=recon.period.start_date,
                journal__date__lte=recon.period.end_date,
            )

        context["matched_items"] = recon.items.filter(status="MATCHED")
        context["unmatched_items"] = recon.items.filter(status__startswith="UNMATCHED")
        context["can_approve"] = recon.status in ("OPEN", "INVESTIGATING")
        context["can_match"] = recon.status not in ("APPROVED",)
        return context


class ReconciliationMatchView(LoginRequiredMixin, AccountingRoleRequiredMixin, DetailView):
    model = AccountReconciliation
    template_name = "accounting/reconciliation_match.html"
    context_object_name = "reconciliation"

    def get_queryset(self):
        return AccountReconciliation.objects.filter(
            company=get_user_company(self.request.user)
        ).select_related("account", "period").prefetch_related(
            "bank_transactions", "items"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recon = self.object
        company = get_user_company(self.request.user)

        context["unmatched_bank"] = recon.bank_transactions.filter(is_matched=False)

        # Already matched journal entry IDs
        matched_entry_ids = recon.items.filter(
            journal_entry__isnull=False
        ).values_list("journal_entry_id", flat=True)

        context["ledger_entries"] = JournalEntry.objects.filter(
            account=recon.account,
            journal__company=company,
            journal__status=Journal.JournalStatus.POSTED,
            journal__date__lte=recon.period.end_date if recon.period else timezone.now().date(),
        ).exclude(id__in=matched_entry_ids).select_related("journal").order_by("journal__date")

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        recon = self.object

        matches = []
        bank_tx_ids = request.POST.getlist("bank_transaction")
        entry_ids = request.POST.getlist("journal_entry")
        amounts = request.POST.getlist("amount_matched")
        notes = request.POST.getlist("match_note")

        for i in range(len(bank_tx_ids)):
            if i < len(entry_ids) and entry_ids[i]:
                matches.append({
                    "bank_transaction_id": int(bank_tx_ids[i]),
                    "journal_entry_id": int(entry_ids[i]),
                    "amount_matched": Decimal(amounts[i]) if i < len(amounts) else None,
                    "note": notes[i] if i < len(notes) else "",
                })

        if not matches:
            messages.warning(request, "No matches selected.")
            return redirect("accounting:reconciliation_match", pk=recon.pk)

        from .utils import match_reconciliation_items
        match_reconciliation_items(recon, matches)
        messages.success(request, f"Matched {len(matches)} transactions.")
        return redirect("accounting:reconciliation_detail", pk=recon.pk)


@login_required
def reconciliation_approve(request, pk):
    recon = get_object_or_404(
        AccountReconciliation.objects.filter(company=get_user_company(request.user)),
        pk=pk,
    )
    if request.method == "POST":
        from .utils import approve_reconciliation
        approve_reconciliation(recon, request.user)
        messages.success(request, "Reconciliation approved.")
        return redirect("accounting:reconciliation_detail", pk=recon.pk)
    return render(request, "accounting/reconciliation_approve.html", {"reconciliation": recon})


@login_required
def reconciliation_import(request):
    """Import bank transactions from CSV for a given account."""
    company = get_user_company(request.user)

    if request.method == "POST":
        from .forms import BankTransactionImportForm
        form = BankTransactionImportForm(request.POST, request.FILES, company=company)
        if form.is_valid():
            account = form.cleaned_data["account"]
            period = form.cleaned_data.get("period")
            txs = form.get_bank_transactions()
            from .utils import create_bank_reconciliation
            recon = create_bank_reconciliation(
                company=company, account=account, period=period,
                user=request.user, bank_transactions_data=txs,
            )
            messages.success(request, f"Imported {len(txs)} bank transactions for {account.name}.")
            return redirect("accounting:reconciliation_detail", pk=recon.pk)
    else:
        from .forms import BankTransactionImportForm
        form = BankTransactionImportForm(company=company)

    return render(request, "accounting/reconciliation_import.html", {"form": form})


@login_required
@auditor_or_accountant_required
def queue_async_report(request, report_type):
    """Queue a financial report for async generation."""
    company = get_user_company(request.user)

    if report_type not in ("trial_balance", "balance_sheet", "income_statement", "general_ledger"):
        messages.error(request, "Invalid report type.")
        return redirect("accounting:reports")

    if request.method == "POST":
        period_id = request.POST.get("period") or None
        as_of_date = request.POST.get("as_of_date") or None

        period = None
        if period_id:
            from accounting.models import AccountingPeriod
            period = get_object_or_404(AccountingPeriod, pk=period_id, company=company)

        from accounting.models import FinancialReportJob
        job = FinancialReportJob.objects.create(
            company=company,
            user=request.user,
            report_type=report_type.upper(),
            period=period,
            as_of_date=as_of_date if as_of_date else None,
        )
        job.enqueue()
        messages.success(request, f"{report_type.replace('_', ' ').title()} is being generated. Check back shortly.")
        return redirect("accounting:report_job_status", pk=job.pk)

    periods = AccountingPeriod.objects.filter(company=company).order_by("-end_date")
    return render(request, "accounting/reports/queue_report.html", {
        "report_type": report_type,
        "periods": periods,
    })


@login_required
@auditor_or_accountant_required
def report_job_list(request):
    """List all async report jobs for the current company."""
    company = get_user_company(request.user)
    from accounting.models import FinancialReportJob
    jobs = FinancialReportJob.objects.filter(company=company).select_related("user", "period").order_by("-queued_at")[:50]
    return render(request, "accounting/reports/report_jobs.html", {"jobs": jobs})


@login_required
@auditor_or_accountant_required
def report_job_status(request, pk):
    """View status of an async report job."""
    company = get_user_company(request.user)
    from accounting.models import FinancialReportJob
    job = get_object_or_404(FinancialReportJob.objects.filter(company=company), pk=pk)
    return render(request, "accounting/reports/report_job_status.html", {"job": job})


@login_required
@auditor_or_accountant_required
def report_job_download(request, pk):
    """Download a completed report PDF."""
    company = get_user_company(request.user)
    from accounting.models import FinancialReportJob
    job = get_object_or_404(FinancialReportJob.objects.filter(company=company), pk=pk)

    if job.status != "completed" or not job.output_file:
        messages.error(request, "Report is not ready for download.")
        return redirect("accounting:report_job_status", pk=job.pk)

    import os
    if not os.path.exists(job.output_file):
        messages.error(request, "Report file no longer available. Please regenerate.")
        return redirect("accounting:report_job_status", pk=job.pk)

    from django.http import FileResponse
    response = FileResponse(open(job.output_file, "rb"), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="paroll_{job.report_type.lower()}_{job.company_id}.pdf"'
    )
    return response


# ── Phase 1: Budget Management ──


@login_required
@accounting_role_required
def budget_list(request):
    company = get_user_company(request.user)
    budgets = Budget.objects.filter(company=company).select_related("fiscal_year")
    return render(request, "accounting/budget_list.html", {"budgets": budgets, "page_title": "Budgets"})


@login_required
@accountant_required
def budget_create(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        form = BudgetForm(request.POST, company=company)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.company = company
            budget.save()
            messages.success(request, "Budget created.")
            return redirect("accounting:budget_detail", pk=budget.pk)
    else:
        form = BudgetForm(company=company)
    return render(request, "accounting/budget_form.html", {"form": form, "page_title": "New Budget"})


@login_required
@accounting_role_required
def budget_detail(request, pk):
    company = get_user_company(request.user)
    budget = get_object_or_404(Budget.objects.filter(company=company).select_related("fiscal_year"), pk=pk)
    lines = budget.lines.select_related("account", "period").order_by("account__account_number")
    return render(request, "accounting/budget_detail.html", {"budget": budget, "lines": lines, "page_title": f"Budget: {budget.name}"})


@login_required
@accountant_required
def budget_line_create(request, budget_pk):
    company = get_user_company(request.user)
    budget = get_object_or_404(Budget.objects.filter(company=company), pk=budget_pk)
    if request.method == "POST":
        form = BudgetLineForm(request.POST, company=company)
        if form.is_valid():
            line = form.save(commit=False)
            line.budget = budget
            line.save()
            messages.success(request, "Budget line added.")
            return redirect("accounting:budget_detail", pk=budget.pk)
    else:
        form = BudgetLineForm(company=company)
    return render(request, "accounting/budget_line_form.html", {"form": form, "budget": budget, "page_title": "Add Budget Line"})


@login_required
@accounting_role_required
def budget_vs_actual_report(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        form = BudgetVsActualForm(request.POST, company=company)
        if form.is_valid():
            fiscal_year = form.cleaned_data["fiscal_year"]
            period = form.cleaned_data.get("period")
            budget_lines = BudgetLine.objects.filter(
                budget__company=company, budget__fiscal_year=fiscal_year
            ).select_related("account", "period")
            report_data = []
            for bl in budget_lines:
                actual = JournalEntry.objects.filter(
                    account=bl.account,
                    journal__company=company,
                    journal__status="POSTED",
                )
                if period:
                    actual = actual.filter(journal__date__gte=period.start_date, journal__date__lte=period.end_date)
                else:
                    actual = actual.filter(journal__date__gte=fiscal_year.start_date, journal__date__lte=fiscal_year.end_date)
                actual_amount = actual.aggregate(
                    debits=Sum("amount", filter=Q(entry_type="DEBIT")),
                    credits=Sum("amount", filter=Q(entry_type="CREDIT")),
                )
                actual_total = (actual_amount["debits"] or Decimal("0")) - (actual_amount["credits"] or Decimal("0"))
                variance = actual_total - bl.amount
                report_data.append({
                    "account": bl.account,
                    "period": bl.period,
                    "budget_amount": bl.amount,
                    "actual_amount": actual_total,
                    "variance": variance,
                    "variance_pct": ((variance / bl.amount * 100) if bl.amount else Decimal("0")),
                })
            return render(request, "accounting/budget_vs_actual.html", {
                "report_data": report_data,
                "fiscal_year": fiscal_year,
                "period": period,
                "page_title": "Budget vs Actual",
            })
    else:
        form = BudgetVsActualForm(company=company)
    return render(request, "accounting/budget_vs_actual_form.html", {"form": form, "page_title": "Budget vs Actual Report"})


# ── Phase 2: Cost Center & Accrual Management ──


@login_required
@accounting_role_required
def cost_center_list(request):
    company = get_user_company(request.user)
    centers = CostCenter.objects.filter(company=company)
    return render(request, "accounting/cost_center_list.html", {"centers": centers, "page_title": "Cost Centers"})


@login_required
@accountant_required
def cost_center_create(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        form = CostCenterForm(request.POST)
        if form.is_valid():
            cc = form.save(commit=False)
            cc.company = company
            cc.save()
            messages.success(request, "Cost center created.")
            return redirect("accounting:cost_center_list")
    else:
        form = CostCenterForm()
    return render(request, "accounting/cost_center_form.html", {"form": form, "page_title": "New Cost Center"})


@login_required
@accountant_required
def cost_center_update(request, pk):
    company = get_user_company(request.user)
    cc = get_object_or_404(CostCenter.objects.filter(company=company), pk=pk)
    if request.method == "POST":
        form = CostCenterForm(request.POST, instance=cc)
        if form.is_valid():
            form.save()
            messages.success(request, "Cost center updated.")
            return redirect("accounting:cost_center_list")
    else:
        form = CostCenterForm(instance=cc)
    return render(request, "accounting/cost_center_form.html", {"form": form, "page_title": "Update Cost Center"})


@login_required
@accounting_role_required
def accrual_template_list(request):
    company = get_user_company(request.user)
    templates = AccrualTemplate.objects.filter(company=company).select_related("debit_account", "credit_account")
    return render(request, "accounting/accrual_list.html", {"templates": templates, "page_title": "Accrual Templates"})


@login_required
@accountant_required
def accrual_template_create(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        form = AccrualTemplateForm(request.POST, company=company)
        if form.is_valid():
            accrual = form.save(commit=False)
            accrual.company = company
            accrual.save()
            messages.success(request, "Accrual template created.")
            return redirect("accounting:accrual_template_list")
    else:
        form = AccrualTemplateForm(company=company)
    return render(request, "accounting/accrual_form.html", {"form": form, "page_title": "New Accrual Template"})


@login_required
@accountant_required
def post_accrual(request, pk):
    company = get_user_company(request.user)
    accrual = get_object_or_404(AccrualTemplate.objects.filter(company=company), pk=pk)
    if request.method == "POST":
        try:
            period = AccountingPeriod.objects.filter(company=company, is_active=True).first()
            journal = create_journal_with_entries(
                company=company,
                date=timezone.now().date(),
                description=f"Accrual: {accrual.name}",
                entries=[
                    {"account": accrual.debit_account, "entry_type": "DEBIT", "amount": accrual.amount, "memo": accrual.name},
                    {"account": accrual.credit_account, "entry_type": "CREDIT", "amount": accrual.amount, "memo": accrual.name},
                ],
                auto_post=True,
            )
            messages.success(request, f"Accrual journal {journal.transaction_number} posted.")
        except Exception as exc:
            messages.error(request, str(exc))
    return redirect("accounting:accrual_template_list")


# ── Phase 3: Exchange Rate & FX Revaluation ──


@login_required
@accounting_role_required
def exchange_rate_list(request):
    company = get_user_company(request.user)
    rates = ExchangeRate.objects.filter(company=company).order_by("-rate_date", "quote_currency")
    return render(request, "accounting/exchange_rate_list.html", {"rates": rates, "page_title": "Exchange Rates"})


@login_required
@accountant_required
def exchange_rate_create(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        form = ExchangeRateForm(request.POST)
        if form.is_valid():
            rate = form.save(commit=False)
            rate.company = company
            rate.save()
            messages.success(request, "Exchange rate created.")
            return redirect("accounting:exchange_rate_list")
    else:
        form = ExchangeRateForm()
    return render(request, "accounting/exchange_rate_form.html", {"form": form, "page_title": "New Exchange Rate"})


@login_required
@accounting_role_required
def revaluation_list(request):
    company = get_user_company(request.user)
    revaluations = CurrencyRevaluation.objects.filter(company=company).select_related("journal", "created_by")
    return render(request, "accounting/revaluation_list.html", {"revaluations": revaluations, "page_title": "Currency Revaluations"})


@login_required
@accountant_required
def revaluation_create(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        form = CurrencyRevaluationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            revaluation = CurrencyRevaluation.objects.create(
                company=company,
                revaluation_date=data["revaluation_date"],
                base_currency=data["base_currency"],
                memo=data.get("memo", ""),
                created_by=request.user,
            )
            messages.success(request, "Revaluation created. Post journal to finalize.")
            return redirect("accounting:revaluation_list")
    else:
        form = CurrencyRevaluationForm()
    return render(request, "accounting/revaluation_form.html", {"form": form, "page_title": "New Currency Revaluation"})


# ── Phase 4: Tax Return Management ──


@login_required
@accounting_role_required
def tax_return_list(request):
    company = get_user_company(request.user)
    returns = TaxReturn.objects.filter(company=company).select_related("period", "filed_by")
    return render(request, "accounting/tax_return_list.html", {"returns": returns, "page_title": "Tax Returns"})


@login_required
@accountant_required
def tax_return_create(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        form = TaxReturnForm(request.POST, company=company)
        if form.is_valid():
            ret = form.save(commit=False)
            ret.company = company
            ret.save()
            messages.success(request, "Tax return created.")
            return redirect("accounting:tax_return_detail", pk=ret.pk)
    else:
        form = TaxReturnForm(company=company)
    return render(request, "accounting/tax_return_form.html", {"form": form, "page_title": "New Tax Return"})


@login_required
@accounting_role_required
def tax_return_detail(request, pk):
    company = get_user_company(request.user)
    ret = get_object_or_404(TaxReturn.objects.filter(company=company).select_related("period", "filed_by"), pk=pk)
    lines = ret.lines.select_related("account", "tax_account")
    return render(request, "accounting/tax_return_detail.html", {"return": ret, "lines": lines, "page_title": f"Tax Return: {ret.get_return_type_display()}"})


@login_required
@accountant_required
def tax_return_line_create(request, return_pk):
    company = get_user_company(request.user)
    ret = get_object_or_404(TaxReturn.objects.filter(company=company), pk=return_pk)
    if request.method == "POST":
        form = TaxReturnLineForm(request.POST, company=company)
        if form.is_valid():
            line = form.save(commit=False)
            line.tax_return = ret
            line.tax_amount = (line.gross_amount * line.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
            line.save()
            ret.total_taxable += line.gross_amount
            ret.total_tax += line.tax_amount
            ret.net_tax_payable = ret.total_tax - ret.total_input_tax
            ret.save(update_fields=["total_taxable", "total_tax", "net_tax_payable", "updated_at"])
            messages.success(request, "Tax return line added.")
            return redirect("accounting:tax_return_detail", pk=ret.pk)
    else:
        form = TaxReturnLineForm(company=company)
    return render(request, "accounting/tax_return_line_form.html", {"form": form, "return": ret, "page_title": "Add Tax Return Line"})


@login_required
@accountant_required
def tax_return_file(request, pk):
    company = get_user_company(request.user)
    ret = get_object_or_404(TaxReturn.objects.filter(company=company), pk=pk)
    if request.method == "POST":
        ret.status = TaxReturn.Status.FILED
        ret.filed_by = request.user
        ret.filed_at = timezone.now()
        ret.filing_reference = request.POST.get("filing_reference", "")
        ret.save(update_fields=["status", "filed_by", "filed_at", "filing_reference", "updated_at"])
        messages.success(request, "Tax return marked as filed.")
    return redirect("accounting:tax_return_detail", pk=pk)


# ── Phase 5: Journal Attachments & Recurring Journals ──


@login_required
@accounting_role_required
def journal_attachment_upload(request, journal_pk):
    company = get_user_company(request.user)
    journal = get_object_or_404(Journal.objects.filter(company=company), pk=journal_pk)
    if request.method == "POST":
        form = JournalAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data["file"]
            JournalAttachment.objects.create(
                company=company,
                journal=journal,
                file=uploaded_file,
                original_filename=uploaded_file.name,
                description=form.cleaned_data.get("description", ""),
                uploaded_by=request.user,
            )
            messages.success(request, "Attachment uploaded.")
    return redirect("accounting:journal_detail", pk=journal.pk)


@login_required
@accounting_role_required
def journal_attachment_download(request, pk):
    company = get_user_company(request.user)
    attachment = get_object_or_404(JournalAttachment.objects.filter(company=company), pk=pk)
    from django.http import FileResponse
    return FileResponse(attachment.file.open("rb"), as_attachment=True, filename=attachment.original_filename)


@login_required
@accounting_role_required
def recurring_template_list(request):
    company = get_user_company(request.user)
    templates = RecurringJournalTemplate.objects.filter(company=company).select_related("debit_account", "credit_account")
    return render(request, "accounting/recurring_list.html", {"templates": templates, "page_title": "Recurring Journal Templates"})


@login_required
@accountant_required
def recurring_template_create(request):
    company = get_user_company(request.user)
    if request.method == "POST":
        form = RecurringJournalTemplateForm(request.POST, company=company)
        if form.is_valid():
            template = form.save(commit=False)
            template.company = company
            template.save()
            messages.success(request, "Recurring template created.")
            return redirect("accounting:recurring_template_list")
    else:
        form = RecurringJournalTemplateForm(company=company)
    return render(request, "accounting/recurring_form.html", {"form": form, "page_title": "New Recurring Template"})


# ── Phase 6: Account Tree & Report Enhancements ──


@login_required
@accounting_role_required
def account_tree(request):
    company = get_user_company(request.user)
    accounts = Account.objects.filter(company=company).order_by("account_number")
    account_map = {}
    for acc in accounts:
        account_map[acc.pk] = {"account": acc, "children": []}
    tree = []
    for acc in accounts:
        node = account_map[acc.pk]
        if acc.parent_account_id and acc.parent_account_id in account_map:
            account_map[acc.parent_account_id]["children"].append(node)
        else:
            tree.append(node)
    return render(request, "accounting/account_tree.html", {"tree": tree, "page_title": "Chart of Accounts Tree"})
