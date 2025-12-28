from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from .models import Account, Journal, JournalEntry


class AccountResource(resources.ModelResource):
    class Meta:
        model = Account


class JournalResource(resources.ModelResource):
    class Meta:
        model = Journal


class JournalEntryResource(resources.ModelResource):
    class Meta:
        model = JournalEntry


@admin.register(Account)
class AccountAdmin(ImportExportModelAdmin):
    resource_class = AccountResource
    list_display = ("account_number", "name", "type", "balance")
    list_filter = ("type",)
    search_fields = ("name", "account_number")
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
