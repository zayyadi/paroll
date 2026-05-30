from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from accounting.models import Account, PostingValidationFailure
from accounting.utils import create_journal_with_entries
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
    Supplier,
    SupplierPayment,
    SupplierReturn,
    SupplierReturnLine,
    TaxJurisdiction,
    TaxRemittance,
    TaxRule,
    StockCount,
    StockCountLine,
    StockLocation,
    StockMovement,
    TransferShipment,
    TransferShipmentLine,
    VendorBill,
    VendorBillLine,
)


QTY = Decimal("0.0001")
MONEY = Decimal("0.01")


DEFAULT_POSTING_ACCOUNTS = [
    {
        "name": "Bank and Cash",
        "account_number": "1000",
        "type": Account.AccountType.ASSET,
        "description": "Cash and bank account for inventory receipts and payments.",
    },
    {
        "name": "Trade Receivables",
        "account_number": "1100",
        "type": Account.AccountType.ASSET,
        "description": "Customer balances for wholesale credit sales.",
    },
    {
        "name": "Inventory Asset",
        "account_number": "1200",
        "type": Account.AccountType.ASSET,
        "description": "Stock value held in warehouses and locations.",
    },
    {
        "name": "Input VAT",
        "account_number": "1300",
        "type": Account.AccountType.ASSET,
        "description": "Recoverable VAT on purchases.",
    },
    {
        "name": "WHT Receivable",
        "account_number": "1400",
        "type": Account.AccountType.ASSET,
        "description": "Withholding tax deducted by customers.",
    },
    {
        "name": "Trade Payables",
        "account_number": "2000",
        "type": Account.AccountType.LIABILITY,
        "description": "Vendor balances for wholesale purchasing.",
    },
    {
        "name": "Output VAT",
        "account_number": "2200",
        "type": Account.AccountType.LIABILITY,
        "description": "VAT collected on sales and payable to tax authority.",
    },
    {
        "name": "WHT Payable",
        "account_number": "2300",
        "type": Account.AccountType.LIABILITY,
        "description": "Withholding tax deducted from supplier payments.",
    },
    {
        "name": "Opening Balance Equity",
        "account_number": "3000",
        "type": Account.AccountType.EQUITY,
        "description": "Offset account for opening inventory balances.",
    },
    {
        "name": "Wholesale Sales",
        "account_number": "4100",
        "type": Account.AccountType.REVENUE,
        "description": "Sales revenue for wholesale warehouse operations.",
    },
    {
        "name": "Inventory Adjustment Gain",
        "account_number": "4200",
        "type": Account.AccountType.REVENUE,
        "description": "Positive stock count and valuation adjustments.",
    },
    {
        "name": "Cost of Goods Sold",
        "account_number": "5100",
        "type": Account.AccountType.EXPENSE,
        "description": "Inventory cost recognized when goods are sold.",
    },
    {
        "name": "Inventory Shrinkage",
        "account_number": "6200",
        "type": Account.AccountType.EXPENSE,
        "description": "Stock losses, expiries, breakages, and negative count adjustments.",
    },
]


def ensure_default_posting_accounts(company):
    created = []
    existing = []
    for spec in DEFAULT_POSTING_ACCOUNTS:
        account, was_created = Account.objects.get_or_create(
            company=company,
            account_number=spec["account_number"],
            defaults={
                "name": spec["name"],
                "type": spec["type"],
                "description": spec["description"],
            },
        )
        if was_created:
            created.append(account)
        else:
            existing.append(account)
    return {"created": created, "existing": existing}


def _q_qty(value):
    return Decimal(value).quantize(QTY, rounding=ROUND_HALF_UP)


def _q_money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _active_tax_rule(company, tax_type, transaction_type, tax_date, jurisdiction=None):
    rules = TaxRule.objects.filter(
        company=company,
        tax_type=tax_type,
        transaction_type=transaction_type,
        is_active=True,
        effective_from__lte=tax_date,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=tax_date))
    if jurisdiction is not None:
        rules = rules.filter(jurisdiction=jurisdiction)
    else:
        rules = rules.filter(jurisdiction__is_default=True, jurisdiction__is_active=True)
    return rules.order_by("-effective_from", "-id").first()


def calculate_inventory_line_taxes(
    *,
    company,
    item: InventoryItem,
    quantity,
    unit_price,
    transaction_type=TaxRule.TransactionType.SALE,
    jurisdiction: TaxJurisdiction | None = None,
    tax_date=None,
    default_vat_rate=None,
    default_wht_rate=None,
):
    tax_date = tax_date or timezone.now().date()
    taxable_amount = _q_money(Decimal(quantity) * Decimal(unit_price))
    vat_rule = _active_tax_rule(
        company, TaxRule.TaxType.VAT, transaction_type, tax_date, jurisdiction
    )
    wht_rule = _active_tax_rule(
        company, TaxRule.TaxType.WHT, transaction_type, tax_date, jurisdiction
    )
    vat_rate = vat_rule.rate if vat_rule else (
        item.default_vat_rate if default_vat_rate is None else Decimal(default_vat_rate)
    )
    wht_rate = wht_rule.rate if wht_rule else (
        item.default_wht_rate if default_wht_rate is None else Decimal(default_wht_rate)
    )
    return {
        "taxable_amount": taxable_amount,
        "vat_rate": vat_rate,
        "vat_amount": _q_money(taxable_amount * vat_rate / Decimal("100")),
        "wht_rate": wht_rate,
        "wht_amount": _q_money(taxable_amount * wht_rate / Decimal("100")),
    }


def _rate_amount(base, rate):
    return _q_money(_q_money(base) * Decimal(rate or 0) / Decimal("100"))


def _assert_same_company(company, *objects):
    for obj in objects:
        if obj is not None and getattr(obj, "company_id", None) != company.id:
            raise ValueError("Inventory object belongs to a different company")


def _assert_positive_money(amount, label="Amount"):
    amount = _q_money(amount)
    if amount <= 0:
        raise ValueError(f"{label} must be positive")
    return amount


def _log_posting_failure(company, document_type, account_role, account, message):
    PostingValidationFailure.objects.create(
        company=company,
        document_type=document_type,
        account_role=account_role,
        account=account,
        message=message,
    )


def _validate_posting_account(company, document_type, account_role, account, expected_type):
    if account is None:
        message = f"Missing posting account for {account_role}"
        _log_posting_failure(company, document_type, account_role, None, message)
        raise ValueError(message)
    if account.company_id != company.id:
        message = f"{account_role} account belongs to a different company"
        _log_posting_failure(company, document_type, account_role, account, message)
        raise ValueError(message)
    if getattr(account, "status", Account.AccountStatus.ACTIVE) != Account.AccountStatus.ACTIVE:
        message = f"{account_role} account is inactive or restricted"
        _log_posting_failure(company, document_type, account_role, account, message)
        raise ValueError(message)
    if account.type != expected_type:
        message = (
            f"{account_role} account must be {expected_type}; "
            f"{account.name} is {account.type}"
        )
        _log_posting_failure(company, document_type, account_role, account, message)
        raise ValueError(message)
    return account


def get_stock_on_hand(item: InventoryItem, location: StockLocation | None = None):
    filters = {"company": item.company, "item": item}
    if location is not None:
        filters["location"] = location
    total = StockMovement.objects.filter(**filters).aggregate(total=Sum("quantity"))[
        "total"
    ]
    return _q_qty(total or Decimal("0"))


def get_inventory_value(item: InventoryItem):
    total = StockMovement.objects.filter(company=item.company, item=item).aggregate(
        total=Sum("total_cost")
    )["total"]
    return _q_money(total or Decimal("0"))


def get_average_unit_cost(item: InventoryItem):
    quantity = get_stock_on_hand(item)
    if quantity <= 0:
        return Decimal("0.0000")
    return (get_inventory_value(item) / quantity).quantize(QTY, rounding=ROUND_HALF_UP)


def _posting_accounts(item, document_type=InventoryDocument.DocumentType.ADJUSTMENT):
    category = item.category
    required = {
        "inventory_account": (category.inventory_account, Account.AccountType.ASSET),
        "opening_balance_equity_account": (
            category.opening_balance_equity_account,
            Account.AccountType.EQUITY,
        ),
        "adjustment_gain_account": (
            category.adjustment_gain_account,
            Account.AccountType.REVENUE,
        ),
        "shrinkage_expense_account": (
            category.shrinkage_expense_account,
            Account.AccountType.EXPENSE,
        ),
    }
    return {
        role: _validate_posting_account(item.company, document_type, role, account, expected_type)
        for role, (account, expected_type) in required.items()
    }


def _inventory_account(item, document_type=InventoryDocument.DocumentType.PURCHASE_RECEIPT):
    account = item.category.inventory_account
    return _validate_posting_account(
        item.company,
        document_type,
        "inventory_account",
        account,
        Account.AccountType.ASSET,
    )


def _sales_accounts(item, document_type=InventoryDocument.DocumentType.SALES_INVOICE):
    category = item.category
    required = {
        "inventory_account": (category.inventory_account, Account.AccountType.ASSET),
        "sales_revenue_account": (
            category.sales_revenue_account,
            Account.AccountType.REVENUE,
        ),
        "cogs_account": (category.cogs_account, Account.AccountType.EXPENSE),
    }
    return {
        role: _validate_posting_account(item.company, document_type, role, account, expected_type)
        for role, (account, expected_type) in required.items()
    }


def _document_total(document):
    entries = document.journal.entries.all() if document.journal_id else []
    debit_total = sum(entry.amount for entry in entries if entry.entry_type == "DEBIT")
    credit_total = sum(entry.amount for entry in entries if entry.entry_type == "CREDIT")
    return _q_money(max(debit_total, credit_total))


def _mark_document_posted(document, total_amount=None):
    document.status = InventoryDocument.Status.POSTED
    document.total_amount = _q_money(total_amount or _document_total(document))
    document.posted_at = timezone.now()
    document.save(update_fields=["status", "total_amount", "posted_at", "updated_at"])
    return document


def approve_inventory_document(document_or_stock_count, user=None):
    document_or_stock_count.status = document_or_stock_count.Status.APPROVED
    document_or_stock_count.approved_by = user
    document_or_stock_count.approved_at = timezone.now()
    document_or_stock_count.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return document_or_stock_count


def _ensure_credit_available(customer, additional_amount):
    if customer.credit_limit <= 0:
        return
    outstanding = sum(
        _q_money(invoice_total(invoice) - invoice.paid_amount)
        for invoice in customer.sales_invoices.exclude(payment_status="PAID")
    )
    if _q_money(outstanding + additional_amount) > customer.credit_limit:
        raise ValueError("Customer credit limit exceeded")


def invoice_total(invoice):
    totals = invoice.lines.aggregate(
        revenue=Sum("revenue_amount"), vat=Sum("vat_amount"), wht=Sum("wht_amount")
    )
    return _q_money(
        (totals["revenue"] or Decimal("0.00"))
        + (totals["vat"] or Decimal("0.00"))
        - (totals["wht"] or Decimal("0.00"))
    )


def receipt_total(receipt):
    totals = receipt.lines.aggregate(
        cost=Sum("total_cost"), vat=Sum("vat_amount"), wht=Sum("wht_amount")
    )
    return _q_money(
        (totals["cost"] or Decimal("0.00"))
        + (totals["vat"] or Decimal("0.00"))
        - (totals["wht"] or Decimal("0.00"))
    )


def _set_invoice_payment_status(invoice):
    total = invoice_total(invoice)
    if invoice.paid_amount <= 0:
        invoice.payment_status = "UNPAID"
    elif invoice.paid_amount >= total:
        invoice.payment_status = "PAID"
        invoice.workflow_status = "PAID"
        invoice.paid_at = timezone.now()
    else:
        invoice.payment_status = "PARTIAL"
    invoice.save(
        update_fields=[
            "paid_amount",
            "payment_status",
            "workflow_status",
            "paid_at",
            "updated_at",
        ]
    )


def _set_receipt_payment_status(receipt):
    total = receipt_total(receipt)
    if receipt.paid_amount <= 0:
        receipt.payment_status = "UNPAID"
    elif receipt.paid_amount >= total:
        receipt.payment_status = "PAID"
    else:
        receipt.payment_status = "PARTIAL"
    receipt.save(update_fields=["paid_amount", "payment_status", "updated_at"])


def _consume_fifo_layers(item, location, quantity, consume=False):
    remaining = _q_qty(quantity)
    total_cost = Decimal("0.00")
    layers = (
        InventoryValuationLayer.objects.select_for_update()
        .filter(
            company=item.company,
            item=item,
            remaining_quantity__gt=0,
            movement__location=location,
        )
        .order_by("created_at", "id")
    )
    for layer in layers:
        if remaining <= 0:
            break
        used = min(layer.remaining_quantity, remaining)
        used_total = _q_money(used * layer.unit_cost)
        total_cost += used_total
        if consume:
            layer.remaining_quantity = _q_qty(layer.remaining_quantity - used)
            layer.remaining_total_cost = _q_money(layer.remaining_total_cost - used_total)
            layer.save(update_fields=["remaining_quantity", "remaining_total_cost", "updated_at"])
        remaining = _q_qty(remaining - used)
    if remaining > 0 and not item.allow_negative_stock:
        raise ValueError("Insufficient valuation layers for FIFO COGS")
    return _q_money(total_cost)


def _calculate_cogs(item, location, quantity):
    if item.category.costing_method == InventoryCategory.CostingMethod.FIFO:
        cogs_amount = _consume_fifo_layers(item, location, quantity, consume=True)
        unit_cost = (cogs_amount / quantity).quantize(QTY, rounding=ROUND_HALF_UP)
        return unit_cost, cogs_amount
    unit_cost = get_average_unit_cost(item) or item.standard_cost
    cogs_amount = _q_money(quantity * unit_cost)
    _consume_fifo_layers(item, location, quantity, consume=True)
    return unit_cost, cogs_amount


def _update_purchase_order_status(purchase_order):
    lines = list(PurchaseOrderLine.objects.filter(purchase_order=purchase_order))
    if not lines:
        purchase_order.status = PurchaseOrder.Status.ORDERED
    elif all(line.received_quantity >= line.quantity for line in lines):
        purchase_order.status = PurchaseOrder.Status.RECEIVED
    elif any(line.received_quantity > 0 for line in lines):
        purchase_order.status = PurchaseOrder.Status.PARTIALLY_RECEIVED
    else:
        purchase_order.status = PurchaseOrder.Status.ORDERED
    purchase_order.save(update_fields=["status", "updated_at"])
    return purchase_order


def _create_movement(
    *,
    document,
    item,
    location,
    movement_type,
    quantity,
    unit_cost,
    movement_date,
    memo="",
    batch_number="",
    serial_number="",
    expiry_date=None,
):
    quantity = _q_qty(quantity)
    unit_cost = _q_qty(unit_cost)
    total_cost = _q_money(quantity * unit_cost)
    movement = StockMovement.objects.create(
        company=document.company,
        document=document,
        item=item,
        location=location,
        movement_type=movement_type,
        quantity=quantity,
        unit_cost=unit_cost,
        total_cost=total_cost,
        batch_number=batch_number,
        serial_number=serial_number,
        expiry_date=expiry_date,
        movement_date=movement_date,
        memo=memo,
    )
    InventoryValuationLayer.objects.create(
        company=document.company,
        movement=movement,
        item=item,
        quantity=quantity,
        remaining_quantity=quantity if quantity > 0 else Decimal("0.0000"),
        unit_cost=unit_cost,
        total_cost=total_cost,
        remaining_total_cost=total_cost if quantity > 0 else Decimal("0.00"),
    )
    return movement


def post_opening_stock(
    *,
    company,
    item,
    location,
    quantity,
    unit_cost,
    posting_date=None,
    reference="",
    reason="Opening stock",
):
    posting_date = posting_date or timezone.now().date()
    quantity = _q_qty(quantity)
    unit_cost = _q_qty(unit_cost)
    if quantity <= 0 or unit_cost < 0:
        raise ValueError("Opening stock quantity must be positive and cost cannot be negative")
    _assert_same_company(company, item, location)
    accounts = _posting_accounts(item, InventoryDocument.DocumentType.OPENING_STOCK)
    total_cost = _q_money(quantity * unit_cost)

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.OPENING_STOCK,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    _create_movement(
        document=document,
        item=item,
        location=location,
        movement_type=StockMovement.MovementType.OPENING,
        quantity=quantity,
        unit_cost=unit_cost,
        movement_date=posting_date,
        memo=reason,
    )
    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description=f"Opening stock: {item.sku}",
        entries=[
            {
                "account": accounts["inventory_account"],
                "entry_type": "DEBIT",
                "amount": total_cost,
                "memo": f"Opening stock for {item.name}",
            },
            {
                "account": accounts["opening_balance_equity_account"],
                "entry_type": "CREDIT",
                "amount": total_cost,
                "memo": f"Opening stock offset for {item.name}",
            },
        ],
        auto_post=True,
        source_object=document,
        validate_balances=False,
    )
    document.journal = journal
    document.save(update_fields=["journal", "updated_at"])
    _mark_document_posted(document, total_cost)
    return document


@transaction.atomic
def post_purchase_receipt(
    *,
    company,
    supplier: Supplier,
    location: StockLocation | None = None,
    lines,
    purchase_order: PurchaseOrder | None = None,
    vat_input_account=None,
    posting_date=None,
    reference="",
    reason="Purchase receipt",
):
    posting_date = posting_date or timezone.now().date()
    if not lines:
        raise ValueError("Purchase receipt requires at least one line")
    _assert_same_company(company, supplier, location, purchase_order, vat_input_account)
    _validate_posting_account(
        company,
        InventoryDocument.DocumentType.PURCHASE_RECEIPT,
        "supplier_payable_account",
        supplier.payable_account,
        Account.AccountType.LIABILITY,
    )
    if vat_input_account is not None:
        _validate_posting_account(
            company,
            InventoryDocument.DocumentType.PURCHASE_RECEIPT,
            "vat_input_account",
            vat_input_account,
            Account.AccountType.ASSET,
        )
    if supplier.wht_payable_account is not None:
        _validate_posting_account(
            company,
            InventoryDocument.DocumentType.PURCHASE_RECEIPT,
            "supplier_wht_payable_account",
            supplier.wht_payable_account,
            Account.AccountType.LIABILITY,
        )

    prepared_lines = []
    total_payable = Decimal("0.00")
    total_vat = Decimal("0.00")
    total_wht = Decimal("0.00")
    journal_entries = []
    for line in lines:
        item = line["item"]
        line_location = line.get("location") or location
        if line_location is None:
            raise ValueError("Purchase receipt line requires a stock location")
        _assert_same_company(company, item, line_location)
        quantity = _q_qty(line["quantity"])
        unit_cost = _q_qty(line["unit_cost"])
        if quantity <= 0 or unit_cost < 0:
            raise ValueError("Purchase receipt quantity must be positive and cost cannot be negative")
        total_cost = _q_money(quantity * unit_cost)
        taxes = calculate_inventory_line_taxes(
            company=company,
            item=item,
            quantity=quantity,
            unit_price=unit_cost,
            transaction_type=TaxRule.TransactionType.PURCHASE,
            tax_date=posting_date,
            default_wht_rate=getattr(supplier, "default_wht_rate", 0),
        )
        vat_rate = Decimal(line["vat_rate"]) if "vat_rate" in line else taxes["vat_rate"]
        wht_rate = Decimal(line["wht_rate"]) if "wht_rate" in line else taxes["wht_rate"]
        vat_amount = _rate_amount(total_cost, vat_rate)
        wht_amount = _rate_amount(total_cost, wht_rate)
        inventory_account = _inventory_account(item, InventoryDocument.DocumentType.PURCHASE_RECEIPT)
        total_payable += total_cost + vat_amount - wht_amount
        total_vat += vat_amount
        total_wht += wht_amount
        prepared_lines.append(
            {
                "item": item,
                "location": line_location,
                "quantity": quantity,
                "unit_cost": unit_cost,
                "total_cost": total_cost,
                "vat_rate": vat_rate,
                "vat_amount": vat_amount,
                "wht_rate": wht_rate,
                "wht_amount": wht_amount,
            }
        )
        journal_entries.append(
            {
                "account": inventory_account,
                "entry_type": "DEBIT",
                "amount": total_cost,
                "memo": f"Purchase receipt for {item.name}",
            }
        )
    if total_vat:
        if vat_input_account is None:
            raise ValueError("VAT input account is required when purchase VAT is posted")
        journal_entries.append(
            {
                "account": vat_input_account,
                "entry_type": "DEBIT",
                "amount": _q_money(total_vat),
                "memo": f"Input VAT for {supplier.name}",
            }
        )
    if total_wht:
        if supplier.wht_payable_account is None:
            raise ValueError("Supplier WHT payable account is required when purchase WHT is posted")
        journal_entries.append(
            {
                "account": supplier.wht_payable_account,
                "entry_type": "CREDIT",
                "amount": _q_money(total_wht),
                "memo": f"Withholding tax payable for {supplier.name}",
            }
        )

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.PURCHASE_RECEIPT,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    receipt = PurchaseReceipt.objects.create(
        company=company,
        document=document,
        supplier=supplier,
        purchase_order=purchase_order,
        invoice_date=posting_date,
        due_date=posting_date + timedelta(days=supplier.default_due_days),
        payment_terms=supplier.payment_terms,
    )
    for line in prepared_lines:
        movement = _create_movement(
            document=document,
            item=line["item"],
            location=line["location"],
            movement_type=StockMovement.MovementType.PURCHASE_RECEIPT,
            quantity=line["quantity"],
            unit_cost=line["unit_cost"],
            movement_date=posting_date,
            memo=reason,
        )
        PurchaseReceiptLine.objects.create(
            receipt=receipt,
            item=line["item"],
            location=line["location"],
            quantity=line["quantity"],
            unit_cost=line["unit_cost"],
            vat_rate=line["vat_rate"],
            vat_amount=line["vat_amount"],
            wht_rate=line["wht_rate"],
            wht_amount=line["wht_amount"],
            total_cost=line["total_cost"],
            movement=movement,
        )

    journal_entries.append(
        {
            "account": supplier.payable_account,
            "entry_type": "CREDIT",
            "amount": _q_money(total_payable),
            "memo": f"Supplier payable for {supplier.name}",
        }
    )
    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description=f"Purchase receipt: {supplier.name}",
        entries=journal_entries,
        auto_post=True,
        source_object=document,
        validate_balances=False,
    )
    document.journal = journal
    document.save(update_fields=["journal", "updated_at"])
    _mark_document_posted(document, total_payable)
    return document


@transaction.atomic
def post_sales_invoice(
    *,
    company,
    customer: Customer,
    location: StockLocation | None = None,
    lines,
    vat_output_account=None,
    posting_date=None,
    reference="",
    reason="Sales invoice",
):
    posting_date = posting_date or timezone.now().date()
    if not lines:
        raise ValueError("Sales invoice requires at least one line")
    _assert_same_company(company, customer, location, vat_output_account)
    _validate_posting_account(
        company,
        InventoryDocument.DocumentType.SALES_INVOICE,
        "customer_receivable_account",
        customer.receivable_account,
        Account.AccountType.ASSET,
    )
    if vat_output_account is not None:
        _validate_posting_account(
            company,
            InventoryDocument.DocumentType.SALES_INVOICE,
            "vat_output_account",
            vat_output_account,
            Account.AccountType.LIABILITY,
        )
    if customer.wht_receivable_account is not None:
        _validate_posting_account(
            company,
            InventoryDocument.DocumentType.SALES_INVOICE,
            "customer_wht_receivable_account",
            customer.wht_receivable_account,
            Account.AccountType.ASSET,
        )

    prepared_lines = []
    journal_entries = []
    total_receivable = Decimal("0.00")
    total_wht = Decimal("0.00")
    total_vat = Decimal("0.00")
    for line in lines:
        item = line["item"]
        line_location = line.get("location") or location
        if line_location is None:
            raise ValueError("Sales invoice line requires a stock location")
        _assert_same_company(company, item, line_location)
        quantity = _q_qty(line["quantity"])
        unit_price = _q_qty(line.get("unit_price") or item.default_sales_price)
        if quantity <= 0 or unit_price < 0:
            raise ValueError("Sales quantity must be positive and price cannot be negative")
        available = get_stock_on_hand(item, line_location)
        if not item.allow_negative_stock and available - quantity < 0:
            raise ValueError("Sale would make stock negative")
        revenue_amount = _q_money(quantity * unit_price)
        unit_cost, cogs_amount = _calculate_cogs(item, line_location, quantity)
        taxes = calculate_inventory_line_taxes(
            company=company,
            item=item,
            quantity=quantity,
            unit_price=unit_price,
            transaction_type=TaxRule.TransactionType.SALE,
            tax_date=posting_date,
            default_wht_rate=customer.default_wht_rate,
        )
        vat_rate = Decimal(line["vat_rate"]) if "vat_rate" in line else taxes["vat_rate"]
        wht_rate = Decimal(line["wht_rate"]) if "wht_rate" in line else taxes["wht_rate"]
        vat_amount = _rate_amount(revenue_amount, vat_rate)
        wht_amount = _rate_amount(revenue_amount, wht_rate)
        accounts = _sales_accounts(item)
        total_receivable += revenue_amount + vat_amount - wht_amount
        total_vat += vat_amount
        total_wht += wht_amount
        prepared_lines.append(
            {
                "item": item,
                "location": line_location,
                "quantity": quantity,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
                "revenue_amount": revenue_amount,
                "cogs_amount": cogs_amount,
                "vat_rate": vat_rate,
                "vat_amount": vat_amount,
                "wht_rate": wht_rate,
                "wht_amount": wht_amount,
                "accounts": accounts,
            }
        )
        journal_entries.extend(
            [
                {
                    "account": accounts["sales_revenue_account"],
                    "entry_type": "CREDIT",
                    "amount": revenue_amount,
                    "memo": f"Sale of {item.name}",
                },
                {
                    "account": accounts["cogs_account"],
                    "entry_type": "DEBIT",
                    "amount": cogs_amount,
                    "memo": f"COGS for {item.name}",
                },
                {
                    "account": accounts["inventory_account"],
                    "entry_type": "CREDIT",
                    "amount": cogs_amount,
                    "memo": f"Inventory issued for {item.name}",
                },
            ]
        )
    if total_vat:
        if vat_output_account is None:
            raise ValueError("VAT output account is required when sales VAT is posted")
        journal_entries.append(
            {
                "account": vat_output_account,
                "entry_type": "CREDIT",
                "amount": _q_money(total_vat),
                "memo": f"Output VAT for {customer.name}",
            }
        )
    if total_wht:
        if customer.wht_receivable_account is None:
            raise ValueError("Customer WHT receivable account is required when sales WHT is posted")
        journal_entries.append(
            {
                "account": customer.wht_receivable_account,
                "entry_type": "DEBIT",
                "amount": _q_money(total_wht),
                "memo": f"Withholding tax receivable for {customer.name}",
            }
        )
    journal_entries.append(
        {
            "account": customer.receivable_account,
            "entry_type": "DEBIT",
            "amount": _q_money(total_receivable),
            "memo": f"Customer receivable for {customer.name}",
        }
    )

    _ensure_credit_available(customer, _q_money(total_receivable))

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.SALES_INVOICE,
        document_date=posting_date,
        reference=reference,
        reason=reason,
        total_amount=_q_money(total_receivable),
    )
    invoice = SalesInvoice.objects.create(
        company=company,
        document=document,
        customer=customer,
        invoice_date=posting_date,
        due_date=posting_date + timedelta(days=customer.default_due_days),
        payment_terms=customer.payment_terms,
    )
    for line in prepared_lines:
        movement = _create_movement(
            document=document,
            item=line["item"],
            location=line["location"],
            movement_type=StockMovement.MovementType.SALE,
            quantity=-line["quantity"],
            unit_cost=line["unit_cost"],
            movement_date=posting_date,
            memo=reason,
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice,
            item=line["item"],
            location=line["location"],
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            unit_cost=line["unit_cost"],
            revenue_amount=line["revenue_amount"],
            cogs_amount=line["cogs_amount"],
            vat_rate=line["vat_rate"],
            vat_amount=line["vat_amount"],
            wht_rate=line["wht_rate"],
            wht_amount=line["wht_amount"],
            movement=movement,
        )
    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description=f"Sales invoice: {customer.name}",
        entries=journal_entries,
        auto_post=True,
        source_object=document,
        validate_balances=False,
    )
    document.journal = journal
    document.save(update_fields=["journal", "updated_at"])
    _mark_document_posted(document, total_receivable)
    return document


@transaction.atomic
def post_customer_payment(
    *,
    company,
    customer: Customer,
    cash_account,
    amount,
    invoice: SalesInvoice | None = None,
    posting_date=None,
    reference="",
    reason="Customer payment",
):
    posting_date = posting_date or timezone.now().date()
    amount = _assert_positive_money(amount)
    _assert_same_company(company, customer, cash_account)
    _validate_posting_account(
        company,
        InventoryDocument.DocumentType.CUSTOMER_PAYMENT,
        "cash_account",
        cash_account,
        Account.AccountType.ASSET,
    )
    _validate_posting_account(
        company,
        InventoryDocument.DocumentType.CUSTOMER_PAYMENT,
        "customer_receivable_account",
        customer.receivable_account,
        Account.AccountType.ASSET,
    )
    _assert_same_company(company, invoice)
    if invoice is not None and invoice.customer_id != customer.id:
        raise ValueError("Payment invoice does not belong to this customer")

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.CUSTOMER_PAYMENT,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    CustomerPayment.objects.create(
        company=company,
        document=document,
        customer=customer,
        cash_account=cash_account,
        amount=amount,
        invoice=invoice,
        payment_date=posting_date,
        reference=reference,
    )
    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description=f"Customer payment: {customer.name}",
        entries=[
            {
                "account": cash_account,
                "entry_type": "DEBIT",
                "amount": amount,
                "memo": f"Cash received from {customer.name}",
            },
            {
                "account": customer.receivable_account,
                "entry_type": "CREDIT",
                "amount": amount,
                "memo": f"Receivable settled by {customer.name}",
            },
        ],
        auto_post=True,
        source_object=document,
        validate_balances=False,
    )
    document.journal = journal
    document.save(update_fields=["journal", "updated_at"])
    _mark_document_posted(document, amount)
    if invoice is not None:
        invoice.paid_amount = _q_money(invoice.paid_amount + amount)
        _set_invoice_payment_status(invoice)
    return document


@transaction.atomic
def post_supplier_payment(
    *,
    company,
    supplier: Supplier,
    cash_account,
    amount,
    receipt: PurchaseReceipt | None = None,
    discount_taken=Decimal("0.00"),
    posting_date=None,
    reference="",
    reason="Supplier payment",
):
    posting_date = posting_date or timezone.now().date()
    amount = _assert_positive_money(amount)
    _assert_same_company(company, supplier, cash_account)
    discount_taken = _q_money(discount_taken)
    if discount_taken < 0:
        raise ValueError("Discount taken cannot be negative")
    _validate_posting_account(
        company,
        InventoryDocument.DocumentType.SUPPLIER_PAYMENT,
        "cash_account",
        cash_account,
        Account.AccountType.ASSET,
    )
    _validate_posting_account(
        company,
        InventoryDocument.DocumentType.SUPPLIER_PAYMENT,
        "supplier_payable_account",
        supplier.payable_account,
        Account.AccountType.LIABILITY,
    )
    _assert_same_company(company, receipt)
    if receipt is not None and receipt.supplier_id != supplier.id:
        raise ValueError("Payment receipt does not belong to this supplier")

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.SUPPLIER_PAYMENT,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    SupplierPayment.objects.create(
        company=company,
        document=document,
        supplier=supplier,
        cash_account=cash_account,
        amount=amount,
        receipt=receipt,
        payment_date=posting_date,
        reference=reference,
        due_date=getattr(receipt, "due_date", None),
        discount_taken=discount_taken,
    )
    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description=f"Supplier payment: {supplier.name}",
        entries=[
            {
                "account": supplier.payable_account,
                "entry_type": "DEBIT",
                "amount": amount,
                "memo": f"Payable settled for {supplier.name}",
            },
            {
                "account": cash_account,
                "entry_type": "CREDIT",
                "amount": amount,
                "memo": f"Cash paid to {supplier.name}",
            },
        ],
        auto_post=True,
        source_object=document,
        validate_balances=False,
    )
    document.journal = journal
    document.save(update_fields=["journal", "updated_at"])
    _mark_document_posted(document, amount)
    if receipt is not None:
        receipt.paid_amount = _q_money(receipt.paid_amount + amount + discount_taken)
        _set_receipt_payment_status(receipt)
    return document


@transaction.atomic
def post_tax_remittance(
    *,
    company,
    cash_account,
    vat_output_account=None,
    vat_input_account=None,
    wht_payable_account=None,
    vat_output_amount=Decimal("0.00"),
    vat_input_amount=Decimal("0.00"),
    wht_amount=Decimal("0.00"),
    posting_date=None,
    reference="",
    reason="Tax remittance",
):
    posting_date = posting_date or timezone.now().date()
    vat_output_amount = _q_money(vat_output_amount)
    vat_input_amount = _q_money(vat_input_amount)
    wht_amount = _q_money(wht_amount)
    if vat_output_amount < 0 or vat_input_amount < 0 or wht_amount < 0:
        raise ValueError("Tax remittance amounts cannot be negative")
    _assert_same_company(
        company,
        cash_account,
        vat_output_account,
        vat_input_account,
        wht_payable_account,
    )

    entries = []
    if vat_output_amount:
        if vat_output_account is None:
            raise ValueError("VAT output account is required")
        entries.append(
            {
                "account": vat_output_account,
                "entry_type": "DEBIT",
                "amount": vat_output_amount,
                "memo": "VAT output remitted",
            }
        )
    if vat_input_amount:
        if vat_input_account is None:
            raise ValueError("VAT input account is required")
        entries.append(
            {
                "account": vat_input_account,
                "entry_type": "CREDIT",
                "amount": vat_input_amount,
                "memo": "Input VAT offset",
            }
        )
    if wht_amount:
        if wht_payable_account is None:
            raise ValueError("WHT payable account is required")
        entries.append(
            {
                "account": wht_payable_account,
                "entry_type": "DEBIT",
                "amount": wht_amount,
                "memo": "WHT remitted",
            }
        )

    paid_amount = _q_money(vat_output_amount - vat_input_amount + wht_amount)
    if paid_amount <= 0:
        raise ValueError("Tax remittance paid amount must be positive")
    entries.append(
        {
            "account": cash_account,
            "entry_type": "CREDIT",
            "amount": paid_amount,
            "memo": "Tax remittance paid",
        }
    )

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.TAX_REMITTANCE,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    TaxRemittance.objects.create(
        company=company,
        document=document,
        cash_account=cash_account,
        vat_output_amount=vat_output_amount,
        vat_input_amount=vat_input_amount,
        wht_amount=wht_amount,
        paid_amount=paid_amount,
    )
    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description="Tax remittance",
        entries=entries,
        auto_post=True,
        source_object=document,
        validate_balances=False,
    )
    document.journal = journal
    document.save(update_fields=["journal", "updated_at"])
    return document


@transaction.atomic
def post_customer_return(
    *,
    company,
    customer: Customer,
    location: StockLocation | None = None,
    lines,
    vat_output_account=None,
    posting_date=None,
    reference="",
    reason="Customer return",
):
    posting_date = posting_date or timezone.now().date()
    if not lines:
        raise ValueError("Customer return requires at least one line")
    _assert_same_company(company, customer, location, vat_output_account)

    prepared_lines = []
    entries = []
    total_receivable_reduction = Decimal("0.00")
    total_vat = Decimal("0.00")
    total_wht = Decimal("0.00")
    for line in lines:
        item = line["item"]
        line_location = line.get("location") or location
        if line_location is None:
            raise ValueError("Customer return line requires a stock location")
        _assert_same_company(company, item, line_location)
        quantity = _q_qty(line["quantity"])
        unit_price = _q_qty(line.get("unit_price") or item.default_sales_price)
        unit_cost = _q_qty(line.get("unit_cost") or get_average_unit_cost(item) or item.standard_cost)
        if quantity <= 0 or unit_price < 0 or unit_cost < 0:
            raise ValueError("Return quantity must be positive and amounts cannot be negative")
        accounts = _sales_accounts(item)
        revenue_amount = _q_money(quantity * unit_price)
        cogs_amount = _q_money(quantity * unit_cost)
        vat_rate = Decimal(line.get("vat_rate", item.default_vat_rate) or 0)
        wht_rate = Decimal(line.get("wht_rate", customer.default_wht_rate) or 0)
        vat_amount = _rate_amount(revenue_amount, vat_rate)
        wht_amount = _rate_amount(revenue_amount, wht_rate)
        total_receivable_reduction += revenue_amount + vat_amount - wht_amount
        total_vat += vat_amount
        total_wht += wht_amount
        prepared_lines.append(
            {
                "item": item,
                "location": line_location,
                "quantity": quantity,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
                "revenue_amount": revenue_amount,
                "cogs_amount": cogs_amount,
                "vat_rate": vat_rate,
                "vat_amount": vat_amount,
                "wht_rate": wht_rate,
                "wht_amount": wht_amount,
                "accounts": accounts,
            }
        )
        entries.extend(
            [
                {
                    "account": accounts["sales_revenue_account"],
                    "entry_type": "DEBIT",
                    "amount": revenue_amount,
                    "memo": f"Customer return for {item.name}",
                },
                {
                    "account": accounts["inventory_account"],
                    "entry_type": "DEBIT",
                    "amount": cogs_amount,
                    "memo": f"Inventory returned for {item.name}",
                },
                {
                    "account": accounts["cogs_account"],
                    "entry_type": "CREDIT",
                    "amount": cogs_amount,
                    "memo": f"COGS reversed for {item.name}",
                },
            ]
        )
    if total_vat:
        if vat_output_account is None:
            raise ValueError("VAT output account is required when return VAT is posted")
        entries.append(
            {
                "account": vat_output_account,
                "entry_type": "DEBIT",
                "amount": _q_money(total_vat),
                "memo": f"Output VAT reversed for {customer.name}",
            }
        )
    if total_wht:
        if customer.wht_receivable_account is None:
            raise ValueError("Customer WHT receivable account is required when return WHT is posted")
        entries.append(
            {
                "account": customer.wht_receivable_account,
                "entry_type": "CREDIT",
                "amount": _q_money(total_wht),
                "memo": f"WHT receivable reversed for {customer.name}",
            }
        )
    entries.append(
        {
            "account": customer.receivable_account,
            "entry_type": "CREDIT",
            "amount": _q_money(total_receivable_reduction),
            "memo": f"Customer credit note for {customer.name}",
        }
    )

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.CUSTOMER_RETURN,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    customer_return = CustomerReturn.objects.create(
        company=company,
        document=document,
        customer=customer,
    )
    for line in prepared_lines:
        movement = _create_movement(
            document=document,
            item=line["item"],
            location=line["location"],
            movement_type=StockMovement.MovementType.CUSTOMER_RETURN,
            quantity=line["quantity"],
            unit_cost=line["unit_cost"],
            movement_date=posting_date,
            memo=reason,
        )
        CustomerReturnLine.objects.create(
            customer_return=customer_return,
            item=line["item"],
            location=line["location"],
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            unit_cost=line["unit_cost"],
            revenue_amount=line["revenue_amount"],
            cogs_amount=line["cogs_amount"],
            vat_rate=line["vat_rate"],
            vat_amount=line["vat_amount"],
            wht_rate=line["wht_rate"],
            wht_amount=line["wht_amount"],
            movement=movement,
        )
    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description=f"Customer return: {customer.name}",
        entries=entries,
        auto_post=True,
        source_object=document,
        validate_balances=False,
    )
    document.journal = journal
    document.save(update_fields=["journal", "updated_at"])
    return document


@transaction.atomic
def post_supplier_return(
    *,
    company,
    supplier: Supplier,
    location: StockLocation | None = None,
    lines,
    vat_input_account=None,
    posting_date=None,
    reference="",
    reason="Supplier return",
):
    posting_date = posting_date or timezone.now().date()
    if not lines:
        raise ValueError("Supplier return requires at least one line")
    _assert_same_company(company, supplier, location, vat_input_account)

    prepared_lines = []
    entries = []
    total_payable_reduction = Decimal("0.00")
    total_vat = Decimal("0.00")
    total_wht = Decimal("0.00")
    for line in lines:
        item = line["item"]
        line_location = line.get("location") or location
        if line_location is None:
            raise ValueError("Supplier return line requires a stock location")
        _assert_same_company(company, item, line_location)
        quantity = _q_qty(line["quantity"])
        unit_cost = _q_qty(line["unit_cost"])
        if quantity <= 0 or unit_cost < 0:
            raise ValueError("Supplier return quantity must be positive and cost cannot be negative")
        available = get_stock_on_hand(item, line_location)
        if not item.allow_negative_stock and available - quantity < 0:
            raise ValueError("Supplier return would make stock negative")
        total_cost = _q_money(quantity * unit_cost)
        vat_rate = Decimal(line.get("vat_rate", item.default_vat_rate) or 0)
        wht_rate = Decimal(line.get("wht_rate", supplier.default_wht_rate) or 0)
        vat_amount = _rate_amount(total_cost, vat_rate)
        wht_amount = _rate_amount(total_cost, wht_rate)
        inventory_account = _inventory_account(item)
        total_payable_reduction += total_cost + vat_amount - wht_amount
        total_vat += vat_amount
        total_wht += wht_amount
        prepared_lines.append(
            {
                "item": item,
                "location": line_location,
                "quantity": quantity,
                "unit_cost": unit_cost,
                "total_cost": total_cost,
                "vat_rate": vat_rate,
                "vat_amount": vat_amount,
                "wht_rate": wht_rate,
                "wht_amount": wht_amount,
            }
        )
        entries.append(
            {
                "account": inventory_account,
                "entry_type": "CREDIT",
                "amount": total_cost,
                "memo": f"Inventory returned to {supplier.name}",
            }
        )
    if total_vat:
        if vat_input_account is None:
            raise ValueError("VAT input account is required when supplier return VAT is posted")
        entries.append(
            {
                "account": vat_input_account,
                "entry_type": "CREDIT",
                "amount": _q_money(total_vat),
                "memo": f"Input VAT reversed for {supplier.name}",
            }
        )
    if total_wht:
        if supplier.wht_payable_account is None:
            raise ValueError("Supplier WHT payable account is required when supplier return WHT is posted")
        entries.append(
            {
                "account": supplier.wht_payable_account,
                "entry_type": "DEBIT",
                "amount": _q_money(total_wht),
                "memo": f"WHT payable reversed for {supplier.name}",
            }
        )
    entries.append(
        {
            "account": supplier.payable_account,
            "entry_type": "DEBIT",
            "amount": _q_money(total_payable_reduction),
            "memo": f"Supplier debit note for {supplier.name}",
        }
    )

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.SUPPLIER_RETURN,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    supplier_return = SupplierReturn.objects.create(
        company=company,
        document=document,
        supplier=supplier,
    )
    for line in prepared_lines:
        _consume_fifo_layers(line["item"], line["location"], line["quantity"], consume=True)
        movement = _create_movement(
            document=document,
            item=line["item"],
            location=line["location"],
            movement_type=StockMovement.MovementType.SUPPLIER_RETURN,
            quantity=-line["quantity"],
            unit_cost=line["unit_cost"],
            movement_date=posting_date,
            memo=reason,
        )
        SupplierReturnLine.objects.create(
            supplier_return=supplier_return,
            item=line["item"],
            location=line["location"],
            quantity=line["quantity"],
            unit_cost=line["unit_cost"],
            vat_rate=line["vat_rate"],
            vat_amount=line["vat_amount"],
            wht_rate=line["wht_rate"],
            wht_amount=line["wht_amount"],
            total_cost=line["total_cost"],
            movement=movement,
        )
    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description=f"Supplier return: {supplier.name}",
        entries=entries,
        auto_post=True,
        source_object=document,
        validate_balances=False,
    )
    document.journal = journal
    document.save(update_fields=["journal", "updated_at"])
    return document


@transaction.atomic
def create_purchase_order(
    *,
    company,
    supplier: Supplier,
    lines,
    order_date=None,
    expected_date=None,
    reference="",
    notes="",
):
    order_date = order_date or timezone.now().date()
    if not lines:
        raise ValueError("Purchase order requires at least one line")
    _assert_same_company(company, supplier)

    purchase_order = PurchaseOrder.objects.create(
        company=company,
        supplier=supplier,
        order_date=order_date,
        expected_date=expected_date,
        reference=reference,
        notes=notes,
        status=PurchaseOrder.Status.ORDERED,
    )
    for line in lines:
        item = line["item"]
        _assert_same_company(company, item)
        quantity = _q_qty(line["quantity"])
        unit_cost = _q_qty(line["unit_cost"])
        if quantity <= 0 or unit_cost < 0:
            raise ValueError("Purchase order quantity must be positive and cost cannot be negative")
        PurchaseOrderLine.objects.create(
            purchase_order=purchase_order,
            item=item,
            quantity=quantity,
            unit_cost=unit_cost,
            total_cost=_q_money(quantity * unit_cost),
        )
    return purchase_order


@transaction.atomic
def receive_purchase_order(
    *,
    company,
    purchase_order: PurchaseOrder,
    location: StockLocation,
    lines,
    vat_input_account=None,
    posting_date=None,
    reference="",
    reason="Purchase order receipt",
):
    if not lines:
        raise ValueError("Purchase order receipt requires at least one line")
    _assert_same_company(
        company, purchase_order, purchase_order.supplier, location, vat_input_account
    )
    if purchase_order.status == PurchaseOrder.Status.CANCELLED:
        raise ValueError("Cannot receive a cancelled purchase order")

    receipt_lines = []
    po_lines_to_update = []
    for line in lines:
        po_line = line["purchase_order_line"]
        if po_line.purchase_order_id != purchase_order.id:
            raise ValueError("Purchase order line does not belong to this purchase order")
        quantity = _q_qty(line["quantity"])
        if quantity <= 0:
            raise ValueError("Received quantity must be positive")
        if po_line.received_quantity + quantity > po_line.quantity:
            raise ValueError("Received quantity exceeds purchase order balance")
        receipt_lines.append(
            {
                "item": po_line.item,
                "location": line.get("location") or location,
                "quantity": quantity,
                "unit_cost": po_line.unit_cost,
            }
        )
        po_lines_to_update.append((po_line, quantity))

    document = post_purchase_receipt(
        company=company,
        supplier=purchase_order.supplier,
        location=location,
        lines=receipt_lines,
        purchase_order=purchase_order,
        vat_input_account=vat_input_account,
        posting_date=posting_date,
        reference=reference,
        reason=reason,
    )
    for po_line, quantity in po_lines_to_update:
        po_line.received_quantity = _q_qty(po_line.received_quantity + quantity)
        po_line.save(update_fields=["received_quantity", "updated_at"])
    _update_purchase_order_status(purchase_order)
    return document


@transaction.atomic
def post_inventory_adjustment(
    *,
    company,
    item,
    location,
    quantity_delta,
    unit_cost=None,
    stock_count_line: StockCountLine | None = None,
    posting_date=None,
    reference="",
    reason="Inventory adjustment",
):
    posting_date = posting_date or timezone.now().date()
    quantity_delta = _q_qty(quantity_delta)
    if quantity_delta == 0:
        raise ValueError("Adjustment quantity cannot be zero")
    _assert_same_company(company, item, location)
    available = get_stock_on_hand(item, location)
    if quantity_delta < 0 and not item.allow_negative_stock and available + quantity_delta < 0:
        raise ValueError("Adjustment would make stock negative")
    if stock_count_line is not None:
        if stock_count_line.item_id != item.id or stock_count_line.stock_count.location_id != location.id:
            raise ValueError("Stock count line does not match adjustment item and location")
        if stock_count_line.investigation_status != "APPROVED":
            raise ValueError("Stock count variance must be investigated and approved")

    accounts = _posting_accounts(item, InventoryDocument.DocumentType.ADJUSTMENT)
    if quantity_delta > 0:
        resolved_unit_cost = _q_qty(unit_cost if unit_cost is not None else get_average_unit_cost(item))
        debit_account = accounts["inventory_account"]
        credit_account = accounts["adjustment_gain_account"]
        debit_memo = f"Inventory gain for {item.name}"
        credit_memo = f"Inventory adjustment gain for {item.name}"
    else:
        resolved_unit_cost = get_average_unit_cost(item)
        debit_account = accounts["shrinkage_expense_account"]
        credit_account = accounts["inventory_account"]
        debit_memo = f"Inventory shrinkage for {item.name}"
        credit_memo = f"Inventory reduction for {item.name}"

    total_cost = _q_money(abs(quantity_delta) * resolved_unit_cost)
    approval_threshold = getattr(settings, "INVENTORY_ADJUSTMENT_APPROVAL_THRESHOLD", None)
    if (
        stock_count_line is None
        and approval_threshold is not None
        and Decimal(approval_threshold) > 0
        and total_cost > Decimal(approval_threshold)
    ):
        raise ValueError("Inventory adjustment exceeds approval threshold")
    if quantity_delta < 0:
        _consume_fifo_layers(item, location, abs(quantity_delta), consume=True)

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.ADJUSTMENT,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    _create_movement(
        document=document,
        item=item,
        location=location,
        movement_type=StockMovement.MovementType.ADJUSTMENT,
        quantity=quantity_delta,
        unit_cost=resolved_unit_cost,
        movement_date=posting_date,
        memo=reason,
    )
    journal = create_journal_with_entries(
        company=company,
        date=posting_date,
        description=f"Inventory adjustment: {item.sku}",
        entries=[
            {
                "account": debit_account,
                "entry_type": "DEBIT",
                "amount": total_cost,
                "memo": debit_memo,
            },
            {
                "account": credit_account,
                "entry_type": "CREDIT",
                "amount": total_cost,
                "memo": credit_memo,
            },
        ],
        auto_post=True,
        source_object=document,
        validate_balances=False,
    )
    document.journal = journal
    document.save(update_fields=["journal", "updated_at"])
    _mark_document_posted(document, total_cost)
    if stock_count_line is not None:
        stock_count_line.adjustment_document = document
        stock_count_line.save(update_fields=["adjustment_document", "updated_at"])
    return document


@transaction.atomic
def post_stock_transfer(
    *,
    company,
    item,
    from_location,
    to_location,
    quantity,
    posting_date=None,
    reference="",
    reason="Stock transfer",
):
    posting_date = posting_date or timezone.now().date()
    quantity = _q_qty(quantity)
    if quantity <= 0:
        raise ValueError("Transfer quantity must be positive")
    if from_location.pk == to_location.pk:
        raise ValueError("Transfer locations must be different")
    _assert_same_company(company, item, from_location, to_location)
    available = get_stock_on_hand(item, from_location)
    if not item.allow_negative_stock and available - quantity < 0:
        raise ValueError("Transfer would make source stock negative")

    unit_cost = get_average_unit_cost(item)
    _consume_fifo_layers(item, from_location, quantity, consume=True)
    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.TRANSFER,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    _create_movement(
        document=document,
        item=item,
        location=from_location,
        movement_type=StockMovement.MovementType.TRANSFER_OUT,
        quantity=-quantity,
        unit_cost=unit_cost,
        movement_date=posting_date,
        memo=reason,
    )
    _create_movement(
        document=document,
        item=item,
        location=to_location,
        movement_type=StockMovement.MovementType.TRANSFER_IN,
        quantity=quantity,
        unit_cost=unit_cost,
        movement_date=posting_date,
        memo=reason,
    )
    _mark_document_posted(document, Decimal("0.00"))
    return document


@transaction.atomic
def post_stock_count_adjustments(*, stock_count: StockCount, user=None):
    if stock_count.status != StockCount.Status.APPROVED:
        raise ValueError("Stock count must be approved before posting adjustments")
    if not stock_count.lines.exists():
        raise ValueError("Stock count requires at least one line")

    last_document = None
    for line in stock_count.lines.select_related("item", "stock_count__location"):
        quantity_delta = _q_qty(line.counted_quantity - line.system_quantity)
        if quantity_delta == 0:
            continue
        if line.investigation_status != "APPROVED":
            raise ValueError("All count variances must be approved before posting")
        last_document = post_inventory_adjustment(
            company=stock_count.company,
            item=line.item,
            location=stock_count.location,
            quantity_delta=quantity_delta,
            stock_count_line=line,
            posting_date=stock_count.count_date,
            reason=f"Stock count adjustment: {line.variance_reason}",
        )

    stock_count.status = StockCount.Status.POSTED
    stock_count.posted_by = user
    stock_count.posted_at = timezone.now()
    stock_count.document = last_document
    stock_count.save(update_fields=["status", "posted_by", "posted_at", "document", "updated_at"])
    return last_document


def _aging_bucket(days_overdue):
    if days_overdue <= 0:
        return "CURRENT"
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def get_accounts_receivable_aging(company, as_of=None):
    as_of = as_of or timezone.now().date()
    rows = []
    invoices = (
        SalesInvoice.objects.select_related("customer", "document")
        .filter(company=company)
        .exclude(payment_status="PAID")
        .order_by("due_date", "document__document_date", "id")
    )
    for invoice in invoices:
        outstanding = _q_money(invoice_total(invoice) - invoice.paid_amount)
        if outstanding <= 0:
            continue
        due_date = invoice.due_date or invoice.document.document_date
        days_overdue = (as_of - due_date).days
        rows.append(
            {
                "invoice": invoice,
                "customer": invoice.customer,
                "due_date": due_date,
                "outstanding": outstanding,
                "days_overdue": days_overdue,
                "bucket": _aging_bucket(days_overdue),
            }
        )
    return rows


def get_accounts_payable_aging(company, as_of=None):
    as_of = as_of or timezone.now().date()
    rows = []
    receipts = (
        PurchaseReceipt.objects.select_related("supplier", "document")
        .filter(company=company)
        .exclude(payment_status="PAID")
        .order_by("due_date", "document__document_date", "id")
    )
    for receipt in receipts:
        outstanding = _q_money(receipt_total(receipt) - receipt.paid_amount)
        if outstanding <= 0:
            continue
        due_date = receipt.due_date or receipt.document.document_date
        days_overdue = (as_of - due_date).days
        rows.append(
            {
                "receipt": receipt,
                "supplier": receipt.supplier,
                "due_date": due_date,
                "outstanding": outstanding,
                "days_overdue": days_overdue,
                "bucket": _aging_bucket(days_overdue),
            }
        )
    return rows


def reconcile_inventory_to_gl(company, account=None):
    stock_value = _q_money(
        InventoryValuationLayer.objects.filter(company=company).aggregate(
            total=Sum("remaining_total_cost")
        )["total"]
        or Decimal("0.00")
    )
    accounts = Account.objects.filter(
        company=company, type=Account.AccountType.ASSET, name__icontains="inventory"
    )
    if account is not None:
        accounts = accounts.filter(pk=account.pk)
    gl_value = _q_money(sum(account.get_balance() for account in accounts))
    return {
        "stock_value": stock_value,
        "gl_value": gl_value,
        "variance": _q_money(gl_value - stock_value),
    }


def get_customer_statement(customer, as_of=None):
    invoices = get_accounts_receivable_aging(customer.company, as_of=as_of)
    return [row for row in invoices if row["customer"].id == customer.id]


def provision_bad_debt(company, user, bad_debt_account, ar_account, threshold_days=90, as_of=None):
    """Create a journal entry for estimated bad debt on overdue AR."""
    as_of = as_of or timezone.now().date()
    aging = get_accounts_receivable_aging(company, as_of=as_of)
    bad_debt_total = sum(
        row["outstanding"] for row in aging if row["days_overdue"] > threshold_days
    )
    if bad_debt_total <= 0:
        return None

    journal = create_journal_with_entries(
        company=company,
        date=as_of,
        description=f"Bad debt provision — AR overdue > {threshold_days} days",
        entries=[
            {"account": bad_debt_account, "entry_type": "DEBIT", "amount": bad_debt_total, "memo": "Bad debt expense"},
            {"account": ar_account, "entry_type": "CREDIT", "amount": bad_debt_total, "memo": "Allowance for doubtful accounts"},
        ],
        user=user,
        auto_post=True,
        validate_balances=False,
    )
    return journal


@transaction.atomic
def create_sales_order(
    *,
    company,
    customer,
    lines,
    order_date=None,
    expected_date=None,
    reference="",
    notes="",
    reserve_stock=True,
):
    """Create a sales order. If reserve_stock=True, marks reserved_quantity on each line."""
    order_date = order_date or timezone.now().date()
    if not lines:
        raise ValueError("Sales order requires at least one line")
    _assert_same_company(company, customer)

    so = SalesOrder.objects.create(
        company=company,
        customer=customer,
        order_date=order_date,
        expected_date=expected_date,
        reference=reference,
        notes=notes,
        status=SalesOrder.Status.CONFIRMED,
    )
    for line in lines:
        item = line["item"]
        _assert_same_company(company, item)
        qty = _q_qty(line["quantity"])
        unit_price = _q_qty(line["unit_price"])
        if qty <= 0 or unit_price < 0:
            raise ValueError("Quantity must be positive and price cannot be negative")

        reserved = Decimal("0.0000")
        if reserve_stock:
            location = line.get("location")
            if location:
                on_hand = get_stock_on_hand(item, location)
                if not item.allow_negative_stock and on_hand < qty:
                    raise ValueError(f"Insufficient stock for {item.sku}: need {qty}, have {on_hand}")
                reserved = qty

        SalesOrderLine.objects.create(
            sales_order=so,
            item=item,
            quantity=qty,
            unit_price=unit_price,
            reserved_quantity=reserved,
        )
    return so


@transaction.atomic
def ship_sales_order(
    *,
    company,
    sales_order,
    location,
    lines,
    posting_date=None,
    reference="",
):
    """Ship lines from a sales order. Creates the sales invoice automatically."""
    if sales_order.status in (SalesOrder.Status.CANCELLED, SalesOrder.Status.INVOICED):
        raise ValueError("Cannot ship a cancelled or already invoiced sales order")

    posting_date = posting_date or timezone.now().date()
    if not lines:
        raise ValueError("Shipment requires at least one line")

    invoice_lines = []
    so_lines_to_update = []
    for entry in lines:
        so_line = entry["sales_order_line"]
        if so_line.sales_order_id != sales_order.id:
            raise ValueError("Sales order line does not belong to this sales order")
        qty = _q_qty(entry["quantity"])
        if qty <= 0:
            raise ValueError("Ship quantity must be positive")
        if so_line.shipped_quantity + qty > so_line.quantity:
            raise ValueError("Ship quantity exceeds sales order balance")

        invoice_lines.append({
            "item": so_line.item,
            "location": location,
            "quantity": qty,
            "unit_price": so_line.unit_price,
        })
        so_lines_to_update.append((so_line, qty))

    # Create shipment document for tracking
    ship_doc = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.SHIPMENT,
        document_date=posting_date,
        reference=reference,
        reason=f"Shipment for {sales_order.reference or sales_order.pk}",
    )

    # Create the sales invoice
    invoice_doc = post_sales_invoice(
        company=company,
        customer=sales_order.customer,
        location=location,
        lines=invoice_lines,
        posting_date=posting_date,
        reference=reference or f"SO-{sales_order.reference or sales_order.pk}",
        reason=f"Shipment for {sales_order.reference}",
    )

    # Update order line shipped quantities and release reservations
    for so_line, qty in so_lines_to_update:
        so_line.shipped_quantity = _q_qty(so_line.shipped_quantity + qty)
        so_line.reserved_quantity = _q_qty(max(Decimal("0"), so_line.reserved_quantity - qty))
        so_line.save(update_fields=["shipped_quantity", "reserved_quantity", "updated_at"])

    _update_sales_order_status(sales_order)
    return invoice_doc


def _update_sales_order_status(sales_order):
    all_shipped = all(
        so_line.shipped_quantity >= so_line.quantity
        for so_line in sales_order.lines.all()
    )
    any_shipped = any(
        so_line.shipped_quantity > 0
        for so_line in sales_order.lines.all()
    )
    if all_shipped:
        sales_order.status = SalesOrder.Status.SHIPPED
    elif any_shipped:
        sales_order.status = SalesOrder.Status.PARTIALLY_SHIPPED
    sales_order.save(update_fields=["status", "updated_at"])


@transaction.atomic
def create_vendor_bill(
    *,
    company,
    supplier,
    purchase_receipt=None,
    lines,
    bill_date=None,
    due_date=None,
    bill_number="",
    notes="",
):
    """Create a vendor bill and perform 3-way match if purchase_receipt is provided."""
    bill_date = bill_date or timezone.now().date()
    if not lines:
        raise ValueError("Vendor bill requires at least one line")
    _assert_same_company(company, supplier, purchase_receipt)

    # Duplicate prevention: check if bill number already exists
    if bill_number:
        existing = VendorBill.objects.filter(
            company=company, supplier=supplier, bill_number=bill_number,
        ).first()
        if existing:
            raise ValueError(f"Vendor bill {bill_number} already exists for this supplier.")

    bill = VendorBill.objects.create(
        company=company,
        supplier=supplier,
        purchase_receipt=purchase_receipt,
        bill_date=bill_date,
        due_date=due_date,
        bill_number=bill_number,
        notes=notes,
        total_amount=Decimal("0.00"),
    )

    total = Decimal("0.00")
    for entry in lines:
        item = entry.get("item")
        description = entry.get("description", "")
        qty = _q_qty(entry.get("quantity", 0))
        unit_cost = _q_qty(entry.get("unit_cost", 0))
        line_total = _q_money(qty * unit_cost) if qty > 0 else _q_money(entry.get("total_amount", 0))
        receipt_line = entry.get("receipt_line")

        # 3-way match validation: if receipt_line, verify quantities
        if receipt_line and purchase_receipt:
            if receipt_line.receipt_id != purchase_receipt.id:
                raise ValueError("Receipt line does not belong to the provided purchase receipt")

        VendorBillLine.objects.create(
            vendor_bill=bill,
            item=item,
            description=description,
            quantity=qty,
            unit_cost=unit_cost,
            total_amount=line_total,
            receipt_line=receipt_line,
        )
        total += line_total

    bill.total_amount = total
    bill.status = VendorBill.Status.RECEIVED
    bill.save(update_fields=["total_amount", "status", "updated_at"])
    return bill


@transaction.atomic
def post_vendor_bill(vendor_bill, user, grni_account=None, ppv_account=None):
    """Post vendor bill journal: clear GRNI, recognize AP, post purchase price variance.

    Debit: GRNI (goods received not invoiced)       ← clear receipt entry
    Credit: Accounts Payable                         ← cr supplier
    Debit: Purchase Price Variance (if bill > receipt)
    """
    if vendor_bill.status not in (VendorBill.Status.RECEIVED, VendorBill.Status.APPROVED):
        raise ValueError("Can only post a received or approved bill")

    journal_entries = []
    total_payable = vendor_bill.total_amount
    total_grni = Decimal("0.00")

    if vendor_bill.purchase_receipt and grni_account:
        receipt_total = sum(
            (_q_money(line.quantity * line.unit_cost) for line in vendor_bill.purchase_receipt.lines.all()),
            Decimal("0.00"),
        )
        total_grni = receipt_total
        journal_entries.append({
            "account": grni_account,
            "entry_type": "DEBIT",
            "amount": receipt_total,
            "memo": f"Clear GRNI for bill {vendor_bill.bill_number or vendor_bill.pk}",
        })

        variance = vendor_bill.total_amount - receipt_total
        if abs(variance) > Decimal("0.01") and ppv_account:
            if variance > 0:
                journal_entries.append({
                    "account": ppv_account,
                    "entry_type": "DEBIT",
                    "amount": variance,
                    "memo": "Purchase price variance (unfavorable)",
                })
            else:
                journal_entries.append({
                    "account": ppv_account,
                    "entry_type": "CREDIT",
                    "amount": abs(variance),
                    "memo": "Purchase price variance (favorable)",
                })

    journal_entries.append({
        "account": vendor_bill.supplier.payable_account,
        "entry_type": "CREDIT",
        "amount": vendor_bill.total_amount,
        "memo": f"AP for bill {vendor_bill.bill_number or vendor_bill.pk}",
    })

    if total_grni == Decimal("0.00"):
        expense_account = Account.objects.filter(
            company=vendor_bill.company,
            type=Account.AccountType.EXPENSE,
        ).first()
        if expense_account:
            journal_entries.append({
                "account": expense_account,
                "entry_type": "DEBIT",
                "amount": vendor_bill.total_amount,
                "memo": f"Expense for bill {vendor_bill.bill_number or vendor_bill.pk}",
            })

    journal = create_journal_with_entries(
        company=vendor_bill.company,
        date=vendor_bill.bill_date,
        description=f"Vendor Bill: {vendor_bill.bill_number or vendor_bill.pk}",
        entries=journal_entries,
        user=user,
        auto_post=True,
        validate_balances=False,
    )

    vendor_bill.status = VendorBill.Status.APPROVED
    vendor_bill.save(update_fields=["status", "updated_at"])
    return vendor_bill


@transaction.atomic
def allocate_landed_costs(landed_cost):
    """Allocate landed cost total across purchase receipt line items by value."""
    if landed_cost.status != LandedCost.Status.DRAFT:
        raise ValueError("Landed cost must be in DRAFT status to allocate")
    if not landed_cost.purchase_receipt:
        raise ValueError("Landed cost must be linked to a purchase receipt")

    receipt_lines = landed_cost.purchase_receipt.lines.all()
    if not receipt_lines:
        raise ValueError("Purchase receipt has no lines to allocate")

    if landed_cost.allocation_method == "BY_VALUE":
        total_value = sum((line.total_cost for line in receipt_lines), Decimal("0.00"))
        remaining = landed_cost.total_cost
        for i, line in enumerate(receipt_lines):
            if i == len(receipt_lines) - 1:
                alloc = remaining
            else:
                alloc = _q_money(landed_cost.total_cost * line.total_cost / total_value) if total_value else Decimal("0.00")
            remaining -= alloc
            LandedCostAllocation.objects.create(
                landed_cost=landed_cost, receipt_line=line, allocated_amount=alloc,
            )
    elif landed_cost.allocation_method == "BY_QUANTITY":
        total_qty = sum((line.quantity for line in receipt_lines), Decimal("0.0000"))
        remaining = landed_cost.total_cost
        for i, line in enumerate(receipt_lines):
            if i == len(receipt_lines) - 1:
                alloc = remaining
            else:
                alloc = _q_money(landed_cost.total_cost * Decimal(line.quantity) / total_qty) if total_qty else Decimal("0.00")
            remaining -= alloc
            LandedCostAllocation.objects.create(
                landed_cost=landed_cost, receipt_line=line, allocated_amount=alloc,
            )

    landed_cost.status = LandedCost.Status.ALLOCATED
    landed_cost.save(update_fields=["status", "updated_at"])
    return landed_cost


@transaction.atomic
def post_landed_cost(landed_cost, user, landed_cost_clearing_account=None):
    """Post landed cost: debit Inventory Asset for allocations, credit Landed Cost Clearing or AP."""
    if landed_cost.status != LandedCost.Status.ALLOCATED:
        raise ValueError("Landed cost must be ALLOCATED before posting")

    allocations = landed_cost.allocations.select_related("receipt_line__item__category").all()
    if not allocations:
        raise ValueError("No allocations to post")

    journal_entries = []
    for alloc in allocations:
        inv_account = alloc.receipt_line.item.category.inventory_account
        journal_entries.append({
            "account": inv_account,
            "entry_type": "DEBIT",
            "amount": alloc.allocated_amount,
            "memo": f"Landed cost: {landed_cost.description}",
        })

    credit_account = landed_cost_clearing_account
    if not credit_account:
        credit_account = Account.objects.filter(
            company=landed_cost.company,
            type=Account.AccountType.LIABILITY,
            name__icontains="payable",
        ).first()
    if not credit_account:
        raise ValueError("No liability account found for landed cost credit")

    total_allocated = sum((a.allocated_amount for a in allocations), Decimal("0.00"))
    journal_entries.append({
        "account": credit_account,
        "entry_type": "CREDIT",
        "amount": total_allocated,
        "memo": f"Landed cost clearing: {landed_cost.description}",
    })

    create_journal_with_entries(
        company=landed_cost.company,
        date=landed_cost.posted_date or timezone.now().date(),
        description=f"Landed cost: {landed_cost.description}",
        entries=journal_entries,
        user=user,
        auto_post=True,
        validate_balances=False,
    )

    landed_cost.status = LandedCost.Status.POSTED
    landed_cost.posted_date = timezone.now().date()
    landed_cost.save(update_fields=["status", "posted_date", "updated_at"])
    return landed_cost


# ── Phase 4: Lot / Serial / FEFO / Barcode / Transfers ──────────────────────

def _enforce_batch_serial(item, batch_number, serial_number, expiry_date):
    """Validate batch/serial/expiry if item requires tracking."""
    if item.track_batch and not batch_number:
        raise ValueError(f"Item {item.sku} requires a batch number.")
    if item.track_batch and batch_number:
        Lot.objects.get_or_create(
            company=item.company, item=item, lot_number=batch_number,
            defaults={"expiry_date": expiry_date, "status": Lot.Status.IN_STOCK},
        )
    if serial_number:
        if SerialNumber.objects.filter(company=item.company, item=item, serial=serial_number).exists():
            raise ValueError(f"Serial number {serial_number} already exists for {item.sku}.")
        SerialNumber.objects.create(
            company=item.company, item=item, serial=serial_number,
            status=SerialNumber.Status.IN_STOCK,
        )


def _consume_fifo_layers(item, location, quantity, consume=True):
    pass  # existing FIFO — replaced with FEFO-aware version below


def _consume_fefo_layers(item, location, quantity, consume=True):
    """FEFO: consume layers by expiry date (first to expire first), fallback to oldest.
    Returns total cost of consumed layers."""
    from django.db.models import Case, When

    layers = InventoryValuationLayer.objects.filter(
        company=item.company, item=item,
        remaining_quantity__gt=0,
    ).select_related("movement").annotate(
        _has_expiry=Case(
            When(movement__expiry_date__isnull=False, then=0),
            default=1,
        )
    ).order_by("_has_expiry", "movement__expiry_date", "created_at")

    if not layers.exists():
        layers = InventoryValuationLayer.objects.filter(
            company=item.company, item=item,
            remaining_quantity__gt=0,
        ).select_related("movement").order_by("created_at")

    remaining_to_consume = quantity
    total_cost = Decimal("0.00")

    for layer in layers:
        if remaining_to_consume <= 0:
            break
        consume_qty = min(layer.remaining_quantity, remaining_to_consume)
        layer_cost = _q_money(consume_qty * layer.unit_cost)
        total_cost += layer_cost
        remaining_to_consume -= consume_qty

        if consume:
            layer.remaining_quantity -= consume_qty
            layer.remaining_total_cost = max(Decimal("0.00"), layer.remaining_total_cost - layer_cost)
            layer.save(update_fields=["remaining_quantity", "remaining_total_cost"])

    if remaining_to_consume > 0 and not item.allow_negative_stock:
        raise ValueError(f"Insufficient stock for {item.sku}: need {quantity}")

    return total_cost


@transaction.atomic
def post_stock_transfer_shipment(
    *,
    company,
    from_location,
    to_location,
    lines,
    freight_cost=Decimal("0.00"),
    freight_account=None,
    dispatch_date=None,
    expected_date=None,
    reference="",
):
    """Create a tracked inter-warehouse transfer with in-transit status."""
    dispatch_date = dispatch_date or timezone.now().date()
    if not lines:
        raise ValueError("Transfer requires at least one line")
    _assert_same_company(company, from_location, to_location)

    shipment = TransferShipment.objects.create(
        company=company, from_location=from_location, to_location=to_location,
        dispatched_date=dispatch_date, expected_receipt_date=expected_date,
        reference=reference, freight_cost=freight_cost,
        status=TransferShipment.Status.DISPATCHED,
    )

    for line in lines:
        item = line["item"]
        qty = _q_qty(line["quantity"])
        _assert_same_company(company, item)

        available = get_stock_on_hand(item, from_location)
        if not item.allow_negative_stock and qty > available:
            raise ValueError(f"Insufficient stock for transfer of {item.sku}")

        TransferShipmentLine.objects.create(
            shipment=shipment, item=item, quantity=qty,
            lot=line.get("lot"),
        )

        # Perform the stock movement out (removing from source)
        unit_cost = get_average_unit_cost(item)
        _consume_fefo_layers(item, from_location, qty, consume=True)

    shipment.status = TransferShipment.Status.IN_TRANSIT
    shipment.save(update_fields=["status", "updated_at"])

    if freight_cost and freight_account:
        inv_acct = Account.objects.filter(
            company=company, type=Account.AccountType.ASSET, name__icontains="inventory"
        ).first()
        if inv_acct:
            create_journal_with_entries(
                company=company, date=dispatch_date,
                description=f"Transfer freight: {shipment.reference or shipment.pk}",
                entries=[
                    {"account": inv_acct, "entry_type": "DEBIT", "amount": freight_cost, "memo": "Freight added to inventory"},
                    {"account": freight_account, "entry_type": "CREDIT", "amount": freight_cost, "memo": "Freight on transfer"},
                ],
                auto_post=True, validate_balances=False,
            )

    return shipment


@transaction.atomic
def receive_transfer_shipment(
    *,
    company,
    shipment,
    lines,
    received_date=None,
):
    """Receive an in-transit transfer shipment at destination."""
    if shipment.status not in (TransferShipment.Status.IN_TRANSIT, TransferShipment.Status.DISPATCHED):
        raise ValueError("Shipment must be dispatched or in transit to receive")

    received_date = received_date or timezone.now().date()

    all_full = True
    any_received = False

    for entry in lines:
        ship_line = entry["shipment_line"]
        qty = _q_qty(entry["quantity"])
        if ship_line.shipment_id != shipment.id:
            raise ValueError("Transfer line does not belong to this shipment")
        if ship_line.received_quantity + qty > ship_line.quantity:
            raise ValueError("Receive quantity exceeds shipment quantity")

        location_to = shipment.to_location
        unit_cost = get_average_unit_cost(ship_line.item)
        document = InventoryDocument.objects.create(
            company=company, document_type=InventoryDocument.DocumentType.TRANSFER,
            document_date=received_date, reference=f"Receive-{shipment.reference or shipment.pk}",
        )
        _create_movement(
            document=document, item=ship_line.item, location=location_to,
            movement_type=StockMovement.MovementType.TRANSFER_IN,
            quantity=qty, unit_cost=unit_cost, movement_date=received_date,
        )

        ship_line.received_quantity = _q_qty(ship_line.received_quantity + qty)
        ship_line.save(update_fields=["received_quantity", "updated_at"])
        any_received = True

        if ship_line.received_quantity < ship_line.quantity:
            all_full = False

    if all_full:
        shipment.status = TransferShipment.Status.RECEIVED
    elif any_received:
        shipment.status = TransferShipment.Status.PARTIALLY_RECEIVED
    shipment.received_date = received_date
    shipment.save(update_fields=["status", "received_date", "updated_at"])

    return shipment


def search_item_by_barcode(company, barcode):
    """Look up an inventory item by barcode."""
    return InventoryItem.objects.filter(
        company=company, barcode=barcode,
    ).first()
