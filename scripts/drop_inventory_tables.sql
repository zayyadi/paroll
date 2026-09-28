-- Drop orphaned inventory_* tables left by ADR-0003 removal.
-- BACK UP FIRST: python manage.py dumpdata inventory --output inventory_backup.json
-- (Run BEFORE deploying the removal, while the app still exists.)
-- Postgres: wrap in a transaction; SQLite: run as-is.

DROP TABLE IF EXISTS "inventory_customer";
DROP TABLE IF EXISTS "inventory_customerpayment";
DROP TABLE IF EXISTS "inventory_customerpaymentallocation";
DROP TABLE IF EXISTS "inventory_customerreturn";
DROP TABLE IF EXISTS "inventory_customerreturnline";
DROP TABLE IF EXISTS "inventory_inventorycategory";
DROP TABLE IF EXISTS "inventory_inventorydocument";
DROP TABLE IF EXISTS "inventory_inventoryitem";
DROP TABLE IF EXISTS "inventory_inventoryvaluationlayer";
DROP TABLE IF EXISTS "inventory_landedcost";
DROP TABLE IF EXISTS "inventory_landedcostallocation";
DROP TABLE IF EXISTS "inventory_lot";
DROP TABLE IF EXISTS "inventory_purchaseorder";
DROP TABLE IF EXISTS "inventory_purchaseorderline";
DROP TABLE IF EXISTS "inventory_purchasereceipt";
DROP TABLE IF EXISTS "inventory_purchasereceiptline";
DROP TABLE IF EXISTS "inventory_salesinvoice";
DROP TABLE IF EXISTS "inventory_salesinvoiceline";
DROP TABLE IF EXISTS "inventory_salesorder";
DROP TABLE IF EXISTS "inventory_salesorderline";
DROP TABLE IF EXISTS "inventory_serialnumber";
DROP TABLE IF EXISTS "inventory_stockcount";
DROP TABLE IF EXISTS "inventory_stockcountline";
DROP TABLE IF EXISTS "inventory_stocklocation";
DROP TABLE IF EXISTS "inventory_stockmovement";
DROP TABLE IF EXISTS "inventory_supplier";
DROP TABLE IF EXISTS "inventory_supplierpayment";
DROP TABLE IF EXISTS "inventory_supplierpaymentallocation";
DROP TABLE IF EXISTS "inventory_supplierreturn";
DROP TABLE IF EXISTS "inventory_supplierreturnline";
DROP TABLE IF EXISTS "inventory_taxjurisdiction";
DROP TABLE IF EXISTS "inventory_taxremittance";
DROP TABLE IF EXISTS "inventory_taxrule";
DROP TABLE IF EXISTS "inventory_transfershipment";
DROP TABLE IF EXISTS "inventory_transfershipmentline";
DROP TABLE IF EXISTS "inventory_unitofmeasure";
DROP TABLE IF EXISTS "inventory_vendorbill";
DROP TABLE IF EXISTS "inventory_vendorbillline";
DROP TABLE IF EXISTS "inventory_warehouse";
DROP TABLE IF EXISTS "inventory_warrantyclaim";

-- Also clear stale migration state:
-- DELETE FROM django_migrations WHERE app = 'inventory';
