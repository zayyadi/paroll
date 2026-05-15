from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounting.models import Account
from company.models import Company, CompanyMembership
from inventory.models import (
    Customer,
    InventoryCategory,
    InventoryDocument,
    InventoryItem,
    PurchaseOrder,
    StockLocation,
    Supplier,
    Warehouse,
)


User = get_user_model()


class InventoryAPITests(APITestCase):
    @staticmethod
    def grant_model_perms(user, model, codenames):
        content_type = ContentType.objects.get_for_model(model)
        perms = Permission.objects.filter(content_type=content_type, codename__in=codenames)
        user.user_permissions.add(*perms)

    def setUp(self):
        self.company = Company.objects.create(name="Inventory API Co")
        self.user = User.objects.create_user(
            email="inventory-api@example.com",
            password="password123",
            first_name="API",
            last_name="User",
            company=self.company,
            active_company=self.company,
        )
        CompanyMembership.objects.get_or_create(
            user=self.user,
            company=self.company,
            defaults={"role": CompanyMembership.ROLE_OWNER, "is_default": True},
        )
        self.client.force_authenticate(self.user)
        self.accounts = self._accounts()
        self.category = InventoryCategory.objects.create(
            company=self.company,
            name="Wholesale",
            inventory_account=self.accounts["inventory"],
            opening_balance_equity_account=self.accounts["opening"],
            adjustment_gain_account=self.accounts["gain"],
            shrinkage_expense_account=self.accounts["shrinkage"],
        )
        self.item = InventoryItem.objects.create(
            company=self.company,
            category=self.category,
            sku="API-001",
            name="API Item",
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
        self.grant_model_perms(
            self.user,
            Supplier,
            ["view_supplier", "add_supplier", "change_supplier", "delete_supplier"],
        )
        self.grant_model_perms(
            self.user,
            Customer,
            ["view_customer", "add_customer", "change_customer", "delete_customer"],
        )
        self.grant_model_perms(
            self.user,
            InventoryDocument,
            ["view_inventorydocument", "add_inventorydocument", "change_inventorydocument"],
        )
        self.grant_model_perms(
            self.user,
            PurchaseOrder,
            ["view_purchaseorder", "add_purchaseorder", "change_purchaseorder"],
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
            "payable": Account.objects.create(
                company=self.company,
                name="Trade Payables",
                account_number="2100",
                type=Account.AccountType.LIABILITY,
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
            "wht_receivable": Account.objects.create(
                company=self.company,
                name="WHT Receivable",
                account_number="1400",
                type=Account.AccountType.ASSET,
            ),
            "wht_payable": Account.objects.create(
                company=self.company,
                name="WHT Payable",
                account_number="2300",
                type=Account.AccountType.LIABILITY,
            ),
            "vat_input": Account.objects.create(
                company=self.company,
                name="Input VAT",
                account_number="1300",
                type=Account.AccountType.ASSET,
            ),
            "bank": Account.objects.create(
                company=self.company,
                name="Bank",
                account_number="1000",
                type=Account.AccountType.ASSET,
            ),
        }

    def test_customer_api_create_attaches_active_company(self):
        response = self.client.post(
            reverse("api:v1:inventory-customer-list"),
            {
                "name": "API Customer",
                "contact_name": "Tunde",
                "email": "tunde@example.com",
                "phone": "08000000003",
                "receivable_account": self.accounts["receivable"].pk,
                "wht_receivable_account": self.accounts["wht_receivable"].pk,
                "default_wht_rate": "5.0000",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["company"], self.company.id)
        self.assertTrue(Customer.objects.filter(company=self.company, name="API Customer").exists())

    def test_supplier_api_create_attaches_active_company(self):
        response = self.client.post(
            reverse("api:v1:inventory-supplier-list"),
            {
                "name": "API Supplier",
                "contact_name": "Sade",
                "email": "sade@example.com",
                "phone": "08000000001",
                "payable_account": self.accounts["payable"].pk,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["company"], self.company.id)
        self.assertTrue(Supplier.objects.filter(company=self.company, name="API Supplier").exists())

    def test_purchase_receipt_api_posts_stock_and_payable(self):
        supplier = Supplier.objects.create(
            company=self.company,
            name="API Receipt Supplier",
            payable_account=self.accounts["payable"],
        )

        response = self.client.post(
            reverse("api:v1:inventory-document-purchase-receipt"),
            {
                "supplier": supplier.pk,
                "item": self.item.pk,
                "location": self.location.pk,
                "quantity": "4.0000",
                "unit_cost": "11.2500",
                "reference": "API-GRN-001",
                "reason": "API receipt",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["document_type"], "PURCHASE_RECEIPT")
        self.assertEqual(self.item.stock_movements.count(), 1)
        self.assertEqual(self.item.stock_movements.get().total_cost, Decimal("45.00"))

    def test_sales_invoice_api_posts_customer_tax_and_cogs(self):
        self.category.sales_revenue_account = self.accounts["sales"]
        self.category.cogs_account = self.accounts["cogs"]
        self.category.save()
        customer = Customer.objects.create(
            company=self.company,
            name="API Buyer",
            receivable_account=self.accounts["receivable"],
            wht_receivable_account=self.accounts["wht_receivable"],
        )
        from inventory.services import post_opening_stock

        post_opening_stock(
            company=self.company,
            item=self.item,
            location=self.location,
            quantity=Decimal("5"),
            unit_cost=Decimal("30.00"),
        )

        response = self.client.post(
            reverse("api:v1:inventory-document-sales-invoice"),
            {
                "customer": customer.pk,
                "item": self.item.pk,
                "location": self.location.pk,
                "quantity": "2.0000",
                "unit_price": "100.0000",
                "vat_rate": "7.5000",
                "wht_rate": "5.0000",
                "vat_output_account": self.accounts["vat_output"].pk,
                "reference": "API-INV-001",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["document_type"], "SALES_INVOICE")
        self.assertEqual(self.item.stock_movements.count(), 2)

    def test_settlement_api_posts_payment_and_tax_documents(self):
        customer = Customer.objects.create(
            company=self.company,
            name="API Paying Customer",
            receivable_account=self.accounts["receivable"],
        )
        supplier = Supplier.objects.create(
            company=self.company,
            name="API Paid Supplier",
            payable_account=self.accounts["payable"],
        )

        customer_response = self.client.post(
            reverse("api:v1:inventory-document-customer-payment"),
            {
                "customer": customer.pk,
                "cash_account": self.accounts["bank"].pk,
                "amount": "410.00",
                "reference": "API-RCPT-001",
            },
            format="json",
        )
        supplier_response = self.client.post(
            reverse("api:v1:inventory-document-supplier-payment"),
            {
                "supplier": supplier.pk,
                "cash_account": self.accounts["bank"].pk,
                "amount": "1025.00",
                "reference": "API-PAY-001",
            },
            format="json",
        )
        tax_response = self.client.post(
            reverse("api:v1:inventory-document-tax-remittance"),
            {
                "cash_account": self.accounts["bank"].pk,
                "vat_output_account": self.accounts["vat_output"].pk,
                "vat_input_account": self.accounts["vat_input"].pk,
                "wht_payable_account": self.accounts["wht_payable"].pk,
                "vat_output_amount": "300.00",
                "vat_input_amount": "75.00",
                "wht_amount": "50.00",
                "reference": "API-TAX-MAY",
            },
            format="json",
        )

        self.assertEqual(customer_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(customer_response.data["document_type"], "CUSTOMER_PAYMENT")
        self.assertEqual(supplier_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(supplier_response.data["document_type"], "SUPPLIER_PAYMENT")
        self.assertEqual(tax_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(tax_response.data["document_type"], "TAX_REMITTANCE")

    def test_purchase_order_api_create_and_receive(self):
        supplier = Supplier.objects.create(
            company=self.company,
            name="API PO Supplier",
            payable_account=self.accounts["payable"],
        )
        create_response = self.client.post(
            reverse("api:v1:inventory-purchase-order-list"),
            {
                "supplier": supplier.pk,
                "reference": "API-PO-001",
                "notes": "API order",
                "lines": [
                    {
                        "item": self.item.pk,
                        "quantity": "8.0000",
                        "unit_cost": "4.5000",
                    }
                ],
            },
            format="json",
        )
        purchase_order = PurchaseOrder.objects.get(reference="API-PO-001")
        receive_response = self.client.post(
            reverse("api:v1:inventory-purchase-order-receive", args=[purchase_order.pk]),
            {
                "location": self.location.pk,
                "reference": "API-GRN-PO-001",
                "reason": "API PO receipt",
                "lines": [
                    {
                        "purchase_order_line": purchase_order.lines.get().pk,
                        "quantity": "8.0000",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(receive_response.status_code, status.HTTP_201_CREATED)
        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(self.item.stock_movements.count(), 1)
