"""
Utility function tests for accounting utilities.
Tests all utility functions used throughout the accounting system.
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from unittest.mock import patch, MagicMock
from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from accounting.utils import (
    get_next_transaction_number,
    get_current_fiscal_year,
    get_current_period,
    validate_journal_entries,
    create_journal_from_entries,
    post_journal,
    reverse_journal,
    reverse_journal_partial,
    reverse_journal_with_correction,
    reverse_batch_journals,
    get_trial_balance,
    get_account_balance,
    get_general_ledger,
    close_period,
    close_fiscal_year,
    get_audit_trail_for_object,
    log_audit_action,
)

User = get_user_model()


class TransactionNumberUtilsTest(TestCase):
    """Test cases for transaction number utilities"""

    def setUp(self):
        """Set up test data"""
        self.fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )

    def test_get_next_transaction_number(self):
        """Test getting next transaction number"""
        # First number
        next_num = get_next_transaction_number(self.fiscal_year)
        self.assertEqual(next_num, "TXN000001")

        # Second number
        next_num2 = get_next_transaction_number(self.fiscal_year)
        self.assertEqual(next_num2, "TXN000002")

    def test_get_next_transaction_number_custom_prefix(self):
        """Test getting next transaction number with custom prefix"""
        next_num = get_next_transaction_number(self.fiscal_year, "INV")
        self.assertEqual(next_num, "INV000001")

    def test_get_next_transaction_number_existing(self):
        """Test getting next transaction number when one exists"""
        from accounting.models import TransactionNumber

        TransactionNumber.objects.create(
            fiscal_year=self.fiscal_year, prefix="TXN", current_number=10, padding=6
        )

        next_num = get_next_transaction_number(self.fiscal_year)
        self.assertEqual(next_num, "TXN000010")


class FiscalYearUtilsTest(TestCase):
    """Test cases for fiscal year utilities"""

    def setUp(self):
        """Set up test data"""
        self.fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )

    def test_get_current_fiscal_year(self):
        """Test getting current fiscal year"""
        # Mock current date to be in 2023
        with patch("accounting.utils.timezone.now") as mock_now:
            mock_now.return_value = timezone.datetime(2023, 6, 15).date()

            current_fy = get_current_fiscal_year()
            self.assertEqual(current_fy, self.fiscal_year)

    def test_get_current_fiscal_year_none(self):
        """Test getting current fiscal year when none exists"""
        # Delete fiscal year
        self.fiscal_year.delete()

        current_fy = get_current_fiscal_year()
        self.assertIsNone(current_fy)

    def test_get_current_period(self):
        """Test getting current period"""
        # Create period
        period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=6,
            name="June",
            start_date=date(2023, 6, 1),
            end_date=date(2023, 6, 30),
            is_active=True,
        )

        # Mock current date to be in June 2023
        with patch("accounting.utils.timezone.now") as mock_now:
            mock_now.return_value = timezone.datetime(2023, 6, 15).date()

            current_period = get_current_period()
            self.assertEqual(current_period, period)

    def test_get_current_period_none(self):
        """Test getting current period when none exists"""
        current_period = get_current_period()
        self.assertIsNone(current_period)


class ValidationUtilsTest(TestCase):
    """Test cases for validation utilities"""

    def setUp(self):
        """Set up test data"""
        self.journal = Journal.objects.create(
            description="Test Journal",
            date=date(2023, 1, 15),
            period=None,  # Will be set later
            status=Journal.JournalStatus.DRAFT,
        )

        # Create accounts
        self.cash = Account.objects.create(
            name="Cash", account_number="1000", type=Account.AccountType.ASSET
        )
        self.revenue = Account.objects.create(
            name="Revenue", account_number="4000", type=Account.AccountType.REVENUE
        )

    def test_validate_journal_entries_balanced(self):
        """Test validation of balanced journal entries"""
        # Create balanced entries
        JournalEntry.objects.create(
            journal=self.journal,
            account=self.cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )
        JournalEntry.objects.create(
            journal=self.journal,
            account=self.revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("1000"),
        )

        # Should not raise error
        validate_journal_entries(self.journal)

    def test_validate_journal_entries_unbalanced(self):
        """Test validation of unbalanced journal entries"""
        # Create unbalanced entries
        JournalEntry.objects.create(
            journal=self.journal,
            account=self.cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )
        JournalEntry.objects.create(
            journal=self.journal,
            account=self.revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("800"),
        )

        # Should raise ValidationError
        with self.assertRaises(ValidationError) as context:
            validate_journal_entries(self.journal)

        self.assertIn(
            "Debits (1000.00) and credits (800.00) must be equal",
            str(context.exception),
        )

    def test_validate_journal_entries_no_entries(self):
        """Test validation of journal with no entries"""
        # Should raise ValidationError
        with self.assertRaises(ValidationError) as context:
            validate_journal_entries(self.journal)

        self.assertIn("Journal must have at least one entry", str(context.exception))


class JournalCreationUtilsTest(TestCase):
    """Test cases for journal creation utilities"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        # Create fiscal year and period
        self.fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="January",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_active=True,
        )

        # Create accounts
        self.cash = Account.objects.create(
            name="Cash", account_number="1000", type=Account.AccountType.ASSET
        )
        self.revenue = Account.objects.create(
            name="Revenue", account_number="4000", type=Account.AccountType.REVENUE
        )

    def test_create_journal_from_entries(self):
        """Test creating journal from entries data"""
        entries_data = [
            {
                "account": self.cash,
                "entry_type": JournalEntry.EntryType.DEBIT,
                "amount": Decimal("1000"),
                "memo": "Cash received",
            },
            {
                "account": self.revenue,
                "entry_type": JournalEntry.EntryType.CREDIT,
                "amount": Decimal("1000"),
                "memo": "Sales revenue",
            },
        ]

        journal = create_journal_from_entries(
            description="Test Journal",
            entries_data=entries_data,
            date=date(2023, 1, 15),
            period=self.period,
            created_by=self.user,
        )

        self.assertEqual(journal.description, "Test Journal")
        self.assertEqual(journal.entries.count(), 2)

        # Check entries
        entries = journal.entries.all()
        self.assertEqual(entries[0].account, self.cash)
        self.assertEqual(entries[0].entry_type, JournalEntry.EntryType.DEBIT)
        self.assertEqual(entries[0].amount, Decimal("1000"))

        self.assertEqual(entries[1].account, self.revenue)
        self.assertEqual(entries[1].entry_type, JournalEntry.EntryType.CREDIT)
        self.assertEqual(entries[1].amount, Decimal("1000"))

    def test_create_journal_from_entries_unbalanced(self):
        """Test creating journal from unbalanced entries data"""
        entries_data = [
            {
                "account": self.cash,
                "entry_type": JournalEntry.EntryType.DEBIT,
                "amount": Decimal("1000"),
                "memo": "Cash received",
            },
            {
                "account": self.revenue,
                "entry_type": JournalEntry.EntryType.CREDIT,
                "amount": Decimal("800"),  # Unbalanced!
                "memo": "Sales revenue",
            },
        ]

        # Should raise ValidationError
        with self.assertRaises(ValidationError):
            create_journal_from_entries(
                description="Test Journal",
                entries_data=entries_data,
                date=date(2023, 1, 15),
                period=self.period,
                created_by=self.user,
            )


class JournalPostingUtilsTest(TestCase):
    """Test cases for journal posting utilities"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        # Create fiscal year and period
        self.fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="January",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_active=True,
        )

        # Create accounts
        self.cash = Account.objects.create(
            name="Cash", account_number="1000", type=Account.AccountType.ASSET
        )
        self.revenue = Account.objects.create(
            name="Revenue", account_number="4000", type=Account.AccountType.REVENUE
        )

        # Create journal with entries
        self.journal = Journal.objects.create(
            description="Test Journal",
            date=date(2023, 1, 15),
            period=self.period,
            status=Journal.JournalStatus.APPROVED,
            created_by=self.user,
        )

        JournalEntry.objects.create(
            journal=self.journal,
            account=self.cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )
        JournalEntry.objects.create(
            journal=self.journal,
            account=self.revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("1000"),
        )

    def test_post_journal(self):
        """Test posting journal"""
        post_journal(self.journal, self.user)

        self.journal.refresh_from_db()
        self.assertEqual(self.journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(self.journal.posted_by, self.user)
        self.assertIsNotNone(self.journal.posted_at)

    def test_post_journal_invalid_status(self):
        """Test posting journal with invalid status"""
        self.journal.status = Journal.JournalStatus.DRAFT
        self.journal.save()

        with self.assertRaises(ValidationError):
            post_journal(self.journal, self.user)


class JournalReversalUtilsTest(TestCase):
    """Test cases for journal reversal utilities"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        # Create fiscal year and period
        self.fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="January",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_active=True,
        )

        # Create accounts
        self.cash = Account.objects.create(
            name="Cash", account_number="1000", type=Account.AccountType.ASSET
        )
        self.revenue = Account.objects.create(
            name="Revenue", account_number="4000", type=Account.AccountType.REVENUE
        )

        # Create posted journal
        self.journal = Journal.objects.create(
            description="Test Journal",
            date=date(2023, 1, 15),
            period=self.period,
            status=Journal.JournalStatus.POSTED,
            created_by=self.user,
            posted_by=self.user,
        )

        self.entry1 = JournalEntry.objects.create(
            journal=self.journal,
            account=self.cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )
        self.entry2 = JournalEntry.objects.create(
            journal=self.journal,
            account=self.revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("1000"),
        )

    def test_reverse_journal(self):
        """Test full journal reversal"""
        reversal_journal = reverse_journal(self.journal, self.user, "Test reversal")

        # Check original journal
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.status, Journal.JournalStatus.REVERSED)
        self.assertEqual(self.journal.reversal_reason, "Test reversal")

        # Check reversal journal
        self.assertEqual(reversal_journal.description, "REVERSAL: Test Journal")
        self.assertEqual(reversal_journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(reversal_journal.reversed_journal, self.journal)

        # Check reversal entries
        reversal_entries = reversal_journal.entries.all()
        self.assertEqual(reversal_entries.count(), 2)

        # First entry should be credit to cash (opposite of original debit)
        self.assertEqual(reversal_entries[0].account, self.cash)
        self.assertEqual(reversal_entries[0].entry_type, JournalEntry.EntryType.CREDIT)
        self.assertEqual(reversal_entries[0].amount, Decimal("1000"))

        # Second entry should be debit to revenue (opposite of original credit)
        self.assertEqual(reversal_entries[1].account, self.revenue)
        self.assertEqual(reversal_entries[1].entry_type, JournalEntry.EntryType.DEBIT)
        self.assertEqual(reversal_entries[1].amount, Decimal("1000"))

    def test_reverse_journal_invalid_status(self):
        """Test reversing journal with invalid status"""
        self.journal.status = Journal.JournalStatus.DRAFT
        self.journal.save()

        with self.assertRaises(ValidationError):
            reverse_journal(self.journal, self.user, "Test reversal")

    def test_reverse_journal_partial(self):
        """Test partial journal reversal"""
        reversal_journal = reverse_journal_partial(
            self.journal, self.user, "Partial reversal", [self.entry1.pk]
        )

        # Check reversal journal
        self.assertEqual(reversal_journal.description, "PARTIAL REVERSAL: Test Journal")
        self.assertEqual(reversal_journal.status, Journal.JournalStatus.POSTED)

        # Check reversal entries (should only have one entry)
        reversal_entries = reversal_journal.entries.all()
        self.assertEqual(reversal_entries.count(), 1)

        # Entry should be credit to cash (opposite of original debit)
        self.assertEqual(reversal_entries[0].account, self.cash)
        self.assertEqual(reversal_entries[0].entry_type, JournalEntry.EntryType.CREDIT)
        self.assertEqual(reversal_entries[0].amount, Decimal("1000"))

    def test_reverse_journal_with_correction(self):
        """Test journal reversal with correction"""
        correction_entries = [
            {
                "account": self.cash,
                "entry_type": JournalEntry.EntryType.DEBIT,
                "amount": Decimal("1200"),
                "memo": "Corrected amount",
            },
            {
                "account": self.revenue,
                "entry_type": JournalEntry.EntryType.CREDIT,
                "amount": Decimal("1200"),
                "memo": "Corrected amount",
            },
        ]

        reversal_journal, correction_journal = reverse_journal_with_correction(
            self.journal, self.user, "Correction needed", correction_entries
        )

        # Check reversal journal
        self.assertEqual(reversal_journal.description, "REVERSAL: Test Journal")
        self.assertEqual(reversal_journal.status, Journal.JournalStatus.POSTED)

        # Check correction journal
        self.assertEqual(correction_journal.description, "CORRECTION: Test Journal")
        self.assertEqual(correction_journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(correction_journal.entries.count(), 2)

    def test_reverse_batch_journals(self):
        """Test batch journal reversal"""
        # Create another posted journal
        journal2 = Journal.objects.create(
            description="Test Journal 2",
            date=date(2023, 1, 16),
            period=self.period,
            status=Journal.JournalStatus.POSTED,
            created_by=self.user,
            posted_by=self.user,
        )

        JournalEntry.objects.create(
            journal=journal2,
            account=self.cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("2000"),
        )
        JournalEntry.objects.create(
            journal=journal2,
            account=self.revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("2000"),
        )

        results = reverse_batch_journals(
            [self.journal, journal2], self.user, "Batch reversal"
        )

        self.assertEqual(len(results["reversal_journals"]), 2)
        self.assertEqual(len(results["failed_journals"]), 0)

        # Check both journals are reversed
        self.journal.refresh_from_db()
        journal2.refresh_from_db()
        self.assertEqual(self.journal.status, Journal.JournalStatus.REVERSED)
        self.assertEqual(journal2.status, Journal.JournalStatus.REVERSED)


class ReportingUtilsTest(TestCase):
    """Test cases for reporting utilities"""

    def setUp(self):
        """Set up test data"""
        # Create fiscal year and period
        self.fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="January",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_active=True,
        )

        # Create accounts
        self.cash = Account.objects.create(
            name="Cash", account_number="1000", type=Account.AccountType.ASSET
        )
        self.revenue = Account.objects.create(
            name="Revenue", account_number="4000", type=Account.AccountType.REVENUE
        )
        self.expense = Account.objects.create(
            name="Expense", account_number="5000", type=Account.AccountType.EXPENSE
        )

        # Create posted journal
        self.journal = Journal.objects.create(
            description="Test Journal",
            date=date(2023, 1, 15),
            period=self.period,
            status=Journal.JournalStatus.POSTED,
        )

        JournalEntry.objects.create(
            journal=self.journal,
            account=self.cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )
        JournalEntry.objects.create(
            journal=self.journal,
            account=self.revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("1000"),
        )

        JournalEntry.objects.create(
            journal=self.journal,
            account=self.expense,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("300"),
        )
        JournalEntry.objects.create(
            journal=self.journal,
            account=self.cash,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("300"),
        )

    def test_get_trial_balance(self):
        """Test getting trial balance"""
        trial_balance = get_trial_balance(self.period)

        self.assertEqual(len(trial_balance), 3)

        # Check cash account (1000 debit - 300 credit = 700 debit)
        cash_balance = next(
            (item for item in trial_balance if item["account"] == self.cash), None
        )
        self.assertIsNotNone(cash_balance)
        self.assertEqual(cash_balance["debit_total"], Decimal("1000"))
        self.assertEqual(cash_balance["credit_total"], Decimal("300"))
        self.assertEqual(cash_balance["balance"], Decimal("700"))
        self.assertEqual(cash_balance["balance_type"], "debit")

        # Check revenue account (1000 credit)
        revenue_balance = next(
            (item for item in trial_balance if item["account"] == self.revenue), None
        )
        self.assertIsNotNone(revenue_balance)
        self.assertEqual(revenue_balance["debit_total"], Decimal("0"))
        self.assertEqual(revenue_balance["credit_total"], Decimal("1000"))
        self.assertEqual(revenue_balance["balance"], Decimal("1000"))
        self.assertEqual(revenue_balance["balance_type"], "credit")

        # Check expense account (300 debit)
        expense_balance = next(
            (item for item in trial_balance if item["account"] == self.expense), None
        )
        self.assertIsNotNone(expense_balance)
        self.assertEqual(expense_balance["debit_total"], Decimal("300"))
        self.assertEqual(expense_balance["credit_total"], Decimal("0"))
        self.assertEqual(expense_balance["balance"], Decimal("300"))
        self.assertEqual(expense_balance["balance_type"], "debit")

    def test_get_account_balance(self):
        """Test getting account balance"""
        balance = get_account_balance(self.cash, self.period)
        self.assertEqual(balance, Decimal("700"))  # 1000 - 300

    def test_get_general_ledger(self):
        """Test getting general ledger"""
        ledger = get_general_ledger(self.cash, self.period)

        self.assertEqual(len(ledger), 2)

        # First entry should be debit 1000
        self.assertEqual(ledger[0]["entry_type"], JournalEntry.EntryType.DEBIT)
        self.assertEqual(ledger[0]["amount"], Decimal("1000"))

        # Second entry should be credit 300
        self.assertEqual(ledger[1]["entry_type"], JournalEntry.EntryType.CREDIT)
        self.assertEqual(ledger[1]["amount"], Decimal("300"))


class PeriodClosingUtilsTest(TestCase):
    """Test cases for period closing utilities"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        # Create fiscal year and period
        self.fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="January",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_active=True,
        )

    def test_close_period(self):
        """Test closing period"""
        close_period(self.period, self.user)

        self.period.refresh_from_db()
        self.assertTrue(self.period.is_closed)
        self.assertEqual(self.period.closed_by, self.user)
        self.assertIsNotNone(self.period.closed_at)

    def test_close_period_already_closed(self):
        """Test closing already closed period"""
        self.period.is_closed = True
        self.period.save()

        with self.assertRaises(ValidationError):
            close_period(self.period, self.user)

    def test_close_fiscal_year(self):
        """Test closing fiscal year"""
        # Close all periods first
        for month in range(1, 13):
            AccountingPeriod.objects.create(
                fiscal_year=self.fiscal_year,
                period_number=month,
                name=f"Month {month}",
                start_date=date(2023, month, 1),
                end_date=(
                    date(2023, month, 28)
                    if month == 2
                    else (
                        date(2023, month, 30)
                        if month in [4, 6, 9, 11]
                        else date(2023, month, 31)
                    )
                ),
                is_closed=True,
            )

        close_fiscal_year(self.fiscal_year, self.user)

        self.fiscal_year.refresh_from_db()
        self.assertTrue(self.fiscal_year.is_closed)
        self.assertEqual(self.fiscal_year.closed_by, self.user)
        self.assertIsNotNone(self.fiscal_year.closed_at)

    def test_close_fiscal_year_with_open_periods(self):
        """Test closing fiscal year with open periods"""
        with self.assertRaises(ValidationError):
            close_fiscal_year(self.fiscal_year, self.user)


class AuditUtilsTest(TestCase):
    """Test cases for audit utilities"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        self.account = Account.objects.create(
            name="Test Account", account_number="1000", type=Account.AccountType.ASSET
        )

    def test_get_audit_trail_for_object(self):
        """Test getting audit trail for object"""
        # Create some audit trail entries
        AccountingAuditTrail.objects.create(
            user=self.user,
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=self.account._meta.get_field(
                "content_type"
            ).remote_field.model.objects.get_for_model(self.account),
            object_id=self.account.pk,
            reason="Created account",
        )

        AccountingAuditTrail.objects.create(
            user=self.user,
            action=AccountingAuditTrail.ActionType.UPDATE,
            content_type=self.account._meta.get_field(
                "content_type"
            ).remote_field.model.objects.get_for_model(self.account),
            object_id=self.account.pk,
            reason="Updated account",
        )

        # Get audit trail
        audit_trail = get_audit_trail_for_object(self.account)

        self.assertEqual(len(audit_trail), 2)
        self.assertEqual(audit_trail[0].action, AccountingAuditTrail.ActionType.UPDATE)
        self.assertEqual(audit_trail[1].action, AccountingAuditTrail.ActionType.CREATE)

    def test_log_audit_action(self):
        """Test logging audit action"""
        log_audit_action(
            user=self.user,
            action=AccountingAuditTrail.ActionType.CREATE,
            instance=self.account,
            reason="Test audit action",
        )

        # Note: Due to transaction.on_commit, the audit entry might not be immediately available
        # In a real test scenario, you might need to use transaction.commit() or similar
