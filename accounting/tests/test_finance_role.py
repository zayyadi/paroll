"""
Tests for the Finance role: read-only access to accounting views, lockdown
bypass, and denial of mutation views.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.tests.fixtures import (
    UserFactory,
    AccountFactory,
    FiscalYearFactory,
    JournalFactory,
)


class FinanceRoleAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.finance = UserFactory.create_finance()
        # A plain user with no accounting role
        cls.plain = UserFactory._create_user(
            email="plain@test.com", password="testpass123"
        )

        cls.fiscal_year = FiscalYearFactory.create_fiscal_year()
        cls.journal = JournalFactory.create_posted_journal("Test Journal", 1000)

    def setUp(self):
        self.client.force_login(self.finance)

    def test_finance_can_view_dashboard(self):
        response = self.client.get(reverse("accounting:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_finance_can_view_journal_list(self):
        response = self.client.get(reverse("accounting:journal_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.journal.transaction_number)

    def test_finance_can_view_audit_trail(self):
        response = self.client.get(reverse("accounting:audit_list"))
        self.assertEqual(response.status_code, 200)

    def test_finance_can_view_reports_index(self):
        response = self.client.get(reverse("accounting:reports"))
        self.assertEqual(response.status_code, 200)

    def test_finance_cannot_create_account(self):
        response = self.client.get(reverse("accounting:account_create"))
        self.assertEqual(response.status_code, 403)

    def test_finance_cannot_create_journal(self):
        response = self.client.get(reverse("accounting:journal_create"))
        self.assertEqual(response.status_code, 403)

    @override_settings(ACCOUNTING_SUPERUSER_ONLY_UNTIL_TENANT_SCOPED=True)
    def test_finance_bypasses_accounting_lockdown(self):
        response = self.client.get(reverse("accounting:dashboard"))
        self.assertEqual(response.status_code, 200)

    @override_settings(ACCOUNTING_SUPERUSER_ONLY_UNTIL_TENANT_SCOPED=True)
    def test_plain_user_blocked_by_lockdown(self):
        self.client.force_login(self.plain)
        response = self.client.get(reverse("accounting:dashboard"))
        self.assertEqual(response.status_code, 403)
