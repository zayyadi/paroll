from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UnitOfMeasure(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="inventory_units"
    )
    name = models.CharField(max_length=80)
    abbreviation = models.CharField(max_length=20)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_inventory_uom_company_name"
            ),
            models.UniqueConstraint(
                fields=["company", "abbreviation"],
                name="uniq_inventory_uom_company_abbreviation",
            ),
        ]

    def __str__(self):
        return self.abbreviation


class InventoryCategory(BaseModel):
    class CostingMethod(models.TextChoices):
        WEIGHTED_AVERAGE = "WEIGHTED_AVERAGE", "Weighted Average"
        FIFO = "FIFO", "FIFO"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="inventory_categories"
    )
    name = models.CharField(max_length=120)
    costing_method = models.CharField(
        max_length=20,
        choices=CostingMethod.choices,
        default=CostingMethod.WEIGHTED_AVERAGE,
    )
    inventory_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_categories_as_inventory",
    )
    opening_balance_equity_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_categories_as_opening_equity",
    )
    adjustment_gain_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_categories_as_adjustment_gain",
    )
    shrinkage_expense_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_categories_as_shrinkage",
    )
    sales_revenue_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_categories_as_sales_revenue",
    )
    cogs_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_categories_as_cogs",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_inventory_category_company_name"
            )
        ]

    def __str__(self):
        return self.name


class InventoryItem(BaseModel):
    class ItemType(models.TextChoices):
        STOCK = "STOCK", "Stock"
        PHARMACY = "PHARMACY", "Pharmacy"
        INGREDIENT = "INGREDIENT", "Ingredient"
        SERVICE = "SERVICE", "Service"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="inventory_items"
    )
    category = models.ForeignKey(
        InventoryCategory, on_delete=models.PROTECT, related_name="items"
    )
    sku = models.CharField(max_length=80)
    name = models.CharField(max_length=160)
    item_type = models.CharField(
        max_length=20, choices=ItemType.choices, default=ItemType.STOCK
    )
    base_unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="items",
    )
    barcode = models.CharField(max_length=120, blank=True)
    track_batch = models.BooleanField(default=False)
    track_expiry = models.BooleanField(default=False)
    allow_negative_stock = models.BooleanField(default=False)
    reorder_point = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("0.0000")
    )
    standard_cost = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("0.0000")
    )
    default_sales_price = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("0.0000")
    )
    default_vat_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0.0000")
    )
    default_wht_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0.0000")
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sku", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "sku"], name="uniq_inventory_item_company_sku"
            )
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"

    def clean(self):
        if self.category_id and self.category.company_id != self.company_id:
            raise ValidationError("Item category must belong to the same company.")
        if self.base_unit_id and self.base_unit.company_id != self.company_id:
            raise ValidationError("Base unit must belong to the same company.")


class Warehouse(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="warehouses"
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_warehouse_company_code"
            )
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class StockLocation(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="stock_locations"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="locations"
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["warehouse__code", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "warehouse", "code"],
                name="uniq_stock_location_company_warehouse_code",
            )
        ]

    def __str__(self):
        return f"{self.warehouse.code}/{self.code}"

    def clean(self):
        if self.warehouse_id and self.warehouse.company_id != self.company_id:
            raise ValidationError("Location warehouse must belong to the same company.")


class Supplier(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="suppliers"
    )
    name = models.CharField(max_length=160)
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    payable_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        related_name="inventory_suppliers_as_payable",
    )
    wht_payable_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_suppliers_as_wht_payable",
    )
    default_wht_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0.0000")
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_supplier_company_name"
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.payable_account_id and self.payable_account.company_id != self.company_id:
            raise ValidationError("Supplier payable account must belong to the same company.")
        if self.wht_payable_account_id and self.wht_payable_account.company_id != self.company_id:
            raise ValidationError("Supplier WHT account must belong to the same company.")


class Customer(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="customers"
    )
    name = models.CharField(max_length=160)
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    receivable_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        related_name="inventory_customers_as_receivable",
    )
    wht_receivable_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_customers_as_wht_receivable",
    )
    default_wht_rate = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal("0.0000")
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="uniq_customer_company_name"
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.receivable_account_id and self.receivable_account.company_id != self.company_id:
            raise ValidationError("Customer receivable account must belong to the same company.")
        if self.wht_receivable_account_id and self.wht_receivable_account.company_id != self.company_id:
            raise ValidationError("Customer WHT account must belong to the same company.")


class PurchaseOrder(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ORDERED = "ORDERED", "Ordered"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially Received"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="purchase_orders"
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    order_date = models.DateField(default=timezone.now)
    expected_date = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.ORDERED)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-order_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "reference"],
                condition=~models.Q(reference=""),
                name="uniq_purchase_order_company_reference",
            )
        ]

    def __str__(self):
        return self.reference or f"PO {self.pk or ''}".strip()

    def clean(self):
        if self.supplier_id and self.supplier.company_id != self.company_id:
            raise ValidationError("Purchase order supplier must belong to the same company.")


class PurchaseOrderLine(BaseModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="purchase_order_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    received_quantity = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal("0.0000")
    )
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["id"]

    @property
    def remaining_quantity(self):
        return self.quantity - self.received_quantity

    def clean(self):
        company_id = self.purchase_order.company_id if self.purchase_order_id else None
        if company_id and self.item_id and self.item.company_id != company_id:
            raise ValidationError("Purchase order item must belong to the same company.")


class InventoryDocument(BaseModel):
    class DocumentType(models.TextChoices):
        OPENING_STOCK = "OPENING_STOCK", "Opening Stock"
        PURCHASE_RECEIPT = "PURCHASE_RECEIPT", "Purchase Receipt"
        SALES_INVOICE = "SALES_INVOICE", "Sales Invoice"
        CUSTOMER_RETURN = "CUSTOMER_RETURN", "Customer Return"
        SUPPLIER_RETURN = "SUPPLIER_RETURN", "Supplier Return"
        CUSTOMER_PAYMENT = "CUSTOMER_PAYMENT", "Customer Payment"
        SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT", "Supplier Payment"
        TAX_REMITTANCE = "TAX_REMITTANCE", "Tax Remittance"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        TRANSFER = "TRANSFER", "Transfer"
        STOCK_COUNT = "STOCK_COUNT", "Stock Count"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        CANCELLED = "CANCELLED", "Cancelled"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="inventory_documents"
    )
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.POSTED
    )
    document_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=80, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    journal = models.ForeignKey(
        "accounting.Journal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_documents",
    )

    class Meta:
        ordering = ["-document_date", "-created_at"]

    def __str__(self):
        return f"{self.get_document_type_display()} {self.pk or ''}".strip()


class StockMovement(BaseModel):
    class MovementType(models.TextChoices):
        OPENING = "OPENING", "Opening"
        PURCHASE_RECEIPT = "PURCHASE_RECEIPT", "Purchase Receipt"
        SALE = "SALE", "Sale"
        CUSTOMER_RETURN = "CUSTOMER_RETURN", "Customer Return"
        SUPPLIER_RETURN = "SUPPLIER_RETURN", "Supplier Return"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"
        TRANSFER_IN = "TRANSFER_IN", "Transfer In"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="stock_movements"
    )
    document = models.ForeignKey(
        InventoryDocument, on_delete=models.CASCADE, related_name="movements"
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name="stock_movements"
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="stock_movements"
    )
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2)
    movement_date = models.DateField(default=timezone.now)
    memo = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["movement_date", "created_at", "id"]
        indexes = [
            models.Index(fields=["company", "item", "location"]),
            models.Index(fields=["company", "movement_date"]),
        ]

    def __str__(self):
        return f"{self.item.sku} {self.quantity} @ {self.location}"

    def clean(self):
        if self.document_id and self.document.company_id != self.company_id:
            raise ValidationError("Movement document must belong to the same company.")
        if self.item_id and self.item.company_id != self.company_id:
            raise ValidationError("Movement item must belong to the same company.")
        if self.location_id and self.location.company_id != self.company_id:
            raise ValidationError("Movement location must belong to the same company.")


class PurchaseReceipt(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="purchase_receipts"
    )
    document = models.OneToOneField(
        InventoryDocument, on_delete=models.CASCADE, related_name="purchase_receipt"
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_receipts")
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipts",
    )

    class Meta:
        ordering = ["-document__document_date", "-created_at"]

    def __str__(self):
        return f"Receipt {self.document.reference or self.document_id} - {self.supplier}"

    def clean(self):
        if self.document_id and self.document.company_id != self.company_id:
            raise ValidationError("Receipt document must belong to the same company.")
        if self.supplier_id and self.supplier.company_id != self.company_id:
            raise ValidationError("Receipt supplier must belong to the same company.")
        if self.purchase_order_id and self.purchase_order.company_id != self.company_id:
            raise ValidationError("Receipt purchase order must belong to the same company.")


class PurchaseReceiptLine(BaseModel):
    receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="purchase_receipt_lines")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="purchase_receipt_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    wht_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    wht_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_cost = models.DecimalField(max_digits=14, decimal_places=2)
    movement = models.OneToOneField(
        StockMovement,
        on_delete=models.PROTECT,
        related_name="purchase_receipt_line",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["id"]

    def clean(self):
        company_id = self.receipt.company_id if self.receipt_id else None
        if company_id and self.item_id and self.item.company_id != company_id:
            raise ValidationError("Receipt item must belong to the same company.")
        if company_id and self.location_id and self.location.company_id != company_id:
            raise ValidationError("Receipt location must belong to the same company.")


class SalesInvoice(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="sales_invoices"
    )
    document = models.OneToOneField(
        InventoryDocument, on_delete=models.CASCADE, related_name="sales_invoice"
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales_invoices")

    class Meta:
        ordering = ["-document__document_date", "-created_at"]

    def __str__(self):
        return f"Invoice {self.document.reference or self.document_id} - {self.customer}"

    def clean(self):
        if self.document_id and self.document.company_id != self.company_id:
            raise ValidationError("Invoice document must belong to the same company.")
        if self.customer_id and self.customer.company_id != self.company_id:
            raise ValidationError("Invoice customer must belong to the same company.")


class SalesInvoiceLine(BaseModel):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="sales_invoice_lines")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="sales_invoice_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    revenue_amount = models.DecimalField(max_digits=14, decimal_places=2)
    cogs_amount = models.DecimalField(max_digits=14, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    wht_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    wht_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    movement = models.OneToOneField(
        StockMovement,
        on_delete=models.PROTECT,
        related_name="sales_invoice_line",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["id"]

    def clean(self):
        company_id = self.invoice.company_id if self.invoice_id else None
        if company_id and self.item_id and self.item.company_id != company_id:
            raise ValidationError("Invoice item must belong to the same company.")
        if company_id and self.location_id and self.location.company_id != company_id:
            raise ValidationError("Invoice location must belong to the same company.")


class CustomerReturn(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="customer_returns"
    )
    document = models.OneToOneField(
        InventoryDocument, on_delete=models.CASCADE, related_name="customer_return"
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="returns")

    class Meta:
        ordering = ["-document__document_date", "-created_at"]


class CustomerReturnLine(BaseModel):
    customer_return = models.ForeignKey(CustomerReturn, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="customer_return_lines")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="customer_return_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    revenue_amount = models.DecimalField(max_digits=14, decimal_places=2)
    cogs_amount = models.DecimalField(max_digits=14, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    wht_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    wht_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    movement = models.OneToOneField(
        StockMovement,
        on_delete=models.PROTECT,
        related_name="customer_return_line",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["id"]


class SupplierReturn(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="supplier_returns"
    )
    document = models.OneToOneField(
        InventoryDocument, on_delete=models.CASCADE, related_name="supplier_return"
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="returns")

    class Meta:
        ordering = ["-document__document_date", "-created_at"]


class SupplierReturnLine(BaseModel):
    supplier_return = models.ForeignKey(SupplierReturn, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="supplier_return_lines")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="supplier_return_lines")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    wht_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    wht_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_cost = models.DecimalField(max_digits=14, decimal_places=2)
    movement = models.OneToOneField(
        StockMovement,
        on_delete=models.PROTECT,
        related_name="supplier_return_line",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["id"]


class CustomerPayment(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="customer_payments"
    )
    document = models.OneToOneField(
        InventoryDocument, on_delete=models.CASCADE, related_name="customer_payment"
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    cash_account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, related_name="customer_payments_as_cash"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["-document__document_date", "-created_at"]


class SupplierPayment(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="supplier_payments"
    )
    document = models.OneToOneField(
        InventoryDocument, on_delete=models.CASCADE, related_name="supplier_payment"
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="payments")
    cash_account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, related_name="supplier_payments_as_cash"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["-document__document_date", "-created_at"]


class TaxRemittance(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="tax_remittances"
    )
    document = models.OneToOneField(
        InventoryDocument, on_delete=models.CASCADE, related_name="tax_remittance"
    )
    cash_account = models.ForeignKey(
        "accounting.Account", on_delete=models.PROTECT, related_name="tax_remittances_as_cash"
    )
    vat_output_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    vat_input_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    wht_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["-document__document_date", "-created_at"]


class InventoryValuationLayer(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="valuation_layers"
    )
    movement = models.OneToOneField(
        StockMovement, on_delete=models.CASCADE, related_name="valuation_layer"
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.PROTECT, related_name="valuation_layers"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["company", "item"])]


class StockCount(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        POSTED = "POSTED", "Posted"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="stock_counts"
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="stock_counts"
    )
    count_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    reason = models.CharField(max_length=255, blank=True)
    document = models.ForeignKey(
        InventoryDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_counts",
    )

    class Meta:
        ordering = ["-count_date", "-created_at"]


class StockCountLine(BaseModel):
    stock_count = models.ForeignKey(
        StockCount, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    counted_quantity = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stock_count", "item"], name="uniq_stock_count_line_item"
            )
        ]
