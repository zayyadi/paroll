from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model

from inventory.models import (
    Supplier, Customer, InventoryCategory, InventoryItem, StockLocation,
    Warehouse, Lot, SerialNumber, TransferShipment, TransferShipmentLine,
    WarrantyClaim,
)
from inventory.services import (
    ensure_default_posting_accounts, post_purchase_receipt,
    _enforce_batch_serial, search_item_by_barcode,
    post_stock_transfer_shipment, receive_transfer_shipment,
)
from accounting.models import Account, FiscalYear, AccountingPeriod
from accounting.utils import get_or_create_fiscal_year, get_or_create_period
from accounting.tests.fixtures import get_test_company

User = get_user_model()


class Phase4LotSerialTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(email="p4ls@test.com", password="testpass")
        ensure_default_posting_accounts(self.company)

        self.ap_acct = Account.objects.get(company=self.company, account_number="2000")
        self.inv_acct = Account.objects.get(company=self.company, account_number="1200")
        self.cogs_acct = Account.objects.get(company=self.company, account_number="5100")
        self.rev_acct = Account.objects.get(company=self.company, account_number="4100")

        self.cat = InventoryCategory.objects.create(
            company=self.company, name="Serialized", costing_method="FIFO",
            inventory_account=self.inv_acct, cogs_account=self.cogs_acct,
            sales_revenue_account=self.rev_acct,
            adjustment_gain_account=Account.objects.get(company=self.company, account_number="4200"),
            shrinkage_expense_account=Account.objects.get(company=self.company, account_number="6200"),
            opening_balance_equity_account=Account.objects.get(company=self.company, account_number="3000"),
        )
        self.wh = Warehouse.objects.create(company=self.company, code="WH4", name="Phase 4 WH")
        self.loc = StockLocation.objects.create(company=self.company, warehouse=self.wh, code="LOC4", name="Shelf D")
        self.loc2 = StockLocation.objects.create(company=self.company, warehouse=self.wh, code="LOC5", name="Shelf E")
        self.supplier = Supplier.objects.create(company=self.company, name="Electronics Co", payable_account=self.ap_acct)

    def test_batch_enforcement(self):
        item = InventoryItem.objects.create(
            company=self.company, sku="BATCH001", name="Batch Product", category=self.cat,
            track_batch=True,
        )
        with self.assertRaises(ValueError):
            _enforce_batch_serial(item, "", None, None)

    def test_batch_creates_lot(self):
        item = InventoryItem.objects.create(
            company=self.company, sku="BATCH002", name="Batch Product 2", category=self.cat,
            track_batch=True,
        )
        _enforce_batch_serial(item, "LOT-ABC", None, date(2027, 6, 1))
        lot = Lot.objects.get(item=item, lot_number="LOT-ABC")
        self.assertEqual(lot.status, Lot.Status.IN_STOCK)
        self.assertEqual(lot.expiry_date, date(2027, 6, 1))

    def test_serial_uniqueness(self):
        item = InventoryItem.objects.create(
            company=self.company, sku="SERIAL001", name="Serialized Item", category=self.cat,
        )
        _enforce_batch_serial(item, None, "SN-001-ABC", None)
        with self.assertRaises(ValueError):
            _enforce_batch_serial(item, None, "SN-001-ABC", None)

    def test_search_by_barcode(self):
        item = InventoryItem.objects.create(
            company=self.company, sku="BC001", name="Barcode Item", category=self.cat,
            barcode="8901234567890",
        )
        result = search_item_by_barcode(self.company, "8901234567890")
        self.assertEqual(result, item)
        self.assertIsNone(search_item_by_barcode(self.company, "0000000000000"))


class Phase4TransferTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(email="p4t@test.com", password="testpass")
        ensure_default_posting_accounts(self.company)

        self.ap_acct = Account.objects.get(company=self.company, account_number="2000")
        self.inv_acct = Account.objects.get(company=self.company, account_number="1200")
        self.cogs_acct = Account.objects.get(company=self.company, account_number="5100")
        self.rev_acct = Account.objects.get(company=self.company, account_number="4100")

        self.cat = InventoryCategory.objects.create(
            company=self.company, name="Transfer Goods", costing_method="WEIGHTED_AVERAGE",
            inventory_account=self.inv_acct, cogs_account=self.cogs_acct,
            sales_revenue_account=self.rev_acct,
            adjustment_gain_account=Account.objects.get(company=self.company, account_number="4200"),
            shrinkage_expense_account=Account.objects.get(company=self.company, account_number="6200"),
            opening_balance_equity_account=Account.objects.get(company=self.company, account_number="3000"),
        )
        self.wh = Warehouse.objects.create(company=self.company, code="WTO", name="Transfer WH")
        self.loc_from = StockLocation.objects.create(company=self.company, warehouse=self.wh, code="LOC-A", name="Shelf A")
        self.loc_to = StockLocation.objects.create(company=self.company, warehouse=self.wh, code="LOC-B", name="Shelf B")
        self.item = InventoryItem.objects.create(company=self.company, sku="TR001", name="Transferable", category=self.cat)
        self.supplier = Supplier.objects.create(company=self.company, name="Wholesale Co", payable_account=self.ap_acct)

        # Seed stock at source location
        post_purchase_receipt(
            company=self.company, supplier=self.supplier, location=self.loc_from,
            lines=[{"item": self.item, "quantity": Decimal("100"), "unit_cost": Decimal("25.00")}],
            posting_date=date(2026, 6, 1),
        )

    def test_create_transfer_shipment(self):
        shipment = post_stock_transfer_shipment(
            company=self.company, from_location=self.loc_from, to_location=self.loc_to,
            lines=[{"item": self.item, "quantity": Decimal("30")}],
        )
        self.assertEqual(shipment.status, TransferShipment.Status.IN_TRANSIT)
        self.assertEqual(shipment.lines.count(), 1)
        self.assertEqual(shipment.lines.first().quantity, Decimal("30.0000"))

    def test_receive_transfer_shipment(self):
        shipment = post_stock_transfer_shipment(
            company=self.company, from_location=self.loc_from, to_location=self.loc_to,
            lines=[{"item": self.item, "quantity": Decimal("20")}],
        )
        line = shipment.lines.first()
        shipment = receive_transfer_shipment(
            company=self.company, shipment=shipment,
            lines=[{"shipment_line": line, "quantity": Decimal("20")}],
        )
        self.assertEqual(shipment.status, TransferShipment.Status.RECEIVED)
        line.refresh_from_db()
        self.assertEqual(line.received_quantity, Decimal("20.0000"))

    def test_partial_receive_transfer(self):
        shipment = post_stock_transfer_shipment(
            company=self.company, from_location=self.loc_from, to_location=self.loc_to,
            lines=[{"item": self.item, "quantity": Decimal("40")}],
        )
        line = shipment.lines.first()
        shipment = receive_transfer_shipment(
            company=self.company, shipment=shipment,
            lines=[{"shipment_line": line, "quantity": Decimal("25")}],
        )
        self.assertEqual(shipment.status, TransferShipment.Status.PARTIALLY_RECEIVED)


class Phase4WarrantyTest(TestCase):
    def setUp(self):
        self.company = get_test_company()
        self.user = User.objects.create_superuser(email="p4w@test.com", password="testpass")
        ensure_default_posting_accounts(self.company)

        self.ar_acct = Account.objects.get(company=self.company, account_number="1100")
        self.cat = InventoryCategory.objects.create(
            company=self.company, name="Warranty Items", costing_method="FIFO",
            inventory_account=Account.objects.get(company=self.company, account_number="1200"),
            cogs_account=Account.objects.get(company=self.company, account_number="5100"),
            sales_revenue_account=Account.objects.get(company=self.company, account_number="4100"),
            adjustment_gain_account=Account.objects.get(company=self.company, account_number="4200"),
            shrinkage_expense_account=Account.objects.get(company=self.company, account_number="6200"),
            opening_balance_equity_account=Account.objects.get(company=self.company, account_number="3000"),
        )
        self.item = InventoryItem.objects.create(company=self.company, sku="WAR001", name="Warranty Device", category=self.cat)
        self.customer = Customer.objects.create(company=self.company, name="Claimant", receivable_account=self.ar_acct)

    def test_warranty_claim_creation(self):
        serial = SerialNumber.objects.create(
            company=self.company, item=self.item, serial="WAR-SN-001",
            warranty_start=date(2026, 1, 1), warranty_end=date(2027, 1, 1),
            warranty_provider="DeviceCorp", status=SerialNumber.Status.SOLD,
            sold_to=self.customer, sold_date=date(2026, 2, 15),
        )
        claim = WarrantyClaim.objects.create(
            company=self.company, serial_number=serial, customer=self.customer,
            claim_date=date(2026, 7, 1),
            description="Screen malfunction",
        )
        self.assertEqual(claim.status, WarrantyClaim.Status.SUBMITTED)
        self.assertEqual(claim.serial_number, serial)
