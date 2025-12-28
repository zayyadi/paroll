"""
Integration tests for complete workflows.
Tests end-to-end functionality and system integration.
"""

from decimal import Decimal

# from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.db import models
from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from accounting.utils import (
    get_trial_balance,
    get_account_balance,
    get_general_ledger,
    close_period,
    close_fiscal_year,
)
from accounting.tests.fixtures import (
    UserFactory,
    AccountFactory,
    FiscalYearFactory,
    JournalFactory,
    CompleteTestDataFactory,
)

User = get_user_model()


class PayrollAccountingIntegrationTest(TestCase):
    """Test payroll transaction integration with accounting"""

    def setUp(self):
        """Set up test data"""
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()
        self.auditor = UserFactory.create_auditor()

        # Create complete test dataset
        self.test_data = CompleteTestDataFactory.create_complete_test_dataset()

    def test_payroll_journal_creation(self):
        """Test payroll journal creation and accounting entries"""
        # Create payroll journal
        payroll_journal = JournalFactory.create_payroll_journal(
            gross_pay=5000, user=self.payroll_processor
        )

        # Verify journal was created
        self.assertIsNotNone(payroll_journal.pk)
        self.assertEqual(payroll_journal.description, "Payroll Journal")

        # Verify entries were created
        self.assertEqual(payroll_journal.entries.count(), 4)

        # Check entry types and amounts
        entries = payroll_journal.entries.all()
        debits = entries.filter(entry_type=JournalEntry.EntryType.DEBIT)
        credits = entries.filter(entry_type=JournalEntry.EntryType.CREDIT)

        self.assertEqual(debits.count(), 2)  # Salaries + Payroll Tax
        self.assertEqual(credits.count(), 2)  # Cash + Taxes Payable

        # Verify amounts
        salaries_expense = debits.filter(account__account_number="5000").first()
        self.assertEqual(salaries_expense.amount, Decimal("5000"))

        payroll_tax_expense = debits.filter(account__account_number="5500").first()
        self.assertEqual(payroll_tax_expense.amount, Decimal("750"))  # 15% of 5000

        cash_credit = credits.filter(account__account_number="1000").first()
        self.assertEqual(cash_credit.amount, Decimal("4250"))  # 5000 - 750

        taxes_payable = credits.filter(account__account_number="2200").first()
        self.assertEqual(taxes_payable.amount, Decimal("750"))

    def test_payroll_journal_approval_workflow(self):
        """Test payroll journal approval workflow"""
        # Create payroll journal
        payroll_journal = JournalFactory.create_payroll_journal(
            gross_pay=5000, user=self.payroll_processor
        )

        # Submit for approval
        payroll_journal.submit_for_approval()
        self.assertEqual(payroll_journal.status, Journal.JournalStatus.PENDING_APPROVAL)

        # Approve by accountant
        payroll_journal.approve(self.accountant)
        self.assertEqual(payroll_journal.status, Journal.JournalStatus.APPROVED)
        self.assertEqual(payroll_journal.approved_by, self.accountant)

        # Post by accountant
        payroll_journal.post(self.accountant)
        self.assertEqual(payroll_journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(payroll_journal.posted_by, self.accountant)

    def test_payroll_journal_permissions(self):
        """Test payroll journal permissions"""
        # Create payroll journal
        payroll_journal = JournalFactory.create_payroll_journal(
            gross_pay=5000, user=self.payroll_processor
        )

        # Payroll processor can modify their own journal
        payroll_journal.description = "Updated Payroll Journal"
        payroll_journal.save()
        self.assertEqual(payroll_journal.description, "Updated Payroll Journal")

        # Accountant can also modify
        payroll_journal.description = "Accountant Updated"
        payroll_journal.save()
        self.assertEqual(payroll_journal.description, "Accountant Updated")

        # Auditor can view but not modify
        self.assertIsNotNone(payroll_journal.pk)
        # (Permission tests are in test_permissions.py)


class JournalWorkflowIntegrationTest(TestCase):
    """Test complete journal workflow integration"""

    def setUp(self):
        """Set up test data"""
        self.accountant = UserFactory.create_accountant()
        self.auditor = UserFactory.create_auditor()

        # Create test data
        self.test_data = CompleteTestDataFactory.create_complete_test_dataset()

    def test_complete_journal_lifecycle(self):
        """Test complete journal lifecycle from creation to reversal"""
        # Create journal
        journal = JournalFactory.create_journal_with_entries(
            "Lifecycle Test", 2000, user=self.accountant
        )

        # Verify initial state
        self.assertEqual(journal.status, Journal.JournalStatus.DRAFT)
        self.assertEqual(journal.entries.count(), 2)

        # Submit for approval
        journal.submit_for_approval()
        self.assertEqual(journal.status, Journal.JournalStatus.PENDING_APPROVAL)

        # Approve
        journal.approve(self.accountant)
        self.assertEqual(journal.status, Journal.JournalStatus.APPROVED)
        self.assertIsNotNone(journal.approved_at)

        # Post
        journal.post(self.accountant)
        self.assertEqual(journal.status, Journal.JournalStatus.POSTED)
        self.assertIsNotNone(journal.posted_at)

        # Reverse
        reversal_journal = journal.reverse(self.accountant, "Test reversal")
        self.assertEqual(journal.status, Journal.JournalStatus.REVERSED)
        self.assertEqual(reversal_journal.status, Journal.JournalStatus.POSTED)

        # Verify reversal entries
        self.assertEqual(reversal_journal.entries.count(), 2)

        # Check that entries are opposite
        original_entries = journal.entries.all()
        reversal_entries = reversal_journal.entries.all()

        for orig_entry in original_entries:
            rev_entry = reversal_entries.filter(account=orig_entry.account).first()
            self.assertIsNotNone(rev_entry)
            self.assertEqual(
                rev_entry.entry_type,
                (
                    JournalEntry.EntryType.CREDIT
                    if orig_entry.entry_type == JournalEntry.EntryType.DEBIT
                    else JournalEntry.EntryType.DEBIT
                ),
            )
            self.assertEqual(rev_entry.amount, orig_entry.amount)

    def test_journal_reversal_with_correction(self):
        """Test journal reversal with correction workflow"""
        # Create and post journal
        journal = JournalFactory.create_posted_journal("Original", 1000)

        # Create correction entries
        correction_entries = [
            {
                "account": Account.objects.get(account_number="1000"),  # Cash
                "entry_type": JournalEntry.EntryType.DEBIT,
                "amount": Decimal("1200"),
                "memo": "Corrected amount",
            },
            {
                "account": Account.objects.get(account_number="4000"),  # Revenue
                "entry_type": JournalEntry.EntryType.CREDIT,
                "amount": Decimal("1200"),
                "memo": "Corrected amount",
            },
        ]

        # Perform reversal with correction
        from accounting.utils import reverse_journal_with_correction

        reversal_journal, correction_journal = reverse_journal_with_correction(
            journal, self.accountant, "Amount correction needed", correction_entries
        )

        # Verify results
        self.assertEqual(journal.status, Journal.JournalStatus.REVERSED)
        self.assertEqual(reversal_journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(correction_journal.status, Journal.JournalStatus.POSTED)

        # Verify correction entries
        self.assertEqual(correction_journal.entries.count(), 2)

        # Check amounts
        cash_entry = correction_journal.entries.get(account__account_number="1000")
        self.assertEqual(cash_entry.amount, Decimal("1200"))
        self.assertEqual(cash_entry.entry_type, JournalEntry.EntryType.DEBIT)

    def test_batch_journal_operations(self):
        """Test batch journal operations"""
        # Create multiple journals
        journals = []
        for i in range(3):
            journal = JournalFactory.create_posted_journal(
                f"Batch Test {i+1}", 1000 * (i + 1)
            )
            journals.append(journal)

        # Perform batch reversal
        from accounting.utils import reverse_batch_journals

        results = reverse_batch_journals(journals, self.accountant, "Batch reversal")

        # Verify results
        self.assertEqual(len(results["reversal_journals"]), 3)
        self.assertEqual(len(results["failed_journals"]), 0)

        # Check all journals are reversed
        for journal in journals:
            journal.refresh_from_db()
            self.assertEqual(journal.status, Journal.JournalStatus.REVERSED)

    def test_partial_journal_reversal(self):
        """Test partial journal reversal workflow"""
        # Create journal with multiple entries
        journal = JournalFactory.create_journal("Partial Test")

        # Add multiple entries
        cash = Account.objects.get(account_number="1000")
        revenue = Account.objects.get(account_number="4000")
        expense = Account.objects.get(account_number="5000")

        entry1 = JournalEntry.objects.create(
            journal=journal,
            account=cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )
        JournalEntry.objects.create(
            journal=journal,
            account=revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("800"),
        )
        entry3 = JournalEntry.objects.create(
            journal=journal,
            account=expense,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("200"),
        )

        # Post journal
        journal.status = Journal.JournalStatus.APPROVED
        journal.save()
        journal.post(self.accountant)

        # Perform partial reversal
        from accounting.utils import reverse_journal_partial

        reversal_journal = reverse_journal_partial(
            journal, self.accountant, "Partial reversal", [entry1.pk, entry3.pk]
        )

        # Verify results
        self.assertEqual(journal.status, Journal.JournalStatus.POSTED)  # Still posted
        self.assertEqual(reversal_journal.status, Journal.JournalStatus.POSTED)

        # Verify reversal entries (should only have 2 entries)
        self.assertEqual(reversal_journal.entries.count(), 2)

        # Check that only specified entries were reversed
        cash_rev = reversal_journal.entries.filter(account=cash).first()
        self.assertIsNotNone(cash_rev)
        self.assertEqual(cash_rev.entry_type, JournalEntry.EntryType.CREDIT)
        self.assertEqual(cash_rev.amount, Decimal("1000"))

        expense_rev = reversal_journal.entries.filter(account=expense).first()
        self.assertIsNotNone(expense_rev)
        self.assertEqual(expense_rev.entry_type, JournalEntry.EntryType.CREDIT)
        self.assertEqual(expense_rev.amount, Decimal("200"))

        # Revenue entry should not be reversed
        revenue_rev = reversal_journal.entries.filter(account=revenue).first()
        self.assertIsNone(revenue_rev)


class PeriodAndFiscalYearIntegrationTest(TestCase):
    """Test period and fiscal year management integration"""

    def setUp(self):
        """Set up test data"""
        self.accountant = UserFactory.create_accountant()
        self.auditor = UserFactory.create_auditor()

        # Create fiscal year
        self.fiscal_year = FiscalYearFactory.create_fiscal_year(2023)

    def test_period_lifecycle(self):
        """Test complete period lifecycle"""
        # Get current period
        period = AccountingPeriod.objects.filter(
            fiscal_year=self.fiscal_year, period_number=timezone.now().month
        ).first()

        # Create journals in period
        journal1 = JournalFactory.create_journal_with_entries("Period Test 1", 1000)
        journal1.period = period
        journal1.save()

        journal2 = JournalFactory.create_journal_with_entries("Period Test 2", 2000)
        journal2.period = period
        journal2.save()

        # Post journals
        journal1.post(self.accountant)
        journal2.post(self.accountant)

        # Verify period data
        posted_journals = period.journals.filter(status=Journal.JournalStatus.POSTED)
        self.assertEqual(posted_journals.count(), 2)

        # Close period
        close_period(period, self.accountant)

        # Verify period is closed
        period.refresh_from_db()
        self.assertTrue(period.is_closed)
        self.assertEqual(period.closed_by, self.accountant)
        self.assertIsNotNone(period.closed_at)

        # Verify audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CLOSE_PERIOD, object_id=period.pk
        ).first()
        self.assertIsNotNone(audit_trail)

    def test_fiscal_year_lifecycle(self):
        """Test complete fiscal year lifecycle"""
        # Create journals in multiple periods
        for period in self.fiscal_year.periods.all()[:3]:  # First 3 periods
            journal = JournalFactory.create_journal_with_entries(
                f"FY Test {period.period_number}", 1000
            )
            journal.period = period
            journal.save()
            journal.post(self.accountant)

        # Close all periods
        for period in self.fiscal_year.periods.all():
            if not period.is_closed:
                close_period(period, self.accountant)

        # Close fiscal year
        close_fiscal_year(self.fiscal_year, self.accountant)

        # Verify fiscal year is closed
        self.fiscal_year.refresh_from_db()
        self.assertTrue(self.fiscal_year.is_closed)
        self.assertEqual(self.fiscal_year.closed_by, self.accountant)
        self.assertIsNotNone(self.fiscal_year.closed_at)

        # Verify audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
            object_id=self.fiscal_year.pk,
        ).first()
        self.assertIsNotNone(audit_trail)

    def test_cross_period_reporting(self):
        """Test reporting across multiple periods"""
        # Create journals in different periods
        periods = list(self.fiscal_year.periods.all()[:3])

        for i, period in enumerate(periods):
            journal = JournalFactory.create_journal_with_entries(
                f"Cross Period {i+1}", 1000 * (i + 1)
            )
            journal.period = period
            journal.save()
            journal.post(self.accountant)

        # Get trial balance for fiscal year
        trial_balance = get_trial_balance(None)  # All periods

        # Should have entries from all periods
        total_debits = sum(item["debit_total"] for item in trial_balance)
        total_credits = sum(item["credit_total"] for item in trial_balance)

        self.assertEqual(total_debits, total_credits)
        self.assertEqual(total_debits, Decimal("6000"))  # 1000 + 2000 + 3000


class ReportingIntegrationTest(TestCase):
    """Test reporting functionality integration"""

    def setUp(self):
        """Set up test data"""
        self.accountant = UserFactory.create_accountant()
        self.auditor = UserFactory.create_auditor()

        # Create test data
        self.test_data = CompleteTestDataFactory.create_complete_test_dataset()

    def test_trial_balance_integration(self):
        """Test trial balance with real data"""
        # Get trial balance
        trial_balance = get_trial_balance()

        # Verify trial balance properties
        self.assertGreater(len(trial_balance), 0)

        # Check that debits equal credits
        total_debits = sum(item["debit_total"] for item in trial_balance)
        total_credits = sum(item["credit_total"] for item in trial_balance)
        self.assertEqual(total_debits, total_credits)

        # Check balance calculations
        for item in trial_balance:
            if item["balance_type"] == "debit":
                self.assertEqual(
                    item["balance"], item["debit_total"] - item["credit_total"]
                )
            else:
                self.assertEqual(
                    item["balance"], item["credit_total"] - item["debit_total"]
                )

    def test_account_activity_integration(self):
        """Test account activity reporting"""
        # Get an account with activity
        cash_account = Account.objects.get(account_number="1000")

        # Get general ledger for cash account
        ledger = get_general_ledger(cash_account)

        # Verify ledger properties
        self.assertGreater(len(ledger), 0)

        # Check that entries are properly ordered
        for i in range(len(ledger) - 1):
            self.assertLessEqual(ledger[i]["date"], ledger[i + 1]["date"])

        # Verify entry details
        for entry in ledger:
            self.assertIn("entry_type", entry)
            self.assertIn("amount", entry)
            self.assertIn("description", entry)
            self.assertIn("date", entry)

    def test_multi_period_reporting(self):
        """Test reporting across multiple periods"""
        # Get current fiscal year
        fiscal_year = FiscalYear.objects.filter(is_active=True).first()

        # Create journals in multiple periods
        periods = fiscal_year.periods.all()[:2]
        for period in periods:
            journal = JournalFactory.create_journal_with_entries(
                f"Multi Period {period.period_number}", 1500
            )
            journal.period = period
            journal.save()
            journal.post(self.accountant)

        # Get trial balance for specific period
        first_period = periods[0]
        period_trial_balance = get_trial_balance(first_period)

        # Get trial balance for all periods
        all_trial_balance = get_trial_balance()

        # Period trial balance should have fewer entries
        self.assertLess(len(period_trial_balance), len(all_trial_balance))

        # Both should balance
        period_debits = sum(item["debit_total"] for item in period_trial_balance)
        period_credits = sum(item["credit_total"] for item in period_trial_balance)
        self.assertEqual(period_debits, period_credits)

        all_debits = sum(item["debit_total"] for item in all_trial_balance)
        all_credits = sum(item["credit_total"] for item in all_trial_balance)
        self.assertEqual(all_debits, all_credits)


class AuditTrailIntegrationTest(TestCase):
    """Test audit trail functionality integration"""

    def setUp(self):
        """Set up test data"""
        self.accountant = UserFactory.create_accountant()
        self.auditor = UserFactory.create_auditor()

    def test_complete_audit_trail_workflow(self):
        """Test audit trail throughout complete workflow"""
        # Create account
        account = AccountFactory.create_account(
            "Audit Test Account", "9999", Account.AccountType.ASSET
        )

        # Create journal
        journal = JournalFactory.create_journal("Audit Test Journal")

        # Add entry
        JournalEntry.objects.create(
            journal=journal,
            account=account,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )

        # Submit, approve, and post
        journal.submit_for_approval()
        journal.approve(self.accountant)
        journal.post(self.accountant)

        # Reverse
        reversal_journal = journal.reverse(self.accountant, "Audit test reversal")

        # Force transaction to commit
        transaction.commit()

        # Get audit trail for journal
        journal_audit = AccountingAuditTrail.objects.filter(
            content_type=ContentType.objects.get_for_model(journal),
            object_id=journal.pk,
        ).order_by("timestamp")

        # Should have entries for all operations
        actions = [entry.action for entry in journal_audit]
        self.assertIn(AccountingAuditTrail.ActionType.CREATE, actions)
        self.assertIn(AccountingAuditTrail.ActionType.APPROVE, actions)
        self.assertIn(AccountingAuditTrail.ActionType.POST, actions)
        self.assertIn(AccountingAuditTrail.ActionType.REVERSE, actions)

        # Get audit trail for account
        account_audit = AccountingAuditTrail.objects.filter(
            content_type=ContentType.objects.get_for_model(account),
            object_id=account.pk,
        ).order_by("timestamp")

        # Should have entry for account creation
        account_actions = [entry.action for entry in account_audit]
        self.assertIn(AccountingAuditTrail.ActionType.CREATE, account_actions)

    def test_audit_trail_data_integrity(self):
        """Test audit trail data integrity"""
        # Create and modify account
        account = AccountFactory.create_account(
            "Integrity Test", "8888", Account.AccountType.ASSET
        )

        # Modify account
        account.name = "Modified Integrity Test"
        account.description = "Modified description"
        account.save()

        # Force transaction to commit
        transaction.commit()

        # Get audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            content_type=ContentType.objects.get_for_model(account),
            object_id=account.pk,
        ).order_by("timestamp")

        # Should have CREATE and UPDATE entries
        create_entry = audit_trail.filter(
            action=AccountingAuditTrail.ActionType.CREATE
        ).first()
        update_entry = audit_trail.filter(
            action=AccountingAuditTrail.ActionType.UPDATE
        ).first()

        self.assertIsNotNone(create_entry)
        self.assertIsNotNone(update_entry)

        # Check update entry has changes
        self.assertIn("name", update_entry.changes)
        self.assertIn("description", update_entry.changes)

        # Check old and new values
        name_change = update_entry.changes["name"]
        self.assertEqual(name_change["old"], "Integrity Test")
        self.assertEqual(name_change["new"], "Modified Integrity Test")


class SystemIntegrationTest(TestCase):
    """Test overall system integration"""

    def setUp(self):
        """Set up test data"""
        self.test_data = CompleteTestDataFactory.create_complete_test_dataset()

    def test_complete_accounting_system_workflow(self):
        """Test complete accounting system workflow"""
        # Get test data
        users = self.test_data["users"]
        accounts = self.test_data["accounts"]
        journals = self.test_data["journals"]

        # Verify users have correct roles
        self.assertIsNotNone(users["auditor"])
        self.assertIsNotNone(users["accountant"])
        self.assertIsNotNone(users["payroll_processor"])

        # Verify accounts were created
        self.assertGreater(len(accounts), 0)

        # Verify journals were created
        self.assertEqual(journals["cash_sale"].status, Journal.JournalStatus.DRAFT)
        self.assertEqual(journals["payroll"].status, Journal.JournalStatus.DRAFT)
        self.assertEqual(journals["expense"].status, Journal.JournalStatus.DRAFT)
        self.assertEqual(journals["posted"].status, Journal.JournalStatus.POSTED)
        self.assertEqual(journals["reversal"].status, Journal.JournalStatus.POSTED)

        # Verify reversal relationship
        self.assertEqual(journals["reversal"].reversed_journal, journals["posted"])
        self.assertEqual(journals["posted"].status, Journal.JournalStatus.REVERSED)

        # Test trial balance
        trial_balance = get_trial_balance()
        self.assertGreater(len(trial_balance), 0)

        # Test account balances
        for account in accounts[:5]:  # Test first 5 accounts
            balance = get_account_balance(account)
            self.assertIsInstance(balance, Decimal)

        # Test audit trail
        audit_trail = AccountingAuditTrail.objects.all()
        self.assertGreater(len(audit_trail), 0)

    def test_multi_user_workflow(self):
        """Test workflow with multiple users"""
        users = self.test_data["users"]

        # Payroll processor creates payroll journal
        payroll_journal = JournalFactory.create_payroll_journal(
            gross_pay=6000, user=users["payroll_processor"]
        )

        # Accountant reviews and approves
        payroll_journal.submit_for_approval()
        payroll_journal.approve(users["accountant"])
        payroll_journal.post(users["accountant"])

        # Auditor reviews audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            content_type=ContentType.objects.get_for_model(payroll_journal),
            object_id=payroll_journal.pk,
        )

        # Auditor should be able to see all operations
        self.assertGreater(len(audit_trail), 0)

        # Verify all users can access appropriate data
        # (Detailed permission tests are in test_permissions.py)
        self.assertIsNotNone(users["auditor"])
        self.assertIsNotNone(users["accountant"])
        self.assertIsNotNone(users["payroll_processor"])

    def test_data_integrity_throughout_workflow(self):
        """Test data integrity throughout complete workflow"""
        # Create complex journal
        journal = JournalFactory.create_journal("Integrity Test")

        # Add multiple entries
        cash = Account.objects.get(account_number="1000")
        revenue = Account.objects.get(account_number="4000")
        expense = Account.objects.get(account_number="5000")

        JournalEntry.objects.create(
            journal=journal,
            account=cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("2000"),
        )
        JournalEntry.objects.create(
            journal=journal,
            account=revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("1500"),
        )
        JournalEntry.objects.create(
            journal=journal,
            account=expense,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("500"),
        )

        # Verify journal is balanced
        debits = journal.entries.filter(
            entry_type=JournalEntry.EntryType.DEBIT
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
        credits = journal.entries.filter(
            entry_type=JournalEntry.EntryType.CREDIT
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
        self.assertEqual(debits, credits)
        self.assertEqual(debits, Decimal("2500"))

        # Post journal
        journal.approve(self.test_data["users"]["accountant"])
        journal.post(self.test_data["users"]["accountant"])

        # Verify account balances
        cash_balance = get_account_balance(cash)
        revenue_balance = get_account_balance(revenue)
        expense_balance = get_account_balance(expense)

        # Cash (asset): debits increase balance
        self.assertEqual(cash_balance, Decimal("2000"))

        # Revenue (revenue): credits increase balance
        self.assertEqual(revenue_balance, Decimal("1500"))

        # Expense (expense): debits increase balance
        self.assertEqual(expense_balance, Decimal("500"))

        # Verify trial balance still balances
        trial_balance = get_trial_balance()
        total_debits = sum(item["debit_total"] for item in trial_balance)
        total_credits = sum(item["credit_total"] for item in trial_balance)
        self.assertEqual(total_debits, total_credits)
