from django.core.management.base import BaseCommand
from accounting.models import Account
from company.models import Company

CHART_OF_ACCOUNTS = [
    {
        "account_number": "1000",
        "name": "Bank and Cash",
        "type": "ASSET",
        "description": "Cash and bank accounts for inventory receipts, payments, and daily transactions.",
    },
    {
        "account_number": "1020",
        "name": "Bank Accounts",
        "type": "ASSET",
        "description": "Separate deposit and current bank accounts for payroll disbursements.",
    },
    {
        "account_number": "1100",
        "name": "Cash and Cash Equivalents",
        "type": "ASSET",
        "description": "Petty cash, cash on hand, and short-term highly liquid investments.",
    },
    {
        "account_number": "1110",
        "name": "Trade Receivables",
        "type": "ASSET",
        "description": "Customer balances for wholesale credit sales.",
    },
    {
        "account_number": "1200",
        "name": "Inventory Asset",
        "type": "ASSET",
        "description": "Stock value held in warehouses, locations, and retail points.",
    },
    {
        "account_number": "1300",
        "name": "Input VAT",
        "type": "ASSET",
        "description": "Recoverable VAT on purchases, expenses, and services.",
    },
    {
        "account_number": "1400",
        "name": "WHT Receivable",
        "type": "ASSET",
        "description": "Withholding tax deducted by customers, recoverable from tax authority.",
    },
    {
        "account_number": "1500",
        "name": "Employee Advances",
        "type": "ASSET",
        "description": "Short-term advances, loans, and reimbursable amounts from employees.",
    },
    {
        "account_number": "2000",
        "name": "Trade Payables",
        "type": "LIABILITY",
        "description": "Vendor balances for wholesale purchasing and inventory procurement.",
    },
    {
        "account_number": "2110",
        "name": "PAYE Tax Payable",
        "type": "LIABILITY",
        "description": "Pay-As-You-Earn income tax deducted from employee salaries, payable to tax authority.",
    },
    {
        "account_number": "2120",
        "name": "Pension Payable",
        "type": "LIABILITY",
        "description": "Employee and employer pension contributions payable to pension fund administrators.",
    },
    {
        "account_number": "2130",
        "name": "Health Contribution Payable",
        "type": "LIABILITY",
        "description": "Health insurance contributions payable to health providers.",
    },
    {
        "account_number": "2140",
        "name": "NSITF Payable",
        "type": "LIABILITY",
        "description": "Nigeria Social Insurance Trust Fund contributions payable.",
    },
    {
        "account_number": "2150",
        "name": "NHF Payable",
        "type": "LIABILITY",
        "description": "National Housing Fund contributions deducted from employees, payable to FMBN.",
    },
    {
        "account_number": "2160",
        "name": "Other Deductions Payable",
        "type": "LIABILITY",
        "description": "Miscellaneous payroll deductions payable to third parties (union dues, levies, etc.).",
    },
    {
        "account_number": "2200",
        "name": "Output VAT",
        "type": "LIABILITY",
        "description": "VAT collected on sales and services, payable to tax authority.",
    },
    {
        "account_number": "2300",
        "name": "WHT Payable",
        "type": "LIABILITY",
        "description": "Withholding tax deducted from supplier payments, payable to tax authority.",
    },
    {
        "account_number": "3000",
        "name": "Opening Balance Equity",
        "type": "EQUITY",
        "description": "Offset account for opening inventory and financial statement balances.",
    },
    {
        "account_number": "4100",
        "name": "Wholesale Sales",
        "type": "REVENUE",
        "description": "Sales revenue from wholesale warehouse and distribution operations.",
    },
    {
        "account_number": "4110",
        "name": "Interest Income",
        "type": "REVENUE",
        "description": "Interest earned on bank deposits, loans, and employee advances.",
    },
    {
        "account_number": "4200",
        "name": "Inventory Adjustment Gain",
        "type": "REVENUE",
        "description": "Positive stock count adjustments, revaluation gains, and write-ups.",
    },
    {
        "account_number": "5100",
        "name": "Cost of Goods Sold",
        "type": "EXPENSE",
        "description": "Inventory cost recognized when goods are sold or consumed.",
    },
    {
        "account_number": "6010",
        "name": "Salaries and Wages Expense",
        "type": "EXPENSE",
        "description": "Gross salaries, wages, overtime, and bonuses for all employees.",
    },
    {
        "account_number": "6015",
        "name": "Allowances Expense",
        "type": "EXPENSE",
        "description": "Allowances paid to employees (housing, transport, meal, etc.).",
    },
    {
        "account_number": "6020",
        "name": "Pension Expense (Employer)",
        "type": "EXPENSE",
        "description": "Employer's mandatory pension contribution expense.",
    },
    {
        "account_number": "6030",
        "name": "Health Contribution Expense (Employer)",
        "type": "EXPENSE",
        "description": "Employer's health insurance contribution expense.",
    },
    {
        "account_number": "6040",
        "name": "NSITF Expense",
        "type": "EXPENSE",
        "description": "Employer's NSITF contribution expense.",
    },
    {
        "account_number": "6200",
        "name": "Inventory Shrinkage",
        "type": "EXPENSE",
        "description": "Stock losses, expiries, breakages, theft, and negative count adjustments.",
    },
]


class Command(BaseCommand):
    help = (
        "Creates a complete chart of accounts for the payroll and inventory system. "
        "Creates 28 accounts across all five account types with detailed descriptions. "
        "Safe to run multiple times — existing accounts are skipped by default. "
        "Use --update-existing to refresh names, types, and descriptions on accounts "
        "that already exist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-id",
            type=int,
            help="Company ID that owns the chart of accounts.",
        )
        parser.add_argument(
            "--company-name",
            default="Default Company",
            help="Company name to create or use when --company-id is not supplied.",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update name, type, and description on accounts that already exist.",
        )

    def handle(self, *args, **options):
        if options.get("company_id"):
            company = Company.objects.get(pk=options["company_id"])
        else:
            company, _ = Company.objects.get_or_create(name=options["company_name"])

        update_existing = options["update_existing"]

        created = 0
        updated = 0
        skipped = 0

        for acc in CHART_OF_ACCOUNTS:
            existing = Account.objects.filter(
                company=company, account_number=acc["account_number"]
            ).first()

            if not existing:
                Account.objects.create(
                    company=company,
                    name=acc["name"],
                    account_number=acc["account_number"],
                    type=acc["type"],
                    description=acc.get("description", ""),
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created:  {acc['account_number']} - {acc['name']}"
                    )
                )
                created += 1

            elif update_existing:
                fields_updated = []

                if (
                    existing.name != acc["name"]
                    and not Account.objects.filter(
                        company=company, name=acc["name"]
                    )
                    .exclude(pk=existing.pk)
                    .exists()
                ):
                    existing.name = acc["name"]
                    fields_updated.append("name")

                if existing.type != acc["type"]:
                    existing.type = acc["type"]
                    fields_updated.append("type")

                if existing.description != acc.get("description", ""):
                    existing.description = acc.get("description", "")
                    fields_updated.append("description")

                if fields_updated:
                    existing.save(update_fields=fields_updated + ["updated_at"])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Updated:  {acc['account_number']} - {acc['name']}"
                        )
                    )
                    updated += 1
                else:
                    self.stdout.write(
                        f"Unchanged: {acc['account_number']} - {acc['name']}"
                    )
                    skipped += 1

            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nChart of accounts complete for '{company.name}': "
                f"created={created}, updated={updated}, skipped={skipped}"
            )
        )
