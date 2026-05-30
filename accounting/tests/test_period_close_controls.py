from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounting.models import (
    Account,
    AccountingPeriod,
    AccrualTemplate,
    Budget,
    BudgetLine,
    FiscalYear,
    Journal,
)
from accounting.utils import close_accounting_period, create_journal_with_entries, get_budget_vs_actual
from company.models import Company


User = get_user_model()


class PeriodCloseControlTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Close Controls Ltd")
        self.user = User.objects.create_user(
            email="close-controls@example.com",
            password="password",
            company=self.company,
            active_company=self.company,
        )
        self.fiscal_year = FiscalYear.objects.create(
            company=self.company,
            year=2026,
            name="FY 2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        self.period = AccountingPeriod.objects.create(
            company=self.company,
            fiscal_year=self.fiscal_year,
            period_number=5,
            name="May 2026",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            is_active=True,
        )
        self.expense = Account.objects.create(
            company=self.company,
            name="Utilities Expense",
            account_number="6100",
            type=Account.AccountType.EXPENSE,
        )
        self.accrued_liability = Account.objects.create(
            company=self.company,
            name="Accrued Liabilities",
            account_number="2400",
            type=Account.AccountType.LIABILITY,
        )

    def test_close_accounting_period_posts_active_accrual_templates(self):
        AccrualTemplate.objects.create(
            company=self.company,
            name="Monthly utilities accrual",
            debit_account=self.expense,
            credit_account=self.accrued_liability,
            amount=Decimal("1250.00"),
            is_active=True,
        )

        close_accounting_period(self.period, self.user, "May close")

        self.period.refresh_from_db()
        self.assertTrue(self.period.is_closed)
        journal = Journal.objects.get(
            company=self.company,
            period=self.period,
            description="Accrual: Monthly utilities accrual",
        )
        self.assertEqual(journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(journal.entries.get(account=self.expense).amount, Decimal("1250.00"))
        self.assertEqual(
            journal.entries.get(account=self.accrued_liability).amount,
            Decimal("1250.00"),
        )

    def test_budget_vs_actual_reports_variance_by_account_and_period(self):
        budget = Budget.objects.create(
            company=self.company,
            fiscal_year=self.fiscal_year,
            name="Operating Budget",
            status="APPROVED",
        )
        BudgetLine.objects.create(
            budget=budget,
            account=self.expense,
            period=self.period,
            amount=Decimal("1000.00"),
        )
        create_journal_with_entries(
            company=self.company,
            date=date(2026, 5, 15),
            description="Utility bill",
            entries=[
                {
                    "account": self.expense,
                    "entry_type": "DEBIT",
                    "amount": Decimal("1250.00"),
                },
                {
                    "account": self.accrued_liability,
                    "entry_type": "CREDIT",
                    "amount": Decimal("1250.00"),
                },
            ],
            user=self.user,
            fiscal_year=self.fiscal_year,
            period=self.period,
            auto_post=True,
            validate_balances=False,
        )

        rows = get_budget_vs_actual(self.company, self.fiscal_year, period=self.period)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["account"], self.expense)
        self.assertEqual(rows[0]["budget_amount"], Decimal("1000.00"))
        self.assertEqual(rows[0]["actual_amount"], Decimal("1250.00"))
        self.assertEqual(rows[0]["variance"], Decimal("250.00"))
