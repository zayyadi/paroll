from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView
from decimal import Decimal
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Sum, Value, When
from django.db.models.functions import Coalesce

from accounting.models import Account
from company.utils import get_user_company
from inventory.forms import (
    CustomerForm,
    CustomerPaymentAllocationForm,
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
    SupplierPaymentAllocationForm,
    SupplierPaymentForm,
    SupplierReturnForm,
    TaxRemittanceForm,
    UnitOfMeasureForm,
    WarehouseForm,
    StockCountCreateForm,
    StockCountLineForm,
    SalesOrderForm,
    VendorBillForm,
    LandedCostForm,
    InventoryDocumentReversalForm,
)
from inventory.models import (
    Customer,
    CustomerPayment,
    InventoryCategory,
    InventoryDocument,
    InventoryItem,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    SalesInvoice,
    StockLocation,
    StockMovement,
    Supplier,
    SupplierPayment,
    Warehouse,
    StockCount,
    StockCountLine,
    SalesOrder,
    SalesOrderLine,
    VendorBill,
    VendorBillLine,
    LandedCost,
    LandedCostAllocation,
    UnitOfMeasure,
    InventoryValuationLayer,
)
from inventory.models import UnitOfMeasure
from inventory.services import (
    allocate_customer_payment,
    allocate_supplier_payment,
    create_sales_order,
    create_purchase_order,
    DEFAULT_POSTING_ACCOUNTS,
    ensure_default_posting_accounts,
    get_average_unit_cost,
    get_customer_payment_unapplied_amount,
    get_inventory_value,
    get_stock_on_hand,
    get_supplier_payment_unapplied_amount,
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
    invoice_total,
    ship_sales_order,
)


def _posted_line_indexes(post_data):
    indexes = set()
    for key in post_data:
        if not key.startswith("lines-"):
            continue
        parts = key.split("-", 2)
        if len(parts) == 3 and parts[1].isdigit():
            indexes.add(int(parts[1]))
    if indexes:
        return sorted(indexes)
    try:
        return list(range(int(post_data.get("line_count", 0))))
    except (TypeError, ValueError):
        return []


def _line_decimal(value, default="0"):
    return Decimal(value or default)


def _model_id(value):
    return str(value or "").replace(",", "")


def _purchase_order_lines_from_post(post_data, company):
    lines = []
    for index in _posted_line_indexes(post_data):
        item_id = post_data.get(f"lines-{index}-item")
        quantity = post_data.get(f"lines-{index}-quantity")
        unit_cost = post_data.get(f"lines-{index}-unit_cost")
        if not item_id and not quantity and not unit_cost:
            continue
        if not item_id or not quantity or not unit_cost:
            raise ValueError("Each purchase order line needs an item, quantity, and unit cost.")
        try:
            item = InventoryItem.objects.get(company=company, pk=_model_id(item_id), is_active=True)
        except InventoryItem.DoesNotExist as exc:
            raise ValueError("Purchase order line item is invalid.") from exc
        lines.append(
            {
                "item": item,
                "quantity": _line_decimal(quantity),
                "unit_cost": _line_decimal(unit_cost),
                "vat_rate": _line_decimal(post_data.get(f"lines-{index}-vat_rate")),
            }
        )
    return lines


def _sales_order_lines_from_post(post_data, company):
    lines = []
    for index in _posted_line_indexes(post_data):
        item_id = post_data.get(f"lines-{index}-item")
        quantity = post_data.get(f"lines-{index}-quantity")
        unit_price = post_data.get(f"lines-{index}-unit_price")
        if not item_id and not quantity and not unit_price:
            continue
        if not item_id or not quantity or not unit_price:
            raise ValueError("Each sales order line needs an item, quantity, and unit price.")
        try:
            item = InventoryItem.objects.get(company=company, pk=_model_id(item_id), is_active=True)
        except InventoryItem.DoesNotExist as exc:
            raise ValueError("Sales order line item is invalid.") from exc
        lines.append(
            {
                "item": item,
                "quantity": _line_decimal(quantity),
                "unit_price": _line_decimal(unit_price),
                "vat_rate": _line_decimal(post_data.get(f"lines-{index}-vat_rate")),
            }
        )
    return lines


def _purchase_order_receive_lines_from_post(post_data, purchase_order):
    lines = []
    for index in _posted_line_indexes(post_data):
        line_id = post_data.get(f"lines-{index}-purchase_order_line")
        quantity = post_data.get(f"lines-{index}-quantity")
        if not line_id and not quantity:
            continue
        if not line_id or not quantity:
            raise ValueError("Each receipt line needs a purchase order line and quantity.")
        try:
            po_line = purchase_order.lines.get(pk=_model_id(line_id))
        except PurchaseOrderLine.DoesNotExist as exc:
            raise ValueError("Receipt line is invalid for this purchase order.") from exc
        if _line_decimal(quantity) <= 0:
            continue
        lines.append(
            {
                "purchase_order_line": po_line,
                "quantity": _line_decimal(quantity),
                "vat_rate": _line_decimal(post_data.get(f"lines-{index}-vat_rate")),
            }
        )
    return lines


def _sales_order_reference(sales_order):
    return f"SO-{sales_order.reference or sales_order.pk}"


def _sales_order_invoice_exists(company, sales_order):
    references = {_sales_order_reference(sales_order)}
    if sales_order.reference:
        references.add(sales_order.reference)
    return SalesInvoice.objects.filter(
        company=company,
        document__reference__in=references,
    ).exists()


def _location_for_sales_order(company, sales_order):
    lines = list(sales_order.lines.select_related("item"))
    locations = StockLocation.objects.filter(company=company, is_active=True).select_related(
        "warehouse"
    )
    for location in locations:
        can_fulfill = True
        for line in lines:
            quantity = line.remaining_quantity if line.remaining_quantity > 0 else line.quantity
            if line.item.allow_negative_stock:
                continue
            if get_stock_on_hand(line.item, location) < quantity:
                can_fulfill = False
                break
        if can_fulfill:
            return location
    raise ValueError("No active stock location has enough stock to fulfil this sales order.")


def _sales_order_invoice_lines(sales_order, *, use_shipped_quantity=False):
    lines = []
    for line in sales_order.lines.select_related("item"):
        quantity = line.shipped_quantity if use_shipped_quantity else line.remaining_quantity
        if quantity <= 0:
            quantity = line.quantity
        lines.append(
            {
                "sales_order_line": line,
                "quantity": quantity,
            }
        )
    return lines


def _post_legacy_sales_order_invoice(company, sales_order):
    location = _location_for_sales_order(company, sales_order)
    document = post_sales_invoice(
        company=company,
        customer=sales_order.customer,
        location=location,
        lines=[
            {
                "item": line.item,
                "quantity": line.shipped_quantity if line.shipped_quantity > 0 else line.quantity,
                "unit_price": line.unit_price,
                "vat_rate": line.vat_rate,
            }
            for line in sales_order.lines.select_related("item")
        ],
        posting_date=timezone.now().date(),
        reference=_sales_order_reference(sales_order),
        reason=f"Sales order invoice for {sales_order.reference or sales_order.pk}",
    )
    return document


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
        accounts_by_name = {account.name: account for account in company_accounts}
        recommendations = []
        for spec in DEFAULT_POSTING_ACCOUNTS:
            recommendations.append(
                {
                    **spec,
                    "account": accounts_by_number.get(spec["account_number"])
                    or accounts_by_name.get(spec["name"]),
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
            .annotate(
                stock_quantity=Coalesce(
                    Sum("stock_movements__quantity"),
                    Value(Decimal("0.0000")),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                ),
                stock_value=Coalesce(
                    Sum("stock_movements__total_cost"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
            )
            .annotate(
                average_cost=Case(
                    When(
                        stock_quantity__gt=0,
                        then=ExpressionWrapper(
                            F("stock_value") / F("stock_quantity"),
                            output_field=DecimalField(max_digits=18, decimal_places=4),
                        ),
                    ),
                    default=Value(Decimal("0.0000")),
                    output_field=DecimalField(max_digits=18, decimal_places=4),
                )
            )
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


class SupplierDetailView(InventoryCompanyMixin, DetailView):
    model = Supplier
    template_name = "inventory/supplier_detail.html"
    context_object_name = "supplier"
    page_title = "Supplier Detail"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        supplier = self.object
        from inventory.services import get_accounts_payable_aging, get_supplier_ledger

        aging = get_accounts_payable_aging(supplier.company)
        supplier_aging = [r for r in aging if r["supplier"].id == supplier.id]
        total_outstanding = sum(r["outstanding"] for r in supplier_aging)

        receipts = PurchaseReceipt.objects.filter(
            supplier=supplier,
        ).select_related("document").order_by("-document__document_date", "-created_at")[:30]

        payments = SupplierPayment.objects.filter(
            supplier=supplier,
        ).select_related("document", "receipt").annotate(
            allocated_amount=Coalesce(
                Sum("allocations__amount"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ).annotate(
            unapplied_amount=ExpressionWrapper(
                F("amount") - F("allocated_amount"),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ).order_by("-payment_date", "-created_at")[:20]

        balance = supplier.payable_account.get_balance() if supplier.payable_account else Decimal("0.00")

        context.update({
            "aging": supplier_aging,
            "total_outstanding": total_outstanding,
            "receipts": receipts,
            "payments": payments,
            "balance": balance,
            "ledger_rows": get_supplier_ledger(supplier),
        })
        return context


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


class CustomerDetailView(InventoryCompanyMixin, DetailView):
    model = Customer
    template_name = "inventory/customer_detail.html"
    context_object_name = "customer"
    page_title = "Customer Detail"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object
        from inventory.services import get_customer_ledger, get_customer_statement

        statement = get_customer_statement(customer)
        total_outstanding = sum(r["outstanding"] for r in statement)

        invoices = SalesInvoice.objects.filter(
            customer=customer,
        ).select_related("document").order_by("-document__document_date", "-created_at")[:30]

        payments = CustomerPayment.objects.filter(
            customer=customer,
        ).select_related("document", "invoice").annotate(
            allocated_amount=Coalesce(
                Sum("allocations__amount"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ).annotate(
            unapplied_amount=ExpressionWrapper(
                F("amount") - F("allocated_amount"),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            )
        ).order_by("-payment_date", "-created_at")[:20]

        balance = customer.receivable_account.get_balance() if customer.receivable_account else Decimal("0.00")

        context.update({
            "aging": statement,
            "total_outstanding": total_outstanding,
            "invoices": invoices,
            "payments": payments,
            "balance": balance,
            "ledger_rows": get_customer_ledger(customer),
        })
        return context


class PurchaseOrderListView(InventoryCompanyMixin, ListView):
    model = PurchaseOrder
    template_name = "inventory/purchase_order_list.html"
    context_object_name = "purchase_orders"
    page_title = "Purchase Orders"

    def get_queryset(self):
        return super().get_queryset().select_related("supplier").prefetch_related("lines__item")


class PurchaseOrderCreateView(InventoryCompanyMixin, FormView):
    form_class = PurchaseOrderForm
    template_name = "inventory/order_form.html"
    success_url = reverse_lazy("inventory:purchase_order_list")
    page_title = "New Purchase Order"
    action_label = "Create Order"
    line_amount_field = "unit_cost"
    party_field = "supplier"
    party_label = "Supplier"
    item_amount_label = "Unit Cost"
    order_kind = "purchase"

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            lines = _purchase_order_lines_from_post(self.request.POST, self.company)
            if not lines and data.get("item"):
                lines = [
                    {
                        "item": data["item"],
                        "quantity": data["quantity"],
                        "unit_cost": data["unit_cost"],
                        "vat_rate": data.get("vat_rate") or 0,
                    }
                ]
            create_purchase_order(
                company=self.company,
                supplier=data["supplier"],
                lines=lines,
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
        context["order_kind"] = self.order_kind
        context["party_field"] = self.party_field
        context["party_label"] = self.party_label
        context["line_amount_field"] = self.line_amount_field
        context["item_amount_label"] = self.item_amount_label
        context["items"] = InventoryItem.objects.filter(
            company=self.company, is_active=True
        ).order_by("sku", "name")
        return context


class PurchaseOrderReceiveView(InventoryCompanyMixin, FormView):
    form_class = PurchaseOrderReceiveForm
    template_name = "inventory/purchase_order_receive_form.html"
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
        purchase_order = self.get_purchase_order()
        try:
            lines = _purchase_order_receive_lines_from_post(self.request.POST, purchase_order)
            if not lines and data.get("purchase_order_line"):
                lines = [
                    {
                        "purchase_order_line": data["purchase_order_line"],
                        "quantity": data["quantity"],
                    }
                ]
            receive_purchase_order(
                company=self.company,
                purchase_order=purchase_order,
                location=data["location"],
                lines=lines,
                vat_input_account=data.get("vat_input_account"),
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
        purchase_order = self.get_purchase_order()
        context["purchase_order"] = purchase_order
        context["receivable_lines"] = purchase_order.lines.filter(
            received_quantity__lt=F("quantity")
        ).select_related("item")
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


class SalesInvoiceListView(InventoryCompanyMixin, ListView):
    model = SalesInvoice
    template_name = "inventory/sales_invoice_list.html"
    context_object_name = "sales_invoices"
    paginate_by = 50
    page_title = "Sales Invoices"

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("customer", "document")
            .order_by("-document__document_date", "-created_at")
        )
        status = self.request.GET.get("status")
        if status == "open":
            return queryset.filter(payment_status__in=["UNPAID", "PARTIAL"]).exclude(
                workflow_status="VOID"
            )
        if status == "pending":
            return queryset.exclude(
                document__status__in=[
                    InventoryDocument.Status.POSTED,
                    InventoryDocument.Status.CANCELLED,
                ]
            ).exclude(workflow_status="VOID")
        if status == "posted":
            return queryset.filter(document__status=InventoryDocument.Status.POSTED)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_status"] = self.request.GET.get("status", "all")
        return context


class SalesInvoiceDetailView(InventoryCompanyMixin, DetailView):
    model = SalesInvoice
    template_name = "inventory/sales_invoice_detail.html"
    context_object_name = "invoice"
    page_title = "Sales Invoice"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("customer", "document")
            .prefetch_related("lines__item", "lines__location", "lines__location__warehouse")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related(
            "item", "location", "location__warehouse"
        )
        context["invoice_total"] = invoice_total(self.object)
        return context


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


class CustomerPaymentAllocateView(InventoryCompanyMixin, FormView):
    form_class = CustomerPaymentAllocationForm
    template_name = "inventory/action_form.html"
    page_title = "Apply Customer Payment"
    action_label = "Apply Payment"

    def get_payment(self):
        try:
            return CustomerPayment.objects.select_related("customer", "document").get(
                company=self.company,
                pk=self.kwargs["pk"],
            )
        except CustomerPayment.DoesNotExist as exc:
            raise Http404("Customer payment not found") from exc

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["payment"] = self.get_payment()
        return kwargs

    def form_valid(self, form):
        payment = self.get_payment()
        try:
            allocate_customer_payment(
                payment=payment,
                invoice=form.cleaned_data["invoice"],
                amount=form.cleaned_data["amount"],
                allocation_date=form.cleaned_data.get("allocation_date"),
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Customer payment applied to invoice.")
        return redirect("inventory:customer_detail", pk=payment.customer_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payment = self.get_payment()
        context["action_label"] = self.action_label
        context["payment"] = payment
        context["unapplied_amount"] = get_customer_payment_unapplied_amount(payment)
        return context


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


class SupplierPaymentAllocateView(InventoryCompanyMixin, FormView):
    form_class = SupplierPaymentAllocationForm
    template_name = "inventory/action_form.html"
    page_title = "Apply Supplier Payment"
    action_label = "Apply Payment"

    def get_payment(self):
        try:
            return SupplierPayment.objects.select_related("supplier", "document").get(
                company=self.company,
                pk=self.kwargs["pk"],
            )
        except SupplierPayment.DoesNotExist as exc:
            raise Http404("Supplier payment not found") from exc

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["payment"] = self.get_payment()
        return kwargs

    def form_valid(self, form):
        payment = self.get_payment()
        try:
            allocate_supplier_payment(
                payment=payment,
                receipt=form.cleaned_data["receipt"],
                amount=form.cleaned_data["amount"],
                allocation_date=form.cleaned_data.get("allocation_date"),
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Supplier payment applied to purchase receipt.")
        return redirect("inventory:supplier_detail", pk=payment.supplier_id)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payment = self.get_payment()
        context["action_label"] = self.action_label
        context["payment"] = payment
        context["unapplied_amount"] = get_supplier_payment_unapplied_amount(payment)
        return context


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


# ── Phase 1: CRUD Completion (Update views) ──


class InventoryItemUpdateView(InventoryCompanyMixin, UpdateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:item_list")
    page_title = "Update Item"


class InventoryCategoryUpdateView(InventoryCompanyMixin, UpdateView):
    model = InventoryCategory
    form_class = InventoryCategoryForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:category_list")
    page_title = "Update Category"


class WarehouseUpdateView(InventoryCompanyMixin, UpdateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:warehouse_list")
    page_title = "Update Warehouse"


class StockLocationListView(InventoryCompanyMixin, ListView):
    model = StockLocation
    template_name = "inventory/location_list.html"
    context_object_name = "locations"
    page_title = "Stock Locations"

    def get_queryset(self):
        return super().get_queryset().select_related("warehouse")


class StockLocationUpdateView(InventoryCompanyMixin, UpdateView):
    model = StockLocation
    form_class = StockLocationForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:warehouse_list")
    page_title = "Update Location"


class SupplierUpdateView(InventoryCompanyMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:supplier_list")
    page_title = "Update Supplier"


class CustomerUpdateView(InventoryCompanyMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:customer_list")
    page_title = "Update Customer"


class UnitOfMeasureListView(InventoryCompanyMixin, ListView):
    model = UnitOfMeasure
    template_name = "inventory/unit_list.html"
    context_object_name = "units"
    page_title = "Units of Measure"


class UnitOfMeasureUpdateView(InventoryCompanyMixin, UpdateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = "inventory/form.html"
    success_url = reverse_lazy("inventory:unit_list")
    page_title = "Update Unit"


# ── Phase 2: Stock Count Workflow ──


class StockCountListView(InventoryCompanyMixin, ListView):
    model = StockCount
    template_name = "inventory/stock_count_list.html"
    context_object_name = "stock_counts"
    page_title = "Stock Counts"

    def get_queryset(self):
        return super().get_queryset().select_related("location", "location__warehouse")


class StockCountCreateView(InventoryCompanyMixin, FormView):
    form_class = StockCountCreateForm
    template_name = "inventory/action_form.html"
    success_url = reverse_lazy("inventory:stock_count_list")
    page_title = "New Stock Count"
    action_label = "Create Count"

    def form_valid(self, form):
        data = form.cleaned_data
        location = data["location"]
        stock_count = StockCount.objects.create(
            company=self.company,
            location=location,
            count_date=data.get("posting_date") or timezone.now().date(),
            reason=data.get("reason") or "Stock count",
            variance_threshold=data.get("variance_threshold") or 0,
        )
        movements = StockMovement.objects.filter(
            company=self.company, location=location
        ).values("item").annotate(total_qty=Sum("quantity"))
        for mv in movements:
            if mv["total_qty"] and mv["total_qty"] > 0:
                StockCountLine.objects.create(
                    stock_count=stock_count,
                    item_id=mv["item"],
                    system_quantity=mv["total_qty"],
                    counted_quantity=mv["total_qty"],
                )
        messages.success(self.request, f"Stock count created with {stock_count.lines.count()} items.")
        return super().form_valid(form)


class StockCountDetailView(InventoryCompanyMixin, DetailView):
    model = StockCount
    template_name = "inventory/stock_count_detail.html"
    context_object_name = "stock_count"
    page_title = "Stock Count Detail"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lines = self.object.lines.select_related("item").order_by("item__sku")
        context["lines"] = lines
        context["variances"] = [l for l in lines if l.variance_quantity != 0]
        return context


class StockCountLineUpdateView(InventoryCompanyMixin, FormView):
    template_name = "inventory/action_form.html"
    success_url = ""
    page_title = "Update Count Line"
    action_label = "Save"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["data"] = self.request.POST or None
        kwargs["files"] = self.request.FILES or None
        return kwargs

    def get_success_url(self):
        return reverse_lazy("inventory:stock_count_detail", kwargs={"pk": self.kwargs["count_pk"]})

    def form_valid(self, form):
        count = StockCount.objects.get(company=self.company, pk=self.kwargs["count_pk"])
        line = StockCountLine.objects.get(stock_count=count, pk=self.kwargs["line_pk"])
        line.counted_quantity = form.cleaned_data["counted_quantity"]
        line.variance_reason = form.cleaned_data.get("variance_reason") or "OTHER"
        line.save(update_fields=["counted_quantity", "variance_reason", "updated_at"])
        messages.success(self.request, "Count line updated.")
        return super().form_valid(form)


class StockCountApproveView(InventoryCompanyMixin, TemplateView):
    def post(self, request, *args, **kwargs):
        from inventory.services import approve_inventory_document
        count = StockCount.objects.get(company=self.company, pk=kwargs["pk"])
        approve_inventory_document(count, user=request.user)
        messages.success(request, "Stock count approved.")
        return redirect("inventory:stock_count_detail", pk=kwargs["pk"])


class StockCountPostView(InventoryCompanyMixin, TemplateView):
    def post(self, request, *args, **kwargs):
        from inventory.services import post_stock_count_adjustments
        count = StockCount.objects.get(company=self.company, pk=kwargs["pk"])
        try:
            post_stock_count_adjustments(stock_count=count, user=request.user)
            messages.success(request, "Stock count adjustments posted.")
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect("inventory:stock_count_detail", pk=kwargs["pk"])


# ── Phase 3: Sales Order Lifecycle ──


class SalesOrderListView(InventoryCompanyMixin, ListView):
    model = SalesOrder
    template_name = "inventory/sales_order_list.html"
    context_object_name = "sales_orders"
    page_title = "Sales Orders"

    def get_queryset(self):
        return super().get_queryset().select_related("customer").prefetch_related("lines__item")


class SalesOrderCreateView(InventoryCompanyMixin, FormView):
    form_class = SalesOrderForm
    template_name = "inventory/order_form.html"
    success_url = reverse_lazy("inventory:sales_order_list")
    page_title = "New Sales Order"
    action_label = "Create Order"
    line_amount_field = "unit_price"
    party_field = "customer"
    party_label = "Customer"
    item_amount_label = "Unit Price"
    order_kind = "sales"

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            lines = _sales_order_lines_from_post(self.request.POST, self.company)
            if not lines and data.get("item"):
                line = {
                    "item": data["item"],
                    "quantity": data["quantity"],
                    "unit_price": data["unit_price"],
                    "vat_rate": data.get("vat_rate") or 0,
                }
                if data.get("location"):
                    line["location"] = data["location"]
                lines = [line]
            create_sales_order(
                company=self.company,
                customer=data["customer"],
                order_date=data.get("posting_date") or timezone.now().date(),
                expected_date=data.get("expected_date"),
                reference=data.get("reference", ""),
                notes=data.get("notes", ""),
                lines=lines,
                reserve_stock=False,
            )
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Sales order created.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action_label"] = self.action_label
        context["order_kind"] = self.order_kind
        context["party_field"] = self.party_field
        context["party_label"] = self.party_label
        context["line_amount_field"] = self.line_amount_field
        context["item_amount_label"] = self.item_amount_label
        context["items"] = InventoryItem.objects.filter(
            company=self.company, is_active=True
        ).order_by("sku", "name")
        return context


class SalesOrderDetailView(InventoryCompanyMixin, DetailView):
    model = SalesOrder
    template_name = "inventory/sales_order_detail.html"
    context_object_name = "order"
    page_title = "Sales Order Detail"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("item")
        context["sales_invoice_exists"] = _sales_order_invoice_exists(
            self.company, self.object
        )
        return context


class SalesOrderShipView(InventoryCompanyMixin, TemplateView):
    def post(self, request, *args, **kwargs):
        order = SalesOrder.objects.prefetch_related("lines__item").get(
            company=self.company, pk=kwargs["pk"]
        )
        if order.status not in [SalesOrder.Status.CONFIRMED, SalesOrder.Status.PARTIALLY_SHIPPED]:
            messages.error(request, "Order cannot be shipped in current status.")
            return redirect("inventory:sales_order_detail", pk=kwargs["pk"])
        try:
            ship_sales_order(
                company=self.company,
                sales_order=order,
                location=_location_for_sales_order(self.company, order),
                lines=_sales_order_invoice_lines(order),
                reference=_sales_order_reference(order),
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("inventory:sales_order_detail", pk=kwargs["pk"])
        messages.success(request, "Sales order shipped and invoice posted.")
        return redirect("inventory:sales_order_detail", pk=kwargs["pk"])


class SalesOrderInvoiceView(InventoryCompanyMixin, TemplateView):
    def post(self, request, *args, **kwargs):
        order = SalesOrder.objects.prefetch_related("lines__item").get(
            company=self.company, pk=kwargs["pk"]
        )
        if order.status not in [SalesOrder.Status.SHIPPED, SalesOrder.Status.INVOICED]:
            messages.error(request, "Order must be shipped before invoicing.")
            return redirect("inventory:sales_order_detail", pk=kwargs["pk"])
        if not _sales_order_invoice_exists(self.company, order):
            try:
                _post_legacy_sales_order_invoice(self.company, order)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("inventory:sales_order_detail", pk=kwargs["pk"])
        order.status = SalesOrder.Status.INVOICED
        order.save(update_fields=["status", "updated_at"])
        messages.success(request, "Sales order invoiced.")
        return redirect("inventory:sales_order_detail", pk=kwargs["pk"])


# ── Phase 4: Reports ──


class ReportStockOnHandView(InventoryCompanyMixin, TemplateView):
    template_name = "inventory/report_stock_on_hand.html"
    page_title = "Stock On Hand Report"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = InventoryItem.objects.filter(
            company=self.company, is_active=True
        ).select_related("category", "base_unit")
        report_data = []
        for item in items:
            movements = StockMovement.objects.filter(
                company=self.company, item=item
            )
            total_qty = movements.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            total_value = movements.aggregate(total=Sum("total_cost"))["total"] or Decimal("0")
            locations = (
                movements.values("location__warehouse__name", "location__name")
                .annotate(qty=Sum("quantity"), val=Sum("total_cost"))
                .filter(qty__gt=0)
            )
            if total_qty > 0:
                report_data.append({
                    "item": item,
                    "total_qty": total_qty,
                    "total_value": total_value,
                    "avg_cost": (total_value / total_qty).quantize(Decimal("0.0001")) if total_qty else Decimal("0"),
                    "locations": list(locations),
                })
        context["report_data"] = report_data
        context["grand_total_qty"] = sum(r["total_qty"] for r in report_data)
        context["grand_total_value"] = sum(r["total_value"] for r in report_data)
        return context


class ReportValuationView(InventoryCompanyMixin, TemplateView):
    template_name = "inventory/report_valuation.html"
    page_title = "Inventory Valuation Report"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = InventoryItem.objects.filter(
            company=self.company, is_active=True
        ).select_related("category", "base_unit")
        report_data = []
        categories = {}
        for item in items:
            total_value = StockMovement.objects.filter(
                company=self.company, item=item
            ).aggregate(total=Sum("total_cost"))["total"] or Decimal("0")
            total_qty = StockMovement.objects.filter(
                company=self.company, item=item
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            if total_qty > 0:
                entry = {
                    "item": item,
                    "qty": total_qty,
                    "value": total_value,
                }
                report_data.append(entry)
                cat_name = item.category.name if item.category else "Uncategorized"
                if cat_name not in categories:
                    categories[cat_name] = {"qty": Decimal("0"), "value": Decimal("0")}
                categories[cat_name]["qty"] += total_qty
                categories[cat_name]["value"] += total_value
        context["report_data"] = report_data
        context["by_category"] = categories
        context["grand_total_value"] = sum(r["value"] for r in report_data)
        return context


class ReportMovementLedgerView(InventoryCompanyMixin, ListView):
    model = StockMovement
    template_name = "inventory/report_movement_ledger.html"
    context_object_name = "movements"
    paginate_by = 50
    page_title = "Stock Movement Ledger"

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "item", "location", "location__warehouse", "document"
        ).order_by("-movement_date", "-created_at")
        item_id = self.request.GET.get("item")
        movement_type = self.request.GET.get("type")
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        if item_id:
            qs = qs.filter(item_id=item_id)
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        if date_from:
            qs = qs.filter(movement_date__gte=date_from)
        if date_to:
            qs = qs.filter(movement_date__lte=date_to)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items"] = InventoryItem.objects.filter(
            company=self.company, is_active=True
        ).order_by("sku")
        context["movement_types"] = StockMovement.MovementType.choices
        context["filters"] = self.request.GET
        return context


class ReportReorderAlertsView(InventoryCompanyMixin, TemplateView):
    template_name = "inventory/report_reorder.html"
    page_title = "Reorder Alerts"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = InventoryItem.objects.filter(
            company=self.company, is_active=True, reorder_point__gt=0
        ).select_related("category", "base_unit")
        alerts = []
        for item in items:
            total_qty = StockMovement.objects.filter(
                company=self.company, item=item
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            if total_qty <= item.reorder_point:
                suggested = item.reorder_point * 2 - total_qty
                alerts.append({
                    "item": item,
                    "current_qty": total_qty,
                    "reorder_point": item.reorder_point,
                    "shortage": item.reorder_point - total_qty,
                    "suggested_reorder": max(suggested, Decimal("0")),
                })
        context["alerts"] = alerts
        return context


class ReportAgingView(InventoryCompanyMixin, TemplateView):
    template_name = "inventory/report_aging.html"
    page_title = "Inventory Aging Report"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        items = InventoryItem.objects.filter(
            company=self.company, is_active=True
        ).select_related("category")
        aging_data = []
        for item in items:
            receipts = StockMovement.objects.filter(
                company=self.company, item=item,
                movement_type=StockMovement.MovementType.PURCHASE_RECEIPT,
            ).order_by("movement_date")
            total_qty = StockMovement.objects.filter(
                company=self.company, item=item
            ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            if total_qty <= 0:
                continue
            buckets = {"0-30": Decimal("0"), "31-60": Decimal("0"), "61-90": Decimal("0"), "90+": Decimal("0")}
            for receipt in receipts:
                if receipt.quantity <= 0:
                    continue
                days = (today - receipt.movement_date).days
                qty = min(receipt.quantity, total_qty - sum(buckets.values()))
                if qty <= 0:
                    break
                if days <= 30:
                    buckets["0-30"] += qty
                elif days <= 60:
                    buckets["31-60"] += qty
                elif days <= 90:
                    buckets["61-90"] += qty
                else:
                    buckets["90+"] += qty
            aging_data.append({
                "item": item,
                "total_qty": total_qty,
                "buckets": buckets,
            })
        context["aging_data"] = aging_data
        return context


# ── Phase 5: Document Approval & Reversal ──


class DocumentApprovalListView(InventoryCompanyMixin, ListView):
    model = InventoryDocument
    template_name = "inventory/document_approval_list.html"
    context_object_name = "documents"
    paginate_by = 25
    page_title = "Pending Approval"

    def get_queryset(self):
        return super().get_queryset().filter(
            status=InventoryDocument.Status.PENDING_APPROVAL
        ).select_related("journal").order_by("-document_date", "-created_at")


class DocumentApproveView(InventoryCompanyMixin, TemplateView):
    def post(self, request, *args, **kwargs):
        from inventory.services import approve_inventory_document
        doc = InventoryDocument.objects.get(company=self.company, pk=kwargs["pk"])
        approve_inventory_document(doc, user=request.user)
        messages.success(request, f"{doc.get_document_type_display()} approved.")
        return redirect("inventory:document_list")


class DocumentRejectView(InventoryCompanyMixin, TemplateView):
    def post(self, request, *args, **kwargs):
        doc = InventoryDocument.objects.get(company=self.company, pk=kwargs["pk"])
        doc.status = InventoryDocument.Status.CANCELLED
        doc.save(update_fields=["status", "updated_at"])
        messages.warning(request, f"{doc.get_document_type_display()} rejected.")
        return redirect("inventory:document_list")


class DocumentReversalView(InventoryCompanyMixin, FormView):
    form_class = InventoryDocumentReversalForm
    template_name = "inventory/action_form.html"
    success_url = reverse_lazy("inventory:document_list")
    page_title = "Reverse Document"
    action_label = "Post Reversal"

    def form_valid(self, form):
        doc = InventoryDocument.objects.get(company=self.company, pk=self.kwargs["pk"])
        reason = form.cleaned_data.get("reason", "Reversal")
        reversal_doc = InventoryDocument.objects.create(
            company=self.company,
            document_type=doc.document_type,
            document_date=form.cleaned_data.get("posting_date") or timezone.now().date(),
            reference=f"REV-{doc.reference or doc.pk}",
            reason=reason,
        )
        movements = doc.movements.all()
        for mv in movements:
            from inventory.services import _create_movement
            _create_movement(
                document=reversal_doc,
                item=mv.item,
                location=mv.location,
                movement_type=mv.movement_type,
                quantity=-mv.quantity,
                unit_cost=mv.unit_cost,
                movement_date=reversal_doc.document_date,
                memo=f"Reversal of {doc.reference or doc.pk}",
            )
        from inventory.services import _mark_document_posted
        _mark_document_posted(reversal_doc)
        messages.success(request, "Reversal document posted.")
        return super().form_valid(form)


# ── Phase 6: Vendor Bills & Landed Costs ──


class VendorBillListView(InventoryCompanyMixin, ListView):
    model = VendorBill
    template_name = "inventory/vendor_bill_list.html"
    context_object_name = "vendor_bills"
    page_title = "Vendor Bills"

    def get_queryset(self):
        return super().get_queryset().select_related("supplier", "purchase_receipt")


class VendorBillCreateView(InventoryCompanyMixin, FormView):
    form_class = VendorBillForm
    template_name = "inventory/action_form.html"
    success_url = reverse_lazy("inventory:vendor_bill_list")
    page_title = "New Vendor Bill"
    action_label = "Create Bill"

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            bill = VendorBill.objects.create(
                company=self.company,
                supplier=data["supplier"],
                purchase_receipt=data.get("purchase_receipt"),
                bill_date=data.get("posting_date") or timezone.now().date(),
                due_date=data.get("due_date"),
                bill_number=data.get("bill_number", ""),
                total_amount=data.get("unit_cost") or 0,
                notes=data.get("reason", ""),
            )
            if data.get("item") and data.get("quantity"):
                VendorBillLine.objects.create(
                    vendor_bill=bill,
                    item=data["item"],
                    description=data.get("description", ""),
                    quantity=data["quantity"],
                    unit_cost=data.get("unit_cost") or 0,
                    total_amount=(data["quantity"] or 0) * (data.get("unit_cost") or 0),
                )
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Vendor bill created.")
        return super().form_valid(form)


class VendorBillDetailView(InventoryCompanyMixin, DetailView):
    model = VendorBill
    template_name = "inventory/vendor_bill_detail.html"
    context_object_name = "bill"
    page_title = "Vendor Bill Detail"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["lines"] = self.object.lines.select_related("item")
        return context


class LandedCostCreateView(InventoryCompanyMixin, FormView):
    form_class = LandedCostForm
    template_name = "inventory/action_form.html"
    success_url = reverse_lazy("inventory:dashboard")
    page_title = "New Landed Cost"
    action_label = "Allocate & Post"

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            landed = LandedCost.objects.create(
                company=self.company,
                purchase_receipt=data.get("purchase_receipt"),
                description=data["description"],
                cost_type=data["cost_type"],
                total_cost=data["total_cost"],
                allocation_method=data.get("allocation_method") or "BY_VALUE",
                status=LandedCost.Status.DRAFT,
            )
            if data.get("receipt_line") and data.get("allocated_amount"):
                LandedCostAllocation.objects.create(
                    landed_cost=landed,
                    receipt_line=data["receipt_line"],
                    allocated_amount=data["allocated_amount"],
                )
            landed.status = LandedCost.Status.ALLOCATED
            landed.save(update_fields=["status", "updated_at"])
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Landed cost allocated.")
        return super().form_valid(form)
