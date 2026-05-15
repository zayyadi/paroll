from datetime import date
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

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
