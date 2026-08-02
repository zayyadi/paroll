from decimal import Decimal

from django.conf import settings
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
    base_unit = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="derived_units",
    )
    conversion_factor = models.DecimalField(
        max_digits=18, decimal_places=6, default=Decimal("1.000000")
    )
    decimal_places = models.PositiveSmallIntegerField(default=4)

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
    barcode_format = models.CharField(max_length=20, blank=True)
    track_batch = models.BooleanField(default=False)
    track_expiry = models.BooleanField(default=False)
    allow_negative_stock = models.BooleanField(default=False)
    reorder_point = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
    )
    standard_cost = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
    )
    default_sales_price = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
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


class TaxJurisdiction(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="tax_jurisdictions"
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    country_code = models.CharField(max_length=2, default="NG")
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["country_code", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_tax_jurisdiction_company_code"
            )
        ]

    def __str__(self):
        return f"{self.country_code}-{self.code}: {self.name}"

    def clean(self):
        self.country_code = (self.country_code or "NG").upper()
        if len(self.country_code) != 2:
            raise ValidationError("Country code must be a 2-letter ISO code.")


class TaxRule(BaseModel):
    class TaxType(models.TextChoices):
        VAT = "VAT", "VAT"
        WHT = "WHT", "Withholding Tax"

    class TransactionType(models.TextChoices):
        SALE = "SALE", "Sale"
        PURCHASE = "PURCHASE", "Purchase"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="tax_rules"
    )
    jurisdiction = models.ForeignKey(
        TaxJurisdiction, on_delete=models.CASCADE, related_name="rules"
    )
    tax_type = models.CharField(max_length=10, choices=TaxType.choices)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    rate = models.DecimalField(max_digits=7, decimal_places=4)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["jurisdiction__code", "tax_type", "-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "company",
                    "jurisdiction",
                    "tax_type",
                    "transaction_type",
                    "effective_from",
                ],
                name="uniq_tax_rule_company_jurisdiction_type_date",
            )
        ]

    def clean(self):
        if self.jurisdiction_id and self.jurisdiction.company_id != self.company_id:
            raise ValidationError("Tax jurisdiction must belong to the same company.")
        if self.rate < 0:
            raise ValidationError("Tax rate cannot be negative.")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError("Tax rule end date cannot be before start date.")


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
    payment_terms = models.CharField(max_length=120, blank=True, default="Net 30")
    default_due_days = models.PositiveIntegerField(default=30)
    discount_terms = models.CharField(max_length=120, blank=True)
    credit_limit = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
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
    payment_terms = models.CharField(max_length=120, blank=True, default="Net 30")
    default_due_days = models.PositiveIntegerField(default=30)
    credit_limit = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    collections_status = models.CharField(
        max_length=20,
        choices=[
            ("CURRENT", "Current"),
            ("WATCH", "Watch"),
            ("ON_HOLD", "On Hold"),
            ("COLLECTIONS", "Collections"),
        ],
        default="CURRENT",
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
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    received_quantity = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
    )
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    total_cost = models.DecimalField(max_digits=18, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

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
        SALES_ORDER = "SALES_ORDER", "Sales Order"
        VENDOR_BILL = "VENDOR_BILL", "Vendor Bill"
        LANDED_COST = "LANDED_COST", "Landed Cost"
        SHIPMENT = "SHIPMENT", "Shipment"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
        COUNTED = "COUNTED", "Counted"
        APPROVED = "APPROVED", "Approved"
        POSTED = "POSTED", "Posted"
        CANCELLED = "CANCELLED", "Cancelled"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="inventory_documents"
    )
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.POSTED
    )
    document_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=80, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    total_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_inventory_documents",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_inventory_documents",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posted_inventory_documents",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
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
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    total_cost = models.DecimalField(max_digits=18, decimal_places=2)
    batch_number = models.CharField(max_length=80, blank=True)
    serial_number = models.CharField(max_length=80, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
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
    invoice_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(max_length=120, blank=True)
    payment_status = models.CharField(
        max_length=20,
        choices=[("UNPAID", "Unpaid"), ("PARTIAL", "Partial"), ("PAID", "Paid"), ("DISPUTED", "Disputed")],
        default="UNPAID",
    )
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

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
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    wht_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    wht_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_cost = models.DecimalField(max_digits=18, decimal_places=2)
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
    invoice_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    payment_terms = models.CharField(max_length=120, blank=True)
    workflow_status = models.CharField(
        max_length=20,
        choices=[
            ("DRAFT", "Draft"),
            ("APPROVED", "Approved"),
            ("SENT", "Sent"),
            ("PAID", "Paid"),
            ("VOID", "Void"),
        ],
        default="APPROVED",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    payment_status = models.CharField(
        max_length=20,
        choices=[("UNPAID", "Unpaid"), ("PARTIAL", "Partial"), ("PAID", "Paid"), ("DISPUTED", "Disputed")],
        default="UNPAID",
    )
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    paid_at = models.DateTimeField(null=True, blank=True)
    bad_debt_provisioned_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )

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
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    revenue_amount = models.DecimalField(max_digits=18, decimal_places=2)
    cogs_amount = models.DecimalField(max_digits=18, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    wht_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    wht_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
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
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    revenue_amount = models.DecimalField(max_digits=18, decimal_places=2)
    cogs_amount = models.DecimalField(max_digits=18, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    wht_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    wht_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
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
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    wht_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    wht_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_cost = models.DecimalField(max_digits=18, decimal_places=2)
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
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
    )
    payment_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=80, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("DRAFT", "Draft"), ("POSTED", "Posted"), ("VOID", "Void")],
        default="POSTED",
    )

    class Meta:
        ordering = ["-document__document_date", "-created_at"]


class CustomerPaymentAllocation(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="customer_payment_allocations"
    )
    payment = models.ForeignKey(
        CustomerPayment, on_delete=models.CASCADE, related_name="allocations"
    )
    invoice = models.ForeignKey(
        SalesInvoice, on_delete=models.PROTECT, related_name="payment_allocations"
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    allocation_date = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["allocation_date", "created_at", "id"]

    def clean(self):
        if self.payment_id and self.payment.company_id != self.company_id:
            raise ValidationError("Payment allocation payment must belong to the same company.")
        if self.invoice_id and self.invoice.company_id != self.company_id:
            raise ValidationError("Payment allocation invoice must belong to the same company.")
        if self.payment_id and self.invoice_id and self.payment.customer_id != self.invoice.customer_id:
            raise ValidationError("Payment allocation invoice must belong to the payment customer.")


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
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    receipt = models.ForeignKey(
        PurchaseReceipt,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
    )
    payment_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=80, blank=True)
    due_date = models.DateField(null=True, blank=True)
    discount_taken = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20,
        choices=[("DRAFT", "Draft"), ("POSTED", "Posted"), ("VOID", "Void")],
        default="POSTED",
    )

    class Meta:
        ordering = ["-document__document_date", "-created_at"]


class SupplierPaymentAllocation(BaseModel):
    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="supplier_payment_allocations"
    )
    payment = models.ForeignKey(
        SupplierPayment, on_delete=models.CASCADE, related_name="allocations"
    )
    receipt = models.ForeignKey(
        PurchaseReceipt, on_delete=models.PROTECT, related_name="payment_allocations"
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    allocation_date = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["allocation_date", "created_at", "id"]

    def clean(self):
        if self.payment_id and self.payment.company_id != self.company_id:
            raise ValidationError("Payment allocation payment must belong to the same company.")
        if self.receipt_id and self.receipt.company_id != self.company_id:
            raise ValidationError("Payment allocation receipt must belong to the same company.")
        if self.payment_id and self.receipt_id and self.payment.supplier_id != self.receipt.supplier_id:
            raise ValidationError("Payment allocation receipt must belong to the payment supplier.")


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
    vat_output_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    vat_input_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    wht_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2)

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
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    remaining_quantity = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
    )
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    total_cost = models.DecimalField(max_digits=18, decimal_places=2)
    remaining_total_cost = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["company", "item"]),
            models.Index(fields=["company", "item", "remaining_quantity"]),
        ]


class StockCount(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        COUNTED = "COUNTED", "Counted"
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
    variance_threshold = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_stock_counts",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posted_stock_counts",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
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
    system_quantity = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
    )
    counted_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    variance_reason = models.CharField(
        max_length=20,
        choices=[
            ("BREAKAGE", "Breakage"),
            ("EXPIRY", "Expiry"),
            ("THEFT", "Theft"),
            ("COUNT_ERROR", "Count Error"),
            ("OTHER", "Other"),
        ],
        default="OTHER",
    )
    investigation_status = models.CharField(
        max_length=20,
        choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected")],
        default="PENDING",
    )
    adjustment_document = models.ForeignKey(
        InventoryDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_count_lines",
    )

    @property
    def variance_quantity(self):
        return self.counted_quantity - self.system_quantity

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stock_count", "item"], name="uniq_stock_count_line_item"
            )
        ]


class SalesOrder(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PARTIALLY_SHIPPED = "PARTIALLY_SHIPPED", "Partially Shipped"
        SHIPPED = "SHIPPED", "Shipped"
        INVOICED = "INVOICED", "Invoiced"
        CANCELLED = "CANCELLED", "Cancelled"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="sales_orders"
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales_orders")
    order_date = models.DateField(default=timezone.now)
    expected_date = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=22, choices=Status.choices, default=Status.CONFIRMED)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-order_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "reference"],
                condition=~models.Q(reference=""),
                name="uniq_sales_order_company_reference",
            )
        ]

    def __str__(self):
        return self.reference or f"SO {self.pk or ''}".strip()


class SalesOrderLine(BaseModel):
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="sales_order_lines")
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    shipped_quantity = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
    )
    reserved_quantity = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
    )
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    vat_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    vat_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]

    @property
    def remaining_quantity(self):
        return self.quantity - self.shipped_quantity

    def clean(self):
        company_id = self.sales_order.company_id if self.sales_order_id else None
        if company_id and self.item_id and self.item.company_id != company_id:
            raise ValidationError("Sales order item must belong to the same company.")


class VendorBill(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        RECEIVED = "RECEIVED", "Received"
        APPROVED = "APPROVED", "Approved"
        PAID = "PAID", "Paid"
        VOID = "VOID", "Void"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="vendor_bills"
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="vendor_bills")
    purchase_receipt = models.ForeignKey(
        PurchaseReceipt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_bills",
    )
    bill_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    bill_number = models.CharField(max_length=80, blank=True)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-bill_date", "-created_at"]

    def __str__(self):
        return self.bill_number or f"Bill {self.pk or ''}".strip()


class VendorBillLine(BaseModel):
    vendor_bill = models.ForeignKey(VendorBill, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, null=True, blank=True, related_name="vendor_bill_lines")
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=18, decimal_places=2)
    receipt_line = models.ForeignKey(
        PurchaseReceiptLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_bill_lines",
    )

    class Meta:
        ordering = ["id"]


class LandedCost(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ALLOCATED = "ALLOCATED", "Allocated"
        POSTED = "POSTED", "Posted"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="landed_costs"
    )
    purchase_receipt = models.ForeignKey(
        PurchaseReceipt,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="landed_costs",
    )
    description = models.CharField(max_length=255)
    cost_type = models.CharField(
        max_length=30,
        choices=[("FREIGHT", "Freight"), ("DUTY", "Customs Duty"), ("INSURANCE", "Insurance"), ("OTHER", "Other")],
    )
    total_cost = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    allocation_method = models.CharField(
        max_length=20,
        choices=[("BY_VALUE", "By Value"), ("BY_WEIGHT", "By Weight"), ("BY_QUANTITY", "By Quantity")],
        default="BY_VALUE",
    )
    posted_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_cost_type_display()} - {self.description}"


class LandedCostAllocation(BaseModel):
    landed_cost = models.ForeignKey(LandedCost, on_delete=models.CASCADE, related_name="allocations")
    receipt_line = models.ForeignKey(
        PurchaseReceiptLine, on_delete=models.PROTECT, related_name="landed_cost_allocations"
    )
    allocated_amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Allocated {self.allocated_amount} to line {self.receipt_line_id}"


class Lot(BaseModel):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        IN_STOCK = "IN_STOCK", "In Stock"
        ALLOCATED = "ALLOCATED", "Allocated"
        SHIPPED = "SHIPPED", "Shipped"
        RECALLED = "RECALLED", "Recalled"
        EXPIRED = "EXPIRED", "Expired"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="inventory_lots"
    )
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="lots")
    lot_number = models.CharField(max_length=80)
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["item__sku", "lot_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "item", "lot_number"],
                name="uniq_lot_company_item_number",
            )
        ]

    def __str__(self):
        return f"{self.item.sku} - Lot {self.lot_number}"


class SerialNumber(BaseModel):
    class Status(models.TextChoices):
        IN_STOCK = "IN_STOCK", "In Stock"
        SOLD = "SOLD", "Sold"
        RESERVED = "RESERVED", "Reserved"
        RETURNED = "RETURNED", "Returned"
        DEFECTIVE = "DEFECTIVE", "Defective"
        SCRAPPED = "SCRAPPED", "Scrapped"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="serial_numbers"
    )
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="serial_numbers")
    serial = models.CharField(max_length=120)
    lot = models.ForeignKey(Lot, on_delete=models.SET_NULL, null=True, blank=True, related_name="serials")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_STOCK)
    warranty_start = models.DateField(null=True, blank=True)
    warranty_end = models.DateField(null=True, blank=True)
    warranty_provider = models.CharField(max_length=160, blank=True)
    sold_to = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchased_serials"
    )
    sold_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["item__sku", "serial"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "item", "serial"],
                name="uniq_serial_company_item_number",
            )
        ]

    def __str__(self):
        return f"{self.item.sku} - {self.serial}"


class WarrantyClaim(BaseModel):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        RESOLVED = "RESOLVED", "Resolved"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="warranty_claims"
    )
    serial_number = models.ForeignKey(
        SerialNumber, on_delete=models.PROTECT, related_name="warranty_claims"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="warranty_claims"
    )
    claim_date = models.DateField(default=timezone.now)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    resolution = models.TextField(blank=True)
    resolved_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-claim_date"]

    def __str__(self):
        return f"Warranty Claim {self.pk} - {self.serial_number.serial}"


class TransferShipment(BaseModel):
    """In-transit tracking for inter-warehouse transfers."""
    class Status(models.TextChoices):
        DISPATCHED = "DISPATCHED", "Dispatched"
        IN_TRANSIT = "IN_TRANSIT", "In Transit"
        RECEIVED = "RECEIVED", "Received"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially Received"

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="transfer_shipments"
    )
    from_location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="outgoing_transfers"
    )
    to_location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="incoming_transfers"
    )
    dispatched_date = models.DateField(default=timezone.now)
    expected_receipt_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=22, choices=Status.choices, default=Status.DISPATCHED)
    reference = models.CharField(max_length=80, blank=True)
    freight_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-dispatched_date"]

    def __str__(self):
        return f"Transfer {self.reference or self.pk} ({self.from_location} → {self.to_location})"


class TransferShipmentLine(BaseModel):
    shipment = models.ForeignKey(TransferShipment, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="transfer_lines")
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    received_quantity = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000")
    )
    lot = models.ForeignKey(Lot, on_delete=models.SET_NULL, null=True, blank=True, related_name="transfer_lines")

    class Meta:
        ordering = ["id"]

    @property
    def remaining_quantity(self):
        return self.quantity - self.received_quantity
