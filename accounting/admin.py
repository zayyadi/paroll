from django.contrib import admin
from .models import Account, Transaction, LedgerEntry


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "balance")
    list_filter = ("type",)
    search_fields = ("name",)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("transaction", "account", "entry_type", "amount")
    list_filter = ("entry_type", "account")
    search_fields = ("transaction__description", "account__name")


class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    extra = 0


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("description", "date")
    list_filter = ("date",)
    search_fields = ("description",)
    inlines = [LedgerEntryInline]
