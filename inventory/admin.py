from django.contrib import admin

from inventory.models import (
    Customer,
    InventoryCategory,
    InventoryDocument,
    InventoryItem,
    InventoryValuationLayer,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    SalesInvoice,
    SalesInvoiceLine,
    StockCount,
    StockCountLine,
    StockLocation,
    StockMovement,
    Supplier,
    UnitOfMeasure,
    Warehouse,
)


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ("company", "name", "abbreviation")
    list_filter = ("company",)
    search_fields = ("name", "abbreviation", "company__name")


@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
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
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "sku",
        "name",
        "item_type",
        "track_batch",
        "track_expiry",
        "is_active",
    )
    list_filter = ("company", "item_type", "track_batch", "track_expiry", "is_active")
    search_fields = ("sku", "name", "barcode", "company__name")


class StockLocationInline(admin.TabularInline):
    model = StockLocation
    extra = 0


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("company", "code", "name", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("code", "name", "company__name")
    inlines = [StockLocationInline]


@admin.register(StockLocation)
class StockLocationAdmin(admin.ModelAdmin):
    list_display = ("company", "warehouse", "code", "name", "is_active")
    list_filter = ("company", "warehouse", "is_active")
    search_fields = ("code", "name", "warehouse__code", "company__name")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("company", "name", "contact_name", "phone", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("name", "contact_name", "email", "phone", "company__name")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("company", "name", "contact_name", "phone", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("name", "contact_name", "email", "phone", "company__name")


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0
    readonly_fields = ("received_quantity", "total_cost")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
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
class InventoryDocumentAdmin(admin.ModelAdmin):
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
class PurchaseReceiptAdmin(admin.ModelAdmin):
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
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = ("company", "document", "customer")
    list_filter = ("company", "customer")
    search_fields = ("customer__name", "document__reference", "company__name")
    inlines = [SalesInvoiceLineInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
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
class InventoryValuationLayerAdmin(admin.ModelAdmin):
    list_display = ("company", "item", "quantity", "unit_cost", "total_cost")
    list_filter = ("company",)
    search_fields = ("item__sku", "item__name", "company__name")
    readonly_fields = ("company", "movement", "item", "quantity", "unit_cost", "total_cost")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StockCountLineInline(admin.TabularInline):
    model = StockCountLine
    extra = 0


@admin.register(StockCount)
class StockCountAdmin(admin.ModelAdmin):
    list_display = ("company", "location", "count_date", "status")
    list_filter = ("company", "status", "count_date")
    search_fields = ("location__code", "reason", "company__name")
    inlines = [StockCountLineInline]
