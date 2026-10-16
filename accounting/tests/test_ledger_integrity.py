from tests.approval_helpers import (
    approved_operation_for,
    approve_journal,
)
from datetime import date, datetime, timezone
from unittest.mock import patch
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.models import Journal, JournalEntry
from accounting.tests import test_journal_entry_validation as fixtures
from accounting.utils import create_journal_with_entries, get_account_balance_as_of, reverse_journal_partial


class LedgerIntegrityTests(TestCase):
    setUp = fixtures.JournalEntryValidationTests.setUp
    def posted_journal(self):
        return approved_operation_for("accounting.change_journal")(create_journal_with_entries,
            company=self.company, date=date(2026, 1, 15), description="Integrity fixture",
            period=self.period, fiscal_year=self.fiscal_year, user=self.user,
            auto_post=True, validate_balances=False,
            entries=[
                {"account": self.cash, "entry_type": "DEBIT", "amount": Decimal("100.00")},
                {"account": self.revenue, "entry_type": "CREDIT", "amount": Decimal("100.00")},
            ],
        )

    def test_posted_entry_cannot_be_edited(self):
        journal = self.posted_journal()
        entry = journal.entries.get(account=self.cash)
        entry.amount = Decimal("250.00")
        with self.assertRaises(ValidationError):
            entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("100.00"))

    def test_posted_entry_cannot_be_deleted(self):
        journal = self.posted_journal()
        with self.assertRaises(ValidationError):
            journal.entries.get(account=self.cash).delete()
        self.assertEqual(journal.entries.count(), 2)

    def test_posted_entries_queryset_cannot_be_edited(self):
        journal = self.posted_journal()
        with self.assertRaises(ValidationError):
            journal.entries.filter(account=self.cash).update(amount=Decimal("250.00"))

    def test_posted_entries_queryset_cannot_be_deleted(self):
        journal = self.posted_journal()
        with self.assertRaises(ValidationError):
            journal.entries.all().delete()

    def test_reversal_restores_balance_and_preserves_original_entries(self):
        journal = self.posted_journal()
        reversal = approved_operation_for("accounting.change_journal")(journal.reverse,self.user, "Correction")
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("0.00"))
        self.assertEqual(journal.entries.count(), 2)
        self.assertEqual(reversal.reversed_journal_id, journal.pk)
        self.assertEqual(reversal.status, Journal.JournalStatus.POSTED)

    def test_empty_journal_cannot_be_posted(self):
        journal = Journal.objects.create(
            company=self.company, date=date(2026, 1, 15), period=self.period,
            description="Empty journal", status=Journal.JournalStatus.DRAFT,
        )
        with self.assertRaises(ValidationError):
            approve_journal(journal)

    def test_reversal_preserves_historical_and_current_ledger_balance(self):
        journal = self.posted_journal()
        with patch("accounting.models.timezone.now", return_value=datetime(2026, 10, 5, tzinfo=timezone.utc)):
            approved_operation_for("accounting.change_journal")(journal.reverse,self.user, "Correction")
        self.assertEqual(get_account_balance_as_of(self.cash, date(2026, 1, 31)), Decimal("100.00"))
        self.assertEqual(get_account_balance_as_of(self.cash, date(2099, 12, 31)), Decimal("0.00"))

    def test_posted_journal_cannot_be_redated(self):
        journal = self.posted_journal()
        journal.date = date(2026, 1, 16)
        with self.assertRaises(ValidationError):
            journal.save()

    def test_posted_journal_queryset_cannot_be_redated(self):
        journal = self.posted_journal()
        with self.assertRaises(ValidationError):
            Journal.objects.filter(pk=journal.pk).update(date=date(2026, 1, 16))

    def test_posted_journal_queryset_cannot_be_deleted(self):
        journal = self.posted_journal()
        with self.assertRaises(ValidationError):
            Journal.objects.filter(pk=journal.pk).delete()

    def test_new_entry_cannot_be_added_to_posted_journal(self):
        journal = self.posted_journal()
        with self.assertRaises(ValidationError):
            JournalEntry.objects.create(journal=journal, account=self.cash, entry_type="DEBIT", amount=Decimal("1.00"))

    def test_reversed_entries_cannot_be_edited_or_deleted(self):
        journal = self.posted_journal()
        approved_operation_for("accounting.change_journal")(journal.reverse,self.user, "Correction")
        with self.assertRaises(ValidationError):
            journal.entries.update(amount=Decimal("250.00"))
        with self.assertRaises(ValidationError):
            journal.entries.all().delete()

    def test_stale_draft_reference_cannot_append_to_posted_journal(self):
        journal = self.posted_journal()
        journal.status = Journal.JournalStatus.DRAFT
        with self.assertRaises(ValidationError):
            JournalEntry.objects.create(journal=journal, account=self.cash, entry_type="DEBIT", amount=Decimal("1.00"))

    def test_bulk_create_cannot_append_to_posted_journal(self):
        journal = self.posted_journal()
        with self.assertRaises(ValidationError):
            JournalEntry.objects.bulk_create([
                JournalEntry(journal=journal, account=self.cash, entry_type="DEBIT", amount=Decimal("1.00"))
            ])

    def test_queryset_cannot_skip_posting_validation(self):
        journal = Journal.objects.create(company=self.company, period=self.period, description="Empty draft")
        with self.assertRaises(ValidationError):
            Journal.objects.filter(pk=journal.pk).update(status=Journal.JournalStatus.POSTED)

    def test_unposted_entries_do_not_change_financial_balance(self):
        self.posted_journal()
        journal = Journal.objects.create(company=self.company, period=self.period, description="Draft cash")
        JournalEntry.objects.create(journal=journal, account=self.cash, entry_type="DEBIT", amount=Decimal("250.00"))
        self.assertEqual(self.cash.get_balance(cached=False), Decimal("100.00"))
        JournalEntry.objects.create(journal=journal, account=self.revenue, entry_type="CREDIT", amount=Decimal("250.00"))
        journal.submit_for_approval()
        approve_journal(journal)
        self.assertEqual(self.cash.get_balance(cached=False), Decimal("100.00"))

    def test_direct_posted_status_save_cannot_skip_balance_updates(self):
        journal = approved_operation_for("accounting.change_journal")(create_journal_with_entries,
            company=self.company, date=date(2026, 1, 15), description="Direct post fixture",
            period=self.period, fiscal_year=self.fiscal_year, user=self.user,
            entries=[
                {"account": self.cash, "entry_type": "DEBIT", "amount": Decimal("100.00")},
                {"account": self.revenue, "entry_type": "CREDIT", "amount": Decimal("100.00")},
            ],
        )
        journal.status = Journal.JournalStatus.POSTED
        with self.assertRaises(ValidationError):
            journal.save()

    def test_direct_creation_cannot_skip_posting_validation(self):
        with self.assertRaises(ValidationError):
            Journal.objects.create(company=self.company, period=self.period, description="Empty posted", status=Journal.JournalStatus.POSTED)

    def test_bulk_creation_cannot_skip_posting_validation(self):
        with self.assertRaises(ValidationError):
            Journal.objects.bulk_create([
                Journal(company=self.company, period=self.period, transaction_number="BYPASS", description="Empty posted", status=Journal.JournalStatus.POSTED)
            ])

    def test_balanced_partial_reversal_posts_and_restores_selected_amount(self):
        journal = self.posted_journal()
        amounts = {entry.pk: Decimal("40.00") for entry in journal.entries.all()}
        reversal = approved_operation_for("accounting.change_journal")(reverse_journal_partial, journal, self.user, "Partial correction", amounts=amounts)
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal("60.00"))
        self.assertEqual(reversal.status, Journal.JournalStatus.POSTED)
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.POSTED)


class LedgerReportReversalTests(TestCase):
    setUp = fixtures.JournalEntryValidationTests.setUp
    posted_journal = LedgerIntegrityTests.posted_journal

    def test_general_ledger_includes_original_and_reversal(self):
        from django.urls import reverse
        journal = self.posted_journal()
        reversal = approved_operation_for("accounting.change_journal")(journal.reverse,self.user, "Report correction")
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounting:general_ledger"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.context["entries"].values_list("journal_id", flat=True)),
            {journal.pk, reversal.pk},
        )

    def test_reconciliation_views_preserve_historical_original(self):
        from django.urls import reverse
        from accounting.utils import create_bank_reconciliation
        journal = self.posted_journal()
        original_entry = journal.entries.get(account=self.cash)
        approved_operation_for("accounting.change_journal")(journal.reverse,self.user, "Report correction")
        reconciliation = create_bank_reconciliation(
            self.company, self.cash, self.period, self.user
        )
        self.client.force_login(self.user)
        for route in ("reconciliation_detail", "reconciliation_match"):
            with self.subTest(route=route):
                response = self.client.get(reverse("accounting:" + route, args=[reconciliation.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertIn(original_entry.pk, response.context["ledger_entries"].values_list("pk", flat=True))
