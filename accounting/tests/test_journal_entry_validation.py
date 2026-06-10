from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounting.models import Account, AccountingPeriod, FiscalYear, Journal, JournalEntry
from company.models import Company


User = get_user_model()


class JournalEntryValidationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Journal Validation Co")
        self.user = User.objects.create_superuser(
            email="journal-validator@example.com",
            password="password123",
            company=self.company,
            active_company=self.company,
        )
        self.fiscal_year = FiscalYear.objects.create(
            company=self.company,
            year=2026,
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            company=self.company,
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="January 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            is_active=True,
        )
        self.cash = Account.objects.create(
            company=self.company,
            name="Cash",
            account_number="1000",
            type=Account.AccountType.ASSET,
        )
        self.revenue = Account.objects.create(
            company=self.company,
            name="Revenue",
            account_number="4000",
            type=Account.AccountType.REVENUE,
        )

    def test_journal_entry_without_amount_raises_validation_error(self):
        journal = Journal(
            company=self.company,
            period=self.period,
            date=date(2026, 1, 15),
            description="Incomplete entry",
        )
        entry = JournalEntry(
            journal=journal,
            account=self.cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=None,
        )

        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_journal_create_with_blank_entry_returns_form_error(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounting:journal_create"),
            {
                "description": "Incomplete entry",
                "date": "2026-01-15",
                "period": self.period.pk,
                "entries-TOTAL_FORMS": "2",
                "entries-INITIAL_FORMS": "0",
                "entries-MIN_NUM_FORMS": "2",
                "entries-MAX_NUM_FORMS": "1000",
                "entries-0-account": self.cash.pk,
                "entries-0-entry_type": JournalEntry.EntryType.DEBIT,
                "entries-0-amount": "",
                "entries-0-memo": "Missing amount",
                "entries-1-account": self.revenue.pk,
                "entries-1-entry_type": JournalEntry.EntryType.CREDIT,
                "entries-1-amount": "100.00",
                "entries-1-memo": "Offset",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please correct the errors below.")
        self.assertFalse(Journal.objects.filter(description="Incomplete entry").exists())

    def test_journal_create_accepts_billion_scale_amounts(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounting:journal_create"),
            {
                "description": "Large capital injection",
                "date": "2026-01-15",
                "period": self.period.pk,
                "entries-TOTAL_FORMS": "2",
                "entries-INITIAL_FORMS": "0",
                "entries-MIN_NUM_FORMS": "2",
                "entries-MAX_NUM_FORMS": "1000",
                "entries-0-account": self.cash.pk,
                "entries-0-entry_type": JournalEntry.EntryType.DEBIT,
                "entries-0-amount": "15000000000.00",
                "entries-0-memo": "Large debit",
                "entries-1-account": self.revenue.pk,
                "entries-1-entry_type": JournalEntry.EntryType.CREDIT,
                "entries-1-amount": "15000000000.00",
                "entries-1-memo": "Large credit",
            },
        )

        self.assertEqual(response.status_code, 302)
        journal = Journal.objects.get(description="Large capital injection")
        self.assertEqual(journal.entries.count(), 2)
