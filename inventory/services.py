from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounting.models import Account
from accounting.utils import create_journal_with_entries
from inventory.models import (
    Customer,
    CustomerPayment,
    CustomerReturn,
    CustomerReturnLine,
    InventoryDocument,
    InventoryItem,
    InventoryValuationLayer,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    SalesInvoice,
    SalesInvoiceLine,
    Supplier,
    SupplierPayment,
    SupplierReturn,
    SupplierReturnLine,
    TaxRemittance,
    StockLocation,
    StockMovement,
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


def _posting_accounts(item):
    category = item.category
    required = {
        "inventory_account": category.inventory_account,
        "opening_balance_equity_account": category.opening_balance_equity_account,
        "adjustment_gain_account": category.adjustment_gain_account,
        "shrinkage_expense_account": category.shrinkage_expense_account,
    }
    missing = [name for name, account in required.items() if account is None]
    if missing:
        raise ValueError(f"Missing inventory posting accounts: {', '.join(missing)}")
    for account in required.values():
        if account.company_id != item.company_id:
            raise ValueError("Inventory posting account belongs to a different company")
    return required


def _inventory_account(item):
    account = item.category.inventory_account
    if account is None:
        raise ValueError("Missing inventory posting account: inventory_account")
    if account.company_id != item.company_id:
        raise ValueError("Inventory posting account belongs to a different company")
    return account


def _sales_accounts(item):
    category = item.category
    required = {
        "inventory_account": category.inventory_account,
        "sales_revenue_account": category.sales_revenue_account,
        "cogs_account": category.cogs_account,
    }
    missing = [name for name, account in required.items() if account is None]
    if missing:
        raise ValueError(f"Missing sales posting accounts: {', '.join(missing)}")
    for account in required.values():
        if account.company_id != item.company_id:
            raise ValueError("Sales posting account belongs to a different company")
    return required


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
        movement_date=movement_date,
        memo=memo,
    )
    InventoryValuationLayer.objects.create(
        company=document.company,
        movement=movement,
        item=item,
        quantity=quantity,
        unit_cost=unit_cost,
        total_cost=total_cost,
    )
    return movement


@transaction.atomic
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
    accounts = _posting_accounts(item)
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
    if supplier.payable_account.company_id != company.id:
        raise ValueError("Supplier payable account belongs to a different company")

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
        vat_rate = Decimal(line.get("vat_rate", getattr(item, "default_vat_rate", 0)) or 0)
        wht_rate = Decimal(line.get("wht_rate", getattr(supplier, "default_wht_rate", 0)) or 0)
        vat_amount = _rate_amount(total_cost, vat_rate)
        wht_amount = _rate_amount(total_cost, wht_rate)
        inventory_account = _inventory_account(item)
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
    if customer.receivable_account.company_id != company.id:
        raise ValueError("Customer receivable account belongs to a different company")

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
        unit_cost = get_average_unit_cost(item) or item.standard_cost
        revenue_amount = _q_money(quantity * unit_price)
        cogs_amount = _q_money(quantity * unit_cost)
        vat_rate = Decimal(line.get("vat_rate", item.default_vat_rate) or 0)
        wht_rate = Decimal(line.get("wht_rate", customer.default_wht_rate) or 0)
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

    document = InventoryDocument.objects.create(
        company=company,
        document_type=InventoryDocument.DocumentType.SALES_INVOICE,
        document_date=posting_date,
        reference=reference,
        reason=reason,
    )
    invoice = SalesInvoice.objects.create(
        company=company,
        document=document,
        customer=customer,
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
    return document


@transaction.atomic
def post_customer_payment(
    *,
    company,
    customer: Customer,
    cash_account,
    amount,
    posting_date=None,
    reference="",
    reason="Customer payment",
):
    posting_date = posting_date or timezone.now().date()
    amount = _assert_positive_money(amount)
    _assert_same_company(company, customer, cash_account)
    if customer.receivable_account.company_id != company.id:
        raise ValueError("Customer receivable account belongs to a different company")

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
    return document


@transaction.atomic
def post_supplier_payment(
    *,
    company,
    supplier: Supplier,
    cash_account,
    amount,
    posting_date=None,
    reference="",
    reason="Supplier payment",
):
    posting_date = posting_date or timezone.now().date()
    amount = _assert_positive_money(amount)
    _assert_same_company(company, supplier, cash_account)
    if supplier.payable_account.company_id != company.id:
        raise ValueError("Supplier payable account belongs to a different company")

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
    posting_date=None,
    reference="",
    reason="Purchase order receipt",
):
    if not lines:
        raise ValueError("Purchase order receipt requires at least one line")
    _assert_same_company(company, purchase_order, purchase_order.supplier, location)
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

    accounts = _posting_accounts(item)
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
    return document
