from django.db import models
from django.db.models import Sum, Q
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.auth import get_user_model
from django.db import transaction
from django.apps import apps
from datetime import date, timedelta
from decimal import Decimal
import json

User = get_user_model()


def _get_default_company_fallback():
    if not getattr(settings, "ALLOW_DEFAULT_COMPANY_FALLBACK", False):
        raise ValidationError("A company is required; default company fallback is disabled.")
    Company = apps.get_model("company", "Company")
    company, _ = Company.objects.get_or_create(name="Default Company")
    return company


class BaseModel(models.Model):
    """Abstract base model to include common fields like timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        abstract = True


class CostCenter(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="cost_centers"
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_cost_center_company_code"
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Account(BaseModel):
    class AccountType(models.TextChoices):
        ASSET = "ASSET", _("Asset")
        LIABILITY = "LIABILITY", _("Liability")
        EQUITY = "EQUITY", _("Equity")
        REVENUE = "REVENUE", _("Revenue")
        EXPENSE = "EXPENSE", _("Expense")

    class AccountStatus(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        INACTIVE = "INACTIVE", _("Inactive")
        RESTRICTED = "RESTRICTED", _("Restricted")

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="accounts"
    )
    parent_account = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="child_accounts",
    )
    name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=20, null=True, blank=True)
    type = models.CharField(max_length=10, choices=AccountType.choices)
    status = models.CharField(
        max_length=12, choices=AccountStatus.choices, default=AccountStatus.ACTIVE
    )
    currency = models.CharField(max_length=3, default="NGN")
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="accounts",
    )
    account_segment_code = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True, null=True)
    current_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return f"{self.account_number} - {self.name}"

    def get_balance(self, cached=True):
        if cached and self.pk:
            return self.current_balance
        debits = (
            self.entries.filter(entry_type="DEBIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )
        credits = (
            self.entries.filter(entry_type="CREDIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )

        if self.type in [self.AccountType.ASSET, self.AccountType.EXPENSE]:
            return debits - credits
        else:  # Liability, Equity, Revenue
            return credits - debits

    def recompute_balance(self):
        self.current_balance = self.get_balance(cached=False)
        self.save(update_fields=["current_balance", "updated_at"])
        return self.current_balance

    @property
    def balance(self):
        return self.get_balance()

    def clean(self):
        if self.parent_account_id and self.parent_account.company_id != self.company_id:
            raise ValidationError("Parent account must belong to the same company")
        if self.cost_center_id and self.cost_center.company_id != self.company_id:
            raise ValidationError("Cost center must belong to the same company")
        if self.currency and len(self.currency) != 3:
            raise ValidationError("Currency must be a 3-letter ISO 4217 code")
        self.currency = (self.currency or "NGN").upper()

    def save(self, *args, **kwargs):
        if not self.company_id:
            self.company = _get_default_company_fallback()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Accounts"
        ordering = ["account_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_account_company_name"
            ),
            models.UniqueConstraint(
                fields=["company", "account_number"],
                name="uniq_account_company_account_number",
            ),
        ]


class ExchangeRate(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="exchange_rates"
    )
    base_currency = models.CharField(max_length=3, default="NGN")
    quote_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    rate_date = models.DateField()
    source = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-rate_date", "quote_currency"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "base_currency", "quote_currency", "rate_date"],
                name="uniq_exchange_rate_company_pair_date",
            )
        ]

    def clean(self):
        self.base_currency = (self.base_currency or "NGN").upper()
        self.quote_currency = (self.quote_currency or "").upper()
        if len(self.base_currency) != 3 or len(self.quote_currency) != 3:
            raise ValidationError("Currencies must be 3-letter ISO 4217 codes")
        if self.rate <= 0:
            raise ValidationError("Exchange rate must be positive")


class CurrencyRevaluation(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        POSTED = "POSTED", _("Posted")
        REVERSED = "REVERSED", _("Reversed")

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="currency_revaluations"
    )
    revaluation_date = models.DateField()
    base_currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    journal = models.ForeignKey(
        "Journal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="currency_revaluations",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_revaluations",
    )
    memo = models.TextField(blank=True)

    class Meta:
        ordering = ["-revaluation_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "revaluation_date", "base_currency"],
                name="uniq_reval_company_date_currency",
            )
        ]

    def __str__(self):
        return f"FX Revaluation {self.revaluation_date} ({self.base_currency})"


class CurrencyRevaluationLine(BaseModel):
    revaluation = models.ForeignKey(
        CurrencyRevaluation, on_delete=models.CASCADE, related_name="lines"
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="revaluation_lines"
    )
    foreign_currency = models.CharField(max_length=3)
    balance_fc = models.DecimalField(max_digits=18, decimal_places=2)
    rate_at_original = models.DecimalField(max_digits=18, decimal_places=8)
    rate_at_revaluation = models.DecimalField(max_digits=18, decimal_places=8)
    base_value_original = models.DecimalField(max_digits=18, decimal_places=2)
    base_value_revalued = models.DecimalField(max_digits=18, decimal_places=2)
    unrealized_gain_loss = models.DecimalField(max_digits=18, decimal_places=2)
    entry_type = models.CharField(max_length=10, choices=[("DEBIT", "Debit"), ("CREDIT", "Credit")])

    class Meta:
        ordering = ["account__account_number"]

    def __str__(self):
        return f"{self.account} - {self.foreign_currency} {self.balance_fc}"


class PostingRule(BaseModel):
    class DocumentType(models.TextChoices):
        OPENING_STOCK = "OPENING_STOCK", _("Opening Stock")
        PURCHASE_RECEIPT = "PURCHASE_RECEIPT", _("Purchase Receipt")
        SALES_INVOICE = "SALES_INVOICE", _("Sales Invoice")
        CUSTOMER_RETURN = "CUSTOMER_RETURN", _("Customer Return")
        SUPPLIER_RETURN = "SUPPLIER_RETURN", _("Supplier Return")
        CUSTOMER_PAYMENT = "CUSTOMER_PAYMENT", _("Customer Payment")
        SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT", _("Supplier Payment")
        TAX_REMITTANCE = "TAX_REMITTANCE", _("Tax Remittance")
        ADJUSTMENT = "ADJUSTMENT", _("Adjustment")
        TRANSFER = "TRANSFER", _("Transfer")
        STOCK_COUNT = "STOCK_COUNT", _("Stock Count")
        SALES_ORDER = "SALES_ORDER", _("Sales Order")
        VENDOR_BILL = "VENDOR_BILL", _("Vendor Bill")
        LANDED_COST = "LANDED_COST", _("Landed Cost")
        SHIPMENT = "SHIPMENT", _("Shipment")

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="posting_rules"
    )
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    account_role = models.CharField(max_length=80)
    expected_account_type = models.CharField(max_length=10, choices=Account.AccountType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["document_type", "account_role"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "document_type", "account_role"],
                name="uniq_posting_rule_company_document_role",
            )
        ]


class PostingValidationFailure(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="posting_validation_failures"
    )
    document_type = models.CharField(max_length=30)
    account_role = models.CharField(max_length=80)
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posting_validation_failures",
    )
    message = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.document_type}:{self.account_role} - {self.message}"


class AccrualTemplate(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="accrual_templates"
    )
    name = models.CharField(max_length=160)
    debit_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="accrual_templates_as_debit"
    )
    credit_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="accrual_templates_as_credit"
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]


class FinancialReportJob(BaseModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class ReportType(models.TextChoices):
        TRIAL_BALANCE = "TRIAL_BALANCE", "Trial Balance"
        BALANCE_SHEET = "BALANCE_SHEET", "Balance Sheet"
        INCOME_STATEMENT = "INCOME_STATEMENT", "Income Statement"
        GENERAL_LEDGER = "GENERAL_LEDGER", "General Ledger"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="financial_report_jobs"
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="report_jobs"
    )
    report_type = models.CharField(max_length=30, choices=ReportType.choices)
    period = models.ForeignKey(
        "AccountingPeriod",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_jobs",
    )
    as_of_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    celery_task_id = models.CharField(max_length=255, blank=True)
    output_file = models.CharField(max_length=500, blank=True)
    error_message = models.TextField(blank=True)
    queued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-queued_at"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["status", "queued_at"]),
        ]

    def __str__(self):
        return f"{self.get_report_type_display()} - {self.get_status_display()}"

    def enqueue(self):
        from accounting.tasks.report_tasks import generate_financial_report_task

        result = generate_financial_report_task.apply_async(
            args=[self.id],
            queue="notifications_normal",
        )
        self.status = self.Status.QUEUED
        self.celery_task_id = result.id or ""
        self.save(update_fields=["status", "celery_task_id", "updated_at"])
        return result


class TaxReturn(BaseModel):
    class ReturnType(models.TextChoices):
        VAT = "VAT", "Value Added Tax"
        WHT = "WHT", "Withholding Tax"
        PAYE = "PAYE", "PAYE Income Tax"
        PENSION = "PENSION", "Pension Contribution"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        FILED = "FILED", "Filed"
        AMENDED = "AMENDED", "Amended"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="tax_returns"
    )
    return_type = models.CharField(max_length=20, choices=ReturnType.choices)
    period = models.ForeignKey(
        "AccountingPeriod",
        on_delete=models.PROTECT,
        related_name="tax_returns",
    )
    jurisdiction_code = models.CharField(max_length=40, default="NG-FIRS")
    return_period_start = models.DateField()
    return_period_end = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_taxable = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_tax = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_input_tax = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    net_tax_payable = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    filed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="filed_tax_returns"
    )
    filed_at = models.DateTimeField(null=True, blank=True)
    filing_reference = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-return_period_end", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "return_type", "return_period_start", "return_period_end"],
                name="uniq_tax_return_company_type_period",
            )
        ]

    def __str__(self):
        return f"{self.get_return_type_display()} Return — {self.return_period_start} to {self.return_period_end}"


class TaxReturnLine(BaseModel):
    tax_return = models.ForeignKey(TaxReturn, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="tax_return_lines")
    tax_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True,
        related_name="tax_return_tax_lines",
    )
    gross_amount = models.DecimalField(max_digits=18, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2)
    line_description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["account__account_number"]

    def __str__(self):
        return f"{self.account} — Tax {self.tax_amount}"


class Budget(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="budgets"
    )
    fiscal_year = models.ForeignKey(
        "FiscalYear", on_delete=models.PROTECT, related_name="budgets"
    )
    name = models.CharField(max_length=160)
    status = models.CharField(
        max_length=20,
        choices=[("DRAFT", "Draft"), ("APPROVED", "Approved"), ("CLOSED", "Closed")],
        default="DRAFT",
    )

    class Meta:
        ordering = ["-fiscal_year__year", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "fiscal_year", "name"],
                name="uniq_budget_company_fiscal_year_name",
            )
        ]


class BudgetLine(BaseModel):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="budget_lines")
    period = models.ForeignKey(
        "AccountingPeriod",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="budget_lines",
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "account", "period"], name="uniq_budget_line_account_period"
            )
        ]


class AccountReconciliation(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="account_reconciliations"
    )
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="reconciliations")
    period = models.ForeignKey(
        "AccountingPeriod",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="account_reconciliations",
    )
    statement_balance = models.DecimalField(max_digits=18, decimal_places=2)
    ledger_balance = models.DecimalField(max_digits=18, decimal_places=2)
    variance = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=[("OPEN", "Open"), ("INVESTIGATING", "Investigating"), ("APPROVED", "Approved")],
        default="OPEN",
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_reconciliations"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Reconciliation {self.account} - {self.period or 'N/A'}"


class BankTransaction(models.Model):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="bank_transactions"
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="bank_transactions"
    )
    transaction_date = models.DateField()
    description = models.CharField(max_length=255)
    reference = models.CharField(max_length=80, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    transaction_type = models.CharField(
        max_length=10, choices=[("DEBIT", "Debit"), ("CREDIT", "Credit")]
    )
    is_matched = models.BooleanField(default=False)
    reconciliation = models.ForeignKey(
        AccountReconciliation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_transactions",
    )

    class Meta:
        ordering = ["transaction_date", "-amount"]

    def __str__(self):
        return f"{self.transaction_date} {self.description} {self.amount}"


class ReconciliationItem(models.Model):
    reconciliation = models.ForeignKey(
        AccountReconciliation, on_delete=models.CASCADE, related_name="items"
    )
    bank_transaction = models.ForeignKey(
        BankTransaction, on_delete=models.PROTECT, related_name="reconciliation_items"
    )
    journal_entry = models.ForeignKey(
        "JournalEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reconciliation_items",
    )
    amount_matched = models.DecimalField(max_digits=18, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("MATCHED", "Matched"), ("UNMATCHED_BANK", "Unmatched (Bank)"), ("UNMATCHED_LEDGER", "Unmatched (Ledger)")],
        default="MATCHED",
    )

    class Meta:
        ordering = ["bank_transaction__transaction_date"]

    def __str__(self):
        return f"{self.bank_transaction} → {self.journal_entry or 'unmatched'}"


class FinancialReportDefinition(BaseModel):
    class ReportType(models.TextChoices):
        PROFIT_LOSS = "PROFIT_LOSS", _("Profit and Loss")
        BALANCE_SHEET = "BALANCE_SHEET", _("Balance Sheet")
        CUSTOM = "CUSTOM", _("Custom Report")

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        related_name="financial_report_definitions",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=40)
    report_type = models.CharField(
        max_length=20,
        choices=ReportType.choices,
        default=ReportType.PROFIT_LOSS,
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"],
                name="uniq_financial_report_company_code",
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class FinancialReportLine(BaseModel):
    class LineType(models.TextChoices):
        HEADING = "HEADING", _("Heading")
        ACCOUNT_SUM = "ACCOUNT_SUM", _("Account Sum")
        FORMULA = "FORMULA", _("Formula")

    report = models.ForeignKey(
        FinancialReportDefinition,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    line_number = models.PositiveIntegerField()
    row_code = models.CharField(max_length=40)
    label = models.CharField(max_length=255)
    line_type = models.CharField(
        max_length=20,
        choices=LineType.choices,
        default=LineType.ACCOUNT_SUM,
    )
    accounts = models.ManyToManyField(
        Account,
        blank=True,
        related_name="financial_report_lines",
    )
    formula = models.CharField(
        max_length=255,
        blank=True,
        help_text="Use row codes with + and - operators, for example REV-COGS.",
    )
    invert_sign = models.BooleanField(
        default=False,
        help_text="Display this line as the opposite sign for contribution-style reports.",
    )
    show_zero = models.BooleanField(default=True)

    class Meta:
        ordering = ["line_number", "row_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["report", "line_number"],
                name="uniq_financial_report_line_number",
            ),
            models.UniqueConstraint(
                fields=["report", "row_code"],
                name="uniq_financial_report_row_code",
            ),
        ]

    @property
    def company(self):
        return self.report.company

    def __str__(self):
        return f"{self.report.code} {self.row_code} - {self.label}"


class FiscalYear(BaseModel):
    """Represents a fiscal year for accounting purposes"""

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="fiscal_years"
    )
    year = models.PositiveIntegerField()
    name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_fiscal_years",
    )

    class Meta:
        ordering = ["-year"]
        verbose_name = "Fiscal Year"
        verbose_name_plural = "Fiscal Years"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "year"], name="uniq_fiscal_year_company_year"
            )
        ]

    def __str__(self):
        return f"FY {self.year} ({self.name})"

    def save(self, *args, **kwargs):
        if not self.company_id:
            self.company = _get_default_company_fallback()
        super().save(*args, **kwargs)

    def clean(self):
        if not self.company_id:
            self.company = _get_default_company_fallback()
        if self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")

        # Check for overlapping fiscal years
        overlapping = FiscalYear.objects.filter(
            models.Q(start_date__lte=self.end_date)
            & models.Q(end_date__gte=self.start_date),
            company=self.company,
        ).exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError("Fiscal year dates overlap with existing fiscal year")

    def close(self, user):
        """Close fiscal year"""
        if self.is_closed:
            raise ValidationError("Fiscal year is already closed")

        # Check if all periods are closed
        if self.periods.filter(is_closed=False).exists():
            raise ValidationError("Cannot close fiscal year with open periods")

        self.is_closed = True
        self.closed_at = timezone.now()
        self.closed_by = user
        self.save()

        # Signal will automatically log the closure through signal handlers


class AccountingPeriod(BaseModel):
    """Represents an accounting period within a fiscal year"""

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.CASCADE, related_name="periods"
    )
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="accounting_periods"
    )
    period_number = models.PositiveIntegerField()
    name = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_periods",
    )

    class Meta:
        ordering = ["fiscal_year", "period_number"]
        verbose_name = "Accounting Period"
        verbose_name_plural = "Accounting Periods"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "fiscal_year", "period_number"],
                name="uniq_period_company_fiscal_year_number",
            )
        ]

    def __str__(self):
        return f"{self.fiscal_year.name} - Period {self.period_number} ({self.name})"

    def save(self, *args, **kwargs):
        if self.fiscal_year_id and not self.company_id:
            self.company = self.fiscal_year.company
        super().save(*args, **kwargs)

    def clean(self):
        if self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")

        if self.fiscal_year_id and self.company_id != self.fiscal_year.company_id:
            raise ValidationError("Period company must match fiscal year company")

        # Check if period is within fiscal year dates
        if (
            self.start_date < self.fiscal_year.start_date
            or self.end_date > self.fiscal_year.end_date
        ):
            raise ValidationError("Period dates must be within fiscal year dates")

        # Check for overlapping periods within the same fiscal year
        overlapping = AccountingPeriod.objects.filter(
            models.Q(start_date__lte=self.end_date)
            & models.Q(end_date__gte=self.start_date),
            company=self.company,
            fiscal_year=self.fiscal_year,
        ).exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError(
                "Period dates overlap with existing period in the same fiscal year"
            )

    def close(self, user):
        """Close accounting period"""
        if self.is_closed:
            raise ValidationError("Accounting period is already closed")

        # Add any period closing logic here
        self.is_closed = True
        self.closed_at = timezone.now()
        self.closed_by = user
        self.save()

        # Signal will automatically log the closure through signal handlers


class TransactionNumber(BaseModel):
    """Manages automatic transaction numbering"""

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.CASCADE, related_name="transaction_numbers"
    )
    prefix = models.CharField(max_length=10, default="TXN")
    current_number = models.PositiveIntegerField(default=1)
    padding = models.PositiveIntegerField(default=6)

    class Meta:
        unique_together = ["fiscal_year", "prefix"]
        verbose_name = "Transaction Number"
        verbose_name_plural = "Transaction Numbers"

    def __str__(self):
        return f"{self.prefix} for {self.fiscal_year.name}"

    @classmethod
    def get_next_number(cls, fiscal_year, prefix="TXN"):
        """Get next globally unique transaction number for this fiscal year/prefix."""
        JournalModel = cls._meta.apps.get_model("accounting", "Journal")

        with transaction.atomic():
            txn_number, created = cls.objects.select_for_update().get_or_create(
                fiscal_year=fiscal_year, prefix=prefix, defaults={"current_number": 1}
            )

            next_number = txn_number.current_number
            formatted_number = f"{prefix}{str(next_number).zfill(txn_number.padding)}"

            # transaction_number is globally unique on Journal, so back-posting older
            # periods can collide with numbers already issued in a different fiscal year.
            while JournalModel.objects.filter(
                transaction_number=formatted_number
            ).exists():
                next_number += 1
                formatted_number = f"{prefix}{str(next_number).zfill(txn_number.padding)}"

            txn_number.current_number = next_number + 1
            txn_number.save()

        return formatted_number


class AccountingAuditTrail(BaseModel):
    """Enhanced audit trail for accounting transactions"""

    class ActionType(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        APPROVE = "APPROVE", "Approve"
        REJECT = "REJECT", "Reject"
        POST = "POST", "Post"
        REVERSE = "REVERSE", "Reverse"
        CLOSE_PERIOD = "CLOSE_PERIOD", "Close Period"
        CLOSE_FISCAL_YEAR = "CLOSE_FISCAL_YEAR", "Close Fiscal Year"
        FX_REVALUATION = "FX_REVALUATION", "FX Revaluation"
        FX_REVALUATION_REVERSE = "FX_REVALUATION_REVERSE", "FX Revaluation Reverse"

    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="accounting_audit_trails",
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=25, choices=ActionType.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Object reference
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    # Change details
    changes = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)

    # Approval workflow
    approval_level = models.PositiveIntegerField(null=True, blank=True)
    approval_status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("APPROVED", "Approved"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING",
    )

    class Meta:
        verbose_name = "Accounting Audit Trail"
        verbose_name_plural = "Accounting Audit Trails"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user} performed {self.action} on {self.content_object} at {self.timestamp}"

    @classmethod
    def _make_json_safe(cls, value):
        if isinstance(value, Decimal):
            return str(value)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, models.Model):
            return value.pk
        if isinstance(value, dict):
            return {
                str(cls._make_json_safe(key)): cls._make_json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [cls._make_json_safe(item) for item in value]
        return value

    @classmethod
    def log_action(
        cls,
        user,
        action,
        instance,
        changes=None,
        reason=None,
        ip_address=None,
        user_agent=None,
        approval_level=None,
        content_type=None,
        object_id=None,
        company=None,
    ):
        """Log an action to audit trail"""
        content_type = content_type or (
            ContentType.objects.get_for_model(instance)
            if instance is not None
            else ContentType.objects.get_for_model(cls)
        )
        object_id = (
            object_id
            if object_id is not None
            else (instance.pk if instance is not None and instance.pk is not None else 0)
        )
        company = company if company is not None else getattr(instance, "company", None)
        safe_changes = cls._make_json_safe(changes or {})

        def create_audit_entry():
            try:
                return cls.objects.create(
                    company=company,
                    user=user,
                    action=action,
                    content_type=content_type,
                    object_id=object_id,
                    changes=safe_changes,
                    reason=reason or "",
                    ip_address=ip_address,
                    user_agent=user_agent or "",
                    approval_level=approval_level,
                )
            except Exception:
                # Silently fail to avoid breaking the main application
                # In production, this should be logged to error monitoring
                pass

        # Check if we're in an atomic block and if the transaction is in a good state
        try:
            # Try to use on_commit if we're in a working transaction
            if transaction.get_connection().in_atomic_block:
                transaction.on_commit(create_audit_entry)
            else:
                # Not in an atomic block, create directly
                create_audit_entry()
        except Exception:
            # If transaction is broken or on_commit fails, try to create directly
            # This handles the case where we're in a broken transaction state
            try:
                # Use a separate transaction to avoid the broken one
                with transaction.atomic(using=None, savepoint=False):
                    create_audit_entry()
            except Exception:
                # As a last resort, try without any transaction wrapper
                # This ensures audit logging doesn't break the main application
                create_audit_entry()


class Journal(BaseModel):
    class JournalStatus(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        PENDING_APPROVAL = "PENDING_APPROVAL", _("Pending Approval")
        APPROVED = "APPROVED", _("Approved")
        POSTED = "POSTED", _("Posted")
        CANCELLED = "CANCELLED", _("Cancelled")
        REVERSED = "REVERSED", _("Reversed")

    # Basic fields
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="journals"
    )
    transaction_number = models.CharField(max_length=20, unique=True, editable=False)
    description = models.CharField(max_length=255)
    date = models.DateField(default=timezone.now)
    period = models.ForeignKey(
        AccountingPeriod, on_delete=models.PROTECT, related_name="journals"
    )
    status = models.CharField(
        max_length=20, choices=JournalStatus.choices, default=JournalStatus.DRAFT
    )

    # Audit fields
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_journals",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_journals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posted_journals",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    # Reversal fields
    reversed_journal = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversal_of",
    )
    reversal_reason = models.TextField(blank=True, null=True)

    # Source transaction reference
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    def __str__(self):
        return f"{self.transaction_number} - {self.description} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if self.period_id and not self.company_id:
            self.company = self.period.company
        if not self.company_id and self.created_by_id:
            self.company = getattr(self.created_by, "active_company", None) or getattr(
                self.created_by, "company", None
            )
        if not self.company_id:
            self.company = _get_default_company_fallback()

        # Generate transaction number if new
        if not self.pk and not self.transaction_number:
            current_year = timezone.now().year
            fiscal_year = FiscalYear.objects.filter(
                company=self.company, year=current_year, is_active=True
            ).first()
            if not fiscal_year:
                # Create or get current fiscal year
                fiscal_year, _ = FiscalYear.objects.get_or_create(
                    company=self.company,
                    year=current_year,
                    defaults={
                        "name": f"FY {current_year}",
                        "start_date": date(current_year, 1, 1),
                        "end_date": date(current_year, 12, 31),
                        "is_active": True,
                    },
                )

            self.transaction_number = TransactionNumber.get_next_number(fiscal_year)

        # Set period if not set
        if not self.period_id:
            current_year = timezone.now().year
            fiscal_year = FiscalYear.objects.get(
                company=self.company, year=current_year, is_active=True
            )
            current_month = timezone.now().month
            period = AccountingPeriod.objects.filter(
                company=self.company,
                fiscal_year=fiscal_year, period_number=current_month
            ).first()
            if not period:
                # Create monthly period
                period = AccountingPeriod.objects.create(
                    company=self.company,
                    fiscal_year=fiscal_year,
                    period_number=current_month,
                    name=f"Month {current_month}",
                    start_date=date(current_year, current_month, 1),
                    end_date=get_last_day_of_month(current_year, current_month),
                    is_active=True,
                )
            self.period = period

        super(Journal, self).save(*args, **kwargs)

    def clean(self):
        if self.period_id and self.company_id != self.period.company_id:
            raise ValidationError("Journal company must match accounting period company")

        # Basic validation
        if self.status == self.JournalStatus.POSTED:
            if not self.entries.exists():
                raise ValidationError("A posted journal must have entries.")
            self.validate_entries()

    def validate_entries(self):
        """Validates that sum of debits equals sum of credits"""
        debits = (
            self.entries.filter(entry_type="DEBIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )
        credits = (
            self.entries.filter(entry_type="CREDIT").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )

        if debits != credits:
            raise ValidationError(
                f"Debits ({debits}) and credits ({credits}) must be equal for a journal."
            )

    def submit_for_approval(self):
        """Submit journal for approval"""
        if self.status != self.JournalStatus.DRAFT:
            raise ValidationError("Only draft journals can be submitted for approval")

        self.status = self.JournalStatus.PENDING_APPROVAL
        self.save()

    def approve(self, user):
        """Approve the journal"""
        if self.status != self.JournalStatus.PENDING_APPROVAL:
            raise ValidationError("Only pending journals can be approved")

        self.status = self.JournalStatus.APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save()

        # Signal will automatically log the approval through signal handlers

    def post(self, user):
        """Mark the journal as posted"""
        if self.status != self.JournalStatus.APPROVED:
            raise ValidationError("Only approved journals can be posted")

        self.validate_entries()
        self.status = self.JournalStatus.POSTED
        self.posted_by = user
        self.posted_at = timezone.now()
        self.save()

        # Signal will automatically log the posting through signal handlers

    def reverse(self, user, reason):
        """Create a reversal journal"""
        if self.status != self.JournalStatus.POSTED:
            raise ValidationError("Only posted journals can be reversed")

        if self.reversed_journal:
            raise ValidationError("Journal has already been reversed")

        with transaction.atomic():
            # Create reversal journal
            reversal_journal = Journal.objects.create(
                company=self.company,
                description=f"REVERSAL: {self.description}",
                date=timezone.now().date(),
                period=self.period,
                status=self.JournalStatus.DRAFT,
                created_by=user,
                reversal_reason=reason,
                reversed_journal=self,
            )

            # Create reversal entries (swap debits and credits)
            for entry in self.entries.all():
                reversal_entry_type = (
                    "CREDIT" if entry.entry_type == "DEBIT" else "DEBIT"
                )
                JournalEntry.objects.create(
                    journal=reversal_journal,
                    account=entry.account,
                    entry_type=reversal_entry_type,
                    amount=entry.amount,
                    memo=f"Reversal of entry {entry.id}: {entry.memo or ''}",
                )

            # Auto-approve and post reversal
            reversal_journal._suppress_status_audit = True
            reversal_journal.submit_for_approval()
            reversal_journal.approve(user)
            reversal_journal.post(user)

            # Mark original journal as reversed
            self.status = self.JournalStatus.REVERSED
            self.reversal_reason = reason
            self.save(update_fields=["status", "reversal_reason", "updated_at"])

            return reversal_journal

    def add_entry(self, account, entry_type, amount, memo=None):
        """Helper to add a journal entry"""
        if self.status in [self.JournalStatus.POSTED, self.JournalStatus.CANCELLED]:
            raise ValidationError(
                "Cannot add entries to a posted or cancelled journal."
            )

        if account.company_id != self.company_id:
            raise ValidationError("Journal entry account must belong to the journal company")

        return JournalEntry.objects.create(
            journal=self,
            account=account,
            entry_type=entry_type,
            amount=amount,
            memo=memo,
        )

    class Meta:
        verbose_name = "Journal"
        verbose_name_plural = "Journals"
        ordering = ["-date", "-created_at"]


class JournalEntry(BaseModel):
    class EntryType(models.TextChoices):
        DEBIT = "DEBIT", _("Debit")
        CREDIT = "CREDIT", _("Credit")

    journal = models.ForeignKey(
        Journal, on_delete=models.CASCADE, related_name="entries"
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="entries"
    )
    entry_type = models.CharField(max_length=6, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    memo = models.CharField(max_length=255, blank=True, null=True)

    # Audit field
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_entries",
    )

    def __str__(self):
        return f"{self.journal.transaction_number} - {self.get_entry_type_display()} {self.amount:.2f} to {self.account.name}"

    def clean(self):
        if self.amount is None:
            return
        if self.amount <= 0:
            raise ValidationError("Amount must be greater than zero")
        if (
            self.journal_id
            and self.account_id
            and self.account.company_id != self.journal.company_id
        ):
            raise ValidationError("Account must belong to the journal company")

    class Meta:
        verbose_name = "Journal Entry"
        verbose_name_plural = "Journal Entries"
        ordering = ["journal__date", "entry_type", "account__name"]


def get_last_day_of_month(year, month):
    """Get the last day of a month"""
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    else:
        return date(year, month + 1, 1) - timedelta(days=1)


class DisciplinaryCase(BaseModel):
    class ViolationLevel(models.TextChoices):
        LEVEL_1 = "LEVEL_1", "Level 1 - Minor"
        LEVEL_2 = "LEVEL_2", "Level 2 - Moderate"
        LEVEL_3 = "LEVEL_3", "Level 3 - Serious"
        LEVEL_4 = "LEVEL_4", "Level 4 - Major"
        LEVEL_5 = "LEVEL_5", "Level 5 - Critical"

    class Status(models.TextChoices):
        INTAKE = "INTAKE", "Intake"
        UNDER_INVESTIGATION = "UNDER_INVESTIGATION", "Under Investigation"
        PANEL_REVIEW = "PANEL_REVIEW", "Panel Review"
        DECIDED = "DECIDED", "Decided"
        APPEALED = "APPEALED", "Appealed"
        CLOSED = "CLOSED", "Closed"
        DISMISSED = "DISMISSED", "Dismissed"

    class Finding(models.TextChoices):
        UNSUBSTANTIATED = "UNSUBSTANTIATED", "Unsubstantiated"
        PARTIALLY_SUBSTANTIATED = "PARTIALLY_SUBSTANTIATED", "Partially Substantiated"
        SUBSTANTIATED = "SUBSTANTIATED", "Substantiated"

    class ReviewLevel(models.TextChoices):
        MANAGER = "MANAGER", "Manager Review"
        HR_LEAD = "HR_LEAD", "HR + Functional Lead"
        PANEL = "PANEL", "Disciplinary Panel"
        EXECUTIVE = "EXECUTIVE", "Executive Oversight"

    case_number = models.CharField(max_length=30, unique=True, editable=False)
    company = models.ForeignKey(
        "company.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="disciplinary_cases",
        db_index=True,
    )
    allegation_summary = models.CharField(max_length=255)
    allegation_details = models.TextField()
    incident_date = models.DateField(null=True, blank=True)
    reported_at = models.DateTimeField(default=timezone.now)
    respondent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_cases_as_respondent",
    )
    reporter = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_cases_reported",
    )
    investigator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disciplinary_cases_investigated",
    )
    violation_level = models.CharField(
        max_length=20,
        choices=ViolationLevel.choices,
        default=ViolationLevel.LEVEL_1,
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.INTAKE)
    finding = models.CharField(
        max_length=30,
        choices=Finding.choices,
        blank=True,
        null=True,
    )
    required_review_level = models.CharField(
        max_length=20,
        choices=ReviewLevel.choices,
        default=ReviewLevel.MANAGER,
    )
    emergency_case = models.BooleanField(default=False)
    repeat_offense_suspected = models.BooleanField(default=False)
    power_imbalance_flag = models.BooleanField(default=False)
    conflict_of_interest_flag = models.BooleanField(default=False)
    mental_health_context = models.BooleanField(default=False)
    cultural_context = models.BooleanField(default=False)
    interim_measures = models.TextField(blank=True)
    findings_summary = models.TextField(blank=True)
    decision_rationale = models.TextField(blank=True)
    due_process_notified_at = models.DateTimeField(null=True, blank=True)
    respondent_response_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disciplinary_cases_decided",
    )
    decision_at = models.DateTimeField(null=True, blank=True)
    appeal_window_ends_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Case"
        verbose_name_plural = "Disciplinary Cases"
        indexes = [
            models.Index(fields=["case_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["violation_level"]),
            models.Index(fields=["required_review_level"]),
        ]

    def __str__(self):
        return f"{self.case_number} - {self.allegation_summary}"

    def save(self, *args, **kwargs):
        if self.company_id is None:
            respondent_company = getattr(self.respondent, "active_company", None) or getattr(
                self.respondent, "company", None
            )
            reporter_company = getattr(self.reporter, "active_company", None) or getattr(
                self.reporter, "company", None
            )
            self.company = respondent_company or reporter_company

        if not self.case_number:
            year = timezone.now().year
            prefix = f"DISC-{year}-"
            latest = (
                DisciplinaryCase.objects.filter(case_number__startswith=prefix)
                .order_by("-case_number")
                .first()
            )
            next_number = 1
            if latest and latest.case_number:
                try:
                    next_number = int(latest.case_number.split("-")[-1]) + 1
                except (ValueError, IndexError):
                    next_number = 1
            self.case_number = f"{prefix}{str(next_number).zfill(5)}"

        self.required_review_level = self.compute_required_review_level()
        super().save(*args, **kwargs)

    def compute_required_review_level(self):
        if self.violation_level in [
            self.ViolationLevel.LEVEL_4,
            self.ViolationLevel.LEVEL_5,
        ]:
            return self.ReviewLevel.PANEL

        if self.violation_level == self.ViolationLevel.LEVEL_3:
            return self.ReviewLevel.PANEL

        if self.repeat_offense_suspected:
            return self.ReviewLevel.HR_LEAD

        if self.power_imbalance_flag or self.conflict_of_interest_flag:
            return self.ReviewLevel.PANEL

        if self.emergency_case:
            return self.ReviewLevel.EXECUTIVE

        if self.violation_level == self.ViolationLevel.LEVEL_2:
            return self.ReviewLevel.HR_LEAD

        return self.ReviewLevel.MANAGER

    def mark_due_process_notice(self):
        self.due_process_notified_at = timezone.now()
        self.save(update_fields=["due_process_notified_at", "updated_at"])

    def mark_respondent_response(self):
        self.respondent_response_at = timezone.now()
        self.save(update_fields=["respondent_response_at", "updated_at"])

    def move_to_investigation(self):
        self.status = self.Status.UNDER_INVESTIGATION
        self.save(update_fields=["status", "updated_at"])

    def decide(self, finding, decided_by, rationale):
        self.finding = finding
        self.decision_rationale = rationale
        self.decided_by = decided_by
        self.decision_at = timezone.now()
        self.appeal_window_ends_at = timezone.now() + timedelta(days=10)
        self.status = self.Status.DECIDED
        self.save(
            update_fields=[
                "finding",
                "decision_rationale",
                "decided_by",
                "decision_at",
                "appeal_window_ends_at",
                "status",
                "updated_at",
            ]
        )

    def close_case(self):
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at", "updated_at"])


class DisciplinaryEvidence(BaseModel):
    class EvidenceType(models.TextChoices):
        DOCUMENT = "DOCUMENT", "Document"
        EMAIL = "EMAIL", "Email"
        CHAT = "CHAT", "Chat"
        SYSTEM_LOG = "SYSTEM_LOG", "System Log"
        CCTV = "CCTV", "CCTV"
        WITNESS_STATEMENT = "WITNESS_STATEMENT", "Witness Statement"
        OTHER = "OTHER", "Other"

    case = models.ForeignKey(
        DisciplinaryCase,
        on_delete=models.CASCADE,
        related_name="evidence_items",
    )
    title = models.CharField(max_length=255)
    evidence_type = models.CharField(max_length=30, choices=EvidenceType.choices)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="disciplinary/evidence/", blank=True, null=True)
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_evidence_submitted",
    )
    is_confidential = models.BooleanField(default=False)
    chain_of_custody_notes = models.TextField(blank=True)
    reliability_score = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Evidence"
        verbose_name_plural = "Disciplinary Evidence"

    def __str__(self):
        return f"{self.case.case_number} - {self.title}"

    def clean(self):
        if not self.description and not self.file:
            raise ValidationError("Provide either a description or an uploaded file.")

        if self.reliability_score and not 1 <= self.reliability_score <= 5:
            raise ValidationError("Reliability score must be between 1 and 5.")


class DisciplinarySanction(BaseModel):
    class SanctionType(models.TextChoices):
        COACHING = "COACHING", "Coaching"
        WRITTEN_WARNING = "WRITTEN_WARNING", "Written Warning"
        FINAL_WARNING = "FINAL_WARNING", "Final Warning"
        TRAINING = "TRAINING", "Mandatory Training"
        PERFORMANCE_PLAN = "PERFORMANCE_PLAN", "Performance Improvement Plan"
        ROLE_RESTRICTION = "ROLE_RESTRICTION", "Role Restriction"
        SUSPENSION = "SUSPENSION", "Suspension"
        DEMOTION = "DEMOTION", "Demotion"
        TERMINATION_REVIEW = "TERMINATION_REVIEW", "Termination Review"
        TERMINATION = "TERMINATION", "Termination"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        REVOKED = "REVOKED", "Revoked"

    case = models.ForeignKey(
        DisciplinaryCase,
        on_delete=models.CASCADE,
        related_name="sanctions",
    )
    sanction_type = models.CharField(max_length=30, choices=SanctionType.choices)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE)
    rationale = models.TextField()
    effective_date = models.DateField(default=timezone.now)
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    compliance_due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_rehabilitative = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_sanctions_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Sanction"
        verbose_name_plural = "Disciplinary Sanctions"

    def __str__(self):
        return f"{self.case.case_number} - {self.get_sanction_type_display()}"

    def clean(self):
        high_impact_sanctions = [
            self.SanctionType.DEMOTION,
            self.SanctionType.TERMINATION_REVIEW,
            self.SanctionType.TERMINATION,
        ]
        if (
            self.sanction_type in high_impact_sanctions
            and self.case.violation_level
            not in [DisciplinaryCase.ViolationLevel.LEVEL_3, DisciplinaryCase.ViolationLevel.LEVEL_4, DisciplinaryCase.ViolationLevel.LEVEL_5]
        ):
            raise ValidationError(
                "High-impact sanctions require a case severity of Level 3 or above."
            )

        if (
            self.sanction_type == self.SanctionType.SUSPENSION
            and not self.duration_days
        ):
            raise ValidationError("Suspension sanctions require duration in days.")

    @property
    def end_date(self):
        if not self.duration_days:
            return None
        return self.effective_date + timedelta(days=self.duration_days - 1)

    def is_effective_on(self, target_date):
        if target_date < self.effective_date:
            return False
        if self.end_date is None:
            return True
        return target_date <= self.end_date

    def overlaps_period(self, period_start, period_end):
        if self.effective_date > period_end:
            return False
        sanction_end = self.end_date
        if sanction_end is None:
            return True
        return sanction_end >= period_start

    def _apply_employment_effects(self):
        if (
            self.status != self.Status.ACTIVE
            or self.sanction_type != self.SanctionType.TERMINATION
        ):
            return

        today = timezone.localdate()
        if self.effective_date and self.effective_date > today:
            return

        respondent = self.case.respondent
        if not respondent:
            return

        if respondent.is_active:
            respondent.is_active = False
            respondent.save(update_fields=["is_active"])

        EmployeeProfile = apps.get_model("payroll", "EmployeeProfile")
        try:
            employee = EmployeeProfile.objects.get(user=respondent)
        except EmployeeProfile.DoesNotExist:
            return

        if employee.status != "terminated":
            employee.status = "terminated"
            employee.save(update_fields=["status"])

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._apply_employment_effects()

    def mark_completed(self):
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])


class DisciplinaryAppeal(BaseModel):
    class AppealGround(models.TextChoices):
        PROCEDURAL_UNFAIRNESS = "PROCEDURAL_UNFAIRNESS", "Procedural Unfairness"
        NEW_EVIDENCE = "NEW_EVIDENCE", "New Evidence"
        BIAS_OR_CONFLICT = "BIAS_OR_CONFLICT", "Bias or Conflict of Interest"
        DISPROPORTIONATE_SANCTION = "DISPROPORTIONATE_SANCTION", "Disproportionate Sanction"

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        UPHELD = "UPHELD", "Upheld"
        MODIFIED = "MODIFIED", "Modified"
        OVERTURNED = "OVERTURNED", "Overturned"
        REINVESTIGATION_ORDERED = "REINVESTIGATION_ORDERED", "Reinvestigation Ordered"
        REJECTED = "REJECTED", "Rejected"

    case = models.ForeignKey(
        DisciplinaryCase,
        on_delete=models.CASCADE,
        related_name="appeals",
    )
    appellant = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disciplinary_appeals_filed",
    )
    grounds = models.CharField(max_length=40, choices=AppealGround.choices)
    details = models.TextField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SUBMITTED)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disciplinary_appeals_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    outcome_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Disciplinary Appeal"
        verbose_name_plural = "Disciplinary Appeals"

    def __str__(self):
        return f"Appeal for {self.case.case_number}"

    def clean(self):
        if (
            not self.pk
            and self.case.appeal_window_ends_at
            and timezone.now() > self.case.appeal_window_ends_at
        ):
            raise ValidationError("Appeal window has closed for this case.")
