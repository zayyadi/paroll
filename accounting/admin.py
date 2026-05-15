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
    FinancialReportDefinition,
    FinancialReportLine,
    Journal,
    JournalEntry,
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
