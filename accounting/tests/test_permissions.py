"""
Permission tests for role-based access controls.
Tests all permission functions, decorators, and mixins.
"""

from decimal import Decimal
from datetime import date
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.views import View
from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    Journal,
    JournalEntry,
)
from accounting.permissions import (
    is_auditor,
    is_accountant,
    is_payroll_processor,
    can_approve_journal,
    can_reverse_journal,
    can_close_period,
    can_view_payroll_data,
    can_modify_payroll_data,
    auditor_required,
    accountant_required,
    payroll_processor_required,
)
from accounting.mixins import (
    AuditorRequiredMixin,
    AccountantRequiredMixin,
    PayrollProcessorRequiredMixin,
)
from accounting.tests.fixtures import (
    UserFactory,
    AccountFactory,
    FiscalYearFactory,
    JournalFactory,
)

User = get_user_model()


class RolePermissionFunctionTest(TestCase):
    """Test cases for role permission functions"""

    def setUp(self):
        """Set up test data"""
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()
        self.admin = UserFactory.create_admin()
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )
        self.anonymous_user = AnonymousUser()

    def test_is_auditor(self):
        """Test auditor role check"""
        self.assertTrue(is_auditor(self.auditor))
        self.assertFalse(is_auditor(self.accountant))
        self.assertFalse(is_auditor(self.payroll_processor))
        self.assertTrue(is_auditor(self.admin))  # Admins have all permissions
        self.assertFalse(is_auditor(self.regular_user))
        self.assertFalse(is_auditor(self.anonymous_user))

    def test_is_accountant(self):
        """Test accountant role check"""
        self.assertFalse(is_accountant(self.auditor))
        self.assertTrue(is_accountant(self.accountant))
        self.assertFalse(is_accountant(self.payroll_processor))
        self.assertTrue(is_accountant(self.admin))  # Admins have all permissions
        self.assertFalse(is_accountant(self.regular_user))
        self.assertFalse(is_accountant(self.anonymous_user))

    def test_is_payroll_processor(self):
        """Test payroll processor role check"""
        self.assertFalse(is_payroll_processor(self.auditor))
        self.assertFalse(is_payroll_processor(self.accountant))
        self.assertTrue(is_payroll_processor(self.payroll_processor))
        self.assertTrue(is_payroll_processor(self.admin))  # Admins have all permissions
        self.assertFalse(is_payroll_processor(self.regular_user))
        self.assertFalse(is_payroll_processor(self.anonymous_user))


class JournalPermissionFunctionTest(TestCase):
    """Test cases for journal permission functions"""

    def setUp(self):
        """Set up test data"""
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()
        self.admin = UserFactory.create_admin()
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )

        # Create test journals
        self.draft_journal = JournalFactory.create_journal("Draft Journal")
        self.pending_journal = JournalFactory.create_journal("Pending Journal")
        self.pending_journal.status = Journal.JournalStatus.PENDING_APPROVAL
        self.pending_journal.save()

        self.approved_journal = JournalFactory.create_journal("Approved Journal")
        self.approved_journal.status = Journal.JournalStatus.APPROVED
        self.approved_journal.save()

        self.posted_journal = JournalFactory.create_posted_journal(
            "Posted Journal", 1000
        )

        # Create journal created by payroll processor
        self.payroll_journal = JournalFactory.create_journal("Payroll Journal")
        self.payroll_journal.created_by = self.payroll_processor
        self.payroll_journal.save()

    def test_can_approve_journal(self):
        """Test journal approval permission"""
        # Draft journal - accountant and admin can approve
        self.assertTrue(can_approve_journal(self.draft_journal, self.accountant))
        self.assertTrue(can_approve_journal(self.draft_journal, self.admin))
        self.assertFalse(can_approve_journal(self.draft_journal, self.auditor))
        self.assertFalse(
            can_approve_journal(self.draft_journal, self.payroll_processor)
        )
        self.assertFalse(can_approve_journal(self.draft_journal, self.regular_user))

        # Pending journal - accountant and admin can approve
        self.assertTrue(can_approve_journal(self.pending_journal, self.accountant))
        self.assertTrue(can_approve_journal(self.pending_journal, self.admin))
        self.assertFalse(can_approve_journal(self.pending_journal, self.auditor))
        self.assertFalse(
            can_approve_journal(self.pending_journal, self.payroll_processor)
        )

        # Approved journal - no one can approve (already approved)
        self.assertFalse(can_approve_journal(self.approved_journal, self.accountant))
        self.assertFalse(can_approve_journal(self.approved_journal, self.admin))

        # Posted journal - no one can approve (already posted)
        self.assertFalse(can_approve_journal(self.posted_journal, self.accountant))
        self.assertFalse(can_approve_journal(self.posted_journal, self.admin))

        # Payroll journal - payroll processor can approve their own
        self.assertTrue(
            can_approve_journal(self.payroll_journal, self.payroll_processor)
        )
        self.assertTrue(can_approve_journal(self.payroll_journal, self.admin))
        self.assertTrue(can_approve_journal(self.payroll_journal, self.accountant))

    def test_can_reverse_journal(self):
        """Test journal reversal permission"""
        # Draft journal - creator and admin can reverse
        self.assertTrue(
            can_reverse_journal(self.draft_journal, self.draft_journal.created_by)
        )
        self.assertTrue(can_reverse_journal(self.draft_journal, self.admin))
        self.assertFalse(can_reverse_journal(self.draft_journal, self.accountant))
        self.assertFalse(can_reverse_journal(self.draft_journal, self.auditor))

        # Posted journal - accountant, auditor, and admin can reverse
        self.assertTrue(can_reverse_journal(self.posted_journal, self.accountant))
        self.assertTrue(can_reverse_journal(self.posted_journal, self.auditor))
        self.assertTrue(can_reverse_journal(self.posted_journal, self.admin))
        self.assertFalse(can_reverse_journal(self.posted_journal, self.regular_user))

        # Payroll journal - payroll processor can reverse their own
        self.assertTrue(
            can_reverse_journal(self.payroll_journal, self.payroll_processor)
        )
        self.assertTrue(can_reverse_journal(self.payroll_journal, self.admin))
        self.assertTrue(can_reverse_journal(self.payroll_journal, self.accountant))


class PeriodPermissionFunctionTest(TestCase):
    """Test cases for period permission functions"""

    def setUp(self):
        """Set up test data"""
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()
        self.admin = UserFactory.create_admin()
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )

        # Create test period
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()
        self.period = AccountingPeriod.objects.filter(
            fiscal_year=self.fiscal_year
        ).first()

    def test_can_close_period(self):
        """Test period closing permission"""
        # Accountant and admin can close periods
        self.assertTrue(can_close_period(self.period, self.accountant))
        self.assertTrue(can_close_period(self.period, self.admin))

        # Auditor cannot close periods (can only view)
        self.assertFalse(can_close_period(self.period, self.auditor))

        # Payroll processor cannot close periods
        self.assertFalse(can_close_period(self.period, self.payroll_processor))

        # Regular user cannot close periods
        self.assertFalse(can_close_period(self.period, self.regular_user))


class PayrollPermissionFunctionTest(TestCase):
    """Test cases for payroll permission functions"""

    def setUp(self):
        """Set up test data"""
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()
        self.admin = UserFactory.create_admin()
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )

    def test_can_view_payroll_data(self):
        """Test payroll data viewing permission"""
        # Auditor, accountant, payroll processor, and admin can view payroll data
        self.assertTrue(can_view_payroll_data(self.auditor))
        self.assertTrue(can_view_payroll_data(self.accountant))
        self.assertTrue(can_view_payroll_data(self.payroll_processor))
        self.assertTrue(can_view_payroll_data(self.admin))

        # Regular user cannot view payroll data
        self.assertFalse(can_view_payroll_data(self.regular_user))

    def test_can_modify_payroll_data(self):
        """Test payroll data modification permission"""
        # Payroll processor and admin can modify payroll data
        self.assertTrue(can_modify_payroll_data(self.payroll_processor))
        self.assertTrue(can_modify_payroll_data(self.admin))

        # Auditor can only view, not modify
        self.assertFalse(can_modify_payroll_data(self.auditor))

        # Accountant can only view, not modify (unless also payroll processor)
        self.assertFalse(can_modify_payroll_data(self.accountant))

        # Regular user cannot modify payroll data
        self.assertFalse(can_modify_payroll_data(self.regular_user))


class PermissionDecoratorTest(TestCase):
    """Test cases for permission decorators"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )

    def test_auditor_required_decorator(self):
        """Test auditor required decorator"""
        request = self.factory.get("/test/")
        request.user = self.auditor

        # Create a test view with decorator
        @auditor_required
        def test_view(request):
            return HttpResponse("Success")

        response = test_view(request)
        self.assertEqual(response.content, b"Success")

        # Test with non-auditor
        request.user = self.regular_user
        response = test_view(request)
        self.assertEqual(response.status_code, 403)

    def test_accountant_required_decorator(self):
        """Test accountant required decorator"""
        request = self.factory.get("/test/")
        request.user = self.accountant

        @accountant_required
        def test_view(request):
            return HttpResponse("Success")

        response = test_view(request)
        self.assertEqual(response.content, b"Success")

        # Test with non-accountant
        request.user = self.regular_user
        response = test_view(request)
        self.assertEqual(response.status_code, 403)

    def test_payroll_processor_required_decorator(self):
        """Test payroll processor required decorator"""
        request = self.factory.get("/test/")
        request.user = self.payroll_processor

        @payroll_processor_required
        def test_view(request):
            return HttpResponse("Success")

        response = test_view(request)
        self.assertEqual(response.content, b"Success")

        # Test with non-payroll processor
        request.user = self.regular_user
        response = test_view(request)
        self.assertEqual(response.status_code, 403)


class PermissionMixinTest(TestCase):
    """Test cases for permission mixins"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )

    def test_auditor_required_mixin(self):
        """Test auditor required mixin"""

        class TestView(AuditorRequiredMixin, View):
            def get(self, request):
                return HttpResponse("Success")

        request = self.factory.get("/test/")
        request.user = self.auditor

        view = TestView.as_view()
        response = view(request)
        self.assertEqual(response.content, b"Success")

        # Test with non-auditor
        request.user = self.regular_user
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_accountant_required_mixin(self):
        """Test accountant required mixin"""

        class TestView(AccountantRequiredMixin, View):
            def get(self, request):
                return HttpResponse("Success")

        request = self.factory.get("/test/")
        request.user = self.accountant

        view = TestView.as_view()
        response = view(request)
        self.assertEqual(response.content, b"Success")

        # Test with non-accountant
        request.user = self.regular_user
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_payroll_processor_required_mixin(self):
        """Test payroll processor required mixin"""

        class TestView(PayrollProcessorRequiredMixin, View):
            def get(self, request):
                return HttpResponse("Success")

        request = self.factory.get("/test/")
        request.user = self.payroll_processor

        view = TestView.as_view()
        response = view(request)
        self.assertEqual(response.content, b"Success")

        # Test with non-payroll processor
        request.user = self.regular_user
        response = view(request)
        self.assertEqual(response.status_code, 403)


class ObjectLevelPermissionTest(TestCase):
    """Test cases for object-level permissions"""

    def setUp(self):
        """Set up test data"""
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()
        self.admin = UserFactory.create_admin()
        self.regular_user = User.objects.create_user(
            username="regular", password="testpass123"
        )

        # Create test objects
        self.account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )
        self.journal = JournalFactory.create_journal("Test Journal")
        self.journal.created_by = self.accountant
        self.journal.save()

    def test_account_object_permissions(self):
        """Test account object-level permissions"""
        # All authenticated users can view accounts
        self.assertTrue(self.auditor.has_perm("accounting.view_account"))
        self.assertTrue(self.accountant.has_perm("accounting.view_account"))
        self.assertTrue(self.payroll_processor.has_perm("accounting.view_account"))
        self.assertTrue(self.admin.has_perm("accounting.view_account"))

        # Only accountants and admins can modify accounts
        self.assertFalse(self.auditor.has_perm("accounting.change_account"))
        self.assertTrue(self.accountant.has_perm("accounting.change_account"))
        self.assertFalse(self.payroll_processor.has_perm("accounting.change_account"))
        self.assertTrue(self.admin.has_perm("accounting.change_account"))

    def test_journal_object_permissions(self):
        """Test journal object-level permissions"""
        # All authenticated users can view journals
        self.assertTrue(self.auditor.has_perm("accounting.view_journal"))
        self.assertTrue(self.accountant.has_perm("accounting.view_journal"))
        self.assertTrue(self.payroll_processor.has_perm("accounting.view_journal"))
        self.assertTrue(self.admin.has_perm("accounting.view_journal"))

        # Creator can modify their own journal
        self.assertTrue(
            self.accountant.has_perm("accounting.change_journal", self.journal)
        )

        # Non-creator cannot modify (unless admin)
        self.assertFalse(
            self.auditor.has_perm("accounting.change_journal", self.journal)
        )
        self.assertTrue(self.admin.has_perm("accounting.change_journal", self.journal))

    def test_audit_trail_permissions(self):
        """Test audit trail permissions"""
        # Only auditors and admins can view audit trail
        self.assertTrue(self.auditor.has_perm("accounting.view_accountingaudittrail"))
        self.assertFalse(
            self.accountant.has_perm("accounting.view_accountingaudittrail")
        )
        self.assertFalse(
            self.payroll_processor.has_perm("accounting.view_accountingaudittrail")
        )
        self.assertTrue(self.admin.has_perm("accounting.view_accountingaudittrail"))

        # Only auditors and admins can modify audit trail
        self.assertTrue(self.auditor.has_perm("accounting.change_accountingaudittrail"))
        self.assertFalse(
            self.accountant.has_perm("accounting.change_accountingaudittrail")
        )
        self.assertFalse(
            self.payroll_processor.has_perm("accounting.change_accountingaudittrail")
        )
        self.assertTrue(self.admin.has_perm("accounting.change_accountingaudittrail"))


class PermissionIntegrationTest(TestCase):
    """Integration tests for permissions with real scenarios"""

    def setUp(self):
        """Set up test data"""
        self.auditor = UserFactory.create_auditor()
        self.accountant = UserFactory.create_accountant()
        self.payroll_processor = UserFactory.create_payroll_processor()
        self.admin = UserFactory.create_admin()

        # Create test data
        self.fiscal_year = FiscalYearFactory.create_fiscal_year()
        self.journal = JournalFactory.create_journal("Test Journal")
        self.account = AccountFactory.create_account(
            "Test Account", "1000", Account.AccountType.ASSET
        )

    def test_journal_workflow_permissions(self):
        """Test permissions throughout journal workflow"""
        # Create journal (accountant only)
        self.assertTrue(self.accountant.has_perm("accounting.add_journal"))
        self.assertFalse(self.auditor.has_perm("accounting.add_journal"))
        self.assertFalse(self.payroll_processor.has_perm("accounting.add_journal"))

        # Submit for approval (accountant only)
        self.assertTrue(can_approve_journal(self.journal, self.accountant))
        self.assertFalse(can_approve_journal(self.journal, self.auditor))

        # Approve journal (accountant and admin)
        self.journal.status = Journal.JournalStatus.PENDING_APPROVAL
        self.journal.save()
        self.assertTrue(can_approve_journal(self.journal, self.accountant))
        self.assertFalse(can_approve_journal(self.journal, self.auditor))

        # Post journal (accountant only)
        self.journal.status = Journal.JournalStatus.APPROVED
        self.journal.save()
        self.assertTrue(self.accountant.has_perm("accounting.post_journal"))
        self.assertFalse(self.auditor.has_perm("accounting.post_journal"))

        # Reverse journal (accountant, auditor, admin)
        self.journal.status = Journal.JournalStatus.POSTED
        self.journal.save()
        self.assertTrue(can_reverse_journal(self.journal, self.accountant))
        self.assertTrue(can_reverse_journal(self.journal, self.auditor))
        self.assertFalse(can_reverse_journal(self.journal, self.payroll_processor))

    def test_period_management_permissions(self):
        """Test permissions for period management"""
        period = AccountingPeriod.objects.filter(fiscal_year=self.fiscal_year).first()

        # Close period (accountant and admin only)
        self.assertTrue(can_close_period(period, self.accountant))
        self.assertFalse(can_close_period(period, self.auditor))
        self.assertFalse(can_close_period(period, self.payroll_processor))

        # View period (all authenticated users)
        self.assertTrue(self.auditor.has_perm("accounting.view_accountingperiod"))
        self.assertTrue(self.accountant.has_perm("accounting.view_accountingperiod"))
        self.assertTrue(
            self.payroll_processor.has_perm("accounting.view_accountingperiod")
        )

    def test_reporting_permissions(self):
        """Test permissions for reporting"""
        # Trial balance (auditor, accountant, admin)
        self.assertTrue(self.auditor.has_perm("accounting.view_trial_balance"))
        self.assertTrue(self.accountant.has_perm("accounting.view_trial_balance"))
        self.assertFalse(
            self.payroll_processor.has_perm("accounting.view_trial_balance")
        )

        # General ledger (auditor, accountant, admin)
        self.assertTrue(self.auditor.has_perm("accounting.view_general_ledger"))
        self.assertTrue(self.accountant.has_perm("accounting.view_general_ledger"))
        self.assertFalse(
            self.payroll_processor.has_perm("accounting.view_general_ledger")
        )

        # Account activity (auditor, accountant, admin)
        self.assertTrue(self.auditor.has_perm("accounting.view_account_activity"))
        self.assertTrue(self.accountant.has_perm("accounting.view_account_activity"))
        self.assertFalse(
            self.payroll_processor.has_perm("accounting.view_account_activity")
        )

    def test_cross_role_permissions(self):
        """Test permissions across different roles"""
        # Accountant should be able to view payroll data but not modify
        self.assertTrue(can_view_payroll_data(self.accountant))
        self.assertFalse(can_modify_payroll_data(self.accountant))

        # Auditor should be able to view all data but not modify
        self.assertTrue(can_view_payroll_data(self.auditor))
        self.assertFalse(can_modify_payroll_data(self.auditor))
        self.assertFalse(can_approve_journal(self.journal, self.auditor))
        self.assertFalse(can_close_period(None, self.auditor))

        # Payroll processor should be able to modify payroll data but not other accounting data
        self.assertTrue(can_modify_payroll_data(self.payroll_processor))
        self.assertFalse(self.payroll_processor.has_perm("accounting.add_account"))
        self.assertFalse(self.payroll_processor.has_perm("accounting.add_journal"))

        # Admin should have all permissions
        self.assertTrue(can_modify_payroll_data(self.admin))
        self.assertTrue(self.admin.has_perm("accounting.add_account"))
        self.assertTrue(self.admin.has_perm("accounting.add_journal"))
        self.assertTrue(can_approve_journal(self.journal, self.admin))
        self.assertTrue(can_close_period(None, self.admin))
