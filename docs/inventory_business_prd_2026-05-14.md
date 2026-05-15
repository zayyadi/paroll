# Inventory And Business Management PRD

Date: 2026-05-14

## Product Vision

This app should become a practical small-business operating system for businesses that need employee management, payroll, inventory, and daily business activity management in one tenant-scoped product.

The next major product area is inventory and business operations. The first version should use a shared wholesale-distribution inventory core, then layer pharmacy and small-restaurant requirements on top.

## Target Segments

Primary v1 segment:
- Wholesale distribution

Supported extension tracks:
- Pharmacy
- Small restaurant

This means v1 must be strong at stock control, purchasing, receiving, warehouses/locations, stock counts, adjustments, transfers, valuation, and low-stock management. Pharmacy and restaurant should not fork the product into separate systems; they should use the same core inventory ledger with specialized fields and workflows.

## Global-Practice Alignment

The design should follow these global practices:

- Inventory accounting should align with IAS 2 principles: inventory measured at cost and expensed through COGS when sold/used; FIFO or weighted average are acceptable cost formulas for interchangeable items; LIFO should not be used for IFRS-aligned reporting.
- Use weighted average cost as the default v1 costing method because it is simpler for SMEs and easier to reconcile. Keep the model extensible for FIFO.
- Keep stock movement as an immutable subledger. Posted receipts, issues, transfers, counts, and adjustments should be reversed or corrected, not edited.
- Use item category posting profiles so G/L accounts are configured, not hardcoded.
- Support GS1-style identifiers where useful: SKU/internal code, barcode/GTIN, batch/lot number, serial number, and expiry date.
- Pharmacy track should support batch/lot, expiry, supplier/manufacturer, FEFO picking, controlled adjustment reasons, and recall traceability.
- Restaurant track should support ingredients, units/conversions, prepared items/recipes, wastage/spoilage, date marking, and stock usage from sales or production.
- Period close controls must prevent backdated inventory changes from silently changing closed financial statements.
- Inventory valuation must reconcile to the accounting inventory asset account.

Reference sources:
- IFRS IAS 2 Inventories: https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/
- GS1 Global Traceability Standard: https://www.gs1.org/standards/gs1-global-traceability-standard/current-standard
- GS1 Healthcare Standards: https://www.gs1.org/industries/healthcare/standards
- FDA Food Code: https://www.fda.gov/food/retail-food-protection/fda-food-code
- CDC Restaurant Date Marking Practices: https://www.cdc.gov/restaurant-food-safety/php/practices/date-marking.html

## Product Principles

- Tenant-first: every item, warehouse, document, journal, report, and setting belongs to a company.
- Operational truth first: inventory quantity lives in inventory documents and stock movements, not in accounting journals.
- Accounting follows inventory: inventory documents generate accounting entries through posting services.
- Simple default, advanced optional: wholesale stock control should work without forcing pharmacy or restaurant complexity.
- Auditability over convenience: posted stock records must not be silently mutable.
- Configuration over hardcoding: accounts, costing method, numbering, tax, and approval thresholds should be company settings.

## MVP Scope

### Phase 1: Stock-Control Core

Build the inventory foundation:

- Item categories
- Items/SKUs
- Units of measure
- Warehouses
- Stock locations
- Opening stock
- Stock movements
- Stock adjustments
- Stock counts
- Transfers between locations/warehouses
- Low-stock and reorder levels
- Stock on hand report
- Stock movement ledger
- Inventory valuation report

Phase 1 should not require sales orders or purchase orders to be useful. A business should be able to create items, receive opening stock, adjust/count stock, transfer stock, and see valuation.

### Phase 2: Purchasing

Add:

- Vendors/suppliers
- Purchase orders
- Goods receipts
- Supplier bills or bill reference fields
- Goods received not invoiced accounting
- Purchase price variance handling
- Landed cost placeholder fields

### Phase 3: Sales And Fulfillment

Add:

- Customers
- Sales quotations/orders
- Sales invoices or invoice reference fields
- Stock reservation/commitment
- Shipment/dispatch
- Returns
- COGS posting

### Phase 4: Pharmacy Extension

Add:

- Batch/lot tracking
- Expiry date tracking
- FEFO picking
- Supplier/manufacturer traceability
- Recall report by batch/lot
- Expiry alerts
- Controlled adjustment reason codes
- Optional serial tracking for regulated items

### Phase 5: Restaurant Extension

Add:

- Ingredient items
- Recipe/BOM definitions
- Unit conversions
- Prep/production batches
- Wastage/spoilage tracking
- Menu item stock usage
- Date marking/prep labels
- Kitchen stock counts

## Core Domain Model

Recommended Django apps:

- `inventory`: item master, warehouses, stock movements, valuation, counts, transfers.
- `business`: vendors, customers, orders, invoices, operational activity records.
- Keep accounting in `accounting`, but expose posting services for inventory/business documents.

Core inventory models:

- `InventoryCategory`
- `InventoryItem`
- `UnitOfMeasure`
- `UnitConversion`
- `Warehouse`
- `StockLocation`
- `StockMovement`
- `InventoryValuationLayer`
- `StockAdjustment`
- `StockAdjustmentLine`
- `StockCount`
- `StockCountLine`
- `StockTransfer`
- `StockTransferLine`
- `InventoryPostingProfile`
- `InventoryPeriodClose`

Purchasing models:

- `Vendor`
- `PurchaseOrder`
- `PurchaseOrderLine`
- `GoodsReceipt`
- `GoodsReceiptLine`

Sales models:

- `Customer`
- `SalesOrder`
- `SalesOrderLine`
- `Shipment`
- `ShipmentLine`
- `SalesReturn`
- `SalesReturnLine`

Pharmacy extension models:

- `ItemBatch`
- `BatchRecall`
- `RegulatedItemProfile`

Restaurant extension models:

- `Recipe`
- `RecipeIngredient`
- `ProductionBatch`
- `WasteLog`

## Accounting Posting Rules

Opening stock:
- Debit Inventory Asset
- Credit Opening Balance Equity

Goods receipt before bill:
- Debit Inventory Asset
- Credit Goods Received Not Invoiced

Supplier bill matched to receipt:
- Debit Goods Received Not Invoiced
- Credit Accounts Payable
- Post difference to Purchase Price Variance where needed.

Sale/shipment:
- Debit COGS
- Credit Inventory Asset

Sales return:
- Debit Inventory Asset
- Credit COGS

Inventory shrinkage/write-off:
- Debit Inventory Shrinkage Expense
- Credit Inventory Asset

Positive adjustment:
- Debit Inventory Asset
- Credit Inventory Adjustment Gain

Restaurant wastage:
- Debit Wastage/Spoilage Expense
- Credit Inventory Asset

Internal warehouse transfer:
- No G/L entry when same company and same inventory valuation account.

## Controls

Required:

- Every inventory model has `company`.
- All APIs filter by active company.
- Posted stock documents are immutable.
- Reversal/correction documents are used for corrections.
- No negative stock by default.
- Optional company setting can allow negative stock for selected workflows, but with warnings and reconciliation reports.
- Stock count approval required before posting variances.
- Adjustment approval thresholds configurable by company.
- Inventory period close prevents backdated postings.
- Inventory valuation must reconcile to accounting.
- Batch/expiry products require batch and expiry before receipt.
- Restaurant prepared foods/ingredients support date/prep marking workflows.

## UX Modules

First navigation group: Inventory

- Dashboard
- Items
- Categories
- Warehouses
- Stock On Hand
- Stock Movements
- Adjustments
- Counts
- Transfers
- Reorder Alerts
- Valuation

Second navigation group: Purchasing

- Vendors
- Purchase Orders
- Goods Receipts

Third navigation group: Sales

- Customers
- Sales Orders
- Shipments
- Returns

Specialized tabs:

- Pharmacy: Batches, Expiry Alerts, Recall Report
- Restaurant: Recipes, Prep/Production, Waste Logs

## Acceptance Criteria

Phase 1 is complete when:

- A tenant can create item categories, items, warehouses, and stock locations.
- The same SKU can exist in different companies without collision.
- Opening stock creates stock movements and a balanced accounting journal.
- Stock adjustment creates immutable movement records and balanced accounting journal.
- Stock count posts approved variances only.
- Transfers move quantity between locations without changing company-level valuation.
- Stock on hand report is company scoped.
- Stock movement ledger is company scoped.
- Inventory valuation report reconciles to the company’s inventory asset account.
- Cross-tenant API access is denied by tests.
- Unit tests cover no-negative-stock, adjustment posting, count variance, valuation calculation, and tenant isolation.

## Non-Goals For MVP

- Manufacturing/MRP
- E-commerce marketplace sync
- Mobile barcode app
- Multi-currency landed cost allocation
- Advanced route optimization
- Full external accounting sync
- POS system
- Controlled-substance legal compliance automation

## Decision Boundaries

Codex may decide:

- Django model names and field details that follow the PRD.
- Basic UI layout consistent with the existing app.
- Test organization and service-layer boundaries.
- Weighted average cost implementation details for v1.
- Conservative validation defaults.

Ask before deciding:

- Adding new dependencies.
- Enabling negative stock.
- Building POS/e-commerce/accounting connector features.
- Implementing country-specific pharmacy compliance beyond batch/expiry/traceability primitives.
- Changing existing payroll behavior.

## Recommended Next Engineering Track

Start with Phase 1 in a new `inventory` Django app:

1. Create tenant-scoped inventory models.
2. Add migrations.
3. Add service layer for stock posting.
4. Add weighted-average valuation service.
5. Add accounting posting service using tenant-scoped accounts.
6. Add DRF serializers/viewsets with tenant filtering.
7. Add web views/templates for basic stock management.
8. Add tests before implementation for tenant isolation and posting correctness.

