from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounting.models import Account
from company.models import Company, CompanyMembership
from inventory.models import (
    Customer,
    InventoryCategory,
    InventoryDocument,
    InventoryItem,
    PurchaseOrder,
    SalesInvoice,
    SalesOrder,
    StockLocation,
    Supplier,
    Warehouse,
)
from inventory.services import (
    post_customer_payment,
    post_opening_stock,
    post_purchase_receipt,
    post_sales_invoice,
    post_supplier_payment,
)


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
        self.assertContains(response, "Qty in Stock")
        self.assertContains(response, "Cost Price")

    def test_item_list_shows_current_quantity_and_cost_price(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-QTY",
            name="Quantity Item",
        )
        post_opening_stock(
            company=self.company,
            item=item,
            location=self.location,
            quantity=Decimal("12"),
            unit_cost=Decimal("25.00"),
        )

        response = self.client.get(reverse("inventory:item_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantity Item")
        self.assertContains(response, "12.00")
        self.assertContains(response, "25.00")

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

    def test_inventory_menu_links_to_sales_orders(self):
        response = self.client.get(reverse("inventory:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("inventory:sales_order_list"))
        self.assertContains(response, "Sales Orders")

    def test_inventory_menu_links_to_sales_invoice_list(self):
        response = self.client.get(reverse("inventory:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("inventory:sales_invoice_list"))
        self.assertContains(response, "Sales Invoices")

    def test_sales_invoice_list_shows_status_filters_and_create_link(self):
        customer = Customer.objects.create(
            company=self.company,
            name="Invoice Customer",
            receivable_account=self.accounts["receivable"],
        )
        document = InventoryDocument.objects.create(
            company=self.company,
            document_type=InventoryDocument.DocumentType.SALES_INVOICE,
            status=InventoryDocument.Status.POSTED,
            reference="INV-LIST-001",
            total_amount=Decimal("125.00"),
        )
        invoice = SalesInvoice.objects.create(
            company=self.company,
            document=document,
            customer=customer,
            payment_status="UNPAID",
        )

        response = self.client.get(reverse("inventory:sales_invoice_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INV-LIST-001")
        self.assertContains(response, "Invoice Customer")
        self.assertContains(response, "Open")
        self.assertContains(response, "Pending")
        self.assertContains(response, "Posted")
        self.assertContains(response, reverse("inventory:sales_invoice"))
        self.assertContains(response, reverse("inventory:sales_invoice_detail", args=[invoice.pk]))

    def test_sales_invoice_detail_displays_invoice_for_viewing(self):
        customer = Customer.objects.create(
            company=self.company,
            name="Detail Customer",
            receivable_account=self.accounts["receivable"],
        )
        document = InventoryDocument.objects.create(
            company=self.company,
            document_type=InventoryDocument.DocumentType.SALES_INVOICE,
            status=InventoryDocument.Status.POSTED,
            reference="INV-DETAIL-001",
            total_amount=Decimal("220.00"),
        )
        invoice = SalesInvoice.objects.create(
            company=self.company,
            document=document,
            customer=customer,
        )

        response = self.client.get(reverse("inventory:sales_invoice_detail", args=[invoice.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INV-DETAIL-001")
        self.assertContains(response, "Detail Customer")
        self.assertContains(response, "Posted")

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

    def test_supplier_update_can_change_posting_accounts(self):
        alternate_payable = Account.objects.create(
            company=self.company,
            name="Alternate Trade Payables",
            account_number="2010",
            type=Account.AccountType.LIABILITY,
        )
        alternate_wht = Account.objects.create(
            company=self.company,
            name="Alternate WHT Payable",
            account_number="2310",
            type=Account.AccountType.LIABILITY,
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="Wrong Supplier",
            payable_account=self.accounts["payable"],
        )

        detail_response = self.client.get(reverse("inventory:supplier_detail", args=[supplier.pk]))
        response = self.client.post(
            reverse("inventory:supplier_update", args=[supplier.pk]),
            {
                "name": "Wrong Supplier",
                "contact_name": "",
                "email": "",
                "phone": "",
                "payable_account": alternate_payable.pk,
                "wht_payable_account": alternate_wht.pk,
                "default_wht_rate": "0.0000",
                "payment_terms": "Net 30",
                "default_due_days": "30",
                "discount_terms": "",
                "credit_limit": "0.00",
                "is_active": "on",
            },
        )
        supplier.refresh_from_db()

        self.assertContains(detail_response, reverse("inventory:supplier_update", args=[supplier.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(supplier.payable_account, alternate_payable)
        self.assertEqual(supplier.wht_payable_account, alternate_wht)

    def test_customer_update_can_change_posting_accounts(self):
        alternate_receivable = Account.objects.create(
            company=self.company,
            name="Alternate Receivables",
            account_number="1110",
            type=Account.AccountType.ASSET,
        )
        alternate_wht = Account.objects.create(
            company=self.company,
            name="Alternate WHT Receivable",
            account_number="1410",
            type=Account.AccountType.ASSET,
        )
        customer = Customer.objects.create(
            company=self.company,
            name="Wrong Customer",
            receivable_account=self.accounts["receivable"],
        )

        detail_response = self.client.get(reverse("inventory:customer_detail", args=[customer.pk]))
        response = self.client.post(
            reverse("inventory:customer_update", args=[customer.pk]),
            {
                "name": "Wrong Customer",
                "contact_name": "",
                "email": "",
                "phone": "",
                "receivable_account": alternate_receivable.pk,
                "wht_receivable_account": alternate_wht.pk,
                "default_wht_rate": "0.0000",
                "payment_terms": "Net 30",
                "default_due_days": "30",
                "credit_limit": "0.00",
                "collections_status": "CURRENT",
                "is_active": "on",
            },
        )
        customer.refresh_from_db()

        self.assertContains(detail_response, reverse("inventory:customer_update", args=[customer.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(customer.receivable_account, alternate_receivable)
        self.assertEqual(customer.wht_receivable_account, alternate_wht)

    def test_customer_and_supplier_detail_pages_show_ledgers(self):
        customer = Customer.objects.create(
            company=self.company,
            name="Ledger Buyer",
            receivable_account=self.accounts["receivable"],
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="Ledger Vendor",
            payable_account=self.accounts["payable"],
        )

        customer_response = self.client.get(
            reverse("inventory:customer_detail", args=[customer.pk])
        )
        supplier_response = self.client.get(
            reverse("inventory:supplier_detail", args=[supplier.pk])
        )

        self.assertEqual(customer_response.status_code, 200)
        self.assertContains(customer_response, "Customer Ledger")
        self.assertEqual(supplier_response.status_code, 200)
        self.assertContains(supplier_response, "Supplier Ledger")

    def test_customer_payment_can_be_allocated_to_invoice_from_ui(self):
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-ALLOC-UI",
            name="Allocation UI Item",
        )
        customer = Customer.objects.create(
            company=self.company,
            name="Allocation UI Customer",
            receivable_account=self.accounts["receivable"],
        )
        post_opening_stock(
            company=self.company,
            item=item,
            location=self.location,
            quantity=Decimal("5"),
            unit_cost=Decimal("40.00"),
        )
        payment_document = post_customer_payment(
            company=self.company,
            customer=customer,
            cash_account=self.accounts["inventory"],
            amount=Decimal("120.00"),
            reference="PAY-ALLOC-UI",
        )
        invoice_document = post_sales_invoice(
            company=self.company,
            customer=customer,
            location=self.location,
            lines=[{"item": item, "quantity": Decimal("2"), "unit_price": Decimal("60.00")}],
            reference="INV-ALLOC-UI",
        )
        payment = payment_document.customer_payment
        invoice = invoice_document.sales_invoice

        detail_response = self.client.get(reverse("inventory:customer_detail", args=[customer.pk]))
        allocate_response = self.client.post(
            reverse("inventory:customer_payment_allocate", args=[payment.pk]),
            {
                "invoice": invoice.pk,
                "amount": "120.00",
            },
        )
        invoice.refresh_from_db()

        self.assertContains(detail_response, "Allocate")
        self.assertEqual(allocate_response.status_code, 302)
        self.assertEqual(invoice.payment_status, "PAID")
        self.assertEqual(invoice.paid_amount, Decimal("120.00"))

    def test_supplier_payment_can_be_allocated_to_purchase_receipt_from_ui(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-SUPP-ALLOC-UI",
            name="Supplier Allocation UI Item",
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="Supplier Allocation UI",
            payable_account=self.accounts["payable"],
        )
        receipt_document = post_purchase_receipt(
            company=self.company,
            supplier=supplier,
            location=self.location,
            lines=[{"item": item, "quantity": Decimal("2"), "unit_cost": Decimal("50.00")}],
            reference="BILL-ALLOC-UI",
        )
        payment_document = post_supplier_payment(
            company=self.company,
            supplier=supplier,
            cash_account=self.accounts["inventory"],
            amount=Decimal("100.00"),
            reference="SUPP-PAY-ALLOC-UI",
        )
        payment = payment_document.supplier_payment
        receipt = receipt_document.purchase_receipt

        detail_response = self.client.get(reverse("inventory:supplier_detail", args=[supplier.pk]))
        allocate_response = self.client.post(
            reverse("inventory:supplier_payment_allocate", args=[payment.pk]),
            {
                "receipt": receipt.pk,
                "amount": "100.00",
            },
        )
        receipt.refresh_from_db()

        self.assertContains(detail_response, "Allocate")
        self.assertEqual(allocate_response.status_code, 302)
        self.assertEqual(receipt.payment_status, "PAID")
        self.assertEqual(receipt.paid_amount, Decimal("100.00"))

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
            payable_account=self.accounts["payable"],
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
            payable_account=self.accounts["payable"],
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

    def test_purchase_order_create_view_renders_three_phase_form(self):
        response = self.client.get(reverse("inventory:purchase_order_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Document Data")
        self.assertContains(response, "Item Lines")
        self.assertContains(response, "Financial Summary")

    @override_settings(USE_THOUSAND_SEPARATOR=True)
    def test_purchase_order_create_view_does_not_localize_item_option_ids(self):
        InventoryItem.objects.create(
            id=200801,
            company=self.company,
            category=self.category,
            sku="SKU-LARGE-ID",
            name="Large ID Item",
        )

        response = self.client.get(reverse("inventory:purchase_order_create"))

        self.assertContains(response, 'value="200801"')
        self.assertNotContains(response, 'value="200,801"')

    def test_purchase_order_create_view_accepts_comma_formatted_item_ids(self):
        item = InventoryItem.objects.create(
            id=200802,
            company=self.company,
            category=self.category,
            sku="SKU-COMMA-ID",
            name="Comma ID Item",
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="Comma Supplier",
            payable_account=self.accounts["payable"],
        )

        response = self.client.post(
            reverse("inventory:purchase_order_create"),
            {
                "supplier": supplier.pk,
                "reference": "PO-COMMA-ID",
                "line_count": "1",
                "lines-0-item": "200,802",
                "lines-0-quantity": "1.0000",
                "lines-0-unit_cost": "10.0000",
                "lines-0-vat_rate": "0.0000",
            },
        )

        self.assertEqual(response.status_code, 302)
        purchase_order = PurchaseOrder.objects.get(reference="PO-COMMA-ID")
        self.assertEqual(purchase_order.lines.get().item, item)

    def test_purchase_order_create_view_accepts_multiple_item_lines(self):
        first_item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-PO-A",
            name="PO Item A",
        )
        second_item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-PO-B",
            name="PO Item B",
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="Multi Supplier",
            payable_account=self.accounts["payable"],
        )

        response = self.client.post(
            reverse("inventory:purchase_order_create"),
            {
                "supplier": supplier.pk,
                "reference": "PO-MULTI-001",
                "notes": "Multi-line order",
                "line_count": "2",
                "lines-0-item": first_item.pk,
                "lines-0-quantity": "3.0000",
                "lines-0-unit_cost": "10.0000",
                "lines-0-vat_rate": "7.5000",
                "lines-1-item": second_item.pk,
                "lines-1-quantity": "2.0000",
                "lines-1-unit_cost": "25.0000",
                "lines-1-vat_rate": "0.0000",
            },
        )

        self.assertEqual(response.status_code, 302)
        purchase_order = PurchaseOrder.objects.get(reference="PO-MULTI-001")
        self.assertEqual(purchase_order.lines.count(), 2)
        first_line = purchase_order.lines.get(item=first_item)
        second_line = purchase_order.lines.get(item=second_item)
        self.assertEqual(first_line.total_cost, Decimal("30.00"))
        self.assertEqual(first_line.vat_rate, Decimal("7.5000"))
        self.assertEqual(first_line.vat_amount, Decimal("2.25"))
        self.assertEqual(second_line.total_cost, Decimal("50.00"))

    def test_purchase_order_receive_view_labels_lines_by_item_name(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-PO-LABEL",
            name="PO Label Item",
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="PO Label Supplier",
            payable_account=self.accounts["opening"],
        )
        purchase_order = PurchaseOrder.objects.create(
            company=self.company,
            supplier=supplier,
            reference="PO-UI-LABEL",
        )
        purchase_order.lines.create(
            item=item,
            quantity=Decimal("5.0000"),
            unit_cost=Decimal("6.2500"),
            total_cost=Decimal("31.25"),
        )

        response = self.client.get(
            reverse("inventory:purchase_order_receive", args=[purchase_order.pk]),
            follow=True,
        )

        self.assertContains(response, "PO Label Item")
        self.assertNotContains(response, "PurchaseOrderLine object")

    def test_purchase_order_receive_view_renders_three_phase_form(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-PO-RENDER",
            name="PO Render Item",
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="PO Render Supplier",
            payable_account=self.accounts["payable"],
        )
        purchase_order = PurchaseOrder.objects.create(
            company=self.company,
            supplier=supplier,
            reference="PO-RENDER",
        )
        purchase_order.lines.create(
            item=item,
            quantity=Decimal("5.0000"),
            unit_cost=Decimal("6.2500"),
            total_cost=Decimal("31.25"),
        )

        response = self.client.get(
            reverse("inventory:purchase_order_receive", args=[purchase_order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Receipt Data")
        self.assertContains(response, "Receivable Lines")
        self.assertContains(response, "Financial Summary")

    def test_purchase_order_receive_view_accepts_multiple_lines(self):
        first_item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-PO-R-A",
            name="PO Receive Item A",
        )
        second_item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-PO-R-B",
            name="PO Receive Item B",
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="PO Receive Supplier",
            payable_account=self.accounts["payable"],
        )
        purchase_order = PurchaseOrder.objects.create(
            company=self.company,
            supplier=supplier,
            reference="PO-RECEIVE-MULTI",
        )
        first_line = purchase_order.lines.create(
            item=first_item,
            quantity=Decimal("3.0000"),
            unit_cost=Decimal("10.0000"),
            total_cost=Decimal("30.00"),
            vat_rate=Decimal("7.5000"),
            vat_amount=Decimal("2.25"),
        )
        second_line = purchase_order.lines.create(
            item=second_item,
            quantity=Decimal("2.0000"),
            unit_cost=Decimal("25.0000"),
            total_cost=Decimal("50.00"),
        )

        response = self.client.post(
            reverse("inventory:purchase_order_receive", args=[purchase_order.pk]),
            {
                "location": self.location.pk,
                "vat_input_account": self.accounts["inventory"].pk,
                "reference": "GRN-MULTI",
                "reason": "Multi-line receipt",
                "line_count": "2",
                "lines-0-purchase_order_line": first_line.pk,
                "lines-0-quantity": "3.0000",
                "lines-0-vat_rate": "7.5000",
                "lines-1-purchase_order_line": second_line.pk,
                "lines-1-quantity": "2.0000",
                "lines-1-vat_rate": "0.0000",
            },
        )

        self.assertEqual(response.status_code, 302)
        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(purchase_order.lines.get(pk=first_line.pk).received_quantity, Decimal("3.0000"))
        self.assertEqual(purchase_order.lines.get(pk=second_line.pk).received_quantity, Decimal("2.0000"))
        receipt = purchase_order.receipts.get()
        self.assertEqual(receipt.lines.count(), 2)
        self.assertEqual(receipt.lines.get(item=first_item).vat_amount, Decimal("2.25"))
        self.assertEqual(first_item.stock_movements.count(), 1)
        self.assertEqual(second_item.stock_movements.count(), 1)

    def test_sales_order_create_view_accepts_multiple_item_lines(self):
        first_item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-SO-A",
            name="SO Item A",
            allow_negative_stock=True,
        )
        second_item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-SO-B",
            name="SO Item B",
            allow_negative_stock=True,
        )
        customer = Customer.objects.create(
            company=self.company,
            name="Multi Customer",
            receivable_account=self.accounts["receivable"],
        )

        response = self.client.post(
            reverse("inventory:sales_order_create"),
            {
                "customer": customer.pk,
                "reference": "SO-MULTI-001",
                "notes": "Multi-line sales order",
                "line_count": "2",
                "lines-0-item": first_item.pk,
                "lines-0-quantity": "3.0000",
                "lines-0-unit_price": "10.0000",
                "lines-1-item": second_item.pk,
                "lines-1-quantity": "2.0000",
                "lines-1-unit_price": "25.0000",
            },
        )

        self.assertEqual(response.status_code, 302)
        sales_order = SalesOrder.objects.get(reference="SO-MULTI-001")
        self.assertEqual(sales_order.lines.count(), 2)
        self.assertEqual(sales_order.lines.get(item=first_item).unit_price, Decimal("10.0000"))
        self.assertEqual(sales_order.lines.get(item=second_item).quantity, Decimal("2.0000"))

    def test_sales_order_ship_posts_inventory_and_visible_sales_invoice(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-SO-SHIP",
            name="SO Ship Item",
        )
        customer = Customer.objects.create(
            company=self.company,
            name="SO Ship Customer",
            receivable_account=self.accounts["receivable"],
        )
        post_opening_stock(
            company=self.company,
            item=item,
            location=self.location,
            quantity=Decimal("5"),
            unit_cost=Decimal("40.00"),
        )
        sales_order = SalesOrder.objects.create(
            company=self.company,
            customer=customer,
            reference="SO-SHIP-001",
            status=SalesOrder.Status.CONFIRMED,
        )
        sales_order.lines.create(
            item=item,
            quantity=Decimal("2.0000"),
            unit_price=Decimal("100.0000"),
            total_amount=Decimal("200.00"),
        )

        response = self.client.post(
            reverse("inventory:sales_order_ship", args=[sales_order.pk])
        )
        list_response = self.client.get(reverse("inventory:sales_invoice_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(item.stock_movements.count(), 2)
        self.assertTrue(
            SalesInvoice.objects.filter(
                company=self.company,
                document__reference="SO-SO-SHIP-001",
            ).exists()
        )
        self.assertContains(list_response, "SO-SO-SHIP-001")

    def test_sales_order_ship_uses_default_output_vat_account(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-SO-VAT",
            name="SO VAT Item",
        )
        customer = Customer.objects.create(
            company=self.company,
            name="SO VAT Customer",
            receivable_account=self.accounts["receivable"],
        )
        post_opening_stock(
            company=self.company,
            item=item,
            location=self.location,
            quantity=Decimal("5"),
            unit_cost=Decimal("40.00"),
        )
        sales_order = SalesOrder.objects.create(
            company=self.company,
            customer=customer,
            reference="SO-VAT-001",
            status=SalesOrder.Status.CONFIRMED,
        )
        sales_order.lines.create(
            item=item,
            quantity=Decimal("2.0000"),
            unit_price=Decimal("100.0000"),
            total_amount=Decimal("200.00"),
            vat_rate=Decimal("7.5000"),
            vat_amount=Decimal("15.00"),
        )

        response = self.client.post(
            reverse("inventory:sales_order_ship", args=[sales_order.pk])
        )

        self.assertEqual(response.status_code, 302)
        invoice = SalesInvoice.objects.get(
            company=self.company,
            document__reference="SO-SO-VAT-001",
        )
        self.assertEqual(invoice.lines.get().vat_amount, Decimal("15.00"))
        self.assertTrue(
            invoice.document.journal.entries.filter(
                account=self.accounts["vat_output"],
                entry_type="CREDIT",
                amount=Decimal("15.00"),
            ).exists()
        )

    def test_sales_order_invoice_repairs_shipped_order_without_invoice(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-SO-LEGACY",
            name="SO Legacy Item",
        )
        customer = Customer.objects.create(
            company=self.company,
            name="SO Legacy Customer",
            receivable_account=self.accounts["receivable"],
        )
        post_opening_stock(
            company=self.company,
            item=item,
            location=self.location,
            quantity=Decimal("5"),
            unit_cost=Decimal("40.00"),
        )
        sales_order = SalesOrder.objects.create(
            company=self.company,
            customer=customer,
            reference="SO-LEGACY-001",
            status=SalesOrder.Status.SHIPPED,
        )
        sales_order.lines.create(
            item=item,
            quantity=Decimal("2.0000"),
            shipped_quantity=Decimal("2.0000"),
            unit_price=Decimal("100.0000"),
            total_amount=Decimal("200.00"),
        )

        response = self.client.post(
            reverse("inventory:sales_order_invoice", args=[sales_order.pk])
        )
        sales_order.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(sales_order.status, SalesOrder.Status.INVOICED)
        self.assertEqual(item.stock_movements.count(), 2)
        self.assertTrue(
            SalesInvoice.objects.filter(
                company=self.company,
                document__reference="SO-SO-LEGACY-001",
            ).exists()
        )

    def test_sales_order_detail_allows_repairing_invoiced_order_without_invoice(self):
        item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="SKU-SO-INVOICED",
            name="SO Invoiced Item",
        )
        customer = Customer.objects.create(
            company=self.company,
            name="SO Invoiced Customer",
            receivable_account=self.accounts["receivable"],
        )
        post_opening_stock(
            company=self.company,
            item=item,
            location=self.location,
            quantity=Decimal("5"),
            unit_cost=Decimal("40.00"),
        )
        sales_order = SalesOrder.objects.create(
            company=self.company,
            customer=customer,
            reference="SO-INVOICED-001",
            status=SalesOrder.Status.INVOICED,
        )
        sales_order.lines.create(
            item=item,
            quantity=Decimal("2.0000"),
            shipped_quantity=Decimal("2.0000"),
            unit_price=Decimal("100.0000"),
            total_amount=Decimal("200.00"),
        )

        detail_response = self.client.get(
            reverse("inventory:sales_order_detail", args=[sales_order.pk])
        )
        post_response = self.client.post(
            reverse("inventory:sales_order_invoice", args=[sales_order.pk])
        )

        self.assertContains(detail_response, "Post Missing Invoice")
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(item.stock_movements.count(), 2)
        self.assertTrue(
            SalesInvoice.objects.filter(
                company=self.company,
                document__reference="SO-SO-INVOICED-001",
            ).exists()
        )

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
