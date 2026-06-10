from decimal import Decimal

from django import forms
from django.test import TestCase

from accounting.forms import BalanceAdjustmentForm, CorrectionEntryForm, JournalPartialReversalForm
from accounting.models import Account, Journal, JournalEntry
from company.models import Company
import inventory.forms as inventory_forms


class AccountingDecimalCapacityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Decimal Capacity Co")
        self.cash = Account.objects.create(
            company=self.company,
            account_number="1000",
            name="Cash",
            type=Account.AccountType.ASSET,
        )
        self.equity = Account.objects.create(
            company=self.company,
            account_number="3000",
            name="Equity",
            type=Account.AccountType.EQUITY,
        )

    def test_balance_adjustment_accepts_billion_scale_amount(self):
        form = BalanceAdjustmentForm(
            company=self.company,
            data={
                "account": self.cash.pk,
                "offset_account": self.equity.pk,
                "adjustment_type": "INCREASE",
                "amount": "15000000000.00",
                "description": "Large capital correction",
            },
        )

        self.assertTrue(form.is_valid(), form.errors.as_data())
        self.assertEqual(form.cleaned_data["amount"], Decimal("15000000000.00"))

    def test_journal_reversal_forms_accept_billion_scale_amounts(self):
        journal = Journal.objects.create(
            company=self.company,
            description="Large journal",
            period=None,
            status=Journal.JournalStatus.POSTED,
        )
        entry = JournalEntry.objects.create(
            journal=journal,
            account=self.cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("15000000000.00"),
        )

        partial_form = JournalPartialReversalForm(
            [entry],
            data={
                f"entry_{entry.id}": "on",
                f"amount_{entry.id}": "15000000000.00",
            },
        )
        correction_form = CorrectionEntryForm(
            data={
                "account": self.cash.pk,
                "entry_type": JournalEntry.EntryType.DEBIT,
                "amount": "15000000000.00",
                "memo": "Large correction",
            }
        )

        self.assertTrue(partial_form.is_valid(), partial_form.errors.as_data())
        self.assertTrue(correction_form.is_valid(), correction_form.errors.as_data())


class InventoryDecimalCapacityTests(TestCase):
    def test_inventory_action_form_decimal_fields_allow_more_than_10_integer_digits(self):
        exempt_rate_fields = {"vat_rate", "wht_rate"}
        checked_fields = []

        for form_class in vars(inventory_forms).values():
            if not isinstance(form_class, type) or not issubclass(form_class, forms.Form):
                continue
            try:
                form = form_class()
            except TypeError:
                continue

            for field_name, field in form.fields.items():
                if not isinstance(field, forms.DecimalField):
                    continue
                if field_name in exempt_rate_fields or field_name.endswith("_rate"):
                    continue
                checked_fields.append(f"{form_class.__name__}.{field_name}")
                self.assertGreaterEqual(
                    field.max_digits - field.decimal_places,
                    12,
                    f"{form_class.__name__}.{field_name} allows only "
                    f"{field.max_digits - field.decimal_places} integer digits",
                )

        self.assertIn("PurchaseOrderForm.unit_cost", checked_fields)
        self.assertIn("CustomerPaymentForm.amount", checked_fields)
