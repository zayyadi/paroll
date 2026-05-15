from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView

from accounting.models import Account
from company.utils import get_user_company
from inventory.forms import (
    CustomerForm,
    CustomerPaymentForm,
    CustomerReturnForm,
    InventoryAdjustmentForm,
    InventoryCategoryForm,
    InventoryItemForm,
    OpeningStockForm,
    PurchaseOrderForm,
    PurchaseOrderReceiveForm,
    PurchaseReceiptForm,
    SalesInvoiceForm,
    StockLocationForm,
    StockTransferForm,
    SupplierForm,
    SupplierPaymentForm,
    SupplierReturnForm,
    TaxRemittanceForm,
    UnitOfMeasureForm,
    WarehouseForm,
)
from inventory.models import (
    Customer,
    InventoryCategory,
    InventoryDocument,
    InventoryItem,
    PurchaseOrder,
    StockLocation,
    StockMovement,
    Supplier,
    Warehouse,
)
from inventory.models import UnitOfMeasure
from inventory.services import (
    create_purchase_order,
    DEFAULT_POSTING_ACCOUNTS,
    ensure_default_posting_accounts,
    get_average_unit_cost,
    get_inventory_value,
    get_stock_on_hand,
    post_inventory_adjustment,
    post_customer_payment,
    post_customer_return,
    post_opening_stock,
    post_purchase_receipt,
    post_sales_invoice,
    post_supplier_payment,
    post_supplier_return,
    post_tax_remittance,
    post_stock_transfer,
    receive_purchase_order,
)


class InventoryCompanyMixin(LoginRequiredMixin):
    page_title = "Inventory"

    def dispatch(self, request, *args, **kwargs):
        self.company = get_user_company(request.user)
        if self.company is None:
            messages.error(request, "Select or create a company before using inventory.")
            return redirect("payroll:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(company=self.company)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "company": self.company,
                "page_title": self.page_title,
            }
        )
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = self.company
        return kwargs


class InventoryDashboardView(InventoryCompanyMixin, TemplateView):
    template_name = "inventory/dashboard.html"
    page_title = "Inventory Dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = list(
            InventoryItem.objects.filter(company=self.company, is_active=True).select_related(
                "category", "base_unit"
            )
        )
        low_stock_items = [
            item for item in items if item.reorder_point and get_stock_on_hand(item) <= item.reorder_point
        ]
        context.update(
            {
                "item_count": len(items),
                "warehouse_count": Warehouse.objects.filter(company=self.company, is_active=True).count(),
                "location_count": StockLocation.objects.filter(company=self.company, is_active=True).count(),
                "document_count": InventoryDocument.objects.filter(company=self.company).count(),
                "open_purchase_order_count": PurchaseOrder.objects.filter(
                    company=self.company,
                    status__in=[
                        PurchaseOrder.Status.ORDERED,
                        PurchaseOrder.Status.PARTIALLY_RECEIVED,
                    ],
                ).count(),
                "supplier_count": Supplier.objects.filter(company=self.company, is_active=True).count(),
                "customer_count": Customer.objects.filter(company=self.company, is_active=True).count(),
                "low_stock_items": low_stock_items[:8],
                "recent_movements": StockMovement.objects.filter(company=self.company)
                .select_related("item", "location", "location__warehouse")
                .order_by("-movement_date", "-created_at")[:8],
            }
        )
        return context


class PostingAccountSetupView(InventoryCompanyMixin, TemplateView):
    template_name = "inventory/posting_account_setup.html"
    page_title = "Posting Account Setup"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_accounts = Account.objects.filter(company=self.company).order_by(
            "account_number", "name"
        )
        accounts_by_number = {
            account.account_number: account
            for account in company_accounts
            if account.account_number
        }
        recommendations = []
        for spec in DEFAULT_POSTING_ACCOUNTS:
            recommendations.append(
                {
                    **spec,
                    "account": accounts_by_number.get(spec["account_number"]),
                }
            )
        context.update(
            {
                "recommendations": recommendations,
                "account_count": company_accounts.count(),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        result = ensure_default_posting_accounts(self.company)
        created_count = len(result["created"])
        if created_count:
            messages.success(
                request,
                f"Created {created_count} recommended posting accounts.",
            )
        else:
            messages.info(request, "All recommended posting accounts already exist.")
        return redirect("inventory:posting_account_setup")


class UnitOfMeasureCreateView(InventoryCompanyMixin, CreateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:item_create")
    page_title = "New Unit"

    def form_valid(self, form):
        messages.success(self.request, "Unit created.")
        return super().form_valid(form)


class InventoryCategoryListView(InventoryCompanyMixin, ListView):
    model = InventoryCategory
    template_name = "inventory/category_list.html"
    context_object_name = "categories"
    page_title = "Categories"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "inventory_account",
            "opening_balance_equity_account",
            "adjustment_gain_account",
            "shrinkage_expense_account",
        )


class InventoryCategoryCreateView(InventoryCompanyMixin, CreateView):
    model = InventoryCategory
    form_class = InventoryCategoryForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:category_list")
    page_title = "New Category"

    def form_valid(self, form):
        messages.success(self.request, "Inventory category created.")
        return super().form_valid(form)


class InventoryItemListView(InventoryCompanyMixin, ListView):
    model = InventoryItem
    template_name = "inventory/item_list.html"
    context_object_name = "items"
    paginate_by = 25
    page_title = "Items"

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("category", "base_unit")
            .order_by("sku", "name")
        )
        search = self.request.GET.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search) | queryset.filter(sku__icontains=search)
        return queryset


class InventoryItemCreateView(InventoryCompanyMixin, CreateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:item_list")
    page_title = "New Item"

    def form_valid(self, form):
        messages.success(self.request, "Inventory item created.")
        return super().form_valid(form)


class InventoryItemDetailView(InventoryCompanyMixin, DetailView):
    model = InventoryItem
    template_name = "inventory/item_detail.html"
    context_object_name = "item"
    page_title = "Item Detail"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        item = self.object
        context.update(
            {
                "stock_on_hand": get_stock_on_hand(item),
                "inventory_value": get_inventory_value(item),
                "average_unit_cost": get_average_unit_cost(item),
                "movements": item.stock_movements.select_related("location", "location__warehouse").order_by(
                    "-movement_date", "-created_at"
                )[:20],
            }
        )
        return context


class WarehouseListView(InventoryCompanyMixin, ListView):
    model = Warehouse
    template_name = "inventory/warehouse_list.html"
    context_object_name = "warehouses"
    page_title = "Warehouses"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("locations")


class WarehouseCreateView(InventoryCompanyMixin, CreateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:warehouse_list")
    page_title = "New Warehouse"

    def form_valid(self, form):
        messages.success(self.request, "Warehouse created.")
        return super().form_valid(form)


class SupplierListView(InventoryCompanyMixin, ListView):
    model = Supplier
    template_name = "inventory/supplier_list.html"
    context_object_name = "suppliers"
    page_title = "Suppliers"

    def get_queryset(self):
        return super().get_queryset().select_related("payable_account")


class SupplierCreateView(InventoryCompanyMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:supplier_list")
    page_title = "New Supplier"

    def form_valid(self, form):
        messages.success(self.request, "Supplier created.")
        return super().form_valid(form)


class CustomerListView(InventoryCompanyMixin, ListView):
    model = Customer
    template_name = "inventory/customer_list.html"
    context_object_name = "customers"
    page_title = "Customers"

    def get_queryset(self):
        return super().get_queryset().select_related("receivable_account", "wht_receivable_account")


class CustomerCreateView(InventoryCompanyMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:customer_list")
    page_title = "New Customer"

    def form_valid(self, form):
        messages.success(self.request, "Customer created.")
        return super().form_valid(form)


class PurchaseOrderListView(InventoryCompanyMixin, ListView):
    model = PurchaseOrder
    template_name = "inventory/purchase_order_list.html"
    context_object_name = "purchase_orders"
    page_title = "Purchase Orders"

    def get_queryset(self):
        return super().get_queryset().select_related("supplier").prefetch_related("lines__item")


class PurchaseOrderCreateView(InventoryCompanyMixin, FormView):
    form_class = PurchaseOrderForm
    template_name = "inventory/action_form.html"
    success_url = reverse_lazy("inventory:purchase_order_list")
    page_title = "New Purchase Order"
    action_label = "Create Order"

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            create_purchase_order(
                company=self.company,
                supplier=data["supplier"],
                lines=[
                    {
                        "item": data["item"],
                        "quantity": data["quantity"],
                        "unit_cost": data["unit_cost"],
                    }
                ],
                order_date=data.get("posting_date"),
                expected_date=data.get("expected_date"),
                reference=data.get("reference", ""),
                notes=data.get("notes", ""),
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Purchase order created.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action_label"] = self.action_label
        return context


class PurchaseOrderReceiveView(InventoryCompanyMixin, FormView):
    form_class = PurchaseOrderReceiveForm
    template_name = "inventory/action_form.html"
    success_url = reverse_lazy("inventory:purchase_order_list")
    page_title = "Receive Purchase Order"
    action_label = "Receive"

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        return response

    def get_purchase_order(self):
        try:
            return PurchaseOrder.objects.get(company=self.company, pk=self.kwargs["pk"])
        except PurchaseOrder.DoesNotExist as exc:
            raise Http404("Purchase order not found") from exc

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["purchase_order"] = self.get_purchase_order()
        return kwargs

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            receive_purchase_order(
                company=self.company,
                purchase_order=self.get_purchase_order(),
                location=data["location"],
                lines=[
                    {
                        "purchase_order_line": data["purchase_order_line"],
                        "quantity": data["quantity"],
                    }
                ],
                posting_date=data.get("posting_date"),
                reference=data.get("reference", ""),
                reason=data.get("reason") or "Purchase order receipt",
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Purchase order received.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["purchase_order"] = self.get_purchase_order()
        context["action_label"] = self.action_label
        return context


class StockLocationCreateView(InventoryCompanyMixin, CreateView):
    model = StockLocation
    form_class = StockLocationForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:warehouse_list")
    page_title = "New Location"

    def form_valid(self, form):
        messages.success(self.request, "Stock location created.")
        return super().form_valid(form)


class StockMovementListView(InventoryCompanyMixin, ListView):
    model = StockMovement
    template_name = "inventory/movement_list.html"
    context_object_name = "movements"
    paginate_by = 50
    page_title = "Stock Movements"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("item", "location", "location__warehouse", "document")
            .order_by("-movement_date", "-created_at")
        )


class InventoryDocumentListView(InventoryCompanyMixin, ListView):
    model = InventoryDocument
    template_name = "inventory/document_list.html"
    context_object_name = "documents"
    paginate_by = 50
    page_title = "Inventory Documents"

    def get_queryset(self):
        return super().get_queryset().select_related("journal").order_by("-document_date", "-created_at")


class InventoryActionView(InventoryCompanyMixin, FormView):
    template_name = "inventory/action_form.html"
    success_url = reverse_lazy("inventory:movement_list")
    action_label = "Post"

    def form_valid(self, form):
        try:
            document = self.post_document(form.cleaned_data)
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, f"{document.get_document_type_display()} posted.")
        return super().form_valid(form)

    def post_document(self, cleaned_data):
        raise NotImplementedError

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action_label"] = self.action_label
        return context


class OpeningStockView(InventoryActionView):
    form_class = OpeningStockForm
    page_title = "Opening Stock"
    action_label = "Post Opening Stock"

    def post_document(self, cleaned_data):
        return post_opening_stock(
            company=self.company,
            item=cleaned_data["item"],
            location=cleaned_data["location"],
            quantity=cleaned_data["quantity"],
            unit_cost=cleaned_data["unit_cost"],
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Opening stock",
        )


class PurchaseReceiptView(InventoryActionView):
    form_class = PurchaseReceiptForm
    page_title = "Purchase Receipt"
    action_label = "Post Receipt"

    def post_document(self, cleaned_data):
        return post_purchase_receipt(
            company=self.company,
            supplier=cleaned_data["supplier"],
            location=cleaned_data["location"],
            lines=[
                {
                    "item": cleaned_data["item"],
                    "quantity": cleaned_data["quantity"],
                    "unit_cost": cleaned_data["unit_cost"],
                    "vat_rate": cleaned_data.get("vat_rate") or 0,
                    "wht_rate": cleaned_data.get("wht_rate") or 0,
                }
            ],
            vat_input_account=cleaned_data.get("vat_input_account"),
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Purchase receipt",
        )


class SalesInvoiceView(InventoryActionView):
    form_class = SalesInvoiceForm
    page_title = "Sales Invoice"
    action_label = "Post Invoice"

    def post_document(self, cleaned_data):
        return post_sales_invoice(
            company=self.company,
            customer=cleaned_data["customer"],
            location=cleaned_data["location"],
            lines=[
                {
                    "item": cleaned_data["item"],
                    "quantity": cleaned_data["quantity"],
                    "unit_price": cleaned_data["unit_price"],
                    "vat_rate": cleaned_data.get("vat_rate") or 0,
                    "wht_rate": cleaned_data.get("wht_rate") or 0,
                }
            ],
            vat_output_account=cleaned_data.get("vat_output_account"),
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Sales invoice",
        )


class CustomerReturnView(InventoryActionView):
    form_class = CustomerReturnForm
    page_title = "Customer Return"
    action_label = "Post Credit Note"

    def post_document(self, cleaned_data):
        return post_customer_return(
            company=self.company,
            customer=cleaned_data["customer"],
            location=cleaned_data["location"],
            lines=[
                {
                    "item": cleaned_data["item"],
                    "quantity": cleaned_data["quantity"],
                    "unit_price": cleaned_data["unit_price"],
                    "unit_cost": cleaned_data["unit_cost"],
                    "vat_rate": cleaned_data.get("vat_rate") or 0,
                    "wht_rate": cleaned_data.get("wht_rate") or 0,
                }
            ],
            vat_output_account=cleaned_data.get("vat_output_account"),
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Customer return",
        )


class SupplierReturnView(InventoryActionView):
    form_class = SupplierReturnForm
    page_title = "Supplier Return"
    action_label = "Post Debit Note"

    def post_document(self, cleaned_data):
        return post_supplier_return(
            company=self.company,
            supplier=cleaned_data["supplier"],
            location=cleaned_data["location"],
            lines=[
                {
                    "item": cleaned_data["item"],
                    "quantity": cleaned_data["quantity"],
                    "unit_cost": cleaned_data["unit_cost"],
                    "vat_rate": cleaned_data.get("vat_rate") or 0,
                    "wht_rate": cleaned_data.get("wht_rate") or 0,
                }
            ],
            vat_input_account=cleaned_data.get("vat_input_account"),
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Supplier return",
        )


class CustomerPaymentView(InventoryActionView):
    form_class = CustomerPaymentForm
    page_title = "Customer Payment"
    action_label = "Post Payment"

    def post_document(self, cleaned_data):
        return post_customer_payment(
            company=self.company,
            customer=cleaned_data["customer"],
            cash_account=cleaned_data["cash_account"],
            amount=cleaned_data["amount"],
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Customer payment",
        )


class SupplierPaymentView(InventoryActionView):
    form_class = SupplierPaymentForm
    page_title = "Supplier Payment"
    action_label = "Post Payment"

    def post_document(self, cleaned_data):
        return post_supplier_payment(
            company=self.company,
            supplier=cleaned_data["supplier"],
            cash_account=cleaned_data["cash_account"],
            amount=cleaned_data["amount"],
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Supplier payment",
        )


class TaxRemittanceView(InventoryActionView):
    form_class = TaxRemittanceForm
    page_title = "Tax Remittance"
    action_label = "Post Remittance"

    def post_document(self, cleaned_data):
        return post_tax_remittance(
            company=self.company,
            cash_account=cleaned_data["cash_account"],
            vat_output_account=cleaned_data.get("vat_output_account"),
            vat_input_account=cleaned_data.get("vat_input_account"),
            wht_payable_account=cleaned_data.get("wht_payable_account"),
            vat_output_amount=cleaned_data.get("vat_output_amount") or 0,
            vat_input_amount=cleaned_data.get("vat_input_amount") or 0,
            wht_amount=cleaned_data.get("wht_amount") or 0,
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Tax remittance",
        )


class InventoryAdjustmentView(InventoryActionView):
    form_class = InventoryAdjustmentForm
    page_title = "Inventory Adjustment"
    action_label = "Post Adjustment"

    def post_document(self, cleaned_data):
        return post_inventory_adjustment(
            company=self.company,
            item=cleaned_data["item"],
            location=cleaned_data["location"],
            quantity_delta=cleaned_data["quantity_delta"],
            unit_cost=cleaned_data.get("unit_cost"),
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Inventory adjustment",
        )


class StockTransferView(InventoryActionView):
    form_class = StockTransferForm
    page_title = "Stock Transfer"
    action_label = "Post Transfer"

    def post_document(self, cleaned_data):
        return post_stock_transfer(
            company=self.company,
            item=cleaned_data["item"],
            from_location=cleaned_data["from_location"],
            to_location=cleaned_data["to_location"],
            quantity=cleaned_data["quantity"],
            posting_date=cleaned_data.get("posting_date"),
            reference=cleaned_data.get("reference", ""),
            reason=cleaned_data.get("reason") or "Stock transfer",
        )
