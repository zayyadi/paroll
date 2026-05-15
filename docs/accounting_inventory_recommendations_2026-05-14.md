# Accounting and Inventory Recommendations

Date: 2026-05-14

## Executive Summary

The current app has the foundation of a double-entry accounting module: chart of accounts, fiscal years, accounting periods, journals, journal entries, approvals, posting, reversals, trial balance reporting, and audit trail. It is strongest as an internal general ledger for payroll postings.

It is not yet ready to support inventory accounting safely. The main blockers are tenant scoping, inventory subledger absence, costing-engine absence, weak period/stock close controls, and no purchasing/sales document flow. Before adding inventory, the accounting layer should be converted from a global ledger into a company-scoped ledger with explicit source-document posting rules.

Recommended product direction:

1. For this payroll/HR app: build an inventory-accounting extension only if the goal is internal asset/consumable tracking, employee equipment, office supplies, and simple stock valuation. Keep it conservative.
2. For a separate inventory management app: build a dedicated inventory subledger and optionally sync summarized accounting entries into this app or external systems such as QuickBooks, Xero, Zoho Books, Sage, Odoo, Business Central, or NetSuite.

## Market Research Baseline

### QuickBooks Online

QuickBooks Online Plus and Advanced include inventory tracking. Intuit documentation states that QuickBooks Online uses FIFO for inventory cost accounting and posts inventory asset and cost of goods sold effects when inventory items are sold. This is good for small businesses that need simple inventory accounting, but it is not a deep warehouse management system.

Useful product lessons:
- Keep the default costing method simple.
- Inventory sales must post both revenue and COGS.
- Backdated stock activity can force costing recalculation, so a serious app needs explicit period locks and recalculation jobs.

Source: [QuickBooks inventory setup](https://quickbooks.intuit.com/learn-support/en-us/help-article/inventory-management/find-difference-stocktake-stock-adjustment/L8XTI179H_US_en_US), [QuickBooks FIFO inventory valuation](https://quickbooks.intuit.com/learn-support/en-us/help-articles/what-is-fifo-and-how-is-it-used-for-inventory-cost-accounting/00/261565)

### Microsoft Dynamics 365 Business Central

Business Central is a strong reference for professional inventory accounting. Microsoft documents company defaults and item-level costing methods, inventory periods, expected cost posting, automatic cost posting, cost adjustment, inventory revaluation, and G/L reconciliation.

Useful product lessons:
- Separate inventory periods from accounting periods.
- Support cost adjustment after late invoices or price corrections.
- Post inventory value to dedicated G/L accounts.
- Make exact cost reversing mandatory for returns when valuation accuracy matters.

Source: [Business Central inventory costs](https://learn.microsoft.com/en-us/dynamics365/business-central/finance-manage-inventory-costs)

### Xero

Xero supports tracked inventory with inventory asset and COGS accounts. It is suitable for lighter inventory needs, but compared with ERP systems it is less of a warehouse operations platform.

Useful product lessons:
- Make inventory setup guided: inventory asset account, COGS account, sales account, opening balances.
- Keep small-business workflows simple and explain when a dedicated inventory app is needed.

Source: [Xero tracked inventory setup](https://central.xero.com/s/article/Set-up-tracked-inventory)

### Zoho Books / Zoho Inventory

Zoho’s accounting and inventory suite offers warehouses, reorder points, landed costs, serial numbers, batch tracking, expiry tracking, inventory adjustments, valuation reports, and FIFO cost lot reporting.

Useful product lessons:
- Inventory users expect stock availability, committed stock, reorder points, purchase orders, barcode scanning, warehouses, serial/batch tracking, landed cost allocation, adjustments, and inventory aging.
- A separate inventory app should support operational stock states, not just accounting quantities.

Source: [Zoho Books inventory accounting](https://www.zoho.com/books/accounting-software/inventory-accounting/)

### Sage 50

Sage 50 has inventory management, purchase orders, inventory valuation and sales reports, and supports multiple costing methods such as FIFO, average, and specific unit costing.

Useful product lessons:
- Desktop/accounting-first products often expose costing method choice early.
- Costing method changes should be controlled because they affect financial statements.

Source: [Sage 50 features](https://www.sage.com/en-us/products/sage-50/features/)

### Odoo

Odoo’s inventory valuation model is a very useful reference because it explicitly separates cost method from accounting valuation mode. It supports standard price, average cost, and FIFO, and supports manual or automated valuation.

Useful product lessons:
- Let the business choose between periodic/manual inventory valuation and perpetual/automated valuation.
- Costing belongs on item categories, not only globally.
- FIFO is financial FIFO, not necessarily the physical pick sequence.

Source: [Odoo inventory valuation](https://www.odoo.com/documentation/13.0/applications/inventory_and_mrp/inventory/management/reporting/inventory_valuation_config.html)

### NetSuite

NetSuite supports average, FIFO, group average, LIFO, specific, lot-numbered, and standard costing. Oracle notes that average costing is the default and that costing method cannot be changed after saving an item record.

Useful product lessons:
- Do not casually allow costing-method changes after stock history exists.
- Lot/serial cost behavior should be designed from the beginning.
- Negative inventory needs explicit policy because it can distort costing.

Source: [NetSuite costing methods](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_N2191818.html)

## Current App Accounting Audit

### What Exists

The app has these accounting primitives:

- `Account`: account name, number, type, and computed balance.
- `FiscalYear`: fiscal year setup and closure.
- `AccountingPeriod`: monthly/period boundary and closure.
- `Journal`: transaction number, status workflow, approval, posting, reversal, and source object link.
- `JournalEntry`: debit/credit lines.
- `AccountingAuditTrail`: user/action/object/change metadata.
- Utilities for creating, posting, reversing, closing periods, and producing trial balance.
- API endpoints for accounts, fiscal years, periods, journals, and journal entries, currently superuser-gated.
- Payroll close posting policy and tests around payroll journal generation.

Primary local references:
- `accounting/models.py`
- `accounting/utils.py`
- `api/v1/viewsets.py`
- `api/v1/serializers.py`
- `docs/accounting_payroll_posting_policy_ng.md`
- `accounting/tests/test_payroll_postings.py`

### Strengths

- Double-entry discipline exists through journal debit/credit validation.
- Journal lifecycle exists: draft, pending approval, approved, posted, reversed.
- Reversal workflow exists instead of silent mutation.
- Period and fiscal-year close concepts exist.
- Generic source-object linking exists, which can support payroll runs and future inventory documents.
- Audit trail exists and captures action, object, changes, user, IP, and user agent.
- API is intentionally superuser-gated until tenant scoping is solved. That is a good temporary safety measure.

### Gaps and Risks

#### Critical: Accounting Is Not Tenant-Scoped

The rest of the app is company-scoped, but accounting models do not carry `company`. Account names and numbers are globally unique. Journals, periods, fiscal years, and audit entries are global. For a SaaS payroll/inventory product, this is the biggest accounting risk.

Impact:
- One company’s chart of accounts can collide with another’s.
- Trial balances can mix companies.
- Inventory valuation would be impossible to trust across tenants.
- Superuser-only API gate is necessary today, but it blocks normal product use.

Recommendation:
- Add `company` to `Account`, `FiscalYear`, `AccountingPeriod`, `Journal`, and preferably `AccountingAuditTrail`.
- Change uniqueness from global to company-scoped, for example `(company, account_number)` and `(company, year)`.
- Ensure every report filters by company.
- Backfill existing data into a default company before opening accounting APIs to tenant users.

#### Critical: No Inventory Subledger

There are no production models for SKU/item, warehouse/location, stock movement, item receipt, shipment, purchase order, sales order, inventory adjustment, stock count, lot, serial number, landed cost, or inventory valuation layer.

Impact:
- Inventory cannot be accounted for from operational truth.
- A journal-only approach would produce ledger numbers without quantity control.
- Reconciliation between stock-on-hand and G/L would be manual and fragile.

Recommendation:
- Build inventory as a subledger. Journals should be generated from immutable stock documents, not typed directly by users.

#### High: No Costing Engine

Current account balances are computed by summing debit/credit journal entries. There is no item-level cost method, cost layer, average cost state, standard cost variance, landed cost allocation, or revaluation workflow.

Recommendation:
- Start with weighted average cost for a first inventory product, or FIFO if regulatory/business requirements demand it.
- Store valuation layers or cost events even if using average cost, so audit and recalculation remain possible.
- Do not support LIFO in the first version.

#### High: Period Controls Are Accounting-Only

There is an `AccountingPeriod`, but no inventory period close, no stock freeze, no inventory count approval, and no rule preventing backdated stock movement from changing closed inventory valuation.

Recommendation:
- Add inventory periods or inventory close status per company.
- Prevent posting stock movements into closed inventory periods.
- For adjustments after close, require dated correction journals in the current open period.

#### High: Account Balance Validation Is Too Naive For Inventory

`validate_account_balance` checks balances for credits to asset/expense accounts. That can be useful for cash control, but inventory accounting needs item quantity and valuation checks, not just G/L account balance checks.

Recommendation:
- Do not use account-level balance validation as the stock availability rule.
- Stock availability should be enforced at `(company, item, warehouse/location, lot/serial)` level.

#### Medium: Direct Journal APIs Need Stronger Accounting Controls

Current API serializers expose journals and journal entries separately. This can create orphaned, incomplete, or unbalanced draft states unless all write paths use the utility methods and transactional validation.

Recommendation:
- For inventory-generated journals, hide manual journal-entry mutation.
- Create domain posting services such as `post_goods_receipt`, `post_sales_shipment`, `post_inventory_adjustment`, and `post_landed_cost`.

#### Medium: Chart Of Accounts Is Payroll-Oriented

The initial account command and policy are mostly payroll-focused. Inventory requires a broader chart:

- Inventory Asset
- Inventory In Transit
- Goods Received Not Invoiced
- Accounts Payable
- Sales Revenue
- Sales Returns and Allowances
- Cost of Goods Sold
- Purchase Price Variance
- Inventory Shrinkage / Write-off
- Inventory Adjustment Gain/Loss
- Landed Cost Clearing
- Work in Progress, if manufacturing is planned

Recommendation:
- Introduce account mapping settings per company and per item category.
- Do not hardcode account numbers inside posting services.

## Recommended Integrated Inventory Accounting Module

This is the right path if inventory is a supporting feature inside the current payroll/business management app.

### Scope

Target use cases:
- Office assets and consumables.
- Employee-issued equipment.
- Simple stock purchases and usage.
- Internal department/location stock.
- Basic valuation reports.

Avoid in v1:
- Manufacturing.
- Complex warehouse picking/packing.
- Multi-currency landed costs.
- Serial warranty workflows.
- Marketplace/e-commerce synchronization.

### Data Model

Minimum models:

- `InventoryItem`: company, SKU, name, item type, category, unit of measure, tracking mode, costing method, active flag.
- `InventoryCategory`: company, name, default inventory account, COGS/expense account, adjustment account, sales account.
- `Warehouse`: company, code, name, address, active flag.
- `StockLocation`: company, warehouse, code, type.
- `StockMovement`: immutable stock event with source document, item, location, quantity in/out, unit cost, total value, movement date.
- `InventoryValuationLayer`: item, movement, quantity, unit cost, remaining quantity, remaining value.
- `StockAdjustment`: header/lines, reason, approval status.
- `StockCount`: count session, lines, variance, approval and posting status.
- `GoodsReceipt`: vendor receipt with lines and optional bill reference.
- `InventoryPostingProfile`: company/category mapping to ledger accounts.

Optional after v1:
- `Lot`
- `SerialNumber`
- `LandedCostAllocation`
- `InventoryTransfer`
- `SalesShipment`
- `PurchaseOrder`

### Accounting Posting Rules

Suggested baseline postings:

Goods receipt, when bill is not yet received:
- Debit Inventory Asset
- Credit Goods Received Not Invoiced

Vendor bill matched to receipt:
- Debit Goods Received Not Invoiced
- Credit Accounts Payable
- Post variance to Purchase Price Variance if bill price differs from receipt valuation.

Sale/shipment:
- Debit COGS
- Credit Inventory Asset

Inventory write-off/shrinkage:
- Debit Inventory Shrinkage Expense
- Credit Inventory Asset

Positive inventory adjustment:
- Debit Inventory Asset
- Credit Inventory Adjustment Gain

Stock transfer:
- No G/L impact if same company and same valuation account.
- G/L impact only if moving between valuation groups or legal entities.

Landed cost:
- Debit Inventory Asset or COGS depending on whether stock remains on hand.
- Credit Landed Cost Clearing or Accounts Payable.

### Costing Recommendation

Use weighted average cost for v1 unless the business explicitly needs FIFO. Weighted average is simpler, performs better, and is easier for SMEs to understand.

Add FIFO later when:
- Perishable goods or batch costing matters.
- Purchase prices fluctuate materially.
- Auditors require FIFO valuation.
- There is a strong reason to preserve cost layers by receipt.

Never allow costing method changes after the item has posted stock movements unless handled through a controlled migration/revaluation workflow.

### Controls

Required controls before go-live:

- Tenant-scoped accounting.
- Immutable posted stock movements.
- Reversal/correction documents instead of editing posted documents.
- Approval for stock adjustments above threshold.
- Closed inventory periods reject backdated postings.
- Stock-on-hand cannot go negative unless a company setting explicitly allows it.
- Every stock posting has source document, user, timestamp, and reason.
- Inventory valuation report must reconcile to G/L inventory account.

## Recommended Separate Inventory Management App

This is the better path if the product goal is a serious inventory system comparable to Zoho Inventory, Odoo Inventory, or a lightweight ERP module.

### Product Positioning

Build it as an operational inventory subledger with accounting integration, not as a general ledger replacement.

Core promise:
- Know what stock exists, where it is, what it cost, what is committed, what needs replenishment, and how its valuation reconciles to accounting.

### Core Modules

1. Item master
2. Warehouses and locations
3. Stock receipts
4. Stock issues/shipments
5. Stock transfers
6. Adjustments and stock counts
7. Reorder points and replenishment
8. Purchase orders
9. Sales orders or outbound reservations
10. Batch/lot/serial tracking
11. Barcode scanning
12. Inventory valuation
13. Accounting sync
14. Audit trail and approvals

### Accounting Integration Pattern

The separate app should produce accounting events, not own every accounting workflow.

Recommended integration modes:

- Internal ledger mode: post summary journals into this app’s accounting module.
- QuickBooks/Xero/Zoho/Sage mode: sync invoices, bills, payments, inventory adjustments, and COGS journals through connectors.
- ERP mode: export/import journals or API-sync to Business Central, Odoo, or NetSuite.

For v1, prefer summarized journal sync:
- One journal per inventory document or per daily posting batch.
- Include source document IDs for drill-through.
- Keep stock movement detail in the inventory app.

### Separate App Architecture

Bounded contexts:

- Inventory core: item, warehouse, movement, quantity.
- Costing: valuation layers, average/FIFO calculations, revaluation.
- Procurement: vendors, purchase orders, receipts.
- Sales fulfillment: reservations, shipments, returns.
- Accounting bridge: posting profiles, journal payloads, sync status.
- Audit/compliance: immutable logs, approvals, period locks.

API-first design:
- REST endpoints for item master, stock movements, stock availability, reservations, receipts, shipments, adjustments, valuation reports, and accounting events.
- Webhooks for document posted, movement posted, valuation changed, period closed, sync failed.
- Idempotency keys on all posting endpoints.

### Reporting Requirements

Minimum reports:

- Stock on hand
- Stock availability
- Inventory valuation
- Inventory aging
- Inventory movement ledger
- Reorder report
- Slow-moving and dead stock
- Adjustment history
- COGS summary
- Inventory-to-G/L reconciliation

## Implementation Roadmap

### Phase 1: Accounting Hardening

- Add company scoping to accounting models and reports.
- Convert unique constraints to company-scoped constraints.
- Backfill existing global accounting records.
- Remove superuser-only API gate after tenant-scoped permissions and tests pass.
- Add account mapping settings per company.
- Add tests proving cross-tenant accounting isolation.

### Phase 2: Inventory Subledger MVP

- Add item, category, warehouse/location, movement, and valuation models.
- Add stock adjustment and goods receipt workflows.
- Add weighted average costing.
- Generate balanced accounting journals from stock documents.
- Add valuation and movement reports.
- Add period close controls.

### Phase 3: Purchasing And Sales Flow

- Add purchase orders, vendor bills/receipt matching, sales orders, reservations, shipments, and returns.
- Add GRNI and purchase price variance accounting.
- Add customer/vendor integrations if needed.

### Phase 4: Advanced Inventory

- Add FIFO valuation layers if required.
- Add lot/serial tracking.
- Add landed cost allocation.
- Add barcode workflows.
- Add multi-warehouse transfer costing.
- Add external accounting connectors.

## Build vs Integrate Recommendation

For this app:
- Build only the accounting hardening and simple internal inventory module.
- Do not try to compete with Business Central, NetSuite, or Odoo inside the payroll app.

For a separate inventory app:
- Build the operational inventory system.
- Integrate with accounting platforms rather than replacing them at first.
- Use this app’s accounting module as an optional native ledger for customers who want one system.

## Immediate Next Engineering Actions

1. Decide whether inventory is internal-support inventory or a standalone product.
2. Tenant-scope accounting before any inventory work.
3. Add company account mapping settings.
4. Write tests for company-isolated chart of accounts, journals, trial balance, and payroll posting.
5. Draft inventory domain models and posting rules.
6. Start with weighted average cost unless FIFO is a confirmed requirement.
7. Create a reconciliation report that ties inventory valuation to the G/L inventory asset account.

