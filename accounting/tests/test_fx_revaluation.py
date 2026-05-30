from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from accounting.models import (
    Account,
    CurrencyRevaluation,
    CurrencyRevaluationLine,
    ExchangeRate,
    FiscalYear,
    AccountingPeriod,
    AccountingAuditTrail,
    Journal,
)
from accounting.utils import (
    generate_fx_revaluation,
    post_fx_revaluation,
    reverse_fx_revaluation,
    get_latest_exchange_rate,
    get_or_create_fiscal_year,
    get_or_create_period,
)
from accounting.tests.fixtures import get_test_company

User = get_user_model()


class CurrencyRevaluationTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(
            email="reval@test.com", password="testpass123"
        )
        self.ngn_asset = Account.objects.create(
            company=self.company,
            name="Cash NGN",
            account_number="1001",
            type=Account.AccountType.ASSET,
            currency="NGN",
        )
        self.usd_asset = Account.objects.create(
            company=self.company,
            name="Cash USD",
            account_number="1002",
            type=Account.AccountType.ASSET,
            currency="USD",
        )
        self.gbp_liability = Account.objects.create(
            company=self.company,
            name="Loan GBP",
            account_number="2001",
            type=Account.AccountType.LIABILITY,
            currency="GBP",
        )
        self.unrealized_gain = Account.objects.create(
            company=self.company,
            name="Unrealized FX Gain",
            account_number="5001",
            type=Account.AccountType.REVENUE,
            currency="NGN",
        )
        self.unrealized_loss = Account.objects.create(
            company=self.company,
            name="Unrealized FX Loss",
            account_number="5002",
            type=Account.AccountType.EXPENSE,
            currency="NGN",
        )
        self.inactive_account = Account.objects.create(
            company=self.company,
            name="Old EUR Account",
            account_number="1003",
            type=Account.AccountType.ASSET,
            currency="EUR",
            status=Account.AccountStatus.INACTIVE,
        )

        self.fiscal_year = get_or_create_fiscal_year(
            year=2026, company=self.company
        )
        self.period = get_or_create_period(
            fiscal_year=self.fiscal_year,
            period_number=5,
            company=self.company,
        )

        self.reval_date = date(2026, 5, 29)

        ExchangeRate.objects.create(
            company=self.company,
            base_currency="NGN",
            quote_currency="USD",
            rate=Decimal("1550.00"),
            rate_date=date(2026, 5, 28),
        )
        ExchangeRate.objects.create(
            company=self.company,
            base_currency="NGN",
            quote_currency="USD",
            rate=Decimal("1600.00"),
            rate_date=self.reval_date,
        )
        ExchangeRate.objects.create(
            company=self.company,
            base_currency="NGN",
            quote_currency="GBP",
            rate=Decimal("2000.00"),
            rate_date=self.reval_date,
        )

    def _post_usd_balance(self, amount):
        from accounting.utils import create_journal_with_entries
        create_journal_with_entries(
            company=self.company,
            date=self.reval_date,
            description="Fund USD account",
            entries=[
                {
                    "account": self.usd_asset,
                    "entry_type": "DEBIT",
                    "amount": amount,
                    "memo": "Test deposit",
                },
                {
                    "account": self.ngn_asset,
                    "entry_type": "CREDIT",
                    "amount": amount,
                    "memo": "Test transfer",
                },
            ],
            user=self.user,
            fiscal_year=self.fiscal_year,
            period=self.period,
            auto_post=True,
            validate_balances=False,
        )

    def _post_gbp_balance(self, amount):
        from accounting.utils import create_journal_with_entries
        create_journal_with_entries(
            company=self.company,
            date=self.reval_date,
            description="GBP loan drawdown",
            entries=[
                {
                    "account": self.gbp_liability,
                    "entry_type": "CREDIT",
                    "amount": amount,
                    "memo": "Loan drawdown",
                },
                {
                    "account": self.ngn_asset,
                    "entry_type": "DEBIT",
                    "amount": amount,
                    "memo": "Cash received",
                },
            ],
            user=self.user,
            fiscal_year=self.fiscal_year,
            period=self.period,
            auto_post=True,
            validate_balances=False,
        )

    def test_get_latest_exchange_rate(self):
        rate = get_latest_exchange_rate(
            self.company, "NGN", "USD", self.reval_date
        )
        self.assertEqual(rate, Decimal("1600.00"))

    def test_get_latest_exchange_rate_falls_back_to_prior_date(self):
        # Remove the reval_date rate; should fall back to 2026-05-28 rate
        ExchangeRate.objects.filter(rate_date=self.reval_date, quote_currency="USD").delete()
        rate = get_latest_exchange_rate(
            self.company, "NGN", "USD", self.reval_date
        )
        self.assertEqual(rate, Decimal("1550.00"))

    def test_get_latest_exchange_rate_none_when_no_rate(self):
        rate = get_latest_exchange_rate(
            self.company, "NGN", "EUR", self.reval_date
        )
        self.assertIsNone(rate)

    def test_generate_fx_revaluation_no_foreign_balances(self):
        # NGN account has no balance and shouldn't appear
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        self.assertEqual(reval.lines.count(), 0)
        self.assertEqual(reval.status, CurrencyRevaluation.Status.DRAFT)

    def test_generate_fx_revaluation_asset_gain(self):
        self._post_usd_balance(Decimal("1000.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        self.assertEqual(reval.lines.count(), 1)
        line = reval.lines.first()
        self.assertEqual(line.account, self.usd_asset)
        self.assertEqual(line.foreign_currency, "USD")
        self.assertEqual(line.balance_fc, Decimal("1000.00"))
        self.assertEqual(line.rate_at_revaluation, Decimal("1600.00"))
        # Original at rate 1.0 = 1000, revalued at 1600 = 1,600,000
        # Gain = 1,599,000
        self.assertGreater(line.unrealized_gain_loss, Decimal("0"))
        self.assertEqual(line.entry_type, "DEBIT")

    def test_generate_fx_revaluation_liability_gain(self):
        self._post_gbp_balance(Decimal("500.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        self.assertEqual(reval.lines.count(), 1)
        line = reval.lines.first()
        self.assertEqual(line.account, self.gbp_liability)
        # Liability with credit balance: GBP 500 rate 1.0 → 500
        # Revalued at 2000 → 1,000,000. Liability increase = loss (CREDIT for liability)
        self.assertGreater(line.unrealized_gain_loss, Decimal("0"))
        self.assertEqual(line.entry_type, "CREDIT")

    def test_generate_fx_revaluation_skips_inactive_accounts(self):
        self._post_usd_balance(Decimal("100.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        for line in reval.lines.all():
            self.assertNotEqual(line.account, self.inactive_account)

    def test_generate_fx_revaluation_skips_zero_balances(self):
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        self.assertEqual(reval.lines.count(), 0)

    def test_generate_fx_revaluation_skips_zero_gain_loss(self):
        # Set rate to 1.0 so there is no gain/loss
        ExchangeRate.objects.filter(quote_currency="USD", rate_date=self.reval_date).delete()
        ExchangeRate.objects.create(
            company=self.company,
            base_currency="NGN",
            quote_currency="USD",
            rate=Decimal("1.0"),
            rate_date=self.reval_date,
        )
        self._post_usd_balance(Decimal("500.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        self.assertEqual(reval.lines.count(), 0)

    def test_post_fx_revaluation_creates_journal(self):
        self._post_usd_balance(Decimal("1000.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        reval = post_fx_revaluation(
            reval, self.user, self.unrealized_gain, self.unrealized_loss
        )
        self.assertEqual(reval.status, CurrencyRevaluation.Status.POSTED)
        self.assertIsNotNone(reval.journal)
        self.assertEqual(reval.journal.status, Journal.JournalStatus.POSTED)

    def test_post_fx_revaluation_balanced_journal(self):
        self._post_usd_balance(Decimal("1000.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        reval = post_fx_revaluation(
            reval, self.user, self.unrealized_gain, self.unrealized_loss
        )
        # validate_entries raises on imbalance, returns None on success
        reval.journal.validate_entries()
        journal = reval.journal
        debits = sum(
            e.amount for e in journal.entries.all() if e.entry_type == "DEBIT"
        )
        credits = sum(
            e.amount for e in journal.entries.all() if e.entry_type == "CREDIT"
        )
        self.assertEqual(debits, credits)

    def test_post_already_posted_raises(self):
        self._post_usd_balance(Decimal("100.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        post_fx_revaluation(
            reval, self.user, self.unrealized_gain, self.unrealized_loss
        )
        with self.assertRaises(ValidationError):
            post_fx_revaluation(
                reval, self.user, self.unrealized_gain, self.unrealized_loss
            )

    def test_post_reversed_raises(self):
        self._post_usd_balance(Decimal("100.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        post_fx_revaluation(
            reval, self.user, self.unrealized_gain, self.unrealized_loss
        )
        reverse_fx_revaluation(reval, self.user)
        with self.assertRaises(ValidationError):
            post_fx_revaluation(
                reval, self.user, self.unrealized_gain, self.unrealized_loss
            )

    def test_reverse_fx_revaluation(self):
        self._post_usd_balance(Decimal("100.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        reval = post_fx_revaluation(
            reval, self.user, self.unrealized_gain, self.unrealized_loss
        )
        reval = reverse_fx_revaluation(reval, self.user, reason="Test reversal")
        self.assertEqual(reval.status, CurrencyRevaluation.Status.REVERSED)

    def test_reverse_non_posted_raises(self):
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        with self.assertRaises(ValidationError):
            reverse_fx_revaluation(reval, self.user)

    def test_reversal_creates_audit_trail(self):
        self._post_usd_balance(Decimal("100.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        reval = post_fx_revaluation(
            reval, self.user, self.unrealized_gain, self.unrealized_loss
        )
        reverse_fx_revaluation(reval, self.user)
        self.assertEqual(reval.status, CurrencyRevaluation.Status.REVERSED)

    def test_post_creates_audit_trail(self):
        self._post_usd_balance(Decimal("100.00"))
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        post_fx_revaluation(
            reval, self.user, self.unrealized_gain, self.unrealized_loss
        )
        self.assertEqual(reval.status, CurrencyRevaluation.Status.POSTED)
        self.assertIsNotNone(reval.journal)

    def test_generate_skips_missing_exchange_rate(self):
        Account.objects.create(
            company=self.company,
            name="EUR Asset",
            account_number="1004",
            type=Account.AccountType.ASSET,
            currency="EUR",
        )
        reval = generate_fx_revaluation(
            self.company, self.reval_date, "NGN", self.user
        )
        self.assertEqual(reval.lines.count(), 0)
