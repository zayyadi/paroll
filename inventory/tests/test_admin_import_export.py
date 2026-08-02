from django.contrib import admin
from django.test import SimpleTestCase

from inventory import admin as inventory_admin
from inventory.models import (
    Customer,
    CustomerPayment,
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


class InventoryAdminImportExportTests(SimpleTestCase):
    def test_registered_inventory_admins_have_matching_import_export_resources(self):
        expected_models = [
            UnitOfMeasure,
            InventoryCategory,
            InventoryItem,
            TaxJurisdiction,
            TaxRule,
            Warehouse,
            StockLocation,
            Supplier,
            Customer,
            PurchaseOrder,
            PurchaseOrderLine,
            InventoryDocument,
            PurchaseReceipt,
            PurchaseReceiptLine,
            SalesInvoice,
            SalesInvoiceLine,
            CustomerReturn,
            CustomerReturnLine,
            SupplierReturn,
            SupplierReturnLine,
            CustomerPayment,
            SupplierPayment,
            TaxRemittance,
            StockMovement,
            InventoryValuationLayer,
            StockCount,
            StockCountLine,
            SalesOrder,
            SalesOrderLine,
            VendorBill,
            VendorBillLine,
            LandedCost,
            LandedCostAllocation,
            Lot,
            SerialNumber,
            WarrantyClaim,
            TransferShipment,
            TransferShipmentLine,
        ]

        for model in expected_models:
            model_admin = admin.site._registry[model]
            with self.subTest(model=model.__name__):
                self.assertIsInstance(
                    model_admin,
                    inventory_admin.ImportExportModelAdmin,
                )
                self.assertIs(model_admin.resource_class.Meta.model, model)
