"""
Comprehensive tests for audit trail functionality.
This test suite ensures that all accounting operations are properly logged
to the audit trail with correct user attribution and metadata.
"""

from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.core.management import call_command

# from django.core.management.base import CommandError
from unittest.mock import MagicMock
from datetime import date
import json

from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from accounting.middleware import (
    AuditTrailMiddleware,
    set_audit_user,
    set_audit_metadata,
)

# from accounting.signal_handlers import (
#     log_journal_approval,
#     log_journal_posting,
#     log_journal_reversal,
#     log_period_closure,
#     log_fiscal_year_closure,
# )
from accounting.utils import (
    create_journal_with_entries,
    reverse_journal,
    post_journal,
    close_accounting_period,
    close_fiscal_year,
)

User = get_user_model()


class AuditTrailMiddlewareTest(TestCase):
    """Test the audit trail middleware functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.middleware = AuditTrailMiddleware(get_response=lambda r: None)

    def test_middleware_captures_user(self):
        """Test that middleware captures authenticated user."""
        from django.http import HttpRequest

        request = HttpRequest()
        request.user = self.user
        request.META = {"HTTP_USER_AGENT": "Test Browser"}

        self.middleware.process_request(request)

        # Check that user is captured
        from accounting.middleware import get_request_user

        captured_user = get_request_user()
        self.assertEqual(captured_user, self.user)

    def test_middleware_captures_ip_address(self):
        """Test that middleware captures IP address."""
        from django.http import HttpRequest

        request = HttpRequest()
        request.user = self.user
        request.META = {"REMOTE_ADDR": "192.168.1.1", "HTTP_USER_AGENT": "Test Browser"}

        self.middleware.process_request(request)

        # Check that IP address is captured
        from accounting.middleware import get_request_metadata

        ip_address, user_agent = get_request_metadata()
        self.assertEqual(ip_address, "192.168.1.1")
        self.assertEqual(user_agent, "Test Browser")

    def test_middleware_handles_x_forwarded_for(self):
        """Test that middleware handles X-Forwarded-For header."""
        from django.http import HttpRequest

        request = HttpRequest()
        request.user = self.user
        request.META = {
            "HTTP_X_FORWARDED_FOR": "10.0.0.1, 192.168.1.1",
            "HTTP_USER_AGENT": "Test Browser",
        }

        self.middleware.process_request(request)

        # Check that first IP is captured
        from accounting.middleware import get_request_metadata

        ip_address, user_agent = get_request_metadata()
        self.assertEqual(ip_address, "10.0.0.1")

    def test_middleware_cleanup(self):
        """Test that middleware cleans up thread-local storage."""
        from django.http import HttpRequest

        request = HttpRequest()
        request.user = self.user
        request.META = {"HTTP_USER_AGENT": "Test Browser"}

        self.middleware.process_request(request)

        # Verify data is stored
        from accounting.middleware import get_request_user

        self.assertIsNotNone(get_request_user())

        # Process response to clean up
        response = MagicMock()
        self.middleware.process_response(request, response)

        # Verify data is cleaned up
        self.assertIsNone(get_request_user())


class AccountAuditTrailTest(TransactionTestCase):
    """Test audit trail functionality for Account model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        set_audit_user(self.user)
        set_audit_metadata("192.168.1.1", "Test Browser")

    def test_account_creation_logged(self):
        """Test that account creation is logged to audit trail."""
        account = Account.objects.create(
            name="Test Account",
            account_number="1001",
            type=Account.AccountType.ASSET,
            description="Test account description",
        )

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(Account),
            object_id=account.pk,
            action=AccountingAuditTrail.ActionType.CREATE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.CREATE)
        self.assertEqual(audit_entry.ip_address, "192.168.1.1")
        self.assertEqual(audit_entry.user_agent, "Test Browser")
        self.assertIn("name", audit_entry.changes)
        self.assertEqual(audit_entry.changes["name"], "Test Account")

    def test_account_update_logged(self):
        """Test that account update is logged to audit trail."""
        account = Account.objects.create(
            name="Test Account", account_number="1001", type=Account.AccountType.ASSET
        )

        # Update the account
        account.description = "Updated description"
        account.save()

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(Account),
            object_id=account.pk,
            action=AccountingAuditTrail.ActionType.UPDATE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.UPDATE)
        self.assertIn("description", audit_entry.changes)
        self.assertEqual(audit_entry.changes["description"]["old"], None)
        self.assertEqual(
            audit_entry.changes["description"]["new"], "Updated description"
        )

    def test_account_deletion_logged(self):
        """Test that account deletion is logged to audit trail."""
        account = Account.objects.create(
            name="Test Account", account_number="1001", type=Account.AccountType.ASSET
        )
        account_id = account.pk

        # Delete the account
        account.delete()

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(Account),
            object_id=account_id,
            action=AccountingAuditTrail.ActionType.DELETE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.DELETE)


class FiscalYearAuditTrailTest(TransactionTestCase):
    """Test audit trail functionality for FiscalYear model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        set_audit_user(self.user)
        set_audit_metadata("192.168.1.1", "Test Browser")

    def test_fiscal_year_creation_logged(self):
        """Test that fiscal year creation is logged to audit trail."""
        fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(FiscalYear),
            object_id=fiscal_year.pk,
            action=AccountingAuditTrail.ActionType.CREATE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.CREATE)
        self.assertIn("year", audit_entry.changes)
        self.assertEqual(audit_entry.changes["year"], 2023)

    def test_fiscal_year_closure_logged(self):
        """Test that fiscal year closure is logged to audit trail."""
        fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )

        # Close the fiscal year
        fiscal_year.close(self.user)

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(FiscalYear),
            object_id=fiscal_year.pk,
            action=AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(
            audit_entry.action, AccountingAuditTrail.ActionType.CLOSE_FISCAL_YEAR
        )


class AccountingPeriodAuditTrailTest(TransactionTestCase):
    """Test audit trail functionality for AccountingPeriod model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )
        set_audit_user(self.user)
        set_audit_metadata("192.168.1.1", "Test Browser")

    def test_period_creation_logged(self):
        """Test that period creation is logged to audit trail."""
        period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="January",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_active=True,
        )

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(AccountingPeriod),
            object_id=period.pk,
            action=AccountingAuditTrail.ActionType.CREATE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.CREATE)
        self.assertIn("period_number", audit_entry.changes)
        self.assertEqual(audit_entry.changes["period_number"], 1)

    def test_period_closure_logged(self):
        """Test that period closure is logged to audit trail."""
        period = AccountingPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            period_number=1,
            name="January",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_active=True,
        )

        # Close the period
        period.close(self.user)

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(AccountingPeriod),
            object_id=period.pk,
            action=AccountingAuditTrail.ActionType.CLOSE_PERIOD,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(
            audit_entry.action, AccountingAuditTrail.ActionType.CLOSE_PERIOD
        )


class JournalAuditTrailTest(TransactionTestCase):
    """Test audit trail functionality for Journal model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
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
        self.account1 = Account.objects.create(
            name="Cash", account_number="1001", type=Account.AccountType.ASSET
        )
        self.account2 = Account.objects.create(
            name="Revenue", account_number="4001", type=Account.AccountType.REVENUE
        )
        set_audit_user(self.user)
        set_audit_metadata("192.168.1.1", "Test Browser")

    def test_journal_creation_logged(self):
        """Test that journal creation is logged to audit trail."""
        entries = [
            {
                "account": self.account1,
                "entry_type": "DEBIT",
                "amount": 1000,
                "memo": "Test debit entry",
            },
            {
                "account": self.account2,
                "entry_type": "CREDIT",
                "amount": 1000,
                "memo": "Test credit entry",
            },
        ]

        journal = create_journal_with_entries(
            date=date(2023, 1, 15),
            description="Test Journal",
            entries=entries,
            fiscal_year=self.fiscal_year,
            period=self.period,
            user=self.user,
        )

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(Journal),
            object_id=journal.pk,
            action=AccountingAuditTrail.ActionType.CREATE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.CREATE)
        self.assertIn("transaction_number", audit_entry.changes)

    def test_journal_approval_logged(self):
        """Test that journal approval is logged to audit trail."""
        journal = Journal.objects.create(
            description="Test Journal",
            date=date(2023, 1, 15),
            period=self.period,
            status=Journal.JournalStatus.PENDING_APPROVAL,
            created_by=self.user,
        )

        # Approve the journal
        journal.approve(self.user)

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(Journal),
            object_id=journal.pk,
            action=AccountingAuditTrail.ActionType.APPROVE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.APPROVE)

    def test_journal_posting_logged(self):
        """Test that journal posting is logged to audit trail."""
        journal = Journal.objects.create(
            description="Test Journal",
            date=date(2023, 1, 15),
            period=self.period,
            status=Journal.JournalStatus.APPROVED,
            created_by=self.user,
            approved_by=self.user,
            approved_at=timezone.now(),
        )

        # Post the journal
        journal.post(self.user)

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(Journal),
            object_id=journal.pk,
            action=AccountingAuditTrail.ActionType.POST,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.POST)

    def test_journal_reversal_logged(self):
        """Test that journal reversal is logged to audit trail."""
        # Create and post a journal first
        journal = Journal.objects.create(
            description="Original Journal",
            date=date(2023, 1, 15),
            period=self.period,
            status=Journal.JournalStatus.POSTED,
            created_by=self.user,
            approved_by=self.user,
            approved_at=timezone.now(),
            posted_by=self.user,
            posted_at=timezone.now(),
        )

        # Reverse the journal
        reversal_journal = journal.reverse(self.user, "Test reversal")

        # Check audit trail entries
        original_audit = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(Journal),
            object_id=journal.pk,
            action=AccountingAuditTrail.ActionType.REVERSE,
        )

        reversal_audit = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(Journal),
            object_id=reversal_journal.pk,
            action=AccountingAuditTrail.ActionType.CREATE,
        )

        self.assertEqual(original_audit.user, self.user)
        self.assertEqual(original_audit.action, AccountingAuditTrail.ActionType.REVERSE)
        self.assertEqual(reversal_audit.user, self.user)
        self.assertEqual(reversal_audit.action, AccountingAuditTrail.ActionType.CREATE)


class JournalEntryAuditTrailTest(TransactionTestCase):
    """Test audit trail functionality for JournalEntry model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
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
        self.account = Account.objects.create(
            name="Cash", account_number="1001", type=Account.AccountType.ASSET
        )
        self.journal = Journal.objects.create(
            description="Test Journal",
            date=date(2023, 1, 15),
            period=self.period,
            status=Journal.JournalStatus.DRAFT,
            created_by=self.user,
        )
        set_audit_user(self.user)
        set_audit_metadata("192.168.1.1", "Test Browser")

    def test_journal_entry_creation_logged(self):
        """Test that journal entry creation is logged to audit trail."""
        entry = JournalEntry.objects.create(
            journal=self.journal,
            account=self.account,
            entry_type="DEBIT",
            amount=1000,
            memo="Test entry",
            created_by=self.user,
        )

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(JournalEntry),
            object_id=entry.pk,
            action=AccountingAuditTrail.ActionType.CREATE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.CREATE)
        self.assertIn("amount", audit_entry.changes)
        self.assertEqual(audit_entry.changes["amount"], "1000.00")

    def test_journal_entry_update_logged(self):
        """Test that journal entry update is logged to audit trail."""
        entry = JournalEntry.objects.create(
            journal=self.journal,
            account=self.account,
            entry_type="DEBIT",
            amount=1000,
            memo="Test entry",
            created_by=self.user,
        )

        # Update the entry
        entry.memo = "Updated memo"
        entry.save()

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(JournalEntry),
            object_id=entry.pk,
            action=AccountingAuditTrail.ActionType.UPDATE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.UPDATE)
        self.assertIn("memo", audit_entry.changes)
        self.assertEqual(audit_entry.changes["memo"]["old"], "Test entry")
        self.assertEqual(audit_entry.changes["memo"]["new"], "Updated memo")

    def test_journal_entry_deletion_logged(self):
        """Test that journal entry deletion is logged to audit trail."""
        entry = JournalEntry.objects.create(
            journal=self.journal,
            account=self.account,
            entry_type="DEBIT",
            amount=1000,
            memo="Test entry",
            created_by=self.user,
        )
        entry_id = entry.pk

        # Delete the entry
        entry.delete()

        # Check audit trail entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(JournalEntry),
            object_id=entry_id,
            action=AccountingAuditTrail.ActionType.DELETE,
        )

        self.assertEqual(audit_entry.user, self.user)
        self.assertEqual(audit_entry.action, AccountingAuditTrail.ActionType.DELETE)


class AuditTrailManagementCommandTest(TestCase):
    """Test the audit trail management command."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_backfill_command_dry_run(self):
        """Test backfill command in dry run mode."""
        # Create some test data without audit entries
        account = Account.objects.create(
            name="Test Account", account_number="1001", type=Account.AccountType.ASSET
        )

        # Run backfill command in dry run mode
        out = self.call_command(
            "audit_trail_management",
            "backfill",
            "--model=account",
            "--dry-run",
            "--verbose",
        )

        self.assertIn("Would create", out)
        self.assertIn("DRY RUN", out)

    def test_verify_command(self):
        """Test audit trail verification command."""
        # Create test data with audit entries
        account = Account.objects.create(
            name="Test Account", account_number="1001", type=Account.AccountType.ASSET
        )

        # Create audit entry
        AccountingAuditTrail.objects.create(
            user=self.user,
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=ContentType.objects.get_for_model(Account),
            object_id=account.pk,
        )

        # Run verify command
        out = self.call_command("audit_trail_management", "verify", "--model=account")

        self.assertIn("No integrity issues found", out)

    def test_stats_command(self):
        """Test audit trail statistics command."""
        # Create some test data
        account = Account.objects.create(
            name="Test Account", account_number="1001", type=Account.AccountType.ASSET
        )

        AccountingAuditTrail.objects.create(
            user=self.user,
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=ContentType.objects.get_for_model(Account),
            object_id=account.pk,
        )

        # Run stats command
        out = self.call_command("audit_trail_management", "stats")

        self.assertIn("Audit Trail Statistics", out)
        self.assertIn("Total audit entries:", out)

    def test_cleanup_command_dry_run(self):
        """Test cleanup command in dry run mode."""
        # Create an orphaned audit entry
        AccountingAuditTrail.objects.create(
            user=self.user,
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=ContentType.objects.get_for_model(Account),
            object_id=99999,  # Non-existent object ID
        )

        # Run cleanup command in dry run mode
        out = self.call_command("audit_trail_management", "cleanup", "--dry-run")

        self.assertIn("Would delete", out)

    def call_command(self, *args, **kwargs):
        """Helper method to call management command and return output."""
        from io import StringIO

        out = StringIO()
        call_command(*args, stdout=out, **kwargs)
        return out.getvalue()


class AuditTrailIntegrationTest(TransactionTestCase):
    """Integration tests for the complete audit trail system."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        set_audit_user(self.user)
        set_audit_metadata("192.168.1.1", "Test Browser")

    def test_complete_journal_workflow_audit(self):
        """Test audit trail for complete journal workflow."""
        # Set up fiscal year and period
        fiscal_year = FiscalYear.objects.create(
            year=2023,
            name="FY 2023",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            is_active=True,
        )
        period = AccountingPeriod.objects.create(
            fiscal_year=fiscal_year,
            period_number=1,
            name="January",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31),
            is_active=True,
        )

        # Create accounts
        cash_account = Account.objects.create(
            name="Cash", account_number="1001", type=Account.AccountType.ASSET
        )
        revenue_account = Account.objects.create(
            name="Revenue", account_number="4001", type=Account.AccountType.REVENUE
        )

        # Create journal with entries
        entries = [
            {
                "account": cash_account,
                "entry_type": "DEBIT",
                "amount": 1000,
                "memo": "Cash received",
            },
            {
                "account": revenue_account,
                "entry_type": "CREDIT",
                "amount": 1000,
                "memo": "Revenue earned",
            },
        ]

        journal = create_journal_with_entries(
            date=date(2023, 1, 15),
            description="Test Journal",
            entries=entries,
            fiscal_year=fiscal_year,
            period=period,
            user=self.user,
        )

        # Approve and post journal
        post_journal(journal, self.user)

        # Reverse the journal
        reversal_journal = reverse_journal(journal, self.user, "Correction needed")

        # Close the period
        close_accounting_period(period, self.user, "Period closed")

        # Close the fiscal year
        close_fiscal_year(fiscal_year, self.user, "Fiscal year closed")

        # Verify all audit trail entries exist
        audit_entries = AccountingAuditTrail.objects.filter(
            content_type=ContentType.objects.get_for_model(Journal)
        ).order_by("timestamp")

        # Should have CREATE, POST, REVERSE, and CREATE (for reversal)
        self.assertEqual(audit_entries.count(), 4)

        # Verify specific actions
        actions = [entry.action for entry in audit_entries]
        self.assertIn(AccountingAuditTrail.ActionType.CREATE, actions)
        self.assertIn(AccountingAuditTrail.ActionType.POST, actions)
        self.assertIn(AccountingAuditTrail.ActionType.REVERSE, actions)

        # Verify user attribution
        for entry in audit_entries:
            self.assertEqual(entry.user, self.user)
            self.assertEqual(entry.ip_address, "192.168.1.1")
            self.assertEqual(entry.user_agent, "Test Browser")

    def test_audit_trail_data_integrity(self):
        """Test that audit trail maintains data integrity."""
        # Create test data
        account = Account.objects.create(
            name="Test Account", account_number="1001", type=Account.AccountType.ASSET
        )

        # Modify the account
        account.description = "Updated description"
        account.save()

        # Get audit entry
        audit_entry = AccountingAuditTrail.objects.get(
            content_type=ContentType.objects.get_for_model(Account),
            object_id=account.pk,
            action=AccountingAuditTrail.ActionType.UPDATE,
        )

        # Verify data integrity
        self.assertIsInstance(audit_entry.changes, dict)
        self.assertIn("description", audit_entry.changes)
        self.assertEqual(audit_entry.changes["description"]["old"], None)
        self.assertEqual(
            audit_entry.changes["description"]["new"], "Updated description"
        )

        # Verify JSON serialization
        changes_json = json.dumps(audit_entry.changes)
        parsed_changes = json.loads(changes_json)
        self.assertEqual(parsed_changes, audit_entry.changes)
