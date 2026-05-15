from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounting.models import Account
from company.models import Company, CompanyMembership
from inventory.models import (
    Customer,
    InventoryCategory,
    InventoryItem,
    PurchaseOrder,
    StockLocation,
    Supplier,
    Warehouse,
)
from inventory.services import post_opening_stock


User = get_user_model()


class InventoryViewTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Inventory UI Co")
        self.user = User.objects.create_user(
            email="inventory-ui@example.com",
            password="password123",
            first_name="Inventory",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        CompanyMembership.objects.get_or_create(
            user=self.user,
            company=self.company,
            defaults={"role": CompanyMembership.ROLE_OWNER, "is_default": True},
        )
        self.client.force_login(self.user)
        self.accounts = self._accounts()
        self.category = InventoryCategory.objects.create(
            company=self.company,
            name="Wholesale",
            inventory_account=self.accounts["inventory"],
            opening_balance_equity_account=self.accounts["opening"],
            adjustment_gain_account=self.accounts["gain"],
            shrinkage_expense_account=self.accounts["shrinkage"],
            sales_revenue_account=self.accounts["sales"],
            cogs_account=self.accounts["cogs"],
        )
        self.warehouse = Warehouse.objects.create(
            company=self.company, code="MAIN", name="Main Store"
        )
        self.location = StockLocation.objects.create(
            company=self.company,
            warehouse=self.warehouse,
            code="A1",
            name="Aisle 1",
        )
        self.branch = Warehouse.objects.create(
            company=self.company, code="BR", name="Branch"
        )
        self.branch_location = StockLocation.objects.create(
            company=self.company,
            warehouse=self.branch,
            code="B1",
            name="Branch Bin",
        )

    def _accounts(self):
        return {
            "inventory": Account.objects.create(
                company=self.company,
                name="Inventory Asset",
                account_number="1200",
                type=Account.AccountType.ASSET,
            ),
            "opening": Account.objects.create(
                company=self.company,
                name="Opening Equity",
                account_number="3000",
                type=Account.AccountType.EQUITY,
            ),
            "gain": Account.objects.create(
                company=self.company,
                name="Inventory Gain",
                account_number="4200",
                type=Account.AccountType.REVENUE,
            ),
            "shrinkage": Account.objects.create(
                company=self.company,
                name="Inventory Shrinkage",
                account_number="6200",
                type=Account.AccountType.EXPENSE,
            ),
            "receivable": Account.objects.create(
                company=self.company,
                name="Trade Receivables",
                account_number="1100",
                type=Account.AccountType.ASSET,
            ),
            "sales": Account.objects.create(
                company=self.company,
                name="Wholesale Sales",
                account_number="4100",
                type=Account.AccountType.REVENUE,
            ),
            "cogs": Account.objects.create(
                company=self.company,
                name="Cost of Goods Sold",
                account_number="5100",
                type=Account.AccountType.EXPENSE,
            ),
            "vat_output": Account.objects.create(
                company=self.company,
                name="Output VAT",
                account_number="2200",
                type=Account.AccountType.LIABILITY,
            ),
            "payable": Account.objects.create(
                company=self.company,
                name="Trade Payables",
                account_number="2000",
                type=Account.AccountType.LIABILITY,
            ),
            "wht_receivable": Account.objects.create(
                company=self.company,
                name="WHT Receivable",
                account_number="1400",
                type=Account.AccountType.ASSET,
            ),
        }

    def test_item_list_renders(self):
        InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-001",
            name="Test Carton",
        )

        response = self.client.get(reverse("inventory:item_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Carton")

    def test_dashboard_renders_inventory_summary(self):
        InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-DASH",
            name="Dashboard Item",
            reorder_point=Decimal("5.0000"),
        )

        response = self.client.get(reverse("inventory:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inventory Dashboard")
        self.assertContains(response, "Dashboard Item")

    def test_item_create_posts_company_scoped_item(self):
        response = self.client.post(
            reverse("inventory:item_create"),
            {
                "category": self.category.pk,
                "sku": "SKU-002",
                "name": "New Item",
                "item_type": InventoryItem.ItemType.STOCK,
                "reorder_point": "5.0000",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            InventoryItem.objects.filter(company=self.company, sku="SKU-002").exists()
        )

    def test_category_create_posts_company_scoped_account_mapping(self):
        response = self.client.post(
            reverse("inventory:category_create"),
            {
                "name": "Pharmacy",
                "costing_method": InventoryCategory.CostingMethod.WEIGHTED_AVERAGE,
                "inventory_account": self.accounts["inventory"].pk,
                "opening_balance_equity_account": self.accounts["opening"].pk,
                "adjustment_gain_account": self.accounts["gain"].pk,
                "shrinkage_expense_account": self.accounts["shrinkage"].pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            InventoryCategory.objects.filter(company=self.company, name="Pharmacy").exists()
        )

    def test_supplier_create_posts_company_scoped_supplier(self):
        response = self.client.post(
            reverse("inventory:supplier_create"),
            {
                "name": "Food Supplier",
                "contact_name": "Ada",
                "email": "ada@example.com",
                "phone": "08000000000",
                "payable_account": self.accounts["payable"].pk,
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Supplier.objects.filter(company=self.company, name="Food Supplier").exists()
        )

    def test_customer_create_posts_company_scoped_customer(self):
        response = self.client.post(
            reverse("inventory:customer_create"),
            {
                "name": "Wholesale Buyer",
                "contact_name": "Bola",
                "email": "buyer@example.com",
                "phone": "08000000002",
                "receivable_account": self.accounts["receivable"].pk,
                "wht_receivable_account": self.accounts["wht_receivable"].pk,
                "default_wht_rate": "5.0000",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Customer.objects.filter(company=self.company, name="Wholesale Buyer").exists()
        )

    def test_purchase_receipt_view_posts_stock_and_supplier_payable(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-REC",
            name="Received Item",
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="Restaurant Supplier",
            payable_account=self.accounts["opening"],
        )

        response = self.client.post(
            reverse("inventory:purchase_receipt"),
            {
                "supplier": supplier.pk,
                "item": item.pk,
                "location": self.location.pk,
                "quantity": "7.0000",
                "unit_cost": "9.5000",
                "reference": "GRN-UI-001",
                "reason": "Received goods",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(item.stock_movements.count(), 1)

    def test_sales_invoice_view_posts_revenue_tax_and_cogs(self):
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-SALE",
            name="Sale Item",
        )
        customer = Customer.objects.create(
            company=self.company,
            name="Restaurant Buyer",
            receivable_account=self.accounts["receivable"],
            wht_receivable_account=self.accounts["wht_receivable"],
        )
        post_opening_stock(
            company=self.company,
            item=item,
            location=self.location,
            quantity=Decimal("10"),
            unit_cost=Decimal("40.00"),
        )

        response = self.client.post(
            reverse("inventory:sales_invoice"),
            {
                "customer": customer.pk,
                "item": item.pk,
                "location": self.location.pk,
                "quantity": "2.0000",
                "unit_price": "100.0000",
                "vat_rate": "7.5000",
                "wht_rate": "5.0000",
                "vat_output_account": self.accounts["vat_output"].pk,
                "reference": "INV-UI-001",
                "reason": "Wholesale sale",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(item.stock_movements.count(), 2)

    def test_purchase_order_create_and_receive_views(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-PO",
            name="PO Item",
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="PO Supplier",
            payable_account=self.accounts["opening"],
        )

        create_response = self.client.post(
            reverse("inventory:purchase_order_create"),
            {
                "supplier": supplier.pk,
                "item": item.pk,
                "quantity": "5.0000",
                "unit_cost": "6.2500",
                "reference": "PO-UI-001",
                "notes": "UI order",
            },
        )
        purchase_order = PurchaseOrder.objects.get(reference="PO-UI-001")
        receive_response = self.client.post(
            reverse("inventory:purchase_order_receive", args=[purchase_order.pk]),
            {
                "purchase_order_line": purchase_order.lines.get().pk,
                "location": self.location.pk,
                "quantity": "5.0000",
                "reference": "GRN-UI-PO-001",
                "reason": "UI PO receipt",
            },
        )
        list_response = self.client.get(reverse("inventory:purchase_order_list"))

        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(receive_response.status_code, 302)
        self.assertEqual(list_response.status_code, 200)
        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(item.stock_movements.count(), 1)

    def test_opening_stock_action_posts_document(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-003",
            name="Opening Item",
        )

        response = self.client.post(
            reverse("inventory:opening_stock"),
            {
                "item": item.pk,
                "location": self.location.pk,
                "quantity": "12.0000",
                "unit_cost": "10.0000",
                "reason": "Initial load",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(item.stock_movements.count(), 1)

    def test_adjustment_transfer_and_movement_pages_render(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-004",
            name="Movement Item",
        )
        post_opening_stock(
            company=self.company,
            item=item,
            location=self.location,
            quantity=Decimal("10"),
            unit_cost=Decimal("8.00"),
        )

        adjust_response = self.client.post(
            reverse("inventory:adjustment"),
            {
                "item": item.pk,
                "location": self.location.pk,
                "quantity_delta": "-2.0000",
                "reason": "Damaged",
            },
        )
        transfer_response = self.client.post(
            reverse("inventory:transfer"),
            {
                "item": item.pk,
                "from_location": self.location.pk,
                "to_location": self.branch_location.pk,
                "quantity": "3.0000",
                "reason": "Branch restock",
            },
        )
        movement_response = self.client.get(reverse("inventory:movement_list"))

        self.assertEqual(adjust_response.status_code, 302)
        self.assertEqual(transfer_response.status_code, 302)
        self.assertEqual(movement_response.status_code, 200)
        self.assertContains(movement_response, "Movement Item")
