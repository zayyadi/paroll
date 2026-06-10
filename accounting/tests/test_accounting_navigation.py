from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from company.models import Company


User = get_user_model()


class AccountingNavigationTests(TestCase):
    def test_sidebar_exposes_core_accounting_workflows(self):
        company = Company.objects.create(name="Accounting Nav Co")
        user = User.objects.create_superuser(
            email="nav-accountant@example.com",
            password="password123",
            company=company,
            active_company=company,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("accounting:dashboard"))

        self.assertEqual(response.status_code, 200)
        expected_links = [
            ("Chart of Accounts", reverse("accounting:account_list")),
            ("Create Account", reverse("accounting:account_create")),
            ("Opening Balances", reverse("accounting:opening_balance_import")),
            ("Journal List", reverse("accounting:journal_list")),
            ("Create Journal", reverse("accounting:journal_create")),
            ("General Ledger", reverse("accounting:general_ledger")),
            ("Trial Balance", reverse("accounting:trial_balance")),
            ("New Fiscal Year", reverse("accounting:fiscal_year_create")),
            ("New Accounting Period", reverse("accounting:period_create")),
            ("Reconciliations", reverse("accounting:reconciliation_list")),
            ("New Reconciliation", reverse("accounting:reconciliation_create")),
        ]
        for label, url in expected_links:
            with self.subTest(label=label):
                self.assertContains(response, label)
                self.assertContains(response, f'href="{url}"')
