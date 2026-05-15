from django import forms
from django.db.models import F
from decimal import Decimal

from accounting.models import Account
from inventory.models import (
    Customer,
    InventoryCategory,
    InventoryItem,
    PurchaseOrderLine,
    StockLocation,
    Supplier,
    UnitOfMeasure,
    Warehouse,
)


FORM_CONTROL = (
    "block w-full rounded-md border-secondary-300 shadow-sm "
    "focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
)
CHECKBOX_CONTROL = "h-4 w-4 rounded border-secondary-300 text-primary-600 focus:ring-primary-500"


def _style_fields(fields):
    for field in fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.setdefault("class", CHECKBOX_CONTROL)
        else:
            field.widget.attrs.setdefault("class", FORM_CONTROL)


def _accounts_for(company, *account_types):
    return Account.objects.filter(company=company, type__in=account_types).order_by(
        "account_number", "name"
    )


class CompanyScopedModelForm(forms.ModelForm):
    company_scoped_fields = ()

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        if company is not None:
            self.instance.company = company
        _style_fields(self.fields)
        if company is not None:
            for field_name, model in self.company_scoped_fields:
                if field_name in self.fields:
                    self.fields[field_name].queryset = model.objects.filter(company=company)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.company is not None:
            instance.company = self.company
        if commit:
            instance.full_clean()
            instance.save()
            self.save_m2m()
        return instance


class UnitOfMeasureForm(CompanyScopedModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ["name", "abbreviation"]


class InventoryCategoryForm(CompanyScopedModelForm):
    class Meta:
        model = InventoryCategory
        fields = [
            "name",
            "costing_method",
            "inventory_account",
            "opening_balance_equity_account",
            "adjustment_gain_account",
            "shrinkage_expense_account",
            "sales_revenue_account",
            "cogs_account",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.company is not None:
            self.fields["inventory_account"].queryset = _accounts_for(
                self.company, Account.AccountType.ASSET
            )
            self.fields["opening_balance_equity_account"].queryset = _accounts_for(
                self.company, Account.AccountType.EQUITY
            )
            self.fields["adjustment_gain_account"].queryset = _accounts_for(
                self.company, Account.AccountType.REVENUE
            )
            self.fields["shrinkage_expense_account"].queryset = _accounts_for(
                self.company, Account.AccountType.EXPENSE
            )
            self.fields["sales_revenue_account"].queryset = _accounts_for(
                self.company, Account.AccountType.REVENUE
            )
            self.fields["cogs_account"].queryset = _accounts_for(
                self.company, Account.AccountType.EXPENSE
            )


class InventoryItemForm(CompanyScopedModelForm):
    company_scoped_fields = (
        ("category", InventoryCategory),
        ("base_unit", UnitOfMeasure),
    )

    class Meta:
        model = InventoryItem
        fields = [
            "category",
            "sku",
            "name",
            "item_type",
            "base_unit",
            "barcode",
            "track_batch",
            "track_expiry",
            "allow_negative_stock",
            "reorder_point",
            "standard_cost",
            "default_sales_price",
            "default_vat_rate",
            "default_wht_rate",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in [
            "standard_cost",
            "default_sales_price",
            "default_vat_rate",
            "default_wht_rate",
        ]:
            self.fields[field_name].required = False

    def clean(self):
        cleaned_data = super().clean()
        for field_name in [
            "standard_cost",
            "default_sales_price",
            "default_vat_rate",
            "default_wht_rate",
        ]:
            cleaned_data[field_name] = cleaned_data.get(field_name) or Decimal("0")
        return cleaned_data


class WarehouseForm(CompanyScopedModelForm):
    class Meta:
        model = Warehouse
        fields = ["code", "name", "is_active"]


class StockLocationForm(CompanyScopedModelForm):
    company_scoped_fields = (("warehouse", Warehouse),)

    class Meta:
        model = StockLocation
        fields = ["warehouse", "code", "name", "is_active"]


class SupplierForm(CompanyScopedModelForm):
    class Meta:
        model = Supplier
        fields = [
            "name",
            "contact_name",
            "email",
            "phone",
            "payable_account",
            "wht_payable_account",
            "default_wht_rate",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_wht_rate"].required = False
        if self.company is not None:
            liabilities = _accounts_for(self.company, Account.AccountType.LIABILITY)
            self.fields["payable_account"].queryset = liabilities
            self.fields["wht_payable_account"].queryset = liabilities

    def clean_default_wht_rate(self):
        return self.cleaned_data.get("default_wht_rate") or Decimal("0")


class CustomerForm(CompanyScopedModelForm):
    class Meta:
        model = Customer
        fields = [
            "name",
            "contact_name",
            "email",
            "phone",
            "receivable_account",
            "wht_receivable_account",
            "default_wht_rate",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_wht_rate"].required = False
        if self.company is not None:
            assets = _accounts_for(self.company, Account.AccountType.ASSET)
            self.fields["receivable_account"].queryset = assets
            self.fields["wht_receivable_account"].queryset = assets

    def clean_default_wht_rate(self):
        return self.cleaned_data.get("default_wht_rate") or Decimal("0")


class InventoryActionForm(forms.Form):
    posting_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    reference = forms.CharField(required=False, max_length=80)
    reason = forms.CharField(required=False, max_length=255)

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        _style_fields(self.fields)


class PurchaseOrderForm(InventoryActionForm):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none())
    item = forms.ModelChoiceField(queryset=InventoryItem.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    unit_cost = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    expected_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(required=False, max_length=255)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["supplier"].queryset = Supplier.objects.filter(company=company, is_active=True)
            self.fields["item"].queryset = InventoryItem.objects.filter(company=company, is_active=True)


class PurchaseOrderReceiveForm(InventoryActionForm):
    purchase_order_line = forms.ModelChoiceField(queryset=PurchaseOrderLine.objects.none())
    location = forms.ModelChoiceField(queryset=StockLocation.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)

    def __init__(self, *args, company=None, purchase_order=None, **kwargs):
        self.purchase_order = purchase_order
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["location"].queryset = StockLocation.objects.filter(
                company=company, is_active=True
            ).select_related("warehouse")
        if purchase_order is not None:
            self.fields["purchase_order_line"].queryset = purchase_order.lines.filter(
                received_quantity__lt=F("quantity")
            ).select_related("item")


class OpeningStockForm(InventoryActionForm):
    item = forms.ModelChoiceField(queryset=InventoryItem.objects.none())
    location = forms.ModelChoiceField(queryset=StockLocation.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    unit_cost = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["item"].queryset = InventoryItem.objects.filter(company=company, is_active=True)
            self.fields["location"].queryset = StockLocation.objects.filter(
                company=company, is_active=True
            ).select_related("warehouse")


class PurchaseReceiptForm(InventoryActionForm):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none())
    item = forms.ModelChoiceField(queryset=InventoryItem.objects.none())
    location = forms.ModelChoiceField(queryset=StockLocation.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    unit_cost = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    vat_rate = forms.DecimalField(max_digits=7, decimal_places=4, min_value=0, required=False)
    wht_rate = forms.DecimalField(max_digits=7, decimal_places=4, min_value=0, required=False)
    vat_input_account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["supplier"].queryset = Supplier.objects.filter(company=company, is_active=True)
            self.fields["item"].queryset = InventoryItem.objects.filter(company=company, is_active=True)
            self.fields["location"].queryset = StockLocation.objects.filter(
                company=company, is_active=True
            ).select_related("warehouse")
            self.fields["vat_input_account"].queryset = _accounts_for(
                company, Account.AccountType.ASSET
            )


class SalesInvoiceForm(InventoryActionForm):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    item = forms.ModelChoiceField(queryset=InventoryItem.objects.none())
    location = forms.ModelChoiceField(queryset=StockLocation.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    unit_price = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    vat_rate = forms.DecimalField(max_digits=7, decimal_places=4, min_value=0, required=False)
    wht_rate = forms.DecimalField(max_digits=7, decimal_places=4, min_value=0, required=False)
    vat_output_account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.filter(company=company, is_active=True)
            self.fields["item"].queryset = InventoryItem.objects.filter(company=company, is_active=True)
            self.fields["location"].queryset = StockLocation.objects.filter(
                company=company, is_active=True
            ).select_related("warehouse")
            self.fields["vat_output_account"].queryset = _accounts_for(
                company, Account.AccountType.LIABILITY
            )


class CustomerReturnForm(InventoryActionForm):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    item = forms.ModelChoiceField(queryset=InventoryItem.objects.none())
    location = forms.ModelChoiceField(queryset=StockLocation.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    unit_price = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    unit_cost = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    vat_rate = forms.DecimalField(max_digits=7, decimal_places=4, min_value=0, required=False)
    wht_rate = forms.DecimalField(max_digits=7, decimal_places=4, min_value=0, required=False)
    vat_output_account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.filter(company=company, is_active=True)
            self.fields["item"].queryset = InventoryItem.objects.filter(company=company, is_active=True)
            self.fields["location"].queryset = StockLocation.objects.filter(
                company=company, is_active=True
            ).select_related("warehouse")
            self.fields["vat_output_account"].queryset = _accounts_for(
                company, Account.AccountType.LIABILITY
            )


class SupplierReturnForm(InventoryActionForm):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none())
    item = forms.ModelChoiceField(queryset=InventoryItem.objects.none())
    location = forms.ModelChoiceField(queryset=StockLocation.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    unit_cost = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    vat_rate = forms.DecimalField(max_digits=7, decimal_places=4, min_value=0, required=False)
    wht_rate = forms.DecimalField(max_digits=7, decimal_places=4, min_value=0, required=False)
    vat_input_account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["supplier"].queryset = Supplier.objects.filter(company=company, is_active=True)
            self.fields["item"].queryset = InventoryItem.objects.filter(company=company, is_active=True)
            self.fields["location"].queryset = StockLocation.objects.filter(
                company=company, is_active=True
            ).select_related("warehouse")
            self.fields["vat_input_account"].queryset = _accounts_for(
                company, Account.AccountType.ASSET
            )


class CustomerPaymentForm(InventoryActionForm):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    cash_account = forms.ModelChoiceField(queryset=Account.objects.none())
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.filter(company=company, is_active=True)
            self.fields["cash_account"].queryset = _accounts_for(
                company, Account.AccountType.ASSET
            )


class SupplierPaymentForm(InventoryActionForm):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none())
    cash_account = forms.ModelChoiceField(queryset=Account.objects.none())
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["supplier"].queryset = Supplier.objects.filter(company=company, is_active=True)
            self.fields["cash_account"].queryset = _accounts_for(
                company, Account.AccountType.ASSET
            )


class TaxRemittanceForm(InventoryActionForm):
    cash_account = forms.ModelChoiceField(queryset=Account.objects.none())
    vat_output_account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False)
    vat_input_account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False)
    wht_payable_account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False)
    vat_output_amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False)
    vat_input_amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False)
    wht_amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["cash_account"].queryset = _accounts_for(
                company, Account.AccountType.ASSET
            )
            self.fields["vat_output_account"].queryset = _accounts_for(
                company, Account.AccountType.LIABILITY
            )
            self.fields["vat_input_account"].queryset = _accounts_for(
                company, Account.AccountType.ASSET
            )
            self.fields["wht_payable_account"].queryset = _accounts_for(
                company, Account.AccountType.LIABILITY
            )


class InventoryAdjustmentForm(InventoryActionForm):
    item = forms.ModelChoiceField(queryset=InventoryItem.objects.none())
    location = forms.ModelChoiceField(queryset=StockLocation.objects.none())
    quantity_delta = forms.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            self.fields["item"].queryset = InventoryItem.objects.filter(company=company, is_active=True)
            self.fields["location"].queryset = StockLocation.objects.filter(
                company=company, is_active=True
            ).select_related("warehouse")

    def clean_quantity_delta(self):
        quantity_delta = self.cleaned_data["quantity_delta"]
        if quantity_delta == 0:
            raise forms.ValidationError("Adjustment quantity cannot be zero.")
        return quantity_delta


class StockTransferForm(InventoryActionForm):
    item = forms.ModelChoiceField(queryset=InventoryItem.objects.none())
    from_location = forms.ModelChoiceField(queryset=StockLocation.objects.none())
    to_location = forms.ModelChoiceField(queryset=StockLocation.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=4, min_value=0)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, company=company, **kwargs)
        if company is not None:
            locations = StockLocation.objects.filter(company=company, is_active=True).select_related(
                "warehouse"
            )
            self.fields["item"].queryset = InventoryItem.objects.filter(company=company, is_active=True)
            self.fields["from_location"].queryset = locations
            self.fields["to_location"].queryset = locations

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("from_location") == cleaned_data.get("to_location"):
            raise forms.ValidationError("Transfer locations must be different.")
        return cleaned_data
