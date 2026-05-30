from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model

from inventory.models import (
    Supplier, Customer, InventoryCategory, InventoryItem, StockLocation,
    Warehouse, PurchaseOrder, PurchaseOrderLine, SalesOrder, SalesOrderLine,
    VendorBill, VendorBillLine, LandedCost, LandedCostAllocation,
)
from inventory.services import (
    create_purchase_order, receive_purchase_order,
    create_sales_order, ship_sales_order,
    create_vendor_bill, post_vendor_bill,
    allocate_landed_costs, post_landed_cost,
    ensure_default_posting_accounts,
)
from accounting.models import Account, FiscalYear, AccountingPeriod
from accounting.utils import get_or_create_fiscal_year, get_or_create_period
from accounting.tests.fixtures import get_test_company

User = get_user_model()


class Phase3SalesOrderTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(email="p3@test.com", password="testpass")
        ensure_default_posting_accounts(self.company)

        self.fiscal_year = get_or_create_fiscal_year(year=2026, company=self.company)
        self.period = get_or_create_period(self.fiscal_year, 5, company=self.company)

        self.wh = Warehouse.objects.create(company=self.company, code="WH1", name="Main")
        self.loc = StockLocation.objects.create(company=self.company, warehouse=self.wh, code="LOC1", name="Shelf A")

        self.ap_acct = Account.objects.get(company=self.company, account_number="2000")
        self.ar_acct = Account.objects.get(company=self.company, account_number="1100")
        self.inv_acct = Account.objects.get(company=self.company, account_number="1200")
        self.cogs_acct = Account.objects.get(company=self.company, account_number="5100")
        self.rev_acct = Account.objects.get(company=self.company, account_number="4100")

        self.cat = InventoryCategory.objects.create(
            company=self.company, name="Sales Goods", costing_method="WEIGHTED_AVERAGE",
            inventory_account=self.inv_acct, cogs_account=self.cogs_acct,
            sales_revenue_account=self.rev_acct,
            adjustment_gain_account=Account.objects.get(company=self.company, account_number="4200"),
            shrinkage_expense_account=Account.objects.get(company=self.company, account_number="6200"),
            opening_balance_equity_account=Account.objects.get(company=self.company, account_number="3000"),
        )
        self.item = InventoryItem.objects.create(
            company=self.company, sku="PROD001", name="Product 1", category=self.cat,
            default_sales_price=Decimal("100.00"),
        )
        self.item2 = InventoryItem.objects.create(
            company=self.company, sku="PROD002", name="Product 2", category=self.cat,
            default_sales_price=Decimal("200.00"),
        )

        self.supplier = Supplier.objects.create(company=self.company, name="Supplier X", payable_account=self.ap_acct)
        self.customer = Customer.objects.create(company=self.company, name="Customer Y", receivable_account=self.ar_acct)

        # Seed stock via a purchase receipt
        from inventory.services import post_purchase_receipt
        post_purchase_receipt(
            company=self.company, supplier=self.supplier, location=self.loc,
            lines=[{"item": self.item, "location": self.loc, "quantity": Decimal("50"), "unit_cost": Decimal("50.00")}],
            posting_date=date(2026, 5, 1),
        )
        post_purchase_receipt(
            company=self.company, supplier=self.supplier, location=self.loc,
            lines=[{"item": self.item2, "location": self.loc, "quantity": Decimal("30"), "unit_cost": Decimal("100.00")}],
            posting_date=date(2026, 5, 1),
        )

    def test_create_sales_order(self):
        so = create_sales_order(
            company=self.company, customer=self.customer,
            lines=[
                {"item": self.item, "quantity": Decimal("5"), "unit_price": Decimal("100.00")},
                {"item": self.item2, "quantity": Decimal("3"), "unit_price": Decimal("200.00")},
            ],
            reserve_stock=False,
        )
        self.assertEqual(so.status, SalesOrder.Status.CONFIRMED)
        self.assertEqual(so.lines.count(), 2)

    def test_create_sales_order_with_reservation(self):
        so = create_sales_order(
            company=self.company, customer=self.customer,
            lines=[
                {"item": self.item, "quantity": Decimal("10"), "unit_price": Decimal("100.00"), "location": self.loc},
            ],
            reserve_stock=True,
        )
        line = so.lines.first()
        self.assertEqual(line.reserved_quantity, Decimal("10.0000"))

    def test_ship_sales_order_creates_invoice(self):
        so = create_sales_order(
            company=self.company, customer=self.customer,
            lines=[
                {"item": self.item, "quantity": Decimal("5"), "unit_price": Decimal("100.00")},
            ],
            reserve_stock=False,
        )
        so_line = so.lines.first()
        invoice = ship_sales_order(
            company=self.company, sales_order=so, location=self.loc,
            lines=[{"sales_order_line": so_line, "quantity": Decimal("5")}],
        )
        so.refresh_from_db()
        so_line.refresh_from_db()
        self.assertEqual(so_line.shipped_quantity, Decimal("5.0000"))
        self.assertEqual(so.status, SalesOrder.Status.SHIPPED)
        self.assertIsNotNone(invoice)

    def test_sales_order_insufficient_stock(self):
        with self.assertRaises(ValueError):
            create_sales_order(
                company=self.company, customer=self.customer,
                lines=[
                    {"item": self.item, "quantity": Decimal("999"), "unit_price": Decimal("100.00"), "location": self.loc},
                ],
                reserve_stock=True,
            )


class Phase3VendorBillTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(email="vb@test.com", password="testpass")
        result = ensure_default_posting_accounts(self.company)

        self.wh = Warehouse.objects.create(company=self.company, code="WHB", name="Main")
        self.loc = StockLocation.objects.create(company=self.company, warehouse=self.wh, code="LOCB", name="Shelf B")

        self.inv_acct = Account.objects.get(company=self.company, account_number="1200")
        self.cogs_acct = Account.objects.get(company=self.company, account_number="5100")
        self.ap_acct = Account.objects.get(company=self.company, account_number="2000")

        self.cat = InventoryCategory.objects.create(
            company=self.company, name="Raw", costing_method="WEIGHTED_AVERAGE",
            inventory_account=self.inv_acct, cogs_account=self.cogs_acct,
            sales_revenue_account=Account.objects.get(company=self.company, account_number="4100"),
            adjustment_gain_account=Account.objects.get(company=self.company, account_number="4200"),
            shrinkage_expense_account=Account.objects.get(company=self.company, account_number="6200"),
            opening_balance_equity_account=Account.objects.get(company=self.company, account_number="3000"),
        )
        self.item = InventoryItem.objects.create(company=self.company, sku="RAW001", name="Raw Mat", category=self.cat)

        self.supplier = Supplier.objects.create(company=self.company, name="VendorCo", payable_account=self.ap_acct)
        self.grni = Account.objects.create(
            company=self.company, name="GRNI", account_number="2001",
            type=Account.AccountType.LIABILITY,
        )
        self.ppv = Account.objects.create(
            company=self.company, name="PPV", account_number="5201",
            type=Account.AccountType.EXPENSE,
        )

    def _create_po_and_receipt(self):
        po = create_purchase_order(
            company=self.company, supplier=self.supplier,
            lines=[{"item": self.item, "quantity": Decimal("10"), "unit_cost": Decimal("50.00")}],
        )
        po_line = po.lines.first()
        receipt_doc = receive_purchase_order(
            company=self.company, purchase_order=po, location=self.loc,
            lines=[{"purchase_order_line": po_line, "quantity": Decimal("10")}],
        )
        receipt = receipt_doc.purchase_receipt
        return receipt

    def test_create_vendor_bill(self):
        receipt = self._create_po_and_receipt()
        bill = create_vendor_bill(
            company=self.company, supplier=self.supplier,
            purchase_receipt=receipt,
            lines=[
                {"item": self.item, "quantity": Decimal("10"), "unit_cost": Decimal("55.00"),
                 "receipt_line": receipt.lines.first()},
            ],
            bill_number="BILL-001",
        )
        self.assertEqual(bill.total_amount, Decimal("550.00"))
        self.assertEqual(bill.status, VendorBill.Status.RECEIVED)

    def test_post_vendor_bill_with_ppv(self):
        receipt = self._create_po_and_receipt()
        bill = create_vendor_bill(
            company=self.company, supplier=self.supplier,
            purchase_receipt=receipt,
            lines=[
                {"item": self.item, "quantity": Decimal("10"), "unit_cost": Decimal("55.00"),
                 "receipt_line": receipt.lines.first()},
            ],
            bill_number="BILL-002",
        )
        post_vendor_bill(bill, self.user, grni_account=self.grni, ppv_account=self.ppv)
        self.assertEqual(bill.status, VendorBill.Status.APPROVED)

    def test_post_vendor_bill_no_receipt(self):
        bill = create_vendor_bill(
            company=self.company, supplier=self.supplier,
            lines=[
                {"item": self.item, "description": "Services", "total_amount": Decimal("500.00")},
            ],
        )
        post_vendor_bill(bill, self.user)
        self.assertEqual(bill.status, VendorBill.Status.APPROVED)


class Phase3LandedCostTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(email="lc@test.com", password="testpass")
        ensure_default_posting_accounts(self.company)

        self.wh = Warehouse.objects.create(company=self.company, code="WHC", name="Main")
        self.loc = StockLocation.objects.create(company=self.company, warehouse=self.wh, code="LOCC", name="Shelf C")

        self.inv_acct = Account.objects.get(company=self.company, account_number="1200")
        self.ap_acct = Account.objects.get(company=self.company, account_number="2000")
        self.cogs = Account.objects.get(company=self.company, account_number="5100")
        self.rev = Account.objects.get(company=self.company, account_number="4100")

        self.cat = InventoryCategory.objects.create(
            company=self.company, name="Goods", costing_method="WEIGHTED_AVERAGE",
            inventory_account=self.inv_acct, cogs_account=self.cogs,
            sales_revenue_account=self.rev,
            adjustment_gain_account=Account.objects.get(company=self.company, account_number="4200"),
            shrinkage_expense_account=Account.objects.get(company=self.company, account_number="6200"),
            opening_balance_equity_account=Account.objects.get(company=self.company, account_number="3000"),
        )
        self.item = InventoryItem.objects.create(company=self.company, sku="LC001", name="Imported Item", category=self.cat)
        self.item2 = InventoryItem.objects.create(company=self.company, sku="LC002", name="Imported Item 2", category=self.cat)
        self.supplier = Supplier.objects.create(company=self.company, name="OverseasCo", payable_account=self.ap_acct)

    def _create_receipt(self):
        from inventory.services import post_purchase_receipt
        return post_purchase_receipt(
            company=self.company, supplier=self.supplier, location=self.loc,
            lines=[
                {"item": self.item, "quantity": Decimal("10"), "unit_cost": Decimal("100.00")},
                {"item": self.item2, "quantity": Decimal("5"), "unit_cost": Decimal("200.00")},
            ],
        ).purchase_receipt

    def test_allocate_by_value(self):
        receipt = self._create_receipt()
        lc = LandedCost.objects.create(
            company=self.company, purchase_receipt=receipt,
            description="Ocean freight", cost_type="FREIGHT",
            total_cost=Decimal("500.00"), allocation_method="BY_VALUE",
        )
        lc = allocate_landed_costs(lc)
        self.assertEqual(lc.status, LandedCost.Status.ALLOCATED)
        self.assertEqual(lc.allocations.count(), 2)

    def test_allocate_by_quantity(self):
        receipt = self._create_receipt()
        lc = LandedCost.objects.create(
            company=self.company, purchase_receipt=receipt,
            description="Customs duty", cost_type="DUTY",
            total_cost=Decimal("300.00"), allocation_method="BY_QUANTITY",
        )
        lc = allocate_landed_costs(lc)
        self.assertEqual(lc.status, LandedCost.Status.ALLOCATED)
        self.assertEqual(lc.allocations.count(), 2)

    def test_post_landed_cost(self):
        receipt = self._create_receipt()
        lc = LandedCost.objects.create(
            company=self.company, purchase_receipt=receipt,
            description="Insurance", cost_type="INSURANCE",
            total_cost=Decimal("200.00"), allocation_method="BY_VALUE",
        )
        lc = allocate_landed_costs(lc)
        lc = post_landed_cost(lc, self.user)
        self.assertEqual(lc.status, LandedCost.Status.POSTED)
        self.assertIsNotNone(lc.posted_date)
