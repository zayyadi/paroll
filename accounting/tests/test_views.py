"""
View tests for all accounting views.
Tests view functionality, permissions, and responses.
"""

from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
    AccountingAuditTrail,
)
from accounting.tests.fixtures import (
    UserFactory,
    AccountFactory,
    FiscalYearFactory,
    JournalFactory,
)

User = get_user_model()


class DashboardViewTest(TestCase):
    """Test cases for dashboard view"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()

        # Create test data
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()
        self.journal = JournalFactory.create_posted_journal("Test Journal", 1000)

    def test_dashboard_view_auditor(self):
        """Test dashboard view for auditor"""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounting:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")
        self.assertContains(response, self.journal.transaction_number)

    def test_dashboard_view_accountant(self):
        """Test dashboard view for accountant"""
        self.client.force_login(self.accountant)
        response = self.client.get(reverse("accounting:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_dashboard_view_unauthenticated(self):
        """Test dashboard view for unauthenticated user"""
        response = self.client.get(reverse("accounting:dashboard"))

        # Should redirect to login
        self.assertEqual(response.status_code, 302)


class AccountViewTest(TestCase):
    """Test cases for account views"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()

        # Create test data
        self.account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )

    def test_account_list_view_auditor(self):
        """Test account list view for auditor"""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounting:account_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Account")

    def test_account_list_view_accountant(self):
        """Test account list view for accountant"""
        self.client.force_login(self.accountant)
        response = self.client.get(reverse("accounting:account_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Account")

    def test_account_detail_view(self):
        """Test account detail view"""
        self.client.force_login(self.auditor)
        response = self.client.get(
            reverse("accounting:account_detail", kwargs={"pk": self.account.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Account")
        self.assertContains(response, "1000")

    def test_account_create_view_accountant(self):
        """Test account create view for accountant"""
        self.client.force_login(self.accountant)
        response = self.client.get(reverse("accounting:account_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Account")

    def test_account_create_post(self):
        """Test account creation via POST"""
        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse("accounting:account_create"),
            {
                "name": "New Account",
                "account_number": "2000",
                "type": Account.AccountType.LIABILITY,
                "description": "Test account creation",
            },
        )

        # Should redirect to account list
        self.assertEqual(response.status_code, 302)

        # Check account was created
        new_account = Account.objects.get(account_number="2000")
        self.assertEqual(new_account.name, "New Account")
        self.assertEqual(new_account.type, Account.AccountType.LIABILITY)

    def test_account_update_view(self):
        """Test account update view"""
        self.client.force_login(self.accountant)
        response = self.client.get(
            reverse("accounting:account_update", kwargs={"pk": self.account.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Account")

    def test_account_update_post(self):
        """Test account update via POST"""
        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse("accounting:account_update", kwargs={"pk": self.account.pk}),
            {
                "name": "Updated Account",
                "account_number": "1000",
                "type": Account.AccountType.ASSET,
                "description": "Updated description",
            },
        )

        # Should redirect to account detail
        self.assertEqual(response.status_code, 302)

        # Check account was updated
        self.account.refresh_from_db()
        self.assertEqual(self.account.name, "Updated Account")
        self.assertEqual(self.account.description, "Updated description")


class JournalViewTest(TestCase):
    """Test cases for journal views"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()

        # Create test data
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()
        self.journal = JournalFactory.create_journal("Test Journal")

    def test_journal_list_view_auditor(self):
        """Test journal list view for auditor"""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounting:journal_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Journal")

    def test_journal_list_view_accountant(self):
        """Test journal list view for accountant"""
        self.client.force_login(self.accountant)
        response = self.client.get(reverse("accounting:journal_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Journal")

    def test_journal_detail_view(self):
        """Test journal detail view"""
        self.client.force_login(self.auditor)
        response = self.client.get(
            reverse("accounting:journal_detail", kwargs={"pk": self.journal.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Journal")

    def test_journal_create_view_accountant(self):
        """Test journal create view for accountant"""
        self.client.force_login(self.accountant)
        response = self.client.get(reverse("accounting:journal_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Journal")

    def test_journal_create_post(self):
        """Test journal creation via POST"""
        self.client.force_login(self.accountant)

        # Get accounts for entries
        cash = AccountFactory.create_account("Cash", "1000", Account.AccountType.ASSET)
        revenue = AccountFactory.create_account(
            "Revenue", "4000", Account.AccountType.REVENUE
        )

        response = self.client.post(
            reverse("accounting:journal_create"),
            {
                "description": "New Journal",
                "date": date.today(),
                "period": self.journal.period.pk,
                "entries-TOTAL_FORMS": "2",
                "entries-INITIAL_FORMS": "0",
                "entries-MIN_NUM_FORMS": "1",
                "entries-MAX_NUM_FORMS": "1000",
                "entries-0-account": cash.pk,
                "entries-0-entry_type": JournalEntry.EntryType.DEBIT,
                "entries-0-amount": "1000.00",
                "entries-0-memo": "Cash received",
                "entries-1-account": revenue.pk,
                "entries-1-entry_type": JournalEntry.EntryType.CREDIT,
                "entries-1-amount": "1000.00",
                "entries-1-memo": "Sales revenue",
            },
        )

        # Should redirect to journal detail
        self.assertEqual(response.status_code, 302)

        # Check journal was created
        new_journal = Journal.objects.get(description="New Journal")
        self.assertEqual(new_journal.entries.count(), 2)

    def test_journal_approve_view(self):
        """Test journal approve view"""
        # Create pending journal
        pending_journal = JournalFactory.create_journal("Pending Journal")
        pending_journal.status = Journal.JournalStatus.PENDING_APPROVAL
        pending_journal.save()

        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse("accounting:journal_approve", kwargs={"pk": pending_journal.pk})
        )

        # Should redirect to journal detail
        self.assertEqual(response.status_code, 302)

        # Check journal was approved
        pending_journal.refresh_from_db()
        self.assertEqual(pending_journal.status, Journal.JournalStatus.APPROVED)
        self.assertEqual(pending_journal.approved_by, self.accountant)

    def test_journal_post_view(self):
        """Test journal post view"""
        # Create approved journal
        approved_journal = JournalFactory.create_journal("Approved Journal")
        approved_journal.status = Journal.JournalStatus.APPROVED
        approved_journal.save()

        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse("accounting:journal_post", kwargs={"pk": approved_journal.pk})
        )

        # Should redirect to journal detail
        self.assertEqual(response.status_code, 302)

        # Check journal was posted
        approved_journal.refresh_from_db()
        self.assertEqual(approved_journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(approved_journal.posted_by, self.accountant)


class FiscalYearViewTest(TestCase):
    """Test cases for fiscal year views"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()

        # Create test data
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()

    def test_fiscal_year_list_view_auditor(self):
        """Test fiscal year list view for auditor"""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounting:fiscal_year_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"FY {self.fiscal_year.year}")

    def test_fiscal_year_detail_view(self):
        """Test fiscal year detail view"""
        self.client.force_login(self.auditor)
        response = self.client.get(
            reverse("accounting:fiscal_year_detail", kwargs={"pk": self.fiscal_year.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"FY {self.fiscal_year.year}")


class AccountingPeriodViewTest(TestCase):
    """Test cases for accounting period views"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()

        # Create test data
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()
        self.period = AccountingPeriod.objects.filter(
            fiscal_year=self.fiscal_year
        ).first()

    def test_period_list_view_auditor(self):
        """Test period list view for auditor"""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounting:period_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.period.name)

    def test_period_detail_view(self):
        """Test period detail view"""
        self.client.force_login(self.auditor)
        response = self.client.get(
            reverse("accounting:period_detail", kwargs={"pk": self.period.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.period.name)

    def test_period_close_view(self):
        """Test period close view"""
        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse("accounting:period_close", kwargs={"pk": self.period.pk})
        )

        # Should redirect to period detail
        self.assertEqual(response.status_code, 302)

        # Check period was closed
        self.period.refresh_from_db()
        self.assertTrue(self.period.is_closed)


class AuditTrailViewTest(TestCase):
    """Test cases for audit trail views"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()

        # Create test data
        self.account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )

    def test_audit_trail_list_view_auditor(self):
        """Test audit trail list view for auditor"""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounting:audit_trail_list"))

        self.assertEqual(response.status_code, 200)

    def test_audit_trail_list_view_accountant_denied(self):
        """Test audit trail list view for accountant (should be denied)"""
        self.client.force_login(self.accountant)
        response = self.client.get(reverse("accounting:audit_trail_list"))

        # Should be forbidden
        self.assertEqual(response.status_code, 403)

    def test_audit_trail_detail_view(self):
        """Test audit trail detail view"""
        # Create audit trail entry
        audit_entry = AccountingAuditTrail.objects.create(
            user=self.auditor,
            action=AccountingAuditTrail.ActionType.CREATE,
            content_type=self.account._meta.get_field(
                "content_type"
            ).remote_field.model.objects.get_for_model(self.account),
            object_id=self.account.pk,
            reason="Test audit entry",
        )

        self.client.force_login(self.auditor)
        response = self.client.get(
            reverse("accounting:audit_trail_detail", kwargs={"pk": audit_entry.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test audit entry")


class ReportViewTest(TestCase):
    """Test cases for report views"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()

        # Create test data
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()
        self.journal = JournalFactory.create_posted_journal("Test Journal", 1000)

    def test_trial_balance_view(self):
        """Test trial balance view"""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounting:report_trial_balance"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trial Balance")

    def test_account_activity_view(self):
        """Test account activity view"""
        # Get account from journal
        account = self.journal.entries.first().account

        self.client.force_login(self.auditor)
        response = self.client.get(
            reverse("accounting:report_account_activity", kwargs={"pk": account.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account Activity")

    def test_general_ledger_view(self):
        """Test general ledger view"""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounting:report_general_ledger"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "General Ledger")

    def test_trial_balance_pdf_view(self):
        """Test trial balance PDF view"""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse("accounting:report_trial_balance_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_account_activity_pdf_view(self):
        """Test account activity PDF view"""
        # Get account from journal
        account = self.journal.entries.first().account

        self.client.force_login(self.auditor)
        response = self.client.get(
            reverse("accounting:report_account_activity_pdf", kwargs={"pk": account.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")


class JournalReversalViewTest(TestCase):
    """Test cases for journal reversal views"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.accountant = UserFactory.create_accountant()

        # Create test data
        self.journal = JournalFactory.create_posted_journal("Test Journal", 1000)

    def test_journal_reversal_initiation_view(self):
        """Test journal reversal initiation view"""
        self.client.force_login(self.accountant)
        response = self.client.get(
            reverse(
                "accounting:journal_reversal_initiation", kwargs={"pk": self.journal.pk}
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reverse Journal")

    def test_journal_reversal_confirmation_view(self):
        """Test journal reversal confirmation view"""
        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse(
                "accounting:journal_reversal_confirmation",
                kwargs={"pk": self.journal.pk},
            ),
            {"reversal_type": "full", "reason": "Test reversal"},
        )

        # Should redirect to journal detail
        self.assertEqual(response.status_code, 302)

        # Check journal was reversed
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.status, Journal.JournalStatus.REVERSED)

    def test_journal_partial_reversal_view(self):
        """Test journal partial reversal view"""
        self.client.force_login(self.accountant)
        response = self.client.get(
            reverse(
                "accounting:journal_partial_reversal", kwargs={"pk": self.journal.pk}
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Partial Reversal")

    def test_journal_reversal_with_correction_view(self):
        """Test journal reversal with correction view"""
        self.client.force_login(self.accountant)
        response = self.client.get(
            reverse(
                "accounting:journal_reversal_with_correction",
                kwargs={"pk": self.journal.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reversal with Correction")

    def test_batch_journal_reversal_view(self):
        """Test batch journal reversal view"""
        # Create another posted journal
        journal2 = JournalFactory.create_posted_journal("Test Journal 2", 2000)

        self.client.force_login(self.accountant)
        response = self.client.get(reverse("accounting:batch_journal_reversal"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Batch Journal Reversal")

    def test_batch_journal_reversal_post(self):
        """Test batch journal reversal via POST"""
        # Create another posted journal
        journal2 = JournalFactory.create_posted_journal("Test Journal 2", 2000)

        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse("accounting:batch_journal_reversal"),
            {
                "journals": [self.journal.pk, journal2.pk],
                "reason": "Batch reversal test",
            },
        )

        # Should redirect to journal list
        self.assertEqual(response.status_code, 302)

        # Check journals were reversed
        self.journal.refresh_from_db()
        journal2.refresh_from_db()
        self.assertEqual(self.journal.status, Journal.JournalStatus.REVERSED)
        self.assertEqual(journal2.status, Journal.JournalStatus.REVERSED)

    def test_journal_reversal_history_view(self):
        """Test journal reversal history view"""
        # Reverse the journal first
        reversal_journal = self.journal.reverse(self.accountant, "Test reversal")

        self.client.force_login(self.accountant)
        response = self.client.get(
            reverse(
                "accounting:journal_reversal_history", kwargs={"pk": self.journal.pk}
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reversal History")
        self.assertContains(response, reversal_journal.transaction_number)


class PermissionViewTest(TestCase):
    """Test cases for view permissions"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()

        # Create test data
        self.journal = JournalFactory.create_journal("Test Journal")
        self.account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )

    def test_auditor_can_view_all(self):
        """Test auditor can view all accounting data"""
        self.client.force_login(self.auditor)

        # Test various views
        response = self.client.get(reverse("accounting:dashboard"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("accounting:account_list"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("accounting:journal_list"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("accounting:audit_trail_list"))
        self.assertEqual(response.status_code, 200)

    def test_accountant_can_create_and_modify(self):
        """Test accountant can create and modify accounting data"""
        self.client.force_login(self.accountant)

        # Test create views
        response = self.client.get(reverse("accounting:account_create"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("accounting:journal_create"))
        self.assertEqual(response.status_code, 200)

        # Test modify views
        response = self.client.get(
            reverse("accounting:account_update", kwargs={"pk": self.account.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_payroll_processor_limited_access(self):
        """Test payroll processor has limited access"""
        self.client.force_login(self.payroll_processor)

        # Should be able to view dashboard
        response = self.client.get(reverse("accounting:dashboard"))
        self.assertEqual(response.status_code, 200)

        # Should NOT be able to access audit trail
        response = self.client.get(reverse("accounting:audit_trail_list"))
        self.assertEqual(response.status_code, 403)

        # Should NOT be able to create accounts
        response = self.client.get(reverse("accounting:account_create"))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_access_denied(self):
        """Test unauthenticated access is denied"""
        # All views should redirect to login or return 403/404
        response = self.client.get(reverse("accounting:dashboard"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

        response = self.client.get(reverse("accounting:account_list"))
        self.assertEqual(response.status_code, 302)  # Redirect to login
