from django.db import models
from django.utils.translation import gettext_lazy as _

class Account(models.Model):
    class AccountType(models.TextChoices):
        ASSET = 'ASSET', _('Asset')
        LIABILITY = 'LIABILITY', _('Liability')
        EQUITY = 'EQUITY', _('Equity')
        REVENUE = 'REVENUE', _('Revenue')
        EXPENSE = 'EXPENSE', _('Expense')

    name = models.CharField(max_length=255, unique=True)
    type = models.CharField(max_length=10, choices=AccountType.choices)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f'{self.name} ({self.get_type_display()})'

class Transaction(models.Model):
    description = models.CharField(max_length=255)
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f'{self.description} on {self.date}'

class LedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        DEBIT = 'DEBIT', _('Debit')
        CREDIT = 'CREDIT', _('Credit')

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='entries')
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    entry_type = models.CharField(max_length=6, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f'{self.get_entry_type_display()} of {self.amount} to {self.account.name}'