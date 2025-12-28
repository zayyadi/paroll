"""
Model tests for all accounting models.
Tests model creation, validation, methods, and relationships.
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    TransactionNumber,
    AccountingAuditTrail,
)
from accounting.tests.fixtures import (
    UserFactory,
    AccountFactory,
    FiscalYearFactory,
    JournalFactory,
)

User = get_user_model()


class AccountModelTest(TestCase):
    """Test cases for Account model"""

    def setUp(self):
        """Set up test data"""
        self.account = AccountFactory.create_account(
            name="Test Account",
            account_number="1001",
            account_type=Account.AccountType.ASSET,
            description="Test account description",
        )

    def test_account_creation(self):
        """Test account creation"""
        self.assertEqual(self.account.name, "Test Account")
        self.assertEqual(self.account.account_number, "1001")
        self.assertEqual(self.account.type, Account.AccountType.ASSET)
        self.assertEqual(self.account.description, "Test account description")
        self.assertIsNotNone(self.account.created_at)
        self.assertIsNotNone(self.account.updated_at)

    def test_account_str_representation(self):
        """Test account string representation"""
        expected = "1001 - Test Account"
        self.assertEqual(str(self.account), expected)

    def test_account_unique_name(self):
        """Test account name uniqueness"""
        with self.assertRaises(Exception):
            Account.objects.create(
                name="Test Account",
                account_number="1002",
                type=Account.AccountType.LIABILITY,
            )

    def test_account_unique_account_number(self):
        """Test account number uniqueness"""
        with self.assertRaises(Exception):
            Account.objects.create(
                name="Another Account",
                account_number="1001",
                type=Account.AccountType.LIABILITY,
            )

    def test_get_balance_zero(self):
        """Test balance calculation with no entries"""
        self.assertEqual(self.account.get_balance(), Decimal("0"))

    def test_get_balance_asset_account(self):
        """Test balance calculation for asset account"""
        # Create a journal with entries for this account
        journal = JournalFactory.create_journal()

        # Add debit entry (increases asset balance)
        JournalEntry.objects.create(
            journal=journal,
            account=self.account,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )

        # Add credit entry (decreases asset balance)
        JournalEntry.objects.create(
            journal=journal,
            account=self.account,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("300"),
        )

        # Asset balance = debits - credits = 1000 - 300 = 700
        self.assertEqual(self.account.get_balance(), Decimal("700"))

    def test_get_balance_liability_account(self):
        """Test balance calculation for liability account"""
        # Create a liability account
        liability_account = AccountFactory.create_account(
            name="Test Liability",
            account_number="2001",
            account_type=Account.AccountType.LIABILITY,
        )

        # Create a journal with entries for this account
        journal = JournalFactory.create_journal()

        # Add debit entry (decreases liability balance)
        JournalEntry.objects.create(
            journal=journal,
            account=liability_account,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("200"),
        )

        # Add credit entry (increases liability balance)
        JournalEntry.objects.create(
            journal=journal,
            account=liability_account,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("1000"),
        )

        # Liability balance = credits - debits = 1000 - 200 = 800
        self.assertEqual(liability_account.get_balance(), Decimal("800"))

    def test_balance_property(self):
        """Test balance property"""
        self.assertEqual(self.account.balance, Decimal("0"))

    def test_account_ordering(self):
        """Test account ordering by account number"""
        AccountFactory.create_account("Account A", "1002", Account.AccountType.ASSET)
        AccountFactory.create_account("Account B", "0999", Account.AccountType.ASSET)

        accounts = Account.objects.all()
        self.assertEqual(accounts[0].account_number, "0999")
        self.assertEqual(accounts[1].account_number, "1001")
        self.assertEqual(accounts[2].account_number, "1002")


class FiscalYearModelTest(TestCase):
    """Test cases for FiscalYear model"""

    def setUp(self):
        """Set up test data"""
        self.fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )

    def test_fiscal_year_creation(self):
        """Test fiscal year creation"""
        self.assertEqual(self.fiscal_year.year, 2023)
        self.assertEqual(self.fiscal_year.name, "FY 2023")
        self.assertEqual(self.fiscal_year.start_date, date(2023, 1, 1))
        self.assertEqual(self.fiscal_year.end_date, date(2023, 12, 31))
        self.assertTrue(self.fiscal_year.is_active)
        self.assertFalse(self.fiscal_year.is_closed)

    def test_fiscal_year_str_representation(self):
        """Test fiscal year string representation"""
        expected = "FY 2023 (FY 2023)"
        self.assertEqual(str(self.fiscal_year), expected)

    def test_fiscal_year_validation_invalid_dates(self):
        """Test fiscal year validation with invalid dates"""
        with self.assertRaises(ValidationError):
            fiscal_year = FiscalYear(
                year=2024,
                name="FY 2024",
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),
                is_active=True,
            )
            fiscal_year.clean()

    def test_fiscal_year_validation_overlapping_dates(self):
        """Test fiscal year validation with overlapping dates"""
        with self.assertRaises(ValidationError):
            fiscal_year = FiscalYear(
                year=2024,
                name="FY 2024",
                start_date=date(2023, 6, 1),
                end_date=date(2024, 6, 1),
                is_active=True,
            )
            fiscal_year.clean()

    def test_fiscal_year_close(self):
        """Test fiscal year closure"""
        user = UserFactory.create_admin()

        # Create periods
        AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="Month 1",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_closed=True,
        )

        # Close fiscal year
        self.fiscal_year.close(user)

        self.assertTrue(self.fiscal_year.is_closed)
        self.assertIsNotNone(self.fiscal_year.closed_at)
        self.assertEqual(self.fiscal_year.closed_by, user)

    def test_fiscal_year_close_with_open_periods(self):
        """Test fiscal year closure with open periods"""
        user = UserFactory.create_admin()

        # Create open period
        AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="Month 1",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_closed=False,
        )

        # Should raise validation error
        with self.assertRaises(ValidationError):
            self.fiscal_year.close(user)

    def test_fiscal_year_ordering(self):
        """Test fiscal year ordering"""
        FiscalYear.objects.create(
            year=2024,
            name="FY 2024",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            is_active=False,
        )

        fiscal_years = FiscalYear.objects.all()
        self.assertEqual(fiscal_years[0].year, 2024)
        self.assertEqual(fiscal_years[1].year, 2023)


class AccountingPeriodModelTest(TestCase):
    """Test cases for AccountingPeriod model"""

    def setUp(self):
        """Set up test data"""
        self.fiscal_year = FiscalYearFactory.create_fiscal_year(2023)
        self.period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="Month 1",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_active=True,
        )

    def test_period_creation(self):
        """Test period creation"""
        self.assertEqual(self.period.fiscal_year, self.fiscal_year)
        self.assertEqual(self.period.period_number, 1)
        self.assertEqual(self.period.name, "Month 1")
        self.assertEqual(self.period.start_date, date(2023, 1, 1))
        self.assertEqual(self.period.end_date, date(2023, 1, 31))
        self.assertTrue(self.period.is_active)
        self.assertFalse(self.period.is_closed)

    def test_period_str_representation(self):
        """Test period string representation"""
        expected = "FY 2023 - Period 1 (Month 1)"
        self.assertEqual(str(self.period), expected)

    def test_period_validation_invalid_dates(self):
        """Test period validation with invalid dates"""
        with self.assertRaises(ValidationError):
            period = AccountingPeriod(
                fiscal_year=self.fiscal_year,
                period_number=2,
                name="Month 2",
                start_date=date(2023, 2, 28),
                end_date=date(2023, 2, 1),
                is_active=False,
            )
            period.clean()

    def test_period_validation_outside_fiscal_year(self):
        """Test period validation with dates outside fiscal year"""
        with self.assertRaises(ValidationError):
            period = AccountingPeriod(
                fiscal_year=self.fiscal_year,
                period_number=13,
                name="Month 13",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                is_active=False,
            )
            period.clean()

    def test_period_validation_overlapping_periods(self):
        """Test period validation with overlapping periods"""
        with self.assertRaises(ValidationError):
            period = AccountingPeriod(
                fiscal_year=self.fiscal_year,
                period_number=2,
                name="Overlapping Month",
                start_date=date(2023, 1, 15),
                end_date=date(2023, 2, 15),
                is_active=False,
            )
            period.clean()

    def test_period_close(self):
        """Test period closure"""
        user = UserFactory.create_admin()

        # Close period
        self.period.close(user)

        self.assertTrue(self.period.is_closed)
        self.assertIsNotNone(self.period.closed_at)
        self.assertEqual(self.period.closed_by, user)

    def test_period_unique_constraint(self):
        """Test period number uniqueness within fiscal year"""
        with self.assertRaises(Exception):
            AccountingPeriod.objects.create(
                fiscal_year=self.fiscal_year,
                period_number=1,
                name="Duplicate Month",
                start_date=date(2023, 2, 1),
                end_date=date(2023, 2, 28),
                is_active=False,
            )

    def test_period_ordering(self):
        """Test period ordering"""
        AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=2,
            name="Month 2",
            start_date=date(2023, 2, 1),
            end_date=date(2023, 2, 28),
            is_active=False,
        )

        periods = AccountingPeriod.objects.all()
        self.assertEqual(periods[0].period_number, 1)
        self.assertEqual(periods[1].period_number, 2)


class TransactionNumberModelTest(TestCase):
    """Test cases for TransactionNumber model"""

    def setUp(self):
        """Set up test data"""
        self.fiscal_year = FiscalYearFactory.create_fiscal_year(2023)
        self.txn_number = TransactionNumber.objects.create(
            fiscal_year=self.fiscal_year, prefix="TXN", current_number=1, padding=6
        )

    def test_transaction_number_creation(self):
        """Test transaction number creation"""
        self.assertEqual(self.txn_number.fiscal_year, self.fiscal_year)
        self.assertEqual(self.txn_number.prefix, "TXN")
        self.assertEqual(self.txn_number.current_number, 1)
        self.assertEqual(self.txn_number.padding, 6)

    def test_transaction_number_str_representation(self):
        """Test transaction number string representation"""
        expected = "TXN for FY 2023"
        self.assertEqual(str(self.txn_number), expected)

    def test_get_next_number(self):
        """Test getting next transaction number"""
        # Get next number
        next_number = TransactionNumber.get_next_number(self.fiscal_year, "TXN")
        self.assertEqual(next_number, "TXN000001")

        # Get another number (should increment)
        next_number2 = TransactionNumber.get_next_number(self.fiscal_year, "TXN")
        self.assertEqual(next_number2, "TXN000002")

        # Check that current_number was updated
        self.txn_number.refresh_from_db()
        self.assertEqual(self.txn_number.current_number, 3)

    def test_get_next_number_new_prefix(self):
        """Test getting next number for new prefix"""
        next_number = TransactionNumber.get_next_number(self.fiscal_year, "INV")
        self.assertEqual(next_number, "INV000001")

        # Check that new TransactionNumber was created
        inv_txn = TransactionNumber.objects.get(
            fiscal_year=self.fiscal_year, prefix="INV"
        )
        self.assertEqual(inv_txn.current_number, 2)

    def test_transaction_number_unique_constraint(self):
        """Test transaction number uniqueness constraint"""
        with self.assertRaises(Exception):
            TransactionNumber.objects.create(
                fiscal_year=self.fiscal_year, prefix="TXN", current_number=5, padding=6
            )


class JournalModelTest(TestCase):
    """Test cases for Journal model"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()
        self.fiscal_year = FiscalYearFactory.create_fiscal_year(2023)
        self.period = AccountingPeriod.objects.filter(
            fiscal_year=self.fiscal_year, period_number=1
        ).first()

        self.journal = Journal.objects.create(
            description="Test Journal",
            date=date(2023, 1, 15),
            period=self.period,
            status=Journal.JournalStatus.DRAFT,
            created_by=self.user,
        )

    def test_journal_creation(self):
        """Test journal creation"""
        self.assertEqual(self.journal.description, "Test Journal")
        self.assertEqual(self.journal.date, date(2023, 1, 15))
        self.assertEqual(self.journal.period, self.period)
        self.assertEqual(self.journal.status, Journal.JournalStatus.DRAFT)
        self.assertEqual(self.journal.created_by, self.user)

    def test_journal_str_representation(self):
        """Test journal string representation"""
        # Journal should have transaction_number after save
        self.journal.refresh_from_db()
        expected = f"{self.journal.transaction_number} - Test Journal (Draft)"
        self.assertEqual(str(self.journal), expected)

    def test_journal_auto_transaction_number(self):
        """Test automatic transaction number generation"""
        self.journal.refresh_from_db()
        self.assertIsNotNone(self.journal.transaction_number)
        self.assertTrue(self.journal.transaction_number.startswith("TXN"))

    def test_journal_auto_period_assignment(self):
        """Test automatic period assignment"""
        # Create journal without period
        journal2 = Journal.objects.create(
            description="Test Journal 2", date=date(2023, 1, 20), created_by=self.user
        )

        # Should automatically assign current period
        self.assertIsNotNone(journal2.period)
        self.assertEqual(journal2.period.period_number, timezone.now().month)

    def test_journal_validation_no_entries(self):
        """Test journal validation with no entries"""
        with self.assertRaises(ValidationError):
            self.journal.status = Journal.JournalStatus.POSTED
            self.journal.clean()

    def test_journal_validation_balanced_entries(self):
        """Test journal validation with balanced entries"""
        # Add balanced entries
        cash = AccountFactory.create_account("Cash", "1000", Account.AccountType.ASSET)
        revenue = AccountFactory.create_account(
            "Revenue", "4000", Account.AccountType.REVENUE
        )

        JournalEntry.objects.create(
            journal=self.journal,
            account=cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )

        JournalEntry.objects.create(
            journal=self.journal,
            account=revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("1000"),
        )

        # Should not raise validation error
        self.journal.status = Journal.JournalStatus.POSTED
        self.journal.clean()

    def test_journal_validation_unbalanced_entries(self):
        """Test journal validation with unbalanced entries"""
        # Add unbalanced entries
        cash = AccountFactory.create_account("Cash", "1000", Account.AccountType.ASSET)
        revenue = AccountFactory.create_account(
            "Revenue", "4000", Account.AccountType.REVENUE
        )

        JournalEntry.objects.create(
            journal=self.journal,
            account=cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )

        JournalEntry.objects.create(
            journal=self.journal,
            account=revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("800"),  # Unbalanced!
        )

        # Should raise validation error
        with self.assertRaises(ValidationError) as context:
            self.journal.status = Journal.JournalStatus.POSTED
            self.journal.clean()

        self.assertIn(
            "Debits (1000.00) and credits (800.00) must be equal",
            str(context.exception),
        )

    def test_journal_submit_for_approval(self):
        """Test submitting journal for approval"""
        self.journal.submit_for_approval()
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.status, Journal.JournalStatus.PENDING_APPROVAL)

    def test_journal_submit_for_approval_invalid_status(self):
        """Test submitting journal for approval with invalid status"""
        self.journal.status = Journal.JournalStatus.POSTED
        self.journal.save()

        with self.assertRaises(ValidationError):
            self.journal.submit_for_approval()

    def test_journal_approve(self):
        """Test approving journal"""
        self.journal.status = Journal.JournalStatus.PENDING_APPROVAL
        self.journal.save()

        self.journal.approve(self.user)
        self.journal.refresh_from_db()

        self.assertEqual(self.journal.status, Journal.JournalStatus.APPROVED)
        self.assertEqual(self.journal.approved_by, self.user)
        self.assertIsNotNone(self.journal.approved_at)

    def test_journal_approve_invalid_status(self):
        """Test approving journal with invalid status"""
        with self.assertRaises(ValidationError):
            self.journal.approve(self.user)

    def test_journal_post(self):
        """Test posting journal"""
        # Create balanced entries
        journal = JournalFactory.create_journal_with_entries("Test Post", 1000)
        user = UserFactory.create_accountant()

        # Approve first
        journal.approve(user)

        # Then post
        journal.post(user)
        journal.refresh_from_db()

        self.assertEqual(journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(journal.posted_by, user)
        self.assertIsNotNone(journal.posted_at)

    def test_journal_post_invalid_status(self):
        """Test posting journal with invalid status"""
        with self.assertRaises(ValidationError):
            self.journal.post(self.user)

    def test_journal_reverse(self):
        """Test reversing journal"""
        # Create and post a journal
        journal = JournalFactory.create_posted_journal("Test Reverse", 1000)
        user = UserFactory.create_accountant()

        # Reverse it
        reversal_journal = journal.reverse(user, "Test reversal")

        # Check original journal
        journal.refresh_from_db()
        self.assertEqual(journal.status, Journal.JournalStatus.REVERSED)
        self.assertEqual(journal.reversal_reason, "Test reversal")

        # Check reversal journal
        self.assertEqual(reversal_journal.description, "REVERSAL: Test Reverse")
        self.assertEqual(reversal_journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(reversal_journal.reversed_journal, journal)

    def test_journal_reverse_invalid_status(self):
        """Test reversing journal with invalid status"""
        with self.assertRaises(ValidationError):
            self.journal.reverse(self.user, "Test reversal")

    def test_journal_reverse_already_reversed(self):
        """Test reversing already reversed journal"""
        journal = JournalFactory.create_posted_journal("Test Reverse 2", 1000)
        user = UserFactory.create_accountant()

        # Reverse once
        journal.reverse(user, "First reversal")

        # Try to reverse again
        with self.assertRaises(ValidationError):
            journal.reverse(user, "Second reversal")

    def test_journal_add_entry(self):
        """Test adding entry to journal"""
        cash = AccountFactory.create_account("Cash", "1000", Account.AccountType.ASSET)

        entry = self.journal.add_entry(
            account=cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("500"),
            memo="Test entry",
        )

        self.assertEqual(entry.journal, self.journal)
        self.assertEqual(entry.account, cash)
        self.assertEqual(entry.entry_type, JournalEntry.EntryType.DEBIT)
        self.assertEqual(entry.amount, Decimal("500"))
        self.assertEqual(entry.memo, "Test entry")

    def test_journal_add_entry_invalid_status(self):
        """Test adding entry to posted journal"""
        self.journal.status = Journal.JournalStatus.POSTED
        self.journal.save()

        cash = AccountFactory.create_account("Cash", "1000", Account.AccountType.ASSET)

        with self.assertRaises(ValidationError):
            self.journal.add_entry(
                account=cash,
                entry_type=JournalEntry.EntryType.DEBIT,
                amount=Decimal("500"),
            )

    def test_journal_ordering(self):
        """Test journal ordering"""
        # Create journals with different dates
        journal1 = JournalFactory.create_journal("Journal 1", date(2023, 1, 10))
        journal2 = JournalFactory.create_journal("Journal 2", date(2023, 1, 20))

        journals = Journal.objects.all()
        # Should be ordered by date descending, then created_at descending
        self.assertEqual(journals[0].date, date(2023, 1, 20))
        self.assertEqual(journals[1].date, date(2023, 1, 10))


class JournalEntryModelTest(TestCase):
    """Test cases for JournalEntry model"""

    def setUp(self):
        """Set up test data"""
        self.journal = JournalFactory.create_journal()
        self.account = AccountFactory.create_account(
            "Test Account", "1001", Account.AccountType.ASSET
        )

        self.entry = JournalEntry.objects.create(
            journal=self.journal,
            account=self.account,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
            memo="Test entry",
        )

    def test_entry_creation(self):
        """Test entry creation"""
        self.assertEqual(self.entry.journal, self.journal)
        self.assertEqual(self.entry.account, self.account)
        self.assertEqual(self.entry.entry_type, JournalEntry.EntryType.DEBIT)
        self.assertEqual(self.entry.amount, Decimal("1000"))
        self.assertEqual(self.entry.memo, "Test entry")

    def test_entry_str_representation(self):
        """Test entry string representation"""
        expected = f"{self.journal.transaction_number} - Debit 1000.00 to Test Account"
        self.assertEqual(str(self.entry), expected)

    def test_entry_validation_negative_amount(self):
        """Test entry validation with negative amount"""
        with self.assertRaises(ValidationError):
            entry = JournalEntry(
                journal=self.journal,
                account=self.account,
                entry_type=JournalEntry.EntryType.DEBIT,
                amount=Decimal("-100"),
            )
            entry.clean()

    def test_entry_validation_zero_amount(self):
        """Test entry validation with zero amount"""
        with self.assertRaises(ValidationError):
            entry = JournalEntry(
                journal=self.journal,
                account=self.account,
                entry_type=JournalEntry.EntryType.DEBIT,
                amount=Decimal("0"),
            )
            entry.clean()

    def test_entry_ordering(self):
        """Test entry ordering"""
        # Create more entries
        account2 = AccountFactory.create_account(
            "Account 2", "1002", Account.AccountType.ASSET
        )

        entry2 = JournalEntry.objects.create(
            journal=self.journal,
            account=account2,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("500"),
        )

        entries = JournalEntry.objects.all()
        # Should be ordered by journal date, entry type, account name
        self.assertEqual(entries[0].entry_type, JournalEntry.EntryType.CREDIT)
        self.assertEqual(entries[1].entry_type, JournalEntry.EntryType.DEBIT)


class AccountingAuditTrailModelTest(TestCase):
    """Test cases for AccountingAuditTrail model"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_auditor()
        self.account = AccountFactory.create_account(
            "Test Account", "1001", Account.AccountType.ASSET
        )

        self.audit_trail = AccountingAuditTrail.objects.create(
            user=self.user,
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=self.account._meta.get_field(
                "content_type"
            ).remote_field.model.objects.get_for_model(self.account),
            object_id=self.account.pk,
            changes={"name": {"old": None, "new": "Test Account"}},
            reason="Created test account",
            ip_address="127.0.0.1",
            user_agent="Test Browser",
        )

    def test_audit_trail_creation(self):
        """Test audit trail creation"""
        self.assertEqual(self.audit_trail.user, self.user)
        self.assertEqual(
            self.audit_trail.action, AccountingAuditTrail.ActionType.CREATE
        )
        self.assertEqual(self.audit_trail.object_id, self.account.pk)
        self.assertEqual(self.audit_trail.reason, "Created test account")
        self.assertEqual(self.audit_trail.ip_address, "127.0.0.1")
        self.assertEqual(self.audit_trail.user_agent, "Test Browser")

    def test_audit_trail_str_representation(self):
        """Test audit trail string representation"""
        expected = f"{self.user} performed CREATE on {self.account} at {self.audit_trail.timestamp}"
        self.assertEqual(str(self.audit_trail), expected)

    def test_audit_trail_ordering(self):
        """Test audit trail ordering"""
        # Create another audit trail
        audit2 = AccountingAuditTrail.objects.create(
            user=self.user,
            action=AccountingAuditTrail.ActionType.UPDATE,
            content_type=self.account._meta.get_field(
                "content_type"
            ).remote_field.model.objects.get_for_model(self.account),
            object_id=self.account.pk,
            reason="Updated test account",
        )

        trails = AccountingAuditTrail.objects.all()
        # Should be ordered by timestamp descending
        self.assertEqual(trails[0].action, AccountingAuditTrail.ActionType.UPDATE)
        self.assertEqual(trails[1].action, AccountingAuditTrail.ActionType.CREATE)

    def test_log_action_classmethod(self):
        """Test log_action class method"""
        # Create a new account to log
        new_account = AccountFactory.create_account(
            "New Account", "1002", Account.AccountType.LIABILITY
        )

        # Log the action
        trail = AccountingAuditTrail.log_action(
            user=self.user,
            action=AccountingAuditTrail.ActionType.CREATE,
            instance=new_account,
            reason="Test log_action",
        )

        # Verify the trail was created (note: due to transaction.on_commit,
        # this might not be immediately available in tests)
        self.assertIsNotNone(trail)
