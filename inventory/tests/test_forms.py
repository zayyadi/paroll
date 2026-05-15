from django.test import TestCase

from accounting.models import Account
from company.models import Company
from inventory.forms import (
    CustomerForm,
    InventoryCategoryForm,
    PurchaseReceiptForm,
    SalesInvoiceForm,
    SupplierForm,
    TaxRemittanceForm,
)


class InventoryAccountDropdownTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Dropdown Co")
        self.other_company = Company.objects.create(name="Other Dropdown Co")
        self.asset = self._account("Inventory Asset", "1200", Account.AccountType.ASSET)
        self.input_vat = self._account("Input VAT", "1300", Account.AccountType.ASSET)
        self.receivable = self._account("Trade Receivables", "1100", Account.AccountType.ASSET)
        self.output_vat = self._account("Output VAT", "2200", Account.AccountType.LIABILITY)
        self.payable = self._account("Trade Payables", "2000", Account.AccountType.LIABILITY)
        self.wht_payable = self._account("WHT Payable", "2300", Account.AccountType.LIABILITY)
        self.sales = self._account("Wholesale Sales", "4100", Account.AccountType.REVENUE)
        self.cogs = self._account("Cost of Goods Sold", "5100", Account.AccountType.EXPENSE)
        self.other_asset = Account.objects.create(
            company=self.other_company,
            name="Other Asset",
            account_number="1200",
            type=Account.AccountType.ASSET,
        )

    def _account(self, name, number, account_type):
        return Account.objects.create(
            company=self.company,
            name=name,
            account_number=number,
            type=account_type,
        )

    def assertFieldAccounts(self, form, field_name, expected_accounts):
        self.assertEqual(
            list(form.fields[field_name].queryset),
            expected_accounts,
        )

    def test_category_posting_fields_show_only_relevant_account_types(self):
        form = InventoryCategoryForm(company=self.company)

        self.assertFieldAccounts(
            form,
            "inventory_account",
            [self.receivable, self.asset, self.input_vat],
        )
        self.assertFieldAccounts(form, "sales_revenue_account", [self.sales])
        self.assertFieldAccounts(form, "cogs_account", [self.cogs])

    def test_supplier_and_customer_account_fields_are_tenant_and_type_filtered(self):
        supplier_form = SupplierForm(company=self.company)
        customer_form = CustomerForm(company=self.company)

        self.assertFieldAccounts(
            supplier_form,
            "payable_account",
            [self.payable, self.output_vat, self.wht_payable],
        )
        self.assertFieldAccounts(
            supplier_form,
            "wht_payable_account",
            [self.payable, self.output_vat, self.wht_payable],
        )
        self.assertFieldAccounts(
            customer_form,
            "receivable_account",
            [self.receivable, self.asset, self.input_vat],
        )
        self.assertNotIn(self.other_asset, customer_form.fields["receivable_account"].queryset)

    def test_transaction_tax_account_fields_show_relevant_accounts(self):
        purchase_form = PurchaseReceiptForm(company=self.company)
        sales_form = SalesInvoiceForm(company=self.company)
        tax_form = TaxRemittanceForm(company=self.company)

        self.assertFieldAccounts(
            purchase_form,
            "vat_input_account",
            [self.receivable, self.asset, self.input_vat],
        )
        self.assertFieldAccounts(
            sales_form,
            "vat_output_account",
            [self.payable, self.output_vat, self.wht_payable],
        )
        self.assertFieldAccounts(
            tax_form,
            "cash_account",
            [self.receivable, self.asset, self.input_vat],
        )
        self.assertFieldAccounts(
            tax_form,
            "wht_payable_account",
            [self.payable, self.output_vat, self.wht_payable],
        )
