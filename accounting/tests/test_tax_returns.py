from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounting.models import (
    Account,
    FiscalYear,
    AccountingPeriod,
    TaxReturn,
    TaxReturnLine,
)
from accounting.utils import (
    generate_tax_return,
    file_tax_return,
    get_or_create_fiscal_year,
    get_or_create_period,
)
from accounting.tests.fixtures import get_test_company

User = get_user_model()


class TaxReturnTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(
            email="tax@test.com", password="testpass123"
        )
        self.revenue = Account.objects.create(
            company=self.company, name="Sales Revenue", account_number="4000",
            type=Account.AccountType.REVENUE,
        )
        self.vat_output = Account.objects.create(
            company=self.company, name="VAT Output", account_number="2500",
            type=Account.AccountType.LIABILITY,
        )
        self.vat_input = Account.objects.create(
            company=self.company, name="VAT Input", account_number="2501",
            type=Account.AccountType.ASSET,
        )
        self.wht_payable = Account.objects.create(
            company=self.company, name="WHT Payable", account_number="2600",
            type=Account.AccountType.LIABILITY,
        )
        self.bank = Account.objects.create(
            company=self.company, name="Bank", account_number="1010",
            type=Account.AccountType.ASSET,
        )

        self.fiscal_year = get_or_create_fiscal_year(year=2026, company=self.company)
        self.period = get_or_create_period(
            fiscal_year=self.fiscal_year, period_number=5, company=self.company
        )

    def _post_sales_with_vat(self, net_amount, vat_amount):
        from accounting.utils import create_journal_with_entries
        total = net_amount + vat_amount
        create_journal_with_entries(
            company=self.company, date=date(2026, 5, 10),
            description="Sale + VAT",
            entries=[
                {"account": self.bank, "entry_type": "DEBIT", "amount": total, "memo": "Sale receipt"},
                {"account": self.revenue, "entry_type": "CREDIT", "amount": net_amount, "memo": "Revenue"},
                {"account": self.vat_output, "entry_type": "CREDIT", "amount": vat_amount, "memo": "VAT"},
            ],
            user=self.user, fiscal_year=self.fiscal_year, period=self.period,
            auto_post=True, validate_balances=False,
        )

    def _post_purchase_with_vat(self, net_amount, vat_amount):
        from accounting.utils import create_journal_with_entries
        total = net_amount + vat_amount
        create_journal_with_entries(
            company=self.company, date=date(2026, 5, 15),
            description="Purchase + VAT",
            entries=[
                {"account": self.vat_input, "entry_type": "DEBIT", "amount": vat_amount, "memo": "Input VAT"},
                {"account": self.bank, "entry_type": "CREDIT", "amount": total, "memo": "Payment"},
                {"account": self.bank, "entry_type": "DEBIT", "amount": total - vat_amount, "memo": "Balancing"},
            ],
            user=self.user, fiscal_year=self.fiscal_year, period=self.period,
            auto_post=True, validate_balances=False,
        )

    def test_generate_vat_return(self):
        self._post_sales_with_vat(Decimal("10000.00"), Decimal("750.00"))
        self._post_purchase_with_vat(Decimal("5000.00"), Decimal("375.00"))

        tax_return = generate_tax_return(
            self.company, "VAT", self.period, self.user,
            tax_accounts={"vat_output": self.vat_output, "vat_input": self.vat_input},
        )
        self.assertEqual(tax_return.total_tax, Decimal("750.00"))
        self.assertEqual(tax_return.total_input_tax, Decimal("375.00"))
        self.assertEqual(tax_return.net_tax_payable, Decimal("375.00"))
        self.assertEqual(tax_return.status, TaxReturn.Status.DRAFT)

    def test_tax_return_list_renders(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounting:tax_return_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tax Returns")

    def test_generate_wht_return(self):
        from accounting.utils import create_journal_with_entries
        create_journal_with_entries(
            company=self.company, date=date(2026, 5, 20),
            description="WHT on supplier",
            entries=[
                {"account": self.bank, "entry_type": "CREDIT", "amount": Decimal("950.00"), "memo": "Net payment"},
                {"account": self.wht_payable, "entry_type": "CREDIT", "amount": Decimal("50.00"), "memo": "WHT"},
                {"account": self.bank, "entry_type": "DEBIT", "amount": Decimal("1000.00"), "memo": "Gross expense"},
            ],
            user=self.user, fiscal_year=self.fiscal_year, period=self.period,
            auto_post=True, validate_balances=False,
        )

        tax_return = generate_tax_return(
            self.company, "WHT", self.period, self.user,
            tax_accounts={"wht_payable": self.wht_payable},
        )
        self.assertEqual(tax_return.total_tax, Decimal("50.00"))
        self.assertEqual(tax_return.return_type, "WHT")

    def test_file_tax_return(self):
        self._post_sales_with_vat(Decimal("10000.00"), Decimal("750.00"))
        tax_return = generate_tax_return(
            self.company, "VAT", self.period, self.user,
            tax_accounts={"vat_output": self.vat_output},
        )
        tax_return = file_tax_return(tax_return, self.user, filing_reference="VAT-Q1-2026-001")
        self.assertEqual(tax_return.status, TaxReturn.Status.FILED)
        self.assertEqual(tax_return.filing_reference, "VAT-Q1-2026-001")
        self.assertEqual(tax_return.filed_by, self.user)
        self.assertIsNotNone(tax_return.filed_at)

    def test_file_already_filed_raises(self):
        tax_return = TaxReturn.objects.create(
            company=self.company, return_type="VAT", period=self.period,
            return_period_start=self.period.start_date,
            return_period_end=self.period.end_date,
            status=TaxReturn.Status.FILED,
        )
        with self.assertRaises(ValidationError):
            file_tax_return(tax_return, self.user)

    def test_duplicate_tax_return_raises(self):
        self._post_sales_with_vat(Decimal("1000.00"), Decimal("75.00"))
        generate_tax_return(
            self.company, "VAT", self.period, self.user,
            tax_accounts={"vat_output": self.vat_output},
        )
        with self.assertRaises(ValidationError):
            generate_tax_return(
                self.company, "VAT", self.period, self.user,
                tax_accounts={"vat_output": self.vat_output},
            )

    def test_generate_empty_return(self):
        tax_return = generate_tax_return(
            self.company, "PAYE", self.period, self.user,
        )
        self.assertEqual(tax_return.total_tax, Decimal("0.00"))
        self.assertEqual(tax_return.lines.count(), 0)
