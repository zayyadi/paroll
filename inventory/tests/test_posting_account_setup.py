from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounting.models import Account
from company.models import Company, CompanyMembership
from inventory.services import ensure_default_posting_accounts


User = get_user_model()


class PostingAccountSetupTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Posting Setup Co")
        self.user = User.objects.create_user(
            email="posting-setup@example.com",
            password="password123",
            first_name="Posting",
            last_name="Setup",
            company=self.company,
            active_company=self.company,
        )
        CompanyMembership.objects.get_or_create(
            user=self.user,
            company=self.company,
            defaults={"role": CompanyMembership.ROLE_OWNER, "is_default": True},
        )
        self.client.force_login(self.user)

    def test_default_posting_accounts_create_vat_wht_and_warehouse_accounts_per_tenant(self):
        result = ensure_default_posting_accounts(self.company)

        self.assertIn("Input VAT", [account.name for account in result["created"]])
        self.assertIn("Output VAT", [account.name for account in result["created"]])
        self.assertIn("WHT Payable", [account.name for account in result["created"]])
        self.assertTrue(
            Account.objects.filter(
                company=self.company,
                name="Trade Payables",
                type=Account.AccountType.LIABILITY,
            ).exists()
        )

        second_result = ensure_default_posting_accounts(self.company)

        self.assertEqual(second_result["created"], [])

    def test_default_posting_accounts_reuse_existing_name_when_number_differs(self):
        existing_adjustment_gain = Account.objects.create(
            company=self.company,
            name="Inventory Adjustment Gain",
            account_number="4650",
            type=Account.AccountType.REVENUE,
        )

        result = ensure_default_posting_accounts(self.company)

        self.assertIn(existing_adjustment_gain, result["existing"])
        self.assertFalse(
            Account.objects.filter(
                company=self.company,
                name="Inventory Adjustment Gain",
                account_number="4200",
            ).exists()
        )
        self.assertEqual(
            Account.objects.filter(
                company=self.company,
                name="Inventory Adjustment Gain",
            ).count(),
            1,
        )

    def test_posting_account_setup_page_matches_existing_account_by_name(self):
        existing_adjustment_gain = Account.objects.create(
            company=self.company,
            name="Inventory Adjustment Gain",
            account_number="4650",
            type=Account.AccountType.REVENUE,
        )

        response = self.client.get(reverse("inventory:posting_account_setup"))

        self.assertEqual(response.status_code, 200)
        recommendation = next(
            item
            for item in response.context["recommendations"]
            if item["name"] == "Inventory Adjustment Gain"
        )
        self.assertEqual(recommendation["account"], existing_adjustment_gain)

    def test_posting_account_setup_page_links_account_creation_and_creates_defaults(self):
        response = self.client.get(reverse("inventory:posting_account_setup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Input VAT")
        self.assertContains(response, reverse("accounting:account_create"))

        response = self.client.post(reverse("inventory:posting_account_setup"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Account.objects.filter(company=self.company, name="Output VAT").exists()
        )
