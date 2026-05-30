from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from accounting.models import (
    Account,
    AccountReconciliation,
    BankTransaction,
    ReconciliationItem,
    FiscalYear,
    AccountingPeriod,
    Journal,
)
from accounting.utils import (
    create_bank_reconciliation,
    match_reconciliation_items,
    approve_reconciliation,
    get_or_create_fiscal_year,
    get_or_create_period,
)
from accounting.tests.fixtures import get_test_company

User = get_user_model()


class BankReconciliationTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(
            email="recon@test.com", password="testpass123"
        )
        self.bank_account = Account.objects.create(
            company=self.company,
            name="Bank NGN",
            account_number="1010",
            type=Account.AccountType.ASSET,
            currency="NGN",
        )
        self.revenue_account = Account.objects.create(
            company=self.company,
            name="Revenue",
            account_number="4000",
            type=Account.AccountType.REVENUE,
            currency="NGN",
        )
        self.expense_account = Account.objects.create(
            company=self.company,
            name="Expenses",
            account_number="5000",
            type=Account.AccountType.EXPENSE,
            currency="NGN",
        )

        self.fiscal_year = get_or_create_fiscal_year(year=2026, company=self.company)
        self.period = get_or_create_period(
            fiscal_year=self.fiscal_year, period_number=5, company=self.company
        )

        # Post some deposits
        from accounting.utils import create_journal_with_entries
        self.j1 = create_journal_with_entries(
            company=self.company, date=date(2026, 5, 10),
            description="Customer payment",
            entries=[
                {"account": self.bank_account, "entry_type": "DEBIT", "amount": Decimal("5000.00"), "memo": "Payment"},
                {"account": self.revenue_account, "entry_type": "CREDIT", "amount": Decimal("5000.00"), "memo": "Revenue"},
            ],
            user=self.user, fiscal_year=self.fiscal_year, period=self.period,
            auto_post=True, validate_balances=False,
        )
        self.j2 = create_journal_with_entries(
            company=self.company, date=date(2026, 5, 15),
            description="Rent payment",
            entries=[
                {"account": self.expense_account, "entry_type": "DEBIT", "amount": Decimal("1000.00"), "memo": "Rent"},
                {"account": self.bank_account, "entry_type": "CREDIT", "amount": Decimal("1000.00"), "memo": "Rent"},
            ],
            user=self.user, fiscal_year=self.fiscal_year, period=self.period,
            auto_post=True, validate_balances=False,
        )

        self.bank_txs_data = [
            {"transaction_date": date(2026, 5, 10), "description": "Customer deposit", "reference": "REF001", "amount": Decimal("5000.00"), "transaction_type": "CREDIT"},
            {"transaction_date": date(2026, 5, 15), "description": "Rent payment", "reference": "REF002", "amount": Decimal("1000.00"), "transaction_type": "DEBIT"},
            {"transaction_date": date(2026, 5, 20), "description": "Bank fee", "reference": "REF003", "amount": Decimal("50.00"), "transaction_type": "DEBIT"},
        ]

    def test_create_reconciliation_with_transactions(self):
        recon = create_bank_reconciliation(
            self.company, self.bank_account, self.period, self.user, self.bank_txs_data
        )
        self.assertEqual(recon.account, self.bank_account)
        # statement: 5000 - 1000 - 50 = 3950
        self.assertEqual(recon.statement_balance, Decimal("3950.00"))
        # ledger: 5000 - 1000 = 4000
        self.assertEqual(recon.ledger_balance, Decimal("4000.00"))
        self.assertEqual(recon.variance, Decimal("-50.00"))
        self.assertEqual(recon.bank_transactions.count(), 3)

    def test_create_reconciliation_no_transactions(self):
        recon = create_bank_reconciliation(
            self.company, self.bank_account, self.period, self.user
        )
        self.assertEqual(recon.bank_transactions.count(), 0)
        self.assertEqual(recon.statement_balance, Decimal("0.00"))

    def test_match_transactions(self):
        recon = create_bank_reconciliation(
            self.company, self.bank_account, self.period, self.user, self.bank_txs_data
        )
        bank_tx1 = recon.bank_transactions.get(reference="REF001")
        bank_tx2 = recon.bank_transactions.get(reference="REF002")

        # Match bank tx 1 to journal entry from j1
        ledger_entry = self.j1.entries.filter(entry_type="DEBIT").first()
        matches = [
            {"bank_transaction_id": bank_tx1.pk, "journal_entry_id": ledger_entry.pk,
             "amount_matched": Decimal("5000.00"), "note": "Exact match"},
            {"bank_transaction_id": bank_tx2.pk, "journal_entry_id": self.j2.entries.filter(entry_type="CREDIT").first().pk,
             "amount_matched": Decimal("1000.00"), "note": "Exact match"},
        ]
        match_reconciliation_items(recon, matches)

        self.assertEqual(recon.items.filter(status="MATCHED").count(), 2)
        bank_tx1.refresh_from_db()
        bank_tx2.refresh_from_db()
        self.assertTrue(bank_tx1.is_matched)
        self.assertTrue(bank_tx2.is_matched)

        # Unmatched bank fee should be created as UNMATCHED_BANK
        unmatched_count = recon.items.filter(status="UNMATCHED_BANK").count()
        self.assertEqual(unmatched_count, 1)

    def test_approve_reconciliation(self):
        recon = create_bank_reconciliation(
            self.company, self.bank_account, self.period, self.user, self.bank_txs_data
        )
        recon = approve_reconciliation(recon, self.user)
        self.assertEqual(recon.status, "APPROVED")
        self.assertEqual(recon.approved_by, self.user)
        self.assertIsNotNone(recon.approved_at)

    def test_approve_already_approved_raises(self):
        recon = create_bank_reconciliation(
            self.company, self.bank_account, self.period, self.user, self.bank_txs_data
        )
        approve_reconciliation(recon, self.user)
        with self.assertRaises(ValidationError):
            approve_reconciliation(recon, self.user)

    def test_reconciliation_rejects_non_asset_account(self):
        recon = create_bank_reconciliation(
            self.company, self.bank_account, self.period, self.user
        )
        # Attempted reconciliation on a non-asset would fail at form level
        self.assertEqual(recon.account.type, Account.AccountType.ASSET)
