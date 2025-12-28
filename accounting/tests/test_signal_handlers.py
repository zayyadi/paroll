"""
Signal handler tests for audit trail functionality.
Tests all signal handlers and audit trail logging.
"""

from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from accounting.signal_handlers import (
    log_journal_approval,
    log_journal_posting,
    log_journal_reversal,
    log_period_closure,
    log_fiscal_year_closure,
    log_partial_journal_reversal,
    log_journal_reversal_with_correction,
    log_batch_journal_reversal,
)
from accounting.tests.fixtures import (
    UserFactory,
    AccountFactory,
    FiscalYearFactory,
    JournalFactory,
)

User = get_user_model()


class AccountSignalHandlerTest(TestCase):
    """Test cases for account signal handlers"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()

    def test_account_creation_signal(self):
        """Test account creation signal handler"""
        # Create account
        account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )

        # Check audit trail was created (note: due to transaction.on_commit,
        # we need to commit the transaction first)
        with transaction.atomic():
            account.save()

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=ContentType.objects.get_for_model(account),
            object_id=account.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.CREATE)

    def test_account_update_signal(self):
        """Test account update signal handler"""
        # Create account first
        account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )

        # Update account
        account.name = "Updated Account"
        account.description = "Updated description"
        with transaction.atomic():
            account.save()

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.UPDATE,
            content_type=ContentType.objects.get_for_model(account),
            object_id=account.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.UPDATE)

        # Check changes were recorded
        changes = audit_trail.changes
        self.assertIn("name", changes)
        self.assertIn("description", changes)

    def test_account_delete_signal(self):
        """Test account deletion signal handler"""
        # Create account first
        account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )
        account_pk = account.pk

        # Delete account
        with transaction.atomic():
            account.delete()

        # Force transaction to commit
        transaction.commit()

        # Check audit trail (note: object_id should still be available)
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.DELETE,
            content_type=ContentType.objects.get_for_model(Account),
            object_id=account_pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.DELETE)


class FiscalYearSignalHandlerTest(TestCase):
    """Test cases for fiscal year signal handlers"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_admin()

    def test_fiscal_year_creation_signal(self):
        """Test fiscal year creation signal handler"""
        # Create fiscal year
        fiscal_year = FiscalYear.objects.create(
            year=2024,
            name="FY 2024",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            is_active=True,
        )

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=ContentType.objects.get_for_model(fiscal_year),
            object_id=fiscal_year.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.CREATE)

    def test_fiscal_year_update_signal(self):
        """Test fiscal year update signal handler"""
        # Create fiscal year first
        fiscal_year = FiscalYear.objects.create(
            year=2024,
            name="FY 2024",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            is_active=True,
        )

        # Update fiscal year
        fiscal_year.name = "Updated FY 2024"
        with transaction.atomic():
            fiscal_year.save()

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.UPDATE,
            content_type=ContentType.objects.get_for_model(fiscal_year),
            object_id=fiscal_year.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.UPDATE)

    def test_fiscal_year_closure_signal(self):
        """Test fiscal year closure signal handler"""
        # Create fiscal year with closed periods
        fiscal_year = FiscalYearFactory.create_fiscal_year(2024)

        # Close all periods
        for period in fiscal_year.periods.all():
            period.is_closed = True
            period.save()

        # Close fiscal year
        with transaction.atomic():
            fiscal_year.close(self.user)

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
            content_type=ContentType.objects.get_for_model(fiscal_year),
            object_id=fiscal_year.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(
            audit_trail.action, AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR
        )


class AccountingPeriodSignalHandlerTest(TestCase):
    """Test cases for accounting period signal handlers"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_admin()
        self.fiscal_year = FiscalYearFactory.create_fiscal_year(2024)

    def test_period_creation_signal(self):
        """Test period creation signal handler"""
        # Create period
        period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=13,
            name="Adjustment Period",
            start_date=date(2024, 12, 31),
            end_date=date(2024, 12, 31),
            is_active=False,
        )

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=ContentType.objects.get_for_model(period),
            object_id=period.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.CREATE)

    def test_period_closure_signal(self):
        """Test period closure signal handler"""
        # Create period
        period = AccountingPeriod.objects.filter(fiscal_year=self.fiscal_year).first()

        # Close period
        with transaction.atomic():
            period.close(self.user)

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CLOSE_PERIOD,
            content_type=ContentType.objects.get_for_model(period),
            object_id=period.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(
            audit_trail.action, AccountingAuditTrail.ActionType.CLOSE_PERIOD
        )


class JournalSignalHandlerTest(TestCase):
    """Test cases for journal signal handlers"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()

    def test_journal_creation_signal(self):
        """Test journal creation signal handler"""
        # Create journal
        journal = JournalFactory.create_journal("Test Journal")

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=ContentType.objects.get_for_model(journal),
            object_id=journal.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.CREATE)

    def test_journal_approval_signal(self):
        """Test journal approval signal handler"""
        # Create and approve journal
        journal = JournalFactory.create_journal("Test Journal")
        journal.status = Journal.JournalStatus.PENDING_APPROVAL
        journal.save()

        # Approve journal
        with transaction.atomic():
            journal.approve(self.user)

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.APPROVE,
            content_type=ContentType.objects.get_for_model(journal),
            object_id=journal.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.APPROVE)

    def test_journal_posting_signal(self):
        """Test journal posting signal handler"""
        # Create, approve, and post journal
        journal = JournalFactory.create_journal_with_entries("Test Journal", 1000)
        journal.approve(self.user)

        # Post journal
        with transaction.atomic():
            journal.post(self.user)

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.POST,
            content_type=ContentType.objects.get_for_model(journal),
            object_id=journal.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.POST)

    def test_journal_reversal_signal(self):
        """Test journal reversal signal handler"""
        # Create and post journal
        journal = JournalFactory.create_posted_journal("Test Journal", 1000)

        # Reverse journal
        with transaction.atomic():
            journal.reverse(self.user, "Test reversal")

        # Force transaction to commit
        transaction.commit()

        # Check audit trail for reversal
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.REVERSE,
            content_type=ContentType.objects.get_for_model(journal),
            object_id=journal.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.REVERSE)


class JournalEntrySignalHandlerTest(TestCase):
    """Test cases for journal entry signal handlers"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()
        self.journal = JournalFactory.create_journal("Test Journal")

    def test_journal_entry_creation_signal(self):
        """Test journal entry creation signal handler"""
        # Create account
        account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )

        # Create entry
        entry = JournalEntry.objects.create(
            journal=self.journal,
            account=account,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
            memo="Test entry",
        )

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=ContentType.objects.get_for_model(entry),
            object_id=entry.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.CREATE)

    def test_journal_entry_update_signal(self):
        """Test journal entry update signal handler"""
        # Create account and entry
        account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )
        entry = JournalEntry.objects.create(
            journal=self.journal,
            account=account,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
            memo="Test entry",
        )

        # Update entry
        entry.memo = "Updated memo"
        entry.amount = Decimal("1500")
        with transaction.atomic():
            entry.save()

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.UPDATE,
            content_type=ContentType.objects.get_for_model(entry),
            object_id=entry.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.UPDATE)

    def test_journal_entry_deletion_signal(self):
        """Test journal entry deletion signal handler"""
        # Create account and entry
        account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )
        entry = JournalEntry.objects.create(
            journal=self.journal,
            account=account,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
            memo="Test entry",
        )
        entry_pk = entry.pk

        # Delete entry
        with transaction.atomic():
            entry.delete()

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.DELETE,
            content_type=ContentType.objects.get_for_model(JournalEntry),
            object_id=entry_pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.DELETE)


class CustomLoggingFunctionTest(TestCase):
    """Test cases for custom logging functions"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()
        self.journal = JournalFactory.create_posted_journal("Test Journal", 1000)

    def test_log_journal_approval_function(self):
        """Test journal approval logging function"""
        # Approve journal
        self.journal.status = Journal.JournalStatus.APPROVED
        self.journal.save()

        # Log approval
        with transaction.atomic():
            log_journal_approval(self.journal, self.user, "Test approval")

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.APPROVE,
            content_type=ContentType.objects.get_for_model(self.journal),
            object_id=self.journal.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.APPROVE)
        self.assertEqual(audit_trail.reason, "Test approval")

    def test_log_journal_posting_function(self):
        """Test journal posting logging function"""
        # Log posting
        with transaction.atomic():
            log_journal_posting(self.journal, self.user, "Test posting")

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.POST,
            content_type=ContentType.objects.get_for_model(self.journal),
            object_id=self.journal.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.POST)
        self.assertEqual(audit_trail.reason, "Test posting")

    def test_log_journal_reversal_function(self):
        """Test journal reversal logging function"""
        # Create reversal journal
        reversal_journal = self.journal.reverse(self.user, "Test reversal")

        # Log reversal
        with transaction.atomic():
            log_journal_reversal(
                self.journal, reversal_journal, self.user, "Test reversal"
            )

        # Force transaction to commit
        transaction.commit()

        # Check audit trail for original journal
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.REVERSE,
            content_type=ContentType.objects.get_for_model(self.journal),
            object_id=self.journal.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.REVERSE)
        self.assertEqual(audit_trail.reason, "Test reversal")

    def test_log_period_closure_function(self):
        """Test period closure logging function"""
        # Create period
        fiscal_year = FiscalYearFactory.create_fiscal_year(2024)
        period = AccountingPeriod.objects.filter(fiscal_year=fiscal_year).first()

        # Log closure
        with transaction.atomic():
            log_period_closure(period, self.user, "Test period closure")

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CLOSE_PERIOD,
            content_type=ContentType.objects.get_for_model(period),
            object_id=period.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(
            audit_trail.action, AccountingAuditTrail.ActionType.CLOSE_PERIOD
        )
        self.assertEqual(audit_trail.reason, "Test period closure")

    def test_log_fiscal_year_closure_function(self):
        """Test fiscal year closure logging function"""
        # Create fiscal year
        fiscal_year = FiscalYearFactory.create_fiscal_year(2024)

        # Log closure
        with transaction.atomic():
            log_fiscal_year_closure(fiscal_year, self.user, "Test fiscal year closure")

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
            content_type=ContentType.objects.get_for_model(fiscal_year),
            object_id=fiscal_year.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(
            audit_trail.action, AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR
        )
        self.assertEqual(audit_trail.reason, "Test fiscal year closure")

    def test_log_partial_journal_reversal_function(self):
        """Test partial journal reversal logging function"""
        # Create reversal journal
        entry = self.journal.entries.first()
        reversal_journal = JournalFactory.create_journal("Partial Reversal")

        # Log partial reversal
        with transaction.atomic():
            log_partial_journal_reversal(
                self.journal,
                reversal_journal,
                self.user,
                "Partial reversal",
                entry_ids=[entry.pk],
                amounts={entry.pk: Decimal("500")},
            )

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.REVERSE,
            content_type=ContentType.objects.get_for_model(self.journal),
            object_id=self.journal.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.REVERSE)
        self.assertEqual(audit_trail.reason, "Partial reversal")

        # Check changes
        changes = audit_trail.changes
        self.assertEqual(changes["reversal_type"], "partial")
        self.assertEqual(changes["reversed_entries"], [entry.pk])

    def test_log_journal_reversal_with_correction_function(self):
        """Test journal reversal with correction logging function"""
        # Create reversal and correction journals
        reversal_journal = JournalFactory.create_journal("Reversal")
        correction_journal = JournalFactory.create_journal("Correction")

        # Log reversal with correction
        with transaction.atomic():
            log_journal_reversal_with_correction(
                self.journal,
                reversal_journal,
                correction_journal,
                self.user,
                "Reversal with correction",
            )

        # Force transaction to commit
        transaction.commit()

        # Check audit trail
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.REVERSE,
            content_type=ContentType.objects.get_for_model(self.journal),
            object_id=self.journal.pk,
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.REVERSE)
        self.assertEqual(audit_trail.reason, "Reversal with correction")

        # Check changes
        changes = audit_trail.changes
        self.assertEqual(changes["reversal_type"], "reversal_with_correction")
        self.assertEqual(changes["reversal_journal_id"], reversal_journal.pk)
        self.assertEqual(changes["correction_journal_id"], correction_journal.pk)

    def test_log_batch_journal_reversal_function(self):
        """Test batch journal reversal logging function"""
        # Create another journal
        journal2 = JournalFactory.create_posted_journal("Test Journal 2", 2000)

        # Create reversal journals
        reversal1 = JournalFactory.create_journal("Reversal 1")
        reversal2 = JournalFactory.create_journal("Reversal 2")

        # Log batch reversal
        with transaction.atomic():
            log_batch_journal_reversal(
                [self.journal, journal2],
                [reversal1, reversal2],
                self.user,
                "Batch reversal",
            )

        # Force transaction to commit
        transaction.commit()

        # Check audit trail (should be one entry for batch operation)
        audit_trail = AccountingAuditTrail.objects.filter(
            action=AccountingAuditTrail.ActionType.REVERSE, reason="Batch reversal"
        ).first()

        self.assertIsNotNone(audit_trail)
        self.assertEqual(audit_trail.action, AccountingAuditTrail.ActionType.REVERSE)

        # Check changes
        changes = audit_trail.changes
        self.assertEqual(changes["operation_type"], "batch_reversal")
        self.assertEqual(len(changes["reversed_journals"]), 2)


class SignalHandlerIntegrationTest(TestCase):
    """Integration tests for signal handlers"""

    def setUp(self):
        """Set up test data"""
        self.user = UserFactory.create_accountant()

    def test_complete_journal_workflow_audit_trail(self):
        """Test audit trail throughout complete journal workflow"""
        # Create journal
        journal = JournalFactory.create_journal("Workflow Test")

        # Add entries
        cash = AccountFactory.create_account("Cash", "1000", Account.AccountType.ASSET)
        revenue = AccountFactory.create_account(
            "Revenue", "4000", Account.AccountType.REVENUE
        )

        JournalEntry.objects.create(
            journal=journal,
            account=cash,
            entry_type=JournalEntry.EntryType.DEBIT,
            amount=Decimal("1000"),
        )
        JournalEntry.objects.create(
            journal=journal,
            account=revenue,
            entry_type=JournalEntry.EntryType.CREDIT,
            amount=Decimal("1000"),
        )

        # Submit for approval
        journal.submit_for_approval()

        # Approve
        journal.approve(self.user)

        # Post
        journal.post(self.user)

        # Reverse
        reversal_journal = journal.reverse(self.user, "Workflow reversal")

        # Force transaction to commit
        transaction.commit()

        # Check audit trail has all expected entries
        audit_trail = AccountingAuditTrail.objects.filter(
            content_type=ContentType.objects.get_for_model(journal)
        ).order_by("timestamp")

        # Should have entries for: CREATE, APPROVE, POST, REVERSE
        actions = [entry.action for entry in audit_trail]
        self.assertIn(AccountingAuditTrail.ActionType.CREATE, actions)
        self.assertIn(AccountingAuditTrail.ActionType.APPROVE, actions)
        self.assertIn(AccountingAuditTrail.ActionType.POST, actions)
        self.assertIn(AccountingAuditTrail.ActionType.REVERSE, actions)

    def test_error_handling_in_signal_handlers(self):
        """Test that signal handlers handle errors gracefully"""
        # Create journal with invalid data that might cause signal handler errors
        journal = JournalFactory.create_journal("Error Test")

        # The signal handler should not raise exceptions even if there are issues
        try:
            journal.save()
            transaction.commit()
        except Exception as e:
            self.fail(f"Signal handler raised exception: {e}")

        # Journal should still be saved
        self.assertIsNotNone(journal.pk)
