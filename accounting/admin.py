from django.contrib import admin
try:
    from import_export import resources
    from import_export.admin import ImportExportModelAdmin
except ImportError:  # pragma: no cover - optional admin dependency
    class _FallbackModelResource:
        class Meta:
            abstract = True

    class _FallbackResources:
        ModelResource = _FallbackModelResource

    resources = _FallbackResources()
    ImportExportModelAdmin = admin.ModelAdmin
from .models import (
    Account,
    AccountReconciliation,
    AccrualTemplate,
    BankTransaction,
    Budget,
    BudgetLine,
    CostCenter,
    CurrencyRevaluation,
    CurrencyRevaluationLine,
    ExchangeRate,
    FinancialReportDefinition,
    FinancialReportLine,
    Journal,
    JournalEntry,
    PostingRule,
    PostingValidationFailure,
    ReconciliationItem,
    DisciplinaryCase,
    DisciplinaryEvidence,
    DisciplinarySanction,
    DisciplinaryAppeal,
)


class AccountResource(resources.ModelResource):
    class Meta:
        model = Account


class JournalResource(resources.ModelResource):
    class Meta:
        model = Journal


class JournalEntryResource(resources.ModelResource):
    class Meta:
        model = JournalEntry


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ("company", "code", "name", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("company__name", "code", "name")


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("company", "base_currency", "quote_currency", "rate", "rate_date", "source")
    list_filter = ("company", "base_currency", "quote_currency", "rate_date")
    search_fields = ("company__name", "base_currency", "quote_currency", "source")


@admin.register(PostingRule)
class PostingRuleAdmin(admin.ModelAdmin):
    list_display = ("company", "document_type", "account_role", "expected_account_type", "is_active")
    list_filter = ("company", "document_type", "expected_account_type", "is_active")
    search_fields = ("company__name", "document_type", "account_role")


@admin.register(PostingValidationFailure)
class PostingValidationFailureAdmin(admin.ModelAdmin):
    list_display = ("company", "document_type", "account_role", "account", "created_at")
    list_filter = ("company", "document_type", "account_role", "created_at")
    search_fields = ("company__name", "document_type", "account_role", "message")
    readonly_fields = ("company", "document_type", "account_role", "account", "message")


@admin.register(AccrualTemplate)
class AccrualTemplateAdmin(admin.ModelAdmin):
    list_display = ("company", "name", "debit_account", "credit_account", "amount", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("company__name", "name")
    raw_id_fields = ("debit_account", "credit_account")


class BudgetLineInline(admin.TabularInline):
    model = BudgetLine
    extra = 0
    raw_id_fields = ("account", "period")


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("company", "name", "fiscal_year", "status")
    list_filter = ("company", "status", "fiscal_year")
    search_fields = ("company__name", "name", "fiscal_year__year")
    raw_id_fields = ("fiscal_year",)
    inlines = [BudgetLineInline]


class ReconciliationItemInline(admin.TabularInline):
    model = ReconciliationItem
    extra = 0
    readonly_fields = ("bank_transaction", "journal_entry", "amount_matched", "status", "note")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AccountReconciliation)
class AccountReconciliationAdmin(admin.ModelAdmin):
    list_display = ("company", "account", "period", "statement_balance", "ledger_balance", "variance", "status")
    list_filter = ("company", "status", "period")
    search_fields = ("company__name", "account__name", "account__account_number")
    raw_id_fields = ("account", "period", "approved_by")
    inlines = [ReconciliationItemInline]


class FinancialReportLineInline(admin.TabularInline):
    model = FinancialReportLine
    extra = 0
    filter_horizontal = ("accounts",)


@admin.register(FinancialReportDefinition)
class FinancialReportDefinitionAdmin(admin.ModelAdmin):
    list_display = ("company", "code", "name", "report_type", "is_active")
    list_filter = ("company", "report_type", "is_active")
    search_fields = ("company__name", "code", "name")
    inlines = [FinancialReportLineInline]


@admin.register(Account)
class AccountAdmin(ImportExportModelAdmin):
    resource_class = AccountResource
    list_display = ("company", "account_number", "name", "type", "balance")
    list_filter = ("company", "type")
    search_fields = ("company__name", "name", "account_number")
    readonly_fields = ("balance",)

    def balance(self, obj):
        return obj.get_balance()

    balance.short_description = "Current Balance"


class JournalEntryInline(admin.TabularInline):
    model = JournalEntry
    extra = 0
    readonly_fields = ("account", "entry_type", "amount")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Journal)
class JournalAdmin(ImportExportModelAdmin):
    resource_class = JournalResource
    list_display = (
        "company",
        "description",
        "date",
        "total_debits",
        "total_credits",
        "is_balanced",
    )
    list_filter = ("date",)
    search_fields = ("description",)
    inlines = [JournalEntryInline]
    readonly_fields = ("date", "description")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("entries")

    def total_debits(self, obj):
        return sum(e.amount for e in obj.entries.all() if e.entry_type == "DEBIT")

    def total_credits(self, obj):
        return sum(e.amount for e in obj.entries.all() if e.entry_type == "CREDIT")

    def is_balanced(self, obj):
        return self.total_debits(obj) == self.total_credits(obj)

    is_balanced.boolean = True

    def has_add_permission(self, request):
        # Journals should be created via signals, not manually in the admin
        return False

    def has_delete_permission(self, request, obj=None):
        # Preventing accidental deletion of financial records
        return False


class DisciplinaryEvidenceInline(admin.TabularInline):
    model = DisciplinaryEvidence
    extra = 0
    readonly_fields = ("title", "evidence_type", "submitted_by", "created_at")


class DisciplinarySanctionInline(admin.TabularInline):
    model = DisciplinarySanction
    extra = 0
    readonly_fields = ("sanction_type", "status", "created_by", "created_at")


class DisciplinaryAppealInline(admin.TabularInline):
    model = DisciplinaryAppeal
    extra = 0
    readonly_fields = ("grounds", "status", "appellant", "reviewed_by", "created_at")


@admin.register(DisciplinaryCase)
class DisciplinaryCaseAdmin(admin.ModelAdmin):
    list_display = (
        "case_number",
        "allegation_summary",
        "violation_level",
        "status",
        "required_review_level",
        "respondent",
        "reporter",
        "created_at",
    )
    list_filter = ("violation_level", "status", "required_review_level")
    search_fields = ("case_number", "allegation_summary", "respondent__email")
    readonly_fields = ("case_number", "required_review_level", "created_at", "updated_at")
    inlines = [
        DisciplinaryEvidenceInline,
        DisciplinarySanctionInline,
        DisciplinaryAppealInline,
    ]


class CurrencyRevaluationLineInline(admin.TabularInline):
    model = CurrencyRevaluationLine
    extra = 0
    readonly_fields = (
        "account", "foreign_currency", "balance_fc", "rate_at_original",
        "rate_at_revaluation", "base_value_original", "base_value_revalued",
        "unrealized_gain_loss", "entry_type",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CurrencyRevaluation)
class CurrencyRevaluationAdmin(admin.ModelAdmin):
    list_display = ("company", "revaluation_date", "base_currency", "status", "created_by", "created_at")
    list_filter = ("company", "status", "revaluation_date")
    search_fields = ("company__name", "memo")
    readonly_fields = ("created_at", "updated_at")
    inlines = [CurrencyRevaluationLineInline]


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ("company", "account", "transaction_date", "description", "amount", "transaction_type", "is_matched")
    list_filter = ("company", "transaction_type", "is_matched", "transaction_date")
    search_fields = ("description", "reference", "account__name")
    raw_id_fields = ("account", "reconciliation")
