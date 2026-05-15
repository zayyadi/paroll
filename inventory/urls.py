from django.urls import path

from inventory import views


app_name = "inventory"

urlpatterns = [
    path("", views.InventoryDashboardView.as_view(), name="dashboard"),
    path(
        "posting-accounts/",
        views.PostingAccountSetupView.as_view(),
        name="posting_account_setup",
    ),
    path("units/new/", views.UnitOfMeasureCreateView.as_view(), name="unit_create"),
    path("categories/", views.InventoryCategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.InventoryCategoryCreateView.as_view(), name="category_create"),
    path("items/", views.InventoryItemListView.as_view(), name="item_list"),
    path("items/new/", views.InventoryItemCreateView.as_view(), name="item_create"),
    path("items/<int:pk>/", views.InventoryItemDetailView.as_view(), name="item_detail"),
    path("warehouses/", views.WarehouseListView.as_view(), name="warehouse_list"),
    path("warehouses/new/", views.WarehouseCreateView.as_view(), name="warehouse_create"),
    path("locations/new/", views.StockLocationCreateView.as_view(), name="location_create"),
    path("suppliers/", views.SupplierListView.as_view(), name="supplier_list"),
    path("suppliers/new/", views.SupplierCreateView.as_view(), name="supplier_create"),
    path("customers/", views.CustomerListView.as_view(), name="customer_list"),
    path("customers/new/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("purchase-orders/", views.PurchaseOrderListView.as_view(), name="purchase_order_list"),
    path("purchase-orders/new/", views.PurchaseOrderCreateView.as_view(), name="purchase_order_create"),
    path("purchase-orders/<int:pk>/receive/", views.PurchaseOrderReceiveView.as_view(), name="purchase_order_receive"),
    path("movements/", views.StockMovementListView.as_view(), name="movement_list"),
    path("documents/", views.InventoryDocumentListView.as_view(), name="document_list"),
    path("opening-stock/", views.OpeningStockView.as_view(), name="opening_stock"),
    path("purchase-receipts/new/", views.PurchaseReceiptView.as_view(), name="purchase_receipt"),
    path("sales-invoices/new/", views.SalesInvoiceView.as_view(), name="sales_invoice"),
    path("customer-returns/new/", views.CustomerReturnView.as_view(), name="customer_return"),
    path("supplier-returns/new/", views.SupplierReturnView.as_view(), name="supplier_return"),
    path("customer-payments/new/", views.CustomerPaymentView.as_view(), name="customer_payment"),
    path("supplier-payments/new/", views.SupplierPaymentView.as_view(), name="supplier_payment"),
    path("tax-remittances/new/", views.TaxRemittanceView.as_view(), name="tax_remittance"),
    path("adjustments/new/", views.InventoryAdjustmentView.as_view(), name="adjustment"),
    path("transfers/new/", views.StockTransferView.as_view(), name="transfer"),
]
