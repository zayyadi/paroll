from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounting.models import Account, Journal
from accounting.utils import create_journal_with_entries, get_trial_balance
from company.models import Company


class AccountingTenantScopingTests(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Tenant A")
        self.company_b = Company.objects.create(name="Tenant B")

    def _account(self, company, name, number, account_type):
        return Account.objects.create(
            company=company,
            name=name,
            account_number=number,
            type=account_type,
        )

    def test_account_numbers_are_unique_per_company_not_global(self):
        self._account(self.company_a, "Cash", "1000", Account.AccountType.ASSET)
        self._account(self.company_b, "Cash", "1000", Account.AccountType.ASSET)

        with self.assertRaises(IntegrityError):
            self._account(
                self.company_a,
                "Duplicate Cash",
                "1000",
                Account.AccountType.ASSET,
            )

    def test_create_journal_with_entries_scopes_fiscal_period_and_journal(self):
        cash = self._account(self.company_a, "Cash", "1000", Account.AccountType.ASSET)
        revenue = self._account(
            self.company_a,
            "Sales Revenue",
            "4000",
            Account.AccountType.REVENUE,
        )

        journal = create_journal_with_entries(
            company=self.company_a,
            date=date(2026, 5, 1),
            description="Tenant A sale",
            entries=[
                {
                    "account": cash,
                    "entry_type": "DEBIT",
                    "amount": Decimal("100.00"),
                },
                {
                    "account": revenue,
                    "entry_type": "CREDIT",
                    "amount": Decimal("100.00"),
                },
            ],
            auto_post=True,
        )

        self.assertEqual(journal.company, self.company_a)
        self.assertEqual(journal.period.company, self.company_a)
        self.assertEqual(journal.period.fiscal_year.company, self.company_a)

    def test_create_journal_rejects_accounts_from_another_company(self):
        cash = self._account(self.company_a, "Cash", "1000", Account.AccountType.ASSET)
        revenue = self._account(
            self.company_b,
            "Sales Revenue",
            "4000",
            Account.AccountType.REVENUE,
        )

        with self.assertRaises(ValueError):
            create_journal_with_entries(
                company=self.company_a,
                date=date(2026, 5, 1),
                description="Cross tenant journal",
                entries=[
                    {
                        "account": cash,
                        "entry_type": "DEBIT",
                        "amount": Decimal("100.00"),
                    },
                    {
                        "account": revenue,
                        "entry_type": "CREDIT",
                        "amount": Decimal("100.00"),
                    },
                ],
            )

    def test_trial_balance_is_filtered_by_company(self):
        cash_a = self._account(self.company_a, "Cash", "1000", Account.AccountType.ASSET)
        revenue_a = self._account(
            self.company_a,
            "Sales Revenue",
            "4000",
            Account.AccountType.REVENUE,
        )
        cash_b = self._account(self.company_b, "Cash", "1000", Account.AccountType.ASSET)
        revenue_b = self._account(
            self.company_b,
            "Sales Revenue",
            "4000",
            Account.AccountType.REVENUE,
        )

        create_journal_with_entries(
            company=self.company_a,
            date=date(2026, 5, 1),
            description="Tenant A sale",
            entries=[
                {"account": cash_a, "entry_type": "DEBIT", "amount": Decimal("100.00")},
                {
                    "account": revenue_a,
                    "entry_type": "CREDIT",
                    "amount": Decimal("100.00"),
                },
            ],
            auto_post=True,
        )
        create_journal_with_entries(
            company=self.company_b,
            date=date(2026, 5, 1),
            description="Tenant B sale",
            entries=[
                {"account": cash_b, "entry_type": "DEBIT", "amount": Decimal("250.00")},
                {
                    "account": revenue_b,
                    "entry_type": "CREDIT",
                    "amount": Decimal("250.00"),
                },
            ],
            auto_post=True,
        )

        trial_balance = get_trial_balance(company=self.company_a)

        self.assertEqual(set(trial_balance.keys()), {cash_a.id, revenue_a.id})
        self.assertEqual(trial_balance[cash_a.id]["balance"], Decimal("100.00"))
        self.assertFalse(
            Journal.objects.filter(company=self.company_a, entries__account=cash_b).exists()
        )


class AccountingViewTenantScopingTests(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Scoped View Tenant A")
        self.company_b = Company.objects.create(name="Scoped View Tenant B")
        self.accountant = get_user_model().objects.create_user(
            email="scoped-accountant@example.com",
            password="password123",
            company=self.company_a,
            active_company=self.company_a,
        )
        accountant_group, _ = Group.objects.get_or_create(name="Accountant")
        self.accountant.groups.add(accountant_group)

    def _account(self, company, name, number, account_type):
        return Account.objects.create(
            company=company,
            name=name,
            account_number=number,
            type=account_type,
        )

    def test_journal_approval_view_does_not_resolve_cross_tenant_journal(self):
        journal = Journal.objects.create(
            company=self.company_b,
            description="Tenant B pending journal",
            date=date(2026, 5, 1),
            status=Journal.JournalStatus.PENDING_APPROVAL,
        )
        self.client.force_login(self.accountant)

        response = self.client.get(
            reverse("accounting:journal_approve", kwargs={"pk": journal.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_account_activity_pdf_does_not_resolve_cross_tenant_account(self):
        account = self._account(
            self.company_b,
            "Tenant B Cash",
            "1000",
            Account.AccountType.ASSET,
        )
        self.client.force_login(self.accountant)

        response = self.client.get(
            reverse("accounting:account_activity_pdf"),
            {"account": account.pk},
        )

        self.assertEqual(response.status_code, 404)
