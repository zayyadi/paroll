from django.contrib import admin
try:
    from import_export import resources
    from import_export.admin import ImportExportModelAdmin
except ImportError:  # pragma: no cover - optional admin dependency
    class _FallbackModelResource:
        class Meta:
            abstract = True

    class _FallbackResources:
        ModelResource = _FallbackModelResource

    resources = _FallbackResources()
    ImportExportModelAdmin = admin.ModelAdmin

from inventory.models import (
    Customer,
    CustomerPayment,
    CustomerPaymentAllocation,
    CustomerReturn,
    CustomerReturnLine,
    InventoryCategory,
    InventoryDocument,
    InventoryItem,
    InventoryValuationLayer,
    LandedCost,
    LandedCostAllocation,
    Lot,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    SalesInvoice,
    SalesInvoiceLine,
    SalesOrder,
    SalesOrderLine,
    SerialNumber,
    StockCount,
    StockCountLine,
    StockLocation,
    StockMovement,
    Supplier,
    SupplierPayment,
    SupplierPaymentAllocation,
    SupplierReturn,
    SupplierReturnLine,
    TaxJurisdiction,
    TaxRemittance,
    TaxRule,
    TransferShipment,
    TransferShipmentLine,
    UnitOfMeasure,
    VendorBill,
    VendorBillLine,
    Warehouse,
    WarrantyClaim,
)


class UnitOfMeasureResource(resources.ModelResource):
    class Meta:
        model = UnitOfMeasure


class InventoryCategoryResource(resources.ModelResource):
    class Meta:
        model = InventoryCategory


class InventoryItemResource(resources.ModelResource):
    class Meta:
        model = InventoryItem


class CustomerReturnResource(resources.ModelResource):
    class Meta:
        model = CustomerReturn


class CustomerReturnLineResource(resources.ModelResource):
    class Meta:
        model = CustomerReturnLine


class SupplierReturnResource(resources.ModelResource):
    class Meta:
        model = SupplierReturn


class SupplierReturnLineResource(resources.ModelResource):
    class Meta:
        model = SupplierReturnLine


class CustomerPaymentResource(resources.ModelResource):
    class Meta:
        model = CustomerPayment


class CustomerPaymentAllocationResource(resources.ModelResource):
    class Meta:
        model = CustomerPaymentAllocation


class SupplierPaymentResource(resources.ModelResource):
    class Meta:
        model = SupplierPayment


class SupplierPaymentAllocationResource(resources.ModelResource):
    class Meta:
        model = SupplierPaymentAllocation


class TaxRemittanceResource(resources.ModelResource):
    class Meta:
        model = TaxRemittance


class TaxJurisdictionResource(resources.ModelResource):
    class Meta:
        model = TaxJurisdiction


class TaxRuleResource(resources.ModelResource):
    class Meta:
        model = TaxRule


class WarehouseResource(resources.ModelResource):
    class Meta:
        model = Warehouse


class StockLocationResource(resources.ModelResource):
    class Meta:
        model = StockLocation


class SupplierResource(resources.ModelResource):
    class Meta:
        model = Supplier


class CustomerResource(resources.ModelResource):
    class Meta:
        model = Customer


class PurchaseOrderResource(resources.ModelResource):
    class Meta:
        model = PurchaseOrder


class InventoryDocumentResource(resources.ModelResource):
    class Meta:
        model = InventoryDocument


class PurchaseReceiptResource(resources.ModelResource):
    class Meta:
        model = PurchaseReceipt


class SalesInvoiceResource(resources.ModelResource):
    class Meta:
        model = SalesInvoice


class StockMovementResource(resources.ModelResource):
    class Meta:
        model = StockMovement


class InventoryValuationLayerResource(resources.ModelResource):
    class Meta:
        model = InventoryValuationLayer


class StockCountResource(resources.ModelResource):
    class Meta:
        model = StockCount


class PurchaseOrderLineResource(resources.ModelResource):
    class Meta:
        model = PurchaseOrderLine


class PurchaseReceiptLineResource(resources.ModelResource):
    class Meta:
        model = PurchaseReceiptLine


class SalesInvoiceLineResource(resources.ModelResource):
    class Meta:
        model = SalesInvoiceLine


class StockCountLineResource(resources.ModelResource):
    class Meta:
        model = StockCountLine


class SalesOrderResource(resources.ModelResource):
    class Meta:
        model = SalesOrder


class SalesOrderLineResource(resources.ModelResource):
    class Meta:
        model = SalesOrderLine


class VendorBillResource(resources.ModelResource):
    class Meta:
        model = VendorBill


class VendorBillLineResource(resources.ModelResource):
    class Meta:
        model = VendorBillLine


class LandedCostResource(resources.ModelResource):
    class Meta:
        model = LandedCost


class LandedCostAllocationResource(resources.ModelResource):
    class Meta:
        model = LandedCostAllocation


class LotResource(resources.ModelResource):
    class Meta:
        model = Lot


class SerialNumberResource(resources.ModelResource):
    class Meta:
        model = SerialNumber


class WarrantyClaimResource(resources.ModelResource):
    class Meta:
        model = WarrantyClaim


class TransferShipmentResource(resources.ModelResource):
    class Meta:
        model = TransferShipment


class TransferShipmentLineResource(resources.ModelResource):
    class Meta:
        model = TransferShipmentLine


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(ImportExportModelAdmin):
    resource_class = UnitOfMeasureResource
    list_display = ("company", "name", "abbreviation", "base_unit", "conversion_factor")
    list_filter = ("company",)
    search_fields = ("name", "abbreviation", "company__name")
    raw_id_fields = ("base_unit",)


@admin.register(InventoryCategory)
class InventoryCategoryAdmin(ImportExportModelAdmin):
    resource_class = InventoryCategoryResource
    list_display = ("company", "name", "costing_method")
    list_filter = ("company", "costing_method")
    search_fields = ("name", "company__name")
    raw_id_fields = (
        "inventory_account",
        "opening_balance_equity_account",
        "adjustment_gain_account",
        "shrinkage_expense_account",
        "sales_revenue_account",
        "cogs_account",
    )


@admin.register(InventoryItem)
class InventoryItemAdmin(ImportExportModelAdmin):
    resource_class = InventoryItemResource
    list_display = (
        "company",
        "sku",
        "name",
        "item_type",
        "barcode_format",
        "track_batch",
        "track_expiry",
        "is_active",
    )
    list_filter = ("company", "item_type", "track_batch", "track_expiry", "is_active")
    search_fields = ("sku", "name", "barcode", "company__name")


class TaxRuleInline(admin.TabularInline):
    model = TaxRule
    extra = 0


@admin.register(TaxJurisdiction)
class TaxJurisdictionAdmin(ImportExportModelAdmin):
    resource_class = TaxJurisdictionResource
    list_display = ("company", "code", "name", "country_code", "is_default", "is_active")
    list_filter = ("company", "country_code", "is_default", "is_active")
    search_fields = ("code", "name", "company__name")
    inlines = [TaxRuleInline]


@admin.register(TaxRule)
class TaxRuleAdmin(ImportExportModelAdmin):
    resource_class = TaxRuleResource
    list_display = (
        "company",
        "jurisdiction",
        "tax_type",
        "transaction_type",
        "rate",
        "effective_from",
        "effective_to",
        "is_active",
    )
    list_filter = ("company", "tax_type", "transaction_type", "is_active")
    search_fields = ("jurisdiction__code", "jurisdiction__name", "company__name")


class StockLocationInline(admin.TabularInline):
    model = StockLocation
    extra = 0


@admin.register(Warehouse)
class WarehouseAdmin(ImportExportModelAdmin):
    resource_class = WarehouseResource
    list_display = ("company", "code", "name", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("code", "name", "company__name")
    inlines = [StockLocationInline]


@admin.register(StockLocation)
class StockLocationAdmin(ImportExportModelAdmin):
    resource_class = StockLocationResource
    list_display = ("company", "warehouse", "code", "name", "is_active")
    list_filter = ("company", "warehouse", "is_active")
    search_fields = ("code", "name", "warehouse__code", "company__name")


@admin.register(Supplier)
class SupplierAdmin(ImportExportModelAdmin):
    resource_class = SupplierResource
    list_display = (
        "company",
        "name",
        "contact_name",
        "phone",
        "payment_terms",
        "default_due_days",
        "credit_limit",
        "is_active",
    )
    list_filter = ("company", "is_active")
    search_fields = ("name", "contact_name", "email", "phone", "company__name")
    raw_id_fields = ("payable_account", "wht_payable_account")


@admin.register(Customer)
class CustomerAdmin(ImportExportModelAdmin):
    resource_class = CustomerResource
    list_display = (
        "company",
        "name",
        "contact_name",
        "phone",
        "payment_terms",
        "default_due_days",
        "credit_limit",
        "collections_status",
        "is_active",
    )
    list_filter = ("company", "collections_status", "is_active")
    search_fields = ("name", "contact_name", "email", "phone", "company__name")
    raw_id_fields = ("receivable_account", "wht_receivable_account")


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0
    readonly_fields = ("received_quantity", "total_cost")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ImportExportModelAdmin):
    resource_class = PurchaseOrderResource
    list_display = ("company", "reference", "supplier", "order_date", "status")
    list_filter = ("company", "status", "order_date")
    search_fields = ("reference", "supplier__name", "notes", "company__name")
    inlines = [PurchaseOrderLineInline]


class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    readonly_fields = (
        "item",
        "location",
        "movement_type",
        "quantity",
        "unit_cost",
        "total_cost",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(InventoryDocument)
class InventoryDocumentAdmin(ImportExportModelAdmin):
    resource_class = InventoryDocumentResource
    list_display = ("company", "document_type", "status", "document_date", "reference")
    list_filter = ("company", "document_type", "status")
    search_fields = ("reference", "reason", "company__name")
    inlines = [StockMovementInline]


class PurchaseReceiptLineInline(admin.TabularInline):
    model = PurchaseReceiptLine
    extra = 0
    readonly_fields = (
        "item",
        "location",
        "quantity",
        "unit_cost",
        "vat_amount",
        "wht_amount",
        "total_cost",
        "movement",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PurchaseReceipt)
class PurchaseReceiptAdmin(ImportExportModelAdmin):
    resource_class = PurchaseReceiptResource
    list_display = ("company", "document", "supplier")
    list_filter = ("company", "supplier")
    search_fields = ("supplier__name", "document__reference", "company__name")
    inlines = [PurchaseReceiptLineInline]


class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
    extra = 0
    readonly_fields = (
        "item",
        "location",
        "quantity",
        "unit_price",
        "unit_cost",
        "revenue_amount",
        "cogs_amount",
        "vat_amount",
        "wht_amount",
        "movement",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(ImportExportModelAdmin):
    resource_class = SalesInvoiceResource
    list_display = ("company", "document", "customer")
    list_filter = ("company", "customer")
    search_fields = ("customer__name", "document__reference", "company__name")
    inlines = [SalesInvoiceLineInline]


@admin.register(StockMovement)
class StockMovementAdmin(ImportExportModelAdmin):
    resource_class = StockMovementResource
    list_display = (
        "company",
        "movement_date",
        "item",
        "location",
        "movement_type",
        "quantity",
        "total_cost",
    )
    list_filter = ("company", "movement_type", "movement_date")
    search_fields = ("item__sku", "item__name", "location__code", "memo")
    readonly_fields = (
        "company",
        "document",
        "item",
        "location",
        "movement_type",
        "quantity",
        "unit_cost",
        "total_cost",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InventoryValuationLayer)
class InventoryValuationLayerAdmin(ImportExportModelAdmin):
    resource_class = InventoryValuationLayerResource
    list_display = (
        "company",
        "item",
        "quantity",
        "remaining_quantity",
        "unit_cost",
        "total_cost",
        "remaining_total_cost",
    )
    list_filter = ("company",)
    search_fields = ("item__sku", "item__name", "company__name")
    readonly_fields = (
        "company",
        "movement",
        "item",
        "quantity",
        "remaining_quantity",
        "unit_cost",
        "total_cost",
        "remaining_total_cost",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StockCountLineInline(admin.TabularInline):
    model = StockCountLine
    extra = 0


@admin.register(StockCount)
class StockCountAdmin(ImportExportModelAdmin):
    resource_class = StockCountResource
    list_display = ("company", "location", "count_date", "status")
    list_filter = ("company", "status", "count_date")
    search_fields = ("location__code", "reason", "company__name")
    inlines = [StockCountLineInline]


@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(ImportExportModelAdmin):
    resource_class = PurchaseOrderLineResource
    list_display = ("purchase_order", "item", "quantity", "received_quantity", "unit_cost", "total_cost")
    raw_id_fields = ("purchase_order", "item")


@admin.register(PurchaseReceiptLine)
class PurchaseReceiptLineAdmin(ImportExportModelAdmin):
    resource_class = PurchaseReceiptLineResource
    list_display = ("receipt", "item", "location", "quantity", "unit_cost", "total_cost")
    raw_id_fields = ("receipt", "item", "location", "movement")


@admin.register(SalesInvoiceLine)
class SalesInvoiceLineAdmin(ImportExportModelAdmin):
    resource_class = SalesInvoiceLineResource
    list_display = ("invoice", "item", "location", "quantity", "unit_price", "revenue_amount")
    raw_id_fields = ("invoice", "item", "location", "movement")


@admin.register(CustomerReturn)
class CustomerReturnAdmin(ImportExportModelAdmin):
    resource_class = CustomerReturnResource
    list_display = ("company", "document", "customer")
    list_filter = ("company", "customer")
    search_fields = ("document__reference", "customer__name", "company__name")
    raw_id_fields = ("document", "customer")


@admin.register(CustomerReturnLine)
class CustomerReturnLineAdmin(ImportExportModelAdmin):
    resource_class = CustomerReturnLineResource
    list_display = ("customer_return", "item", "location", "quantity", "unit_cost", "unit_price")
    raw_id_fields = ("customer_return", "item", "location", "movement")


@admin.register(SupplierReturn)
class SupplierReturnAdmin(ImportExportModelAdmin):
    resource_class = SupplierReturnResource
    list_display = ("company", "document", "supplier")
    list_filter = ("company", "supplier")
    search_fields = ("document__reference", "supplier__name", "company__name")
    raw_id_fields = ("document", "supplier")


@admin.register(SupplierReturnLine)
class SupplierReturnLineAdmin(ImportExportModelAdmin):
    resource_class = SupplierReturnLineResource
    list_display = ("supplier_return", "item", "location", "quantity", "unit_cost")
    raw_id_fields = ("supplier_return", "item", "location", "movement")


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(ImportExportModelAdmin):
    resource_class = CustomerPaymentResource
    list_display = ("company", "customer", "document", "amount", "payment_date")
    list_filter = ("company", "payment_date")
    search_fields = ("customer__name", "document__reference", "reference")
    raw_id_fields = ("customer", "document", "cash_account")


@admin.register(CustomerPaymentAllocation)
class CustomerPaymentAllocationAdmin(ImportExportModelAdmin):
    resource_class = CustomerPaymentAllocationResource
    list_display = ("company", "payment", "invoice", "amount", "allocation_date")
    list_filter = ("company", "allocation_date")
    search_fields = ("payment__reference", "payment__customer__name", "invoice__document__reference")
    raw_id_fields = ("company", "payment", "invoice")


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(ImportExportModelAdmin):
    resource_class = SupplierPaymentResource
    list_display = ("company", "supplier", "document", "amount", "payment_date")
    list_filter = ("company", "payment_date")
    search_fields = ("supplier__name", "document__reference", "reference")
    raw_id_fields = ("supplier", "document", "cash_account")


@admin.register(SupplierPaymentAllocation)
class SupplierPaymentAllocationAdmin(ImportExportModelAdmin):
    resource_class = SupplierPaymentAllocationResource
    list_display = ("company", "payment", "receipt", "amount", "allocation_date")
    list_filter = ("company", "allocation_date")
    search_fields = ("payment__reference", "payment__supplier__name", "receipt__document__reference")
    raw_id_fields = ("company", "payment", "receipt")


@admin.register(TaxRemittance)
class TaxRemittanceAdmin(ImportExportModelAdmin):
    resource_class = TaxRemittanceResource
    list_display = ("company", "document", "paid_amount", "vat_output_amount", "vat_input_amount", "wht_amount")
    list_filter = ("company",)
    search_fields = ("document__reference",)
    raw_id_fields = ("document", "cash_account")


@admin.register(StockCountLine)
class StockCountLineAdmin(ImportExportModelAdmin):
    resource_class = StockCountLineResource
    list_display = ("stock_count", "item", "system_quantity", "counted_quantity", "variance_quantity")
    raw_id_fields = ("stock_count", "item")


@admin.register(SalesOrder)
class SalesOrderAdmin(ImportExportModelAdmin):
    resource_class = SalesOrderResource
    list_display = ("company", "reference", "customer", "order_date", "status")
    list_filter = ("company", "status", "order_date")
    search_fields = ("reference", "customer__name", "company__name")
    raw_id_fields = ("customer",)


@admin.register(SalesOrderLine)
class SalesOrderLineAdmin(ImportExportModelAdmin):
    resource_class = SalesOrderLineResource
    list_display = ("sales_order", "item", "quantity", "shipped_quantity", "reserved_quantity", "unit_price")
    raw_id_fields = ("sales_order", "item")


@admin.register(VendorBill)
class VendorBillAdmin(ImportExportModelAdmin):
    resource_class = VendorBillResource
    list_display = ("company", "bill_number", "supplier", "bill_date", "status")
    list_filter = ("company", "status", "bill_date")
    search_fields = ("bill_number", "supplier__name", "company__name")
    raw_id_fields = ("supplier",)


@admin.register(VendorBillLine)
class VendorBillLineAdmin(ImportExportModelAdmin):
    resource_class = VendorBillLineResource
    list_display = ("vendor_bill", "item", "description", "quantity", "unit_cost", "total_amount")
    raw_id_fields = ("vendor_bill", "item", "receipt_line")


@admin.register(LandedCost)
class LandedCostAdmin(ImportExportModelAdmin):
    resource_class = LandedCostResource
    list_display = ("company", "description", "cost_type", "purchase_receipt", "allocation_method", "status")
    list_filter = ("company", "status", "allocation_method")
    search_fields = ("description", "purchase_receipt__document__reference", "company__name")
    raw_id_fields = ("purchase_receipt",)


@admin.register(LandedCostAllocation)
class LandedCostAllocationAdmin(ImportExportModelAdmin):
    resource_class = LandedCostAllocationResource
    list_display = ("landed_cost", "receipt_line", "allocated_amount")
    raw_id_fields = ("landed_cost", "receipt_line")


@admin.register(Lot)
class LotAdmin(ImportExportModelAdmin):
    resource_class = LotResource
    list_display = ("company", "item", "lot_number", "status", "received_date", "expiry_date")
    list_filter = ("company", "status", "expiry_date")
    search_fields = ("item__sku", "item__name", "lot_number")
    raw_id_fields = ("item",)


@admin.register(SerialNumber)
class SerialNumberAdmin(ImportExportModelAdmin):
    resource_class = SerialNumberResource
    list_display = ("company", "item", "serial", "status", "sold_to")
    list_filter = ("company", "status")
    search_fields = ("item__sku", "item__name", "serial")
    raw_id_fields = ("item", "sold_to", "lot")


@admin.register(WarrantyClaim)
class WarrantyClaimAdmin(ImportExportModelAdmin):
    resource_class = WarrantyClaimResource
    list_display = ("company", "id", "customer", "serial_number", "status", "claim_date")
    list_filter = ("company", "status", "claim_date")
    search_fields = ("customer__name", "serial_number__serial", "serial_number__item__sku")
    raw_id_fields = ("customer", "serial_number")


@admin.register(TransferShipment)
class TransferShipmentAdmin(ImportExportModelAdmin):
    resource_class = TransferShipmentResource
    list_display = ("company", "reference", "from_location", "to_location", "dispatched_date", "status")
    list_filter = ("company", "status", "dispatched_date")
    search_fields = ("reference", "from_location__code", "to_location__code")
    raw_id_fields = ("from_location", "to_location")


@admin.register(TransferShipmentLine)
class TransferShipmentLineAdmin(ImportExportModelAdmin):
    resource_class = TransferShipmentLineResource
    list_display = ("shipment", "item", "quantity", "received_quantity")
    raw_id_fields = ("shipment", "item", "lot")
