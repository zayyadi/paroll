from datetime import date
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from accounting.models import Account, Journal
from company.models import Company
from inventory.models import (
    Customer,
    InventoryCategory,
    InventoryItem,
    PurchaseOrder,
    StockMovement,
    Supplier,
)
from inventory.services import (
    create_purchase_order,
    get_stock_on_hand,
    post_inventory_adjustment,
    post_opening_stock,
    post_purchase_receipt,
    post_customer_payment,
    post_customer_return,
    post_sales_invoice,
    post_supplier_payment,
    post_supplier_return,
    post_tax_remittance,
    receive_purchase_order,
    post_stock_transfer,
)


class InventoryCoreTests(TestCase):
    def setUp(self):
        self.company_a = Company.objects.create(name="Inventory Tenant A")
        self.company_b = Company.objects.create(name="Inventory Tenant B")
        self.accounts = self._create_accounts(self.company_a)
        self.category = InventoryCategory.objects.create(
            company=self.company_a,
            name="Wholesale Goods",
            inventory_account=self.accounts["inventory"],
            opening_balance_equity_account=self.accounts["opening_equity"],
            adjustment_gain_account=self.accounts["adjustment_gain"],
            shrinkage_expense_account=self.accounts["shrinkage"],
        )
        self.item = InventoryItem.objects.create(
            company=self.company_a,
            category=self.category,
            sku="MED-001",
            name="Paracetamol Carton",
        )
        self.main = self.item.company.warehouses.create(code="MAIN", name="Main Store")
        self.main_location = self.main.locations.create(
            company=self.company_a,
            code="MAIN-BIN",
            name="Main Bin",
        )
        self.branch = self.item.company.warehouses.create(
            code="BRANCH", name="Branch Store"
        )
        self.branch_location = self.branch.locations.create(
            company=self.company_a,
            code="BRANCH-BIN",
            name="Branch Bin",
        )

    def _create_accounts(self, company):
        return {
            "inventory": Account.objects.create(
                company=company,
                name="Inventory Asset",
                account_number="1200",
                type=Account.AccountType.ASSET,
            ),
            "opening_equity": Account.objects.create(
                company=company,
                name="Opening Balance Equity",
                account_number="3000",
                type=Account.AccountType.EQUITY,
            ),
            "adjustment_gain": Account.objects.create(
                company=company,
                name="Inventory Adjustment Gain",
                account_number="4200",
                type=Account.AccountType.REVENUE,
            ),
            "shrinkage": Account.objects.create(
                company=company,
                name="Inventory Shrinkage",
                account_number="6200",
                type=Account.AccountType.EXPENSE,
            ),
            "payable": Account.objects.create(
                company=company,
                name="Trade Payables",
                account_number="2100",
                type=Account.AccountType.LIABILITY,
            ),
            "receivable": Account.objects.create(
                company=company,
                name="Trade Receivables",
                account_number="1100",
                type=Account.AccountType.ASSET,
            ),
            "sales": Account.objects.create(
                company=company,
                name="Wholesale Sales",
                account_number="4100",
                type=Account.AccountType.REVENUE,
            ),
            "cogs": Account.objects.create(
                company=company,
                name="Cost of Goods Sold",
                account_number="5100",
                type=Account.AccountType.EXPENSE,
            ),
            "vat_input": Account.objects.create(
                company=company,
                name="Input VAT",
                account_number="1300",
                type=Account.AccountType.ASSET,
            ),
            "vat_output": Account.objects.create(
                company=company,
                name="Output VAT",
                account_number="2200",
                type=Account.AccountType.LIABILITY,
            ),
            "wht_payable": Account.objects.create(
                company=company,
                name="WHT Payable",
                account_number="2300",
                type=Account.AccountType.LIABILITY,
            ),
            "wht_receivable": Account.objects.create(
                company=company,
                name="WHT Receivable",
                account_number="1400",
                type=Account.AccountType.ASSET,
            ),
            "bank": Account.objects.create(
                company=company,
                name="Bank",
                account_number="1000",
                type=Account.AccountType.ASSET,
            ),
        }

    def test_sku_is_unique_per_company_not_global(self):
        other_category = InventoryCategory.objects.create(
            company=self.company_b,
            name="Wholesale Goods",
        )
        InventoryItem.objects.create(
            company=self.company_b,
            category=other_category,
            sku="MED-001",
            name="Tenant B Paracetamol",
        )

        with self.assertRaises(IntegrityError):
            InventoryItem.objects.create(
                company=self.company_a,
                category=self.category,
                sku="MED-001",
                name="Duplicate Paracetamol",
            )

    def test_opening_stock_posts_stock_movement_and_balanced_journal(self):
        document = post_opening_stock(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity=Decimal("10"),
            unit_cost=Decimal("25.00"),
            posting_date=date(2026, 5, 1),
        )

        self.assertEqual(get_stock_on_hand(self.item), Decimal("10.0000"))
        self.assertEqual(document.journal.status, Journal.JournalStatus.POSTED)
        self.assertEqual(document.journal.company, self.company_a)
        self.assertEqual(document.journal.entries.count(), 2)
        self.assertEqual(
            document.movements.get().total_cost,
            Decimal("250.00"),
        )

    def test_negative_adjustment_cannot_exceed_available_stock(self):
        post_opening_stock(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity=Decimal("5"),
            unit_cost=Decimal("20.00"),
        )

        with self.assertRaises(ValueError):
            post_inventory_adjustment(
                company=self.company_a,
                item=self.item,
                location=self.main_location,
                quantity_delta=Decimal("-6"),
                reason="Count shortage",
            )

    def test_positive_and_negative_adjustments_post_expected_journals(self):
        post_opening_stock(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity=Decimal("10"),
            unit_cost=Decimal("10.00"),
        )
        gain = post_inventory_adjustment(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity_delta=Decimal("2"),
            unit_cost=Decimal("12.00"),
            reason="Found stock",
        )
        loss = post_inventory_adjustment(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity_delta=Decimal("-3"),
            reason="Damaged stock",
        )

        self.assertEqual(get_stock_on_hand(self.item), Decimal("9.0000"))
        self.assertEqual(gain.journal.entries.filter(entry_type="DEBIT").count(), 1)
        self.assertEqual(loss.journal.entries.filter(entry_type="CREDIT").count(), 1)

    def test_transfer_moves_stock_without_creating_journal(self):
        post_opening_stock(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity=Decimal("10"),
            unit_cost=Decimal("15.00"),
        )

        transfer = post_stock_transfer(
            company=self.company_a,
            item=self.item,
            from_location=self.main_location,
            to_location=self.branch_location,
            quantity=Decimal("4"),
            reason="Branch replenishment",
        )

        self.assertIsNone(transfer.journal)
        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("6.0000"))
        self.assertEqual(get_stock_on_hand(self.item, self.branch_location), Decimal("4.0000"))
        self.assertEqual(
            StockMovement.objects.filter(document_id=transfer.id).count(),
            2,
        )

    def test_purchase_receipt_increases_stock_and_posts_payable_journal(self):
        supplier = Supplier.objects.create(
            company=self.company_a,
            name="MedSupply Wholesale",
            payable_account=self.accounts["payable"],
            wht_payable_account=self.accounts["wht_payable"],
        )

        receipt = post_purchase_receipt(
            company=self.company_a,
            supplier=supplier,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("6"),
                    "unit_cost": Decimal("18.50"),
                }
            ],
            posting_date=date(2026, 5, 2),
            reference="GRN-001",
            reason="Supplier delivery",
        )

        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("6.0000"))
        self.assertEqual(receipt.document_type, receipt.DocumentType.PURCHASE_RECEIPT)
        self.assertEqual(receipt.purchase_receipt.supplier, supplier)
        self.assertEqual(receipt.movements.get().total_cost, Decimal("111.00"))
        self.assertEqual(receipt.journal.company, self.company_a)
        self.assertEqual(receipt.journal.entries.filter(entry_type="DEBIT").count(), 1)
        self.assertEqual(receipt.journal.entries.filter(entry_type="CREDIT").count(), 1)

    def test_purchase_receipt_posts_input_vat_and_purchase_wht(self):
        supplier = Supplier.objects.create(
            company=self.company_a,
            name="Taxed Supplier",
            payable_account=self.accounts["payable"],
            wht_payable_account=self.accounts["wht_payable"],
        )

        receipt = post_purchase_receipt(
            company=self.company_a,
            supplier=supplier,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("10"),
                    "unit_cost": Decimal("100.00"),
                    "vat_rate": Decimal("7.50"),
                    "wht_rate": Decimal("5.00"),
                }
            ],
            vat_input_account=self.accounts["vat_input"],
            posting_date=date(2026, 5, 2),
            reference="GRN-TAX-001",
        )

        entries = receipt.journal.entries.select_related("account")
        self.assertEqual(entries.get(account=self.accounts["inventory"]).amount, Decimal("1000.00"))
        self.assertEqual(entries.get(account=self.accounts["vat_input"]).amount, Decimal("75.00"))
        self.assertEqual(entries.get(account=self.accounts["wht_payable"]).amount, Decimal("50.00"))
        self.assertEqual(entries.get(account=self.accounts["payable"]).amount, Decimal("1025.00"))

    def test_purchase_order_can_be_partially_and_fully_received(self):
        supplier = Supplier.objects.create(
            company=self.company_a,
            name="PO Supplier",
            payable_account=self.accounts["payable"],
        )
        purchase_order = create_purchase_order(
            company=self.company_a,
            supplier=supplier,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("10"),
                    "unit_cost": Decimal("7.50"),
                }
            ],
            order_date=date(2026, 5, 3),
            reference="PO-001",
            notes="Weekly restock",
        )

        self.assertEqual(purchase_order.status, PurchaseOrder.Status.ORDERED)
        receipt = receive_purchase_order(
            company=self.company_a,
            purchase_order=purchase_order,
            location=self.main_location,
            lines=[
                {
                    "purchase_order_line": purchase_order.lines.get(),
                    "quantity": Decimal("4"),
                }
            ],
            posting_date=date(2026, 5, 4),
            reference="GRN-PO-001",
            reason="Partial delivery",
        )

        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.Status.PARTIALLY_RECEIVED)
        self.assertEqual(purchase_order.lines.get().received_quantity, Decimal("4.0000"))
        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("4.0000"))
        self.assertEqual(receipt.purchase_receipt.purchase_order, purchase_order)

        receive_purchase_order(
            company=self.company_a,
            purchase_order=purchase_order,
            location=self.main_location,
            lines=[
                {
                    "purchase_order_line": purchase_order.lines.get(),
                    "quantity": Decimal("6"),
                }
            ],
            posting_date=date(2026, 5, 5),
            reference="GRN-PO-002",
            reason="Final delivery",
        )

        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(purchase_order.lines.get().received_quantity, Decimal("10.0000"))
        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("10.0000"))

    def test_sales_invoice_posts_revenue_tax_cogs_and_reduces_stock(self):
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        customer = Customer.objects.create(
            company=self.company_a,
            name="Wholesale Customer",
            receivable_account=self.accounts["receivable"],
            wht_receivable_account=self.accounts["wht_receivable"],
        )
        post_opening_stock(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity=Decimal("10"),
            unit_cost=Decimal("60.00"),
        )

        invoice = post_sales_invoice(
            company=self.company_a,
            customer=customer,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("4"),
                    "unit_price": Decimal("100.00"),
                    "vat_rate": Decimal("7.50"),
                    "wht_rate": Decimal("5.00"),
                }
            ],
            vat_output_account=self.accounts["vat_output"],
            posting_date=date(2026, 5, 6),
            reference="INV-001",
        )

        entries = invoice.journal.entries.select_related("account")
        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("6.0000"))
        self.assertEqual(entries.get(account=self.accounts["receivable"]).amount, Decimal("410.00"))
        self.assertEqual(entries.get(account=self.accounts["wht_receivable"]).amount, Decimal("20.00"))
        self.assertEqual(entries.get(account=self.accounts["sales"]).amount, Decimal("400.00"))
        self.assertEqual(entries.get(account=self.accounts["vat_output"]).amount, Decimal("30.00"))
        self.assertEqual(entries.get(account=self.accounts["cogs"]).amount, Decimal("240.00"))
        self.assertEqual(
            entries.get(account=self.accounts["inventory"], entry_type="CREDIT").amount,
            Decimal("240.00"),
        )

    def test_customer_payment_debits_bank_and_credits_receivable(self):
        customer = Customer.objects.create(
            company=self.company_a,
            name="Paying Customer",
            receivable_account=self.accounts["receivable"],
        )

        payment = post_customer_payment(
            company=self.company_a,
            customer=customer,
            cash_account=self.accounts["bank"],
            amount=Decimal("410.00"),
            posting_date=date(2026, 5, 7),
            reference="RCPT-001",
        )

        entries = payment.journal.entries.select_related("account")
        self.assertEqual(entries.get(account=self.accounts["bank"]).entry_type, "DEBIT")
        self.assertEqual(entries.get(account=self.accounts["bank"]).amount, Decimal("410.00"))
        self.assertEqual(entries.get(account=self.accounts["receivable"]).entry_type, "CREDIT")
        self.assertEqual(entries.get(account=self.accounts["receivable"]).amount, Decimal("410.00"))

    def test_supplier_payment_debits_payable_and_credits_bank(self):
        supplier = Supplier.objects.create(
            company=self.company_a,
            name="Paid Supplier",
            payable_account=self.accounts["payable"],
        )

        payment = post_supplier_payment(
            company=self.company_a,
            supplier=supplier,
            cash_account=self.accounts["bank"],
            amount=Decimal("1025.00"),
            posting_date=date(2026, 5, 8),
            reference="PAY-001",
        )

        entries = payment.journal.entries.select_related("account")
        self.assertEqual(entries.get(account=self.accounts["payable"]).entry_type, "DEBIT")
        self.assertEqual(entries.get(account=self.accounts["payable"]).amount, Decimal("1025.00"))
        self.assertEqual(entries.get(account=self.accounts["bank"]).entry_type, "CREDIT")
        self.assertEqual(entries.get(account=self.accounts["bank"]).amount, Decimal("1025.00"))

    def test_tax_remittance_nets_input_vat_and_pays_liabilities(self):
        remittance = post_tax_remittance(
            company=self.company_a,
            cash_account=self.accounts["bank"],
            vat_output_account=self.accounts["vat_output"],
            vat_input_account=self.accounts["vat_input"],
            wht_payable_account=self.accounts["wht_payable"],
            vat_output_amount=Decimal("300.00"),
            vat_input_amount=Decimal("75.00"),
            wht_amount=Decimal("50.00"),
            posting_date=date(2026, 5, 31),
            reference="TAX-MAY",
        )

        entries = remittance.journal.entries.select_related("account")
        self.assertEqual(entries.get(account=self.accounts["vat_output"]).entry_type, "DEBIT")
        self.assertEqual(entries.get(account=self.accounts["vat_output"]).amount, Decimal("300.00"))
        self.assertEqual(entries.get(account=self.accounts["vat_input"]).entry_type, "CREDIT")
        self.assertEqual(entries.get(account=self.accounts["vat_input"]).amount, Decimal("75.00"))
        self.assertEqual(entries.get(account=self.accounts["wht_payable"]).entry_type, "DEBIT")
        self.assertEqual(entries.get(account=self.accounts["wht_payable"]).amount, Decimal("50.00"))
        self.assertEqual(entries.get(account=self.accounts["bank"]).entry_type, "CREDIT")
        self.assertEqual(entries.get(account=self.accounts["bank"]).amount, Decimal("275.00"))

    def test_customer_return_reverses_sale_tax_cogs_and_restocks(self):
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        customer = Customer.objects.create(
            company=self.company_a,
            name="Returning Customer",
            receivable_account=self.accounts["receivable"],
            wht_receivable_account=self.accounts["wht_receivable"],
        )
        post_opening_stock(
            company=self.company_a,
            item=self.item,
            location=self.main_location,
            quantity=Decimal("10"),
            unit_cost=Decimal("60.00"),
        )
        post_sales_invoice(
            company=self.company_a,
            customer=customer,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("4"),
                    "unit_price": Decimal("100.00"),
                    "vat_rate": Decimal("7.50"),
                    "wht_rate": Decimal("5.00"),
                }
            ],
            vat_output_account=self.accounts["vat_output"],
        )

        credit_note = post_customer_return(
            company=self.company_a,
            customer=customer,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("1"),
                    "unit_price": Decimal("100.00"),
                    "unit_cost": Decimal("60.00"),
                    "vat_rate": Decimal("7.50"),
                    "wht_rate": Decimal("5.00"),
                }
            ],
            vat_output_account=self.accounts["vat_output"],
            posting_date=date(2026, 5, 9),
            reference="CN-001",
        )

        entries = credit_note.journal.entries.select_related("account")
        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("7.0000"))
        self.assertEqual(entries.get(account=self.accounts["sales"]).entry_type, "DEBIT")
        self.assertEqual(entries.get(account=self.accounts["sales"]).amount, Decimal("100.00"))
        self.assertEqual(entries.get(account=self.accounts["vat_output"]).entry_type, "DEBIT")
        self.assertEqual(entries.get(account=self.accounts["vat_output"]).amount, Decimal("7.50"))
        self.assertEqual(entries.get(account=self.accounts["wht_receivable"]).entry_type, "CREDIT")
        self.assertEqual(entries.get(account=self.accounts["wht_receivable"]).amount, Decimal("5.00"))
        self.assertEqual(entries.get(account=self.accounts["receivable"]).entry_type, "CREDIT")
        self.assertEqual(entries.get(account=self.accounts["receivable"]).amount, Decimal("102.50"))
        self.assertEqual(entries.get(account=self.accounts["inventory"]).entry_type, "DEBIT")
        self.assertEqual(entries.get(account=self.accounts["inventory"]).amount, Decimal("60.00"))
        self.assertEqual(entries.get(account=self.accounts["cogs"]).entry_type, "CREDIT")
        self.assertEqual(entries.get(account=self.accounts["cogs"]).amount, Decimal("60.00"))

    def test_supplier_return_reverses_purchase_tax_and_reduces_stock(self):
        supplier = Supplier.objects.create(
            company=self.company_a,
            name="Return Supplier",
            payable_account=self.accounts["payable"],
            wht_payable_account=self.accounts["wht_payable"],
        )
        post_purchase_receipt(
            company=self.company_a,
            supplier=supplier,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("5"),
                    "unit_cost": Decimal("100.00"),
                    "vat_rate": Decimal("7.50"),
                    "wht_rate": Decimal("5.00"),
                }
            ],
            vat_input_account=self.accounts["vat_input"],
        )

        debit_note = post_supplier_return(
            company=self.company_a,
            supplier=supplier,
            location=self.main_location,
            lines=[
                {
                    "item": self.item,
                    "quantity": Decimal("1"),
                    "unit_cost": Decimal("100.00"),
                    "vat_rate": Decimal("7.50"),
                    "wht_rate": Decimal("5.00"),
                }
            ],
            vat_input_account=self.accounts["vat_input"],
            posting_date=date(2026, 5, 10),
            reference="DN-001",
        )

        entries = debit_note.journal.entries.select_related("account")
        self.assertEqual(get_stock_on_hand(self.item, self.main_location), Decimal("4.0000"))
        self.assertEqual(entries.get(account=self.accounts["payable"]).entry_type, "DEBIT")
        self.assertEqual(entries.get(account=self.accounts["payable"]).amount, Decimal("102.50"))
        self.assertEqual(entries.get(account=self.accounts["inventory"]).entry_type, "CREDIT")
        self.assertEqual(entries.get(account=self.accounts["inventory"]).amount, Decimal("100.00"))
        self.assertEqual(entries.get(account=self.accounts["vat_input"]).entry_type, "CREDIT")
        self.assertEqual(entries.get(account=self.accounts["vat_input"]).amount, Decimal("7.50"))
        self.assertEqual(entries.get(account=self.accounts["wht_payable"]).entry_type, "DEBIT")
        self.assertEqual(entries.get(account=self.accounts["wht_payable"]).amount, Decimal("5.00"))
